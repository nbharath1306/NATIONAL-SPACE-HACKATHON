/**
 * ORBITAL INSIGHT — Premium Dashboard Engine
 * =============================================
 * Canvas-based rendering at 60 FPS for 50+ satellites and 10K+ debris.
 */

'use strict';

// ─── Configuration ───────────────────────────────────────────────
const API_BASE = window.location.port === '8000' ? '' : 'http://127.0.0.1:8000';
const POLL_MS = 2000;

// ─── Global State ────────────────────────────────────────────────
const S = {
  satellites: [],
  debrisCloud: [],
  simTimeSec: 0,
  epoch: new Date('2026-03-12T08:00:00Z'),
  selectedSat: null,
  trails: {},
  maneuvers: [],
  dvHistory: [],
  connected: false,
  showTrails: true,
  showTerminator: true,
  showDebris: true,
  totalCollisions: 0,
};

// ─── DOM ─────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const els = {
  simClock: $('simClock'), epochClock: $('epochClock'),
  satCount: $('statSatCount'), debCount: $('statDebrisCount'), cdmCount: $('statCDMCount'),
  connBadge: $('connBadge'), connLabel: $('connLabel'),
  alert: $('alertBanner'), alertText: $('alertText'),
  selector: $('satSelector'), fuelAvg: $('fleetFuelAvg'), tooltip: $('mapTooltip'),
  fuelBadge: $('fuelBadge'), dvBadge: $('dvBadge'),
};

// ─── Canvas Setup ────────────────────────────────────────────────
const CID = ['groundTrack', 'bullseye', 'fuel', 'gantt', 'dv'];
const canvas = {}, ctx = {};
for (const id of CID) {
  canvas[id] = $(id + 'Canvas');
  ctx[id] = canvas[id].getContext('2d');
}

function resize() {
  for (const id of CID) {
    const c = canvas[id];
    const r = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.floor(r.width);
    const h = Math.floor(r.height);
    if (c.width !== w * dpr || c.height !== h * dpr) {
      c.width = w * dpr;
      c.height = h * dpr;
      c.style.width = w + 'px';
      c.style.height = h + 'px';
      ctx[id].setTransform(dpr, 0, 0, dpr, 0, 0);
    }
  }
}
window.addEventListener('resize', resize);
setTimeout(resize, 100);

// ─── Helpers ─────────────────────────────────────────────────────
function ll2xy(lat, lon, W, H) {
  return [((lon + 180) / 360) * W, ((90 - lat) / 180) * H];
}

function statusColor(s) {
  return { NOMINAL: '#39ff7a', EVADING: '#ffb830', RECOVERING: '#3b8bff', EOL: '#a855f7', DEAD: '#ff3b52' }[s] || '#39ff7a';
}

function formatTime(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = Math.floor(sec % 60);
  return `T+${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

// ═════════════════════════════════════════════════════════════════
// MODULE 1: GROUND TRACK MAP
// ═════════════════════════════════════════════════════════════════

const GS = [
  { name: 'ISTRAC', lat: 13.033, lon: 77.517 },
  { name: 'Svalbard', lat: 78.230, lon: 15.408 },
  { name: 'Goldstone', lat: 35.427, lon: -116.89 },
  { name: 'P.Arenas', lat: -53.15, lon: -70.917 },
  { name: 'IIT Delhi', lat: 28.545, lon: 77.193 },
  { name: 'McMurdo', lat: -77.846, lon: 166.668 },
];

function drawMap() {
  const c = canvas.groundTrack, g = ctx.groundTrack;
  const r = c.getBoundingClientRect();
  const W = r.width, H = r.height;

  // Background gradient
  const bg = g.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#040a18');
  bg.addColorStop(0.5, '#061020');
  bg.addColorStop(1, '#040a18');
  g.fillStyle = bg;
  g.fillRect(0, 0, W, H);

  // Grid
  g.lineWidth = 0.5;
  for (let lon = -180; lon <= 180; lon += 30) {
    const x = ll2xy(0, lon, W, H)[0];
    g.strokeStyle = lon === 0 ? 'rgba(0,229,255,0.12)' : 'rgba(20,40,70,0.5)';
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
    if (lon % 60 === 0) {
      g.fillStyle = 'rgba(60,100,140,0.35)';
      g.font = '8px "Share Tech Mono"';
      g.fillText(`${lon}°`, x + 2, H - 4);
    }
  }
  for (let lat = -90; lat <= 90; lat += 30) {
    const y = ll2xy(lat, 0, W, H)[1];
    g.strokeStyle = lat === 0 ? 'rgba(0,180,200,0.2)' : 'rgba(20,40,70,0.5)';
    g.lineWidth = lat === 0 ? 1 : 0.5;
    g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    if (lat !== 0 && lat % 30 === 0) {
      g.fillStyle = 'rgba(60,100,140,0.35)';
      g.font = '8px "Share Tech Mono"';
      g.fillText(`${lat}°`, 3, y - 3);
    }
  }

  // Terminator
  if (S.showTerminator) {
    const hourAngle = (S.simTimeSec / 3600) * 15;
    const sunLon = ((-180 + hourAngle) % 360 + 360) % 360 - 180;
    const nightLon = ((sunLon + 180) % 360 + 360) % 360 - 180;
    const [nx] = ll2xy(0, nightLon, W, H);
    const hw = W / 4;

    g.save();
    g.globalAlpha = 0.3;
    g.fillStyle = '#000510';
    // Night band
    const left = nx - hw, right = nx + hw;
    if (left < 0) {
      g.fillRect(0, 0, right, H);
      g.fillRect(W + left, 0, -left, H);
    } else if (right > W) {
      g.fillRect(left, 0, W - left, H);
      g.fillRect(0, 0, right - W, H);
    } else {
      g.fillRect(left, 0, hw * 2, H);
    }
    g.restore();

    // Terminator lines
    g.strokeStyle = 'rgba(255,200,50,0.15)';
    g.lineWidth = 1;
    g.setLineDash([6, 4]);
    const tl = ll2xy(0, sunLon - 90, W, H)[0];
    const tr = ll2xy(0, sunLon + 90, W, H)[0];
    g.beginPath(); g.moveTo(tl, 0); g.lineTo(tl, H); g.stroke();
    g.beginPath(); g.moveTo(tr, 0); g.lineTo(tr, H); g.stroke();
    g.setLineDash([]);
  }

  // Debris
  if (S.showDebris && S.debrisCloud.length > 0) {
    g.fillStyle = 'rgba(255,80,80,0.2)';
    for (const d of S.debrisCloud) {
      const [x, y] = ll2xy(d[1], d[2], W, H);
      g.fillRect(x - 0.5, y - 0.5, 1.5, 1.5);
    }
  }

  // Ground stations
  for (const gs of GS) {
    const [x, y] = ll2xy(gs.lat, gs.lon, W, H);
    // Range circle
    g.beginPath(); g.arc(x, y, 20, 0, Math.PI * 2);
    g.strokeStyle = 'rgba(0,229,255,0.08)'; g.lineWidth = 1; g.stroke();
    g.fillStyle = 'rgba(0,229,255,0.04)'; g.fill();
    // Station dot
    g.beginPath(); g.arc(x, y, 3, 0, Math.PI * 2);
    g.fillStyle = 'rgba(0,229,255,0.7)'; g.fill();
    // Diamond shape
    g.strokeStyle = 'rgba(0,229,255,0.5)'; g.lineWidth = 1;
    g.beginPath();
    g.moveTo(x, y - 5); g.lineTo(x + 4, y); g.lineTo(x, y + 5); g.lineTo(x - 4, y); g.closePath();
    g.stroke();
    // Label
    g.fillStyle = 'rgba(0,229,255,0.5)';
    g.font = '7px "Share Tech Mono"';
    g.fillText(gs.name, x + 7, y + 3);
  }

  // Trails
  if (S.showTrails) {
    for (const [id, trail] of Object.entries(S.trails)) {
      if (trail.length < 2) continue;
      const sat = S.satellites.find(s => s.id === id);
      const col = statusColor(sat?.status);
      for (let i = 1; i < trail.length; i++) {
        const a = (i / trail.length) * 0.5;
        const [x0, y0] = ll2xy(trail[i - 1].lat, trail[i - 1].lon, W, H);
        const [x1, y1] = ll2xy(trail[i].lat, trail[i].lon, W, H);
        if (Math.abs(x1 - x0) > W * 0.3) continue;
        g.strokeStyle = col.replace(')', `,${a})`).replace('rgb', 'rgba');
        g.lineWidth = 1;
        g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
      }
    }
  }

  // Satellites
  for (const sat of S.satellites) {
    const [x, y] = ll2xy(sat.lat, sat.lon, W, H);
    const col = statusColor(sat.status);
    const sel = sat.id === S.selectedSat;

    // Glow
    if (sel) {
      g.beginPath(); g.arc(x, y, 14, 0, Math.PI * 2);
      g.strokeStyle = 'rgba(0,229,255,0.4)'; g.lineWidth = 1.5; g.stroke();
      g.beginPath(); g.arc(x, y, 18, 0, Math.PI * 2);
      g.strokeStyle = 'rgba(0,229,255,0.15)'; g.lineWidth = 1; g.stroke();
    }

    // Body
    g.save(); g.translate(x, y);
    // Solar panels
    g.fillStyle = 'rgba(40,80,160,0.7)';
    g.fillRect(-8, -2, 5, 4); g.fillRect(3, -2, 5, 4);
    // Panel lines
    g.strokeStyle = 'rgba(60,120,200,0.4)'; g.lineWidth = 0.5;
    g.strokeRect(-8, -2, 5, 4); g.strokeRect(3, -2, 5, 4);
    // Strut
    g.fillStyle = 'rgba(160,180,200,0.6)';
    g.fillRect(-3, -0.5, 6, 1);
    // Core
    g.beginPath(); g.arc(0, 0, sel ? 3.5 : 2.5, 0, Math.PI * 2);
    g.fillStyle = col; g.shadowBlur = sel ? 16 : 8; g.shadowColor = col;
    g.fill(); g.shadowBlur = 0;
    g.restore();

    // Label
    if (sel) {
      g.fillStyle = 'rgba(0,229,255,0.9)';
      g.font = 'bold 10px "Share Tech Mono"';
      g.fillText(sat.id, x + 12, y - 6);
      g.fillStyle = 'rgba(200,220,240,0.6)';
      g.font = '8px "Share Tech Mono"';
      g.fillText(`${sat.lat.toFixed(1)}°, ${sat.lon.toFixed(1)}°`, x + 12, y + 5);
    }
  }

  // Map label
  g.fillStyle = 'rgba(0,229,255,0.12)';
  g.font = 'bold 10px "Orbitron"';
  g.fillText('ECI J2000', W - 75, H - 8);
}

// ═════════════════════════════════════════════════════════════════
// MODULE 2: BULLSEYE PLOT
// ═════════════════════════════════════════════════════════════════

function drawBullseye() {
  const c = canvas.bullseye, g = ctx.bullseye;
  const r = c.getBoundingClientRect();
  const W = r.width, H = r.height;
  const cx = W / 2, cy = H / 2;
  const maxR = Math.min(W, H) / 2 - 20;

  g.fillStyle = '#040a14';
  g.fillRect(0, 0, W, H);

  // Rings
  const rings = [
    { f: 0.25, label: '6h', col: 'rgba(255,59,82,0.06)' },
    { f: 0.50, label: '12h', col: 'rgba(255,184,48,0.04)' },
    { f: 0.75, label: '18h', col: 'rgba(59,139,255,0.03)' },
    { f: 1.00, label: '24h', col: 'rgba(20,40,70,0.15)' },
  ];
  for (const ring of rings) {
    const rr = maxR * ring.f;
    // Fill zone
    g.beginPath(); g.arc(cx, cy, rr, 0, Math.PI * 2);
    g.fillStyle = ring.col; g.fill();
    // Ring line
    g.strokeStyle = 'rgba(30,60,100,0.5)'; g.lineWidth = 0.5; g.stroke();
    // Label
    g.fillStyle = 'rgba(80,120,160,0.5)';
    g.font = '8px "Share Tech Mono"';
    g.fillText(ring.label, cx + rr - 14, cy - 4);
  }

  // Crosshairs
  g.strokeStyle = 'rgba(30,60,100,0.4)'; g.lineWidth = 0.5;
  g.setLineDash([3, 3]);
  g.beginPath(); g.moveTo(cx - maxR, cy); g.lineTo(cx + maxR, cy); g.stroke();
  g.beginPath(); g.moveTo(cx, cy - maxR); g.lineTo(cx, cy + maxR); g.stroke();
  // Diagonal crosses
  g.beginPath(); g.moveTo(cx - maxR * 0.7, cy - maxR * 0.7); g.lineTo(cx + maxR * 0.7, cy + maxR * 0.7); g.stroke();
  g.beginPath(); g.moveTo(cx + maxR * 0.7, cy - maxR * 0.7); g.lineTo(cx - maxR * 0.7, cy + maxR * 0.7); g.stroke();
  g.setLineDash([]);

  // Direction labels
  g.fillStyle = 'rgba(80,120,160,0.5)';
  g.font = '8px "Share Tech Mono"';
  g.textAlign = 'center';
  g.fillText('PROGRADE', cx, cy - maxR - 6);
  g.fillText('RETROGRADE', cx, cy + maxR + 12);
  g.textAlign = 'right'; g.fillText('+R', cx + maxR + 2, cy - 4);
  g.textAlign = 'left'; g.fillText('-R', cx - maxR - 12, cy - 4);
  g.textAlign = 'left';

  const sat = S.satellites.find(s => s.id === S.selectedSat);
  if (!sat) {
    g.fillStyle = 'rgba(80,120,160,0.3)';
    g.font = '11px "Share Tech Mono"';
    g.textAlign = 'center';
    g.fillText('SELECT SATELLITE', cx, cy - 6);
    g.fillText('FOR CONJUNCTIONS', cx, cy + 10);
    g.textAlign = 'left';
    g.beginPath(); g.arc(cx, cy, 4, 0, Math.PI * 2);
    g.fillStyle = 'rgba(0,229,255,0.2)'; g.fill();
    return;
  }

  // Plot debris
  const conjs = getConjunctions(sat);
  let critCount = 0;
  for (const c of conjs) {
    const rf = Math.min(c.tca / 24, 1);
    const pr = rf * maxR;
    const a = c.bearing - Math.PI / 2;
    const px = cx + Math.cos(a) * pr;
    const py = cy + Math.sin(a) * pr;

    let col, sz;
    if (c.miss < 0.1) { col = '#ff3b52'; sz = 5; critCount++; }
    else if (c.miss < 1) { col = '#ff7832'; sz = 4; }
    else if (c.miss < 5) { col = '#ffb830'; sz = 3; }
    else { col = 'rgba(57,255,122,0.5)'; sz = 2; }

    g.beginPath(); g.arc(px, py, sz, 0, Math.PI * 2);
    g.fillStyle = col;
    if (c.miss < 1) { g.shadowBlur = 10; g.shadowColor = col; }
    g.fill(); g.shadowBlur = 0;

    if (c.miss < 1) {
      g.fillStyle = col;
      g.font = '7px "Share Tech Mono"';
      g.fillText(c.id.slice(-5), px + 6, py - 2);
    }
  }

  // Center satellite
  g.beginPath(); g.arc(cx, cy, 6, 0, Math.PI * 2);
  g.fillStyle = '#00e5ff'; g.shadowBlur = 18; g.shadowColor = '#00e5ff';
  g.fill(); g.shadowBlur = 0;
  // Inner ring
  g.beginPath(); g.arc(cx, cy, 9, 0, Math.PI * 2);
  g.strokeStyle = 'rgba(0,229,255,0.3)'; g.lineWidth = 1; g.stroke();

  g.fillStyle = 'rgba(0,229,255,0.8)';
  g.font = '9px "Share Tech Mono"';
  g.textAlign = 'center';
  g.fillText(sat.id, cx, cy + 22);
  if (critCount > 0) {
    g.fillStyle = '#ff3b52';
    g.fillText(`${critCount} CRITICAL`, cx, H - 8);
  }
  g.textAlign = 'left';
}

function getConjunctions(sat) {
  const res = [];
  const sample = S.debrisCloud.slice(0, 300);
  for (const d of sample) {
    const dlat = d[1] - sat.lat, dlon = d[2] - sat.lon;
    const ang = Math.sqrt(dlat * dlat + dlon * dlon);
    if (ang > 15) continue;
    const miss = ang * 111 * 0.01 + Math.abs(d[3] - 550) * 0.1;
    res.push({ id: d[0], miss, bearing: Math.atan2(dlon, dlat), tca: ang * 111 / 3600 + Math.random() * 4 });
  }
  return res.sort((a, b) => b.miss - a.miss);
}

// ═════════════════════════════════════════════════════════════════
// MODULE 3: FUEL HEATMAP
// ═════════════════════════════════════════════════════════════════

function drawFuel() {
  const c = canvas.fuel, g = ctx.fuel;
  const r = c.getBoundingClientRect();
  const W = r.width, H = r.height;

  g.fillStyle = '#060c18';
  g.fillRect(0, 0, W, H);

  const n = S.satellites.length;
  if (!n) {
    g.fillStyle = 'rgba(80,120,160,0.3)';
    g.font = '11px "Share Tech Mono"';
    g.textAlign = 'center';
    g.fillText('AWAITING FLEET DATA', W / 2, H / 2);
    g.textAlign = 'left';
    return;
  }

  const cols = Math.ceil(Math.sqrt(n * (W / H)));
  const rows = Math.ceil(n / cols);
  const cw = W / cols, ch = H / rows;
  const pad = 2;
  let totalF = 0;

  for (let i = 0; i < n; i++) {
    const sat = S.satellites[i];
    const col = i % cols, row = Math.floor(i / cols);
    const x = col * cw + pad, y = row * ch + pad;
    const w = cw - pad * 2, h = ch - pad * 2;
    const f = Math.max(0, Math.min(1, sat.fuel_kg / 50));
    totalF += f;

    // Cell bg
    g.fillStyle = 'rgba(10,18,30,0.8)';
    g.fillRect(x, y, w, h);

    // Fuel bar
    const fc = f > 0.5 ? `rgba(57,255,122,${0.5 + f * 0.4})` :
               f > 0.2 ? `rgba(255,184,48,${0.6 + f * 0.3})` :
                          `rgba(255,59,82,0.8)`;
    g.fillStyle = fc;
    g.fillRect(x, y + h * (1 - f), w, h * f);

    // Status strip
    g.fillStyle = statusColor(sat.status);
    g.fillRect(x, y, w, 2);

    // Border
    g.strokeStyle = sat.id === S.selectedSat ? 'rgba(0,229,255,0.7)' : 'rgba(20,40,60,0.5)';
    g.lineWidth = sat.id === S.selectedSat ? 1.5 : 0.5;
    g.strokeRect(x, y, w, h);

    // Labels
    if (ch > 28) {
      g.fillStyle = f > 0.15 ? 'rgba(255,255,255,0.85)' : '#ff3b52';
      g.font = `bold ${Math.min(10, ch * 0.25)}px "Share Tech Mono"`;
      g.textAlign = 'center';
      g.fillText(`${Math.round(f * 100)}%`, x + w / 2, y + h / 2 + 3);
      g.textAlign = 'left';
    }
    if (ch > 40) {
      g.fillStyle = 'rgba(200,220,240,0.5)';
      g.font = `${Math.min(7, ch * 0.16)}px "Share Tech Mono"`;
      g.textAlign = 'center';
      g.fillText(sat.id.replace('SAT-', ''), x + w / 2, y + h - 3);
      g.textAlign = 'left';
    }
  }

  const avg = (totalF / n) * 100;
  els.fuelAvg.textContent = `FLEET AVG: ${avg.toFixed(1)}%`;
  els.fuelAvg.style.color = avg > 50 ? '#39ff7a' : avg > 20 ? '#ffb830' : '#ff3b52';
  els.fuelBadge.textContent = `${n} SATS`;
}

// ═════════════════════════════════════════════════════════════════
// MODULE 4: GANTT TIMELINE
// ═════════════════════════════════════════════════════════════════

function drawGantt() {
  const c = canvas.gantt, g = ctx.gantt;
  const r = c.getBoundingClientRect();
  const W = r.width, H = r.height;

  g.fillStyle = '#060c18';
  g.fillRect(0, 0, W, H);

  const sats = S.satellites.slice(0, 20);
  if (!sats.length) {
    g.fillStyle = 'rgba(80,120,160,0.3)';
    g.font = '11px "Share Tech Mono"';
    g.textAlign = 'center';
    g.fillText('AWAITING MANEUVER DATA', W / 2, H / 2);
    g.textAlign = 'left';
    return;
  }

  const rowH = Math.max(14, (H - 16) / Math.max(sats.length, 1));
  const labelW = 70;
  const tlW = W - labelW;
  const winSec = 7200;
  const tStart = S.simTimeSec - winSec * 0.3;
  const tEnd = tStart + winSec;

  const t2x = t => labelW + ((t - tStart) / (tEnd - tStart)) * tlW;

  // Time grid
  g.strokeStyle = 'rgba(20,40,60,0.4)';
  g.lineWidth = 0.5;
  for (let t = Math.ceil(tStart / 600) * 600; t <= tEnd; t += 600) {
    const x = t2x(t);
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
    g.fillStyle = 'rgba(60,100,140,0.4)';
    g.font = '7px "Share Tech Mono"';
    g.fillText(`T+${Math.round(t / 60)}m`, x + 2, H - 2);
  }

  // NOW line
  const nx = t2x(S.simTimeSec);
  g.strokeStyle = 'rgba(0,229,255,0.6)';
  g.lineWidth = 1.5;
  g.setLineDash([4, 3]);
  g.beginPath(); g.moveTo(nx, 0); g.lineTo(nx, H - 12); g.stroke();
  g.setLineDash([]);
  g.fillStyle = 'rgba(0,229,255,0.7)';
  g.font = '7px "Share Tech Mono"';
  g.fillText('NOW', nx + 2, 10);

  // Rows
  const burnCol = {
    EVASION:  { f: 'rgba(255,184,48,0.7)',  s: 'rgba(255,184,48,1)' },
    RECOVERY: { f: 'rgba(59,139,255,0.7)',   s: 'rgba(59,139,255,1)' },
    EOL:      { f: 'rgba(168,85,247,0.7)',   s: 'rgba(168,85,247,1)' },
    MANUAL:   { f: 'rgba(57,255,122,0.6)',   s: 'rgba(57,255,122,1)' },
  };

  for (let i = 0; i < sats.length; i++) {
    const sat = sats[i];
    const ry = i * rowH;

    // Row bg
    g.fillStyle = i % 2 === 0 ? 'rgba(8,14,26,0.6)' : 'rgba(12,20,34,0.4)';
    g.fillRect(labelW, ry, tlW, rowH - 1);

    // Label
    g.fillStyle = sat.id === S.selectedSat ? 'rgba(0,229,255,0.9)' : 'rgba(100,150,200,0.6)';
    g.font = `${Math.min(8, rowH * 0.55)}px "Share Tech Mono"`;
    g.textAlign = 'right';
    g.fillText(sat.id.replace('SAT-', ''), labelW - 4, ry + rowH * 0.65);
    g.textAlign = 'left';

    // Burns
    const burns = S.maneuvers.filter(b => b.satId === sat.id);
    for (const burn of burns) {
      const bx = t2x(burn.startTime);
      const bw = Math.max(3, t2x(burn.endTime) - bx);
      if (bx > W || bx + bw < labelW) continue;
      const bc = burnCol[burn.type] || burnCol.MANUAL;
      g.fillStyle = bc.f;
      g.fillRect(bx, ry + 1, bw, rowH - 3);
      g.strokeStyle = bc.s; g.lineWidth = 0.5;
      g.strokeRect(bx, ry + 1, bw, rowH - 3);

      // Cooldown
      const cdx = bx + bw;
      const cdw = t2x(burn.endTime + 600) - cdx;
      if (cdw > 0) {
        g.fillStyle = 'rgba(20,35,55,0.4)';
        g.fillRect(cdx, ry + 1, Math.min(cdw, W - cdx), rowH - 3);
      }
    }
  }

  // Divider
  g.strokeStyle = 'rgba(20,40,60,0.6)'; g.lineWidth = 1;
  g.beginPath(); g.moveTo(labelW, 0); g.lineTo(labelW, H); g.stroke();
}

// ═════════════════════════════════════════════════════════════════
// MODULE 5: DELTA-V GRAPH
// ═════════════════════════════════════════════════════════════════

function drawDV() {
  const c = canvas.dv, g = ctx.dv;
  const r = c.getBoundingClientRect();
  const W = r.width, H = r.height;

  g.fillStyle = '#050b14';
  g.fillRect(0, 0, W, H);

  const M = { t: 8, r: 12, b: 20, l: 40 };
  const pw = W - M.l - M.r, ph = H - M.t - M.b;

  if (S.dvHistory.length < 2) {
    g.fillStyle = 'rgba(80,120,160,0.3)';
    g.font = '10px "Share Tech Mono"';
    g.textAlign = 'center';
    g.fillText('COLLECTING TELEMETRY DATA...', W / 2, H / 2);
    g.textAlign = 'left';
    return;
  }

  // Axes
  g.strokeStyle = 'rgba(30,60,100,0.6)'; g.lineWidth = 1;
  g.beginPath();
  g.moveTo(M.l, M.t); g.lineTo(M.l, M.t + ph); g.lineTo(M.l + pw, M.t + ph);
  g.stroke();

  g.fillStyle = 'rgba(60,100,140,0.5)';
  g.font = '8px "Share Tech Mono"';
  g.textAlign = 'center';
  g.fillText('SIMULATION TIME', M.l + pw / 2, H - 2);
  g.textAlign = 'left';

  const maxF = Math.max(...S.dvHistory.map(d => d.fuel), 1);
  const n = S.dvHistory.length;
  const pt = (i, v, mv) => [M.l + (i / (n - 1)) * pw, M.t + ph - (v / mv) * ph];

  // Fuel line (amber)
  g.strokeStyle = 'rgba(255,184,48,0.8)'; g.lineWidth = 1.5;
  g.beginPath();
  S.dvHistory.forEach((d, i) => { const [x, y] = pt(i, d.fuel, maxF); i === 0 ? g.moveTo(x, y) : g.lineTo(x, y); });
  g.stroke();

  // Area fill
  g.save();
  const last = pt(n - 1, S.dvHistory[n - 1].fuel, maxF);
  const first = pt(0, S.dvHistory[0].fuel, maxF);
  g.lineTo(last[0], M.t + ph); g.lineTo(first[0], M.t + ph); g.closePath();
  const grad = g.createLinearGradient(0, M.t, 0, M.t + ph);
  grad.addColorStop(0, 'rgba(255,184,48,0.12)');
  grad.addColorStop(1, 'rgba(255,184,48,0)');
  g.fillStyle = grad; g.fill();
  g.restore();

  // Collisions avoided (green)
  const maxA = Math.max(...S.dvHistory.map(d => d.avoided), 1);
  if (maxA > 0) {
    g.strokeStyle = 'rgba(57,255,122,0.7)'; g.lineWidth = 1.5;
    g.beginPath();
    S.dvHistory.forEach((d, i) => { const [x, y] = pt(i, d.avoided, maxA); i === 0 ? g.moveTo(x, y) : g.lineTo(x, y); });
    g.stroke();
  }

  // Legend
  g.fillStyle = 'rgba(255,184,48,0.8)'; g.fillRect(M.l + 5, M.t + 2, 14, 2);
  g.fillStyle = 'rgba(255,184,48,0.7)'; g.font = '7px "Share Tech Mono"';
  g.fillText('FUEL USED', M.l + 22, M.t + 6);
  g.fillStyle = 'rgba(57,255,122,0.8)'; g.fillRect(M.l + 85, M.t + 2, 14, 2);
  g.fillStyle = 'rgba(57,255,122,0.7)';
  g.fillText('AVOIDED', M.l + 102, M.t + 6);
}

// ═════════════════════════════════════════════════════════════════
// API POLLING
// ═════════════════════════════════════════════════════════════════

async function poll() {
  try {
    const resp = await fetch(`${API_BASE}/api/visualization/snapshot`);
    if (!resp.ok) throw new Error();
    const data = await resp.json();

    S.satellites = data.satellites || [];
    S.debrisCloud = data.debris_cloud || [];
    S.simTimeSec = data.sim_time_s ?? S.simTimeSec + POLL_MS / 1000;

    // Update trails
    for (const sat of S.satellites) {
      if (!S.trails[sat.id]) S.trails[sat.id] = [];
      S.trails[sat.id].push({ lat: sat.lat, lon: sat.lon });
      if (S.trails[sat.id].length > 90) S.trails[sat.id].shift();
    }

    updateUI(true);
    updateSelector();
  } catch {
    updateUI(false);
  }

  try {
    const hr = await fetch(`${API_BASE}/health`);
    if (hr.ok) {
      const hd = await hr.json();
      els.cdmCount.textContent = hd.active_cdms || 0;

      // DV history
      const totalFuelLeft = S.satellites.reduce((s, sat) => s + sat.fuel_kg, 0);
      const totalUsed = S.satellites.length * 50 - totalFuelLeft;
      S.dvHistory.push({ fuel: Math.max(0, totalUsed), avoided: hd.total_collisions || 0, t: S.simTimeSec });
      if (S.dvHistory.length > 80) S.dvHistory.shift();
      els.dvBadge.textContent = `${totalUsed.toFixed(1)} kg`;
    }
  } catch {}

  // Seed maneuvers for gantt
  if (S.maneuvers.length === 0 && S.satellites.length > 0) seedManeuvers();
}

function seedManeuvers() {
  const types = ['EVASION', 'RECOVERY', 'MANUAL'];
  for (let i = 0; i < Math.min(S.satellites.length, 15); i++) {
    const sat = S.satellites[i];
    const off = (Math.random() - 0.3) * 3600;
    S.maneuvers.push({
      satId: sat.id, burnId: `B${i}`,
      startTime: S.simTimeSec + off,
      endTime: S.simTimeSec + off + 60 + Math.random() * 120,
      type: types[i % 3],
    });
  }
}

function updateUI(online) {
  S.connected = online;
  els.connBadge.className = `conn-badge ${online ? 'online' : 'offline'}`;
  els.connLabel.textContent = online ? 'LIVE' : 'OFFLINE';
  els.satCount.textContent = S.satellites.length;
  els.debCount.textContent = S.debrisCloud.length;

  els.simClock.textContent = formatTime(S.simTimeSec);
  const d = new Date(S.epoch.getTime() + S.simTimeSec * 1000);
  els.epochClock.textContent = d.toISOString().replace('T', ' ').slice(0, 19);

  // Fuel alert
  const crit = S.satellites.filter(s => s.fuel_kg < 2.5);
  if (crit.length > 0) showAlert(`FUEL CRITICAL: ${crit.map(s => s.id).join(', ')}`);
}

function updateSelector() {
  const cur = els.selector.value;
  els.selector.innerHTML = '<option value="">-- SELECT SATELLITE --</option>';
  for (const sat of S.satellites) {
    const o = document.createElement('option');
    o.value = sat.id;
    o.textContent = sat.id + (sat.status !== 'NOMINAL' ? ` [${sat.status}]` : '');
    els.selector.appendChild(o);
  }
  if (cur) els.selector.value = cur;
  if (!S.selectedSat && S.satellites.length > 0) {
    S.selectedSat = S.satellites[0].id;
    els.selector.value = S.selectedSat;
  }
}

function showAlert(msg) {
  els.alertText.textContent = msg;
  els.alert.classList.add('visible');
  setTimeout(() => els.alert.classList.remove('visible'), 5000);
}

// ─── Demo Data (offline mode) ────────────────────────────────────

function loadDemo() {
  const statuses = ['NOMINAL', 'NOMINAL', 'NOMINAL', 'EVADING', 'RECOVERING'];
  for (let i = 0; i < 50; i++) {
    const p = Math.floor(i / 10), sl = i % 10;
    S.satellites.push({
      id: `SAT-P${p + 1}-${String(sl + 1).padStart(2, '0')}`,
      lat: Math.sin(p * 1.256 + sl * 0.628) * 53,
      lon: ((p * 72 + sl * 36) % 360) - 180,
      fuel_kg: 50 - Math.random() * 15,
      status: statuses[Math.floor(Math.random() * statuses.length)],
    });
  }
  for (let i = 0; i < 2000; i++) {
    S.debrisCloud.push([`DEB-${String(i).padStart(5, '0')}`, (Math.random() - 0.5) * 160, (Math.random() - 0.5) * 360, 400 + Math.random() * 400]);
  }
  for (let i = 0; i < 30; i++) {
    S.dvHistory.push({ fuel: i * 0.08 + Math.random() * 0.2, avoided: Math.floor(i * 0.3), t: i * 60 });
  }
  updateSelector();
  seedManeuvers();
  updateUI(false);
}

// ─── Interactions ────────────────────────────────────────────────

els.selector.addEventListener('change', e => { S.selectedSat = e.target.value || null; });

$('btnToggleTrails').addEventListener('click', function () {
  S.showTrails = !S.showTrails;
  this.classList.toggle('active', S.showTrails);
});
$('btnToggleTerminator').addEventListener('click', function () {
  S.showTerminator = !S.showTerminator;
  this.classList.toggle('active', S.showTerminator);
});
$('btnToggleDebrisMap').addEventListener('click', function () {
  S.showDebris = !S.showDebris;
  this.classList.toggle('active', S.showDebris);
});

// Map tooltip & click
canvas.groundTrack.addEventListener('mousemove', e => {
  const rect = canvas.groundTrack.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const W = rect.width, H = rect.height;

  let hit = null;
  for (const sat of S.satellites) {
    const [sx, sy] = ll2xy(sat.lat, sat.lon, W, H);
    if (Math.hypot(mx - sx, my - sy) < 10) { hit = sat; break; }
  }

  if (hit) {
    els.tooltip.style.display = 'block';
    els.tooltip.style.left = (e.clientX + 14) + 'px';
    els.tooltip.style.top = (e.clientY - 10) + 'px';
    els.tooltip.innerHTML =
      `<b style="color:#00e5ff">${hit.id}</b><br>` +
      `LAT ${hit.lat.toFixed(2)}° LON ${hit.lon.toFixed(2)}°<br>` +
      `FUEL ${hit.fuel_kg.toFixed(1)} kg<br>` +
      `<span style="color:${statusColor(hit.status)}">${hit.status}</span>`;
  } else {
    els.tooltip.style.display = 'none';
  }
});

canvas.groundTrack.addEventListener('click', e => {
  const rect = canvas.groundTrack.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const W = rect.width, H = rect.height;
  for (const sat of S.satellites) {
    const [sx, sy] = ll2xy(sat.lat, sat.lon, W, H);
    if (Math.hypot(mx - sx, my - sy) < 12) {
      S.selectedSat = sat.id;
      els.selector.value = sat.id;
      break;
    }
  }
});

// Demo animation (when offline)
setInterval(() => {
  if (!S.connected && S.satellites.length > 0) {
    for (const sat of S.satellites) {
      sat.lon = ((sat.lon + 0.15 + 360) % 360);
      if (sat.lon > 180) sat.lon -= 360;
      sat.lat += (Math.random() - 0.5) * 0.03;
      if (!S.trails[sat.id]) S.trails[sat.id] = [];
      S.trails[sat.id].push({ lat: sat.lat, lon: sat.lon });
      if (S.trails[sat.id].length > 90) S.trails[sat.id].shift();
    }
    S.simTimeSec += 30;
    updateUI(false);
  }
}, 500);

// ═════════════════════════════════════════════════════════════════
// RENDER LOOP (60 FPS)
// ═════════════════════════════════════════════════════════════════

function render() {
  resize();
  drawMap();
  drawBullseye();
  drawFuel();
  drawGantt();
  drawDV();
  requestAnimationFrame(render);
}

// ═════════════════════════════════════════════════════════════════
// INIT
// ═════════════════════════════════════════════════════════════════

async function init() {
  resize();
  const ok = await poll().then(() => S.connected).catch(() => false);
  if (!S.connected) {
    console.warn('API offline — loading demo data');
    loadDemo();
  }
  setInterval(poll, POLL_MS);
  requestAnimationFrame(render);
}

init();
