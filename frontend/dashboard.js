/**
 * ORBITAL INSIGHT — Dashboard Engine
 * ====================================
 * All rendering is done on <canvas> elements for performance.
 * At 50 satellites + 10,000 debris, DOM-based rendering would
 * drop to ~5 FPS. Canvas lets us hit 60 FPS easily.
 *
 * Architecture:
 *  - API polling every 2s for /api/visualization/snapshot
 *  - Each module has its own canvas and draw() function
 *  - State is stored globally in `state` object
 *  - requestAnimationFrame drives rendering at 60 FPS
 */

'use strict';

// ─── Global State ────────────────────────────────────────────────
// Use relative URL when served from backend, fallback to localhost for dev
const API_BASE = window.location.port === '8000' ? '' : 'http://127.0.0.1:8000';
const POLL_INTERVAL_MS = 2000;

const state = {
  satellites: [],         // [{id, lat, lon, fuel_kg, status}]
  debrisCloud: [],        // [[id, lat, lon, alt_km], ...]
  simTimeSec: 0,
  epochDate: new Date('2026-03-12T08:00:00Z'),
  selectedSat: null,
  trailHistory: {},       // {satId: [{lat,lon}, ...]} — last 90min of positions
  maneuverLog: [],        // [{satId, burnId, startTime, endTime, type}]
  dvHistory: [],          // [{fuel_used, collisions_avoided, timestamp}]
  lastSnapshot: null,
  isConnected: false,
  showTrails: true,
  showTerminator: true,
  showDebrisOnMap: true,
  totalCollisionsAvoided: 0,
  totalFuelUsed: 0,
};

// ─── DOM References ───────────────────────────────────────────────
const els = {
  simClock:        document.getElementById('simClock'),
  epochClock:      document.getElementById('epochClock'),
  statSatCount:    document.getElementById('statSatCount'),
  statDebrisCount: document.getElementById('statDebrisCount'),
  statCDMCount:    document.getElementById('statCDMCount'),
  connDot:         document.getElementById('connDot'),
  connLabel:       document.getElementById('connLabel'),
  alertBanner:     document.getElementById('alertBanner'),
  alertText:       document.getElementById('alertText'),
  satSelector:     document.getElementById('satSelector'),
  fleetFuelAvg:    document.getElementById('fleetFuelAvg'),
  mapTooltip:      document.getElementById('mapTooltip'),
};

// ─── Canvas Contexts ──────────────────────────────────────────────
const canvases = {
  groundTrack: document.getElementById('groundTrackCanvas'),
  bullseye:    document.getElementById('bullseyeCanvas'),
  fuel:        document.getElementById('fuelCanvas'),
  gantt:       document.getElementById('ganttCanvas'),
  dv:          document.getElementById('dvCanvas'),
};

const ctx = {};
for (const [k, c] of Object.entries(canvases)) {
  ctx[k] = c.getContext('2d');
}

// ─── Resize all canvases to match their container ─────────────────
function resizeAll() {
  for (const [k, c] of Object.entries(canvases)) {
    const parent = c.parentElement;
    c.width  = parent.offsetWidth;
    c.height = parent.offsetHeight;
  }
}
window.addEventListener('resize', () => { resizeAll(); });
resizeAll();


// ═══════════════════════════════════════════════════════════════════
// MODULE 1: GROUND TRACK MAP (Mercator Projection)
// ═══════════════════════════════════════════════════════════════════

/**
 * Mercator projection:
 * Maps lat/lon to x/y on a flat rectangle.
 * x = (lon + 180) / 360 * width          (linear)
 * y = (90 - lat)  / 180 * height         (linear — simplified flat Mercator)
 *
 * The "Terminator line" is the day/night boundary. It's a great circle
 * rotated by the sun's hour angle. We approximate the sun's subsolar
 * point and draw a sinusoidal curve across the map.
 */

// World map image (we draw a minimalist grid ourselves)
let worldMapDrawn = false;

function latLonToXY(lat, lon, W, H) {
  const x = ((lon + 180) / 360) * W;
  const y = ((90 - lat) / 180) * H;
  return [x, y];
}

function drawGroundTrack() {
  const c = canvases.groundTrack;
  const g = ctx.groundTrack;
  const W = c.width, H = c.height;

  // ── Background ──
  g.fillStyle = '#020810';
  g.fillRect(0, 0, W, H);

  // ── Grid lines (lon/lat every 30°) ──
  g.strokeStyle = 'rgba(26,45,69,0.6)';
  g.lineWidth = 0.5;
  for (let lon = -180; lon <= 180; lon += 30) {
    const [x] = latLonToXY(0, lon, W, H);
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
  }
  for (let lat = -90; lat <= 90; lat += 30) {
    const [, y] = latLonToXY(lat, 0, W, H);
    g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
  }

  // Equator highlight
  g.strokeStyle = 'rgba(0,150,170,0.25)';
  g.lineWidth = 1;
  const [, eqY] = latLonToXY(0, 0, W, H);
  g.beginPath(); g.moveTo(0, eqY); g.lineTo(W, eqY); g.stroke();

  // ── Terminator Line (day/night) ──
  if (state.showTerminator) {
    drawTerminator(g, W, H);
  }

  // ── Debris Cloud ──
  if (state.showDebrisOnMap && state.debrisCloud.length > 0) {
    g.fillStyle = 'rgba(255,100,100,0.25)';
    for (const d of state.debrisCloud) {
      const [, lat, lon] = d;
      const [x, y] = latLonToXY(lat, lon, W, H);
      g.fillRect(x - 0.5, y - 0.5, 1.5, 1.5);
    }
  }

  // ── Ground Stations ──
  const groundStations = [
    { name: 'ISTRAC', lat: 13.0333, lon: 77.5167 },
    { name: 'Svalbard', lat: 78.2297, lon: 15.4077 },
    { name: 'Goldstone', lat: 35.4266, lon: -116.890 },
    { name: 'Punta Arenas', lat: -53.15, lon: -70.917 },
    { name: 'IIT Delhi', lat: 28.545, lon: 77.193 },
    { name: 'McMurdo', lat: -77.846, lon: 166.668 },
  ];
  for (const gs of groundStations) {
    const [x, y] = latLonToXY(gs.lat, gs.lon, W, H);
    g.strokeStyle = 'rgba(0,229,255,0.5)';
    g.lineWidth = 1;
    g.beginPath();
    g.arc(x, y, 5, 0, Math.PI * 2);
    g.stroke();
    g.fillStyle = 'rgba(0,229,255,0.6)';
    g.font = '7px "Share Tech Mono"';
    g.fillText(gs.name, x + 6, y + 3);
  }

  // ── Orbit Trails ──
  if (state.showTrails) {
    for (const [satId, trail] of Object.entries(state.trailHistory)) {
      if (trail.length < 2) continue;
      const sat = state.satellites.find(s => s.id === satId);
      const baseColor = satStatusColor(sat?.status);

      g.lineWidth = 0.8;
      g.setLineDash([3, 4]);
      for (let i = 1; i < trail.length; i++) {
        const alpha = (i / trail.length) * 0.4;
        g.strokeStyle = baseColor.replace('1)', `${alpha})`);
        g.beginPath();
        const [x0, y0] = latLonToXY(trail[i-1].lat, trail[i-1].lon, W, H);
        const [x1, y1] = latLonToXY(trail[i].lat, trail[i].lon, W, H);
        // Don't draw line if it wraps around the globe
        if (Math.abs(x1 - x0) < W * 0.3) {
          g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
        }
      }
      g.setLineDash([]);
    }
  }

  // ── Predicted Track (dashed, next 90 min) ──
  // In a live system, this would use the physics propagator.
  // Here we draw a simplified sinusoidal approximation.
  for (const sat of state.satellites) {
    if (!sat._predictedTrack) continue;
    g.strokeStyle = 'rgba(59,139,255,0.35)';
    g.lineWidth = 0.7;
    g.setLineDash([5, 6]);
    g.beginPath();
    let first = true;
    for (const pt of sat._predictedTrack) {
      const [x, y] = latLonToXY(pt.lat, pt.lon, W, H);
      if (first) { g.moveTo(x, y); first = false; }
      else g.lineTo(x, y);
    }
    g.stroke();
    g.setLineDash([]);
  }

  // ── Satellite Markers ──
  for (const sat of state.satellites) {
    const [x, y] = latLonToXY(sat.lat, sat.lon, W, H);
    const color = satStatusColor(sat.status);
    const isSelected = sat.id === state.selectedSat;

    // Glow ring for selected
    if (isSelected) {
      g.beginPath();
      g.arc(x, y, 10, 0, Math.PI * 2);
      g.strokeStyle = 'rgba(0,229,255,0.6)';
      g.lineWidth = 1.5;
      g.stroke();
    }

    // Satellite realistic shape (central body + solar panels)
    g.save();
    g.translate(x, y);
    // Draw solar panels
    g.fillStyle = '#2c5282'; // Deep blue panels
    g.fillRect(-7, -1.5, 4, 3);
    g.fillRect(3, -1.5, 4, 3);
    
    // Draw connecting strut
    g.fillStyle = '#a0aec0';
    g.fillRect(-3, -0.5, 6, 1);
    
    // Draw central body
    g.beginPath();
    g.arc(0, 0, isSelected ? 3 : 2, 0, Math.PI * 2);
    g.fillStyle = color;
    g.shadowBlur = isSelected ? 12 : 5;
    g.shadowColor = color;
    g.fill();
    g.shadowBlur = 0;
    
    // Add a tiny glowing antenna
    g.fillStyle = '#ffffff';
    g.fillRect(-0.5, -3, 1, 2);
    g.restore();

    // Label for selected sat
    if (isSelected) {
      g.fillStyle = 'rgba(0,229,255,0.9)';
      g.font = 'bold 9px "Share Tech Mono"';
      g.fillText(sat.id, x + 8, y - 5);
    }
  }
}

function satStatusColor(status) {
  const map = {
    'NOMINAL':    'rgba(57,255,122,1)',
    'EVADING':    'rgba(255,184,48,1)',
    'RECOVERING': 'rgba(59,139,255,1)',
    'EOL':        'rgba(168,85,247,1)',
    'DEAD':       'rgba(255,59,82,1)',
  };
  return map[status] || 'rgba(57,255,122,1)';
}

function drawTerminator(g, W, H) {
  /**
   * Approximate the day/night terminator.
   * The subsolar point moves east at 360°/24h = 15°/hour.
   * We compute the subsolar longitude from simulation time and
   * shade the night side with a dark overlay.
   *
   * Solar declination varies seasonally; we use a fixed ~0° (equinox)
   * since the simulation epoch is near the March equinox.
   */
  const hourAngle = (state.simTimeSec / 3600) * 15; // degrees east
  const subSolarLon = -180 + (hourAngle % 360);
  const subSolarLat = 0; // equinox approximation

  // Draw night side as a dark overlay west of the terminator
  // We sample every 2px across the width and shade accordingly
  const termX = ((subSolarLon + 180) / 360) * W;

  // Night side fill (180° opposite the subsolar point)
  const nightWidth = W / 2;
  let nightStart = termX - nightWidth / 2;

  // Draw dark overlay for night side
  g.save();
  g.globalAlpha = 0.35;
  g.fillStyle = '#000820';

  // Night is opposite the subsolar point
  const nightLon = subSolarLon + 180;
  const [nx] = latLonToXY(0, ((nightLon + 180) % 360) - 180, W, H);

  // Simple: shade a band around the anti-solar point
  if (nx + nightWidth / 2 > W) {
    g.fillRect(nx - nightWidth / 2, 0, W - (nx - nightWidth / 2), H);
    g.fillRect(0, 0, (nx + nightWidth / 2) - W, H);
  } else if (nx - nightWidth / 2 < 0) {
    g.fillRect(0, 0, nx + nightWidth / 2, H);
    g.fillRect(W + (nx - nightWidth / 2), 0, -(nx - nightWidth / 2), H);
  } else {
    g.fillRect(nx - nightWidth / 2, 0, nightWidth, H);
  }
  g.restore();

  // Terminator line
  g.strokeStyle = 'rgba(0,229,255,0.2)';
  g.lineWidth = 1;
  g.setLineDash([4, 5]);
  g.beginPath();
  g.moveTo(termX - nightWidth / 2, 0);
  g.lineTo(termX - nightWidth / 2, H);
  g.stroke();
  g.setLineDash([]);
}

// Ground track tooltip on hover
canvases.groundTrack.addEventListener('mousemove', (e) => {
  const rect = canvases.groundTrack.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const W = canvases.groundTrack.width;
  const H = canvases.groundTrack.height;

  let hovered = null;
  for (const sat of state.satellites) {
    const [sx, sy] = latLonToXY(sat.lat, sat.lon, W, H);
    if (Math.hypot(mx - sx, my - sy) < 8) { hovered = sat; break; }
  }

  const tip = els.mapTooltip;
  if (hovered) {
    tip.classList.remove('hidden');
    tip.style.left = (mx + 14) + 'px';
    tip.style.top  = (my - 10) + 'px';
    tip.innerHTML =
      `<b>${hovered.id}</b><br>` +
      `Lat: ${hovered.lat.toFixed(2)}° Lon: ${hovered.lon.toFixed(2)}°<br>` +
      `Fuel: ${hovered.fuel_kg.toFixed(2)} kg<br>` +
      `Status: <span style="color:${satStatusColor(hovered.status)}">${hovered.status}</span>`;
  } else {
    tip.classList.add('hidden');
  }
});

canvases.groundTrack.addEventListener('click', (e) => {
  const rect = canvases.groundTrack.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const W = canvases.groundTrack.width;
  const H = canvases.groundTrack.height;

  for (const sat of state.satellites) {
    const [sx, sy] = latLonToXY(sat.lat, sat.lon, W, H);
    if (Math.hypot(mx - sx, my - sy) < 10) {
      state.selectedSat = sat.id;
      els.satSelector.value = sat.id;
      break;
    }
  }
});

// Toggle buttons
document.getElementById('btnToggleTrails').addEventListener('click', function() {
  state.showTrails = !state.showTrails;
  this.classList.toggle('active', state.showTrails);
});
document.getElementById('btnToggleTerminator').addEventListener('click', function() {
  state.showTerminator = !state.showTerminator;
  this.classList.toggle('active', state.showTerminator);
});
document.getElementById('btnToggleDebrisMap').addEventListener('click', function() {
  state.showDebrisOnMap = !state.showDebrisOnMap;
  this.classList.toggle('active', state.showDebrisOnMap);
});


// ═══════════════════════════════════════════════════════════════════
// MODULE 2: CONJUNCTION BULLSEYE PLOT (Polar Chart)
// ═══════════════════════════════════════════════════════════════════

/**
 * The bullseye is a polar coordinate view:
 * - Center = selected satellite
 * - Radial distance = time to closest approach (TCA) in minutes
 *   (inner ring = imminent, outer = far future)
 * - Angle = approach direction (relative bearing of debris)
 * - Color = risk level based on miss distance
 *
 * Since we don't have real CDM data in the frontend, we synthesize
 * demo data from the debris cloud based on proximity.
 */

function drawBullseye() {
  const c = canvases.bullseye;
  const g = ctx.bullseye;
  const W = c.width, H = c.height;
  const cx = W / 2, cy = H / 2;
  const maxR = Math.min(W, H) / 2 - 24;

  g.clearRect(0, 0, W, H);

  // ── Concentric rings ──
  const rings = [
    { r: maxR * 0.25, label: '6h', color: 'rgba(255,59,82,0.15)' },
    { r: maxR * 0.50, label: '12h', color: 'rgba(255,184,48,0.08)' },
    { r: maxR * 0.75, label: '18h', color: 'rgba(59,139,255,0.06)' },
    { r: maxR * 1.00, label: '24h', color: 'rgba(26,45,69,0.3)' },
  ];

  for (const ring of rings) {
    g.beginPath();
    g.arc(cx, cy, ring.r, 0, Math.PI * 2);
    g.strokeStyle = 'rgba(26,60,90,0.7)';
    g.lineWidth = 0.5;
    g.stroke();
    // Ring label
    g.fillStyle = 'rgba(61,96,128,0.7)';
    g.font = '8px "Share Tech Mono"';
    g.fillText(ring.label, cx + ring.r - 12, cy - 3);
  }

  // ── Crosshairs ──
  g.strokeStyle = 'rgba(26,60,90,0.5)';
  g.lineWidth = 0.5;
  g.beginPath(); g.moveTo(cx - maxR, cy); g.lineTo(cx + maxR, cy); g.stroke();
  g.beginPath(); g.moveTo(cx, cy - maxR); g.lineTo(cx, cy + maxR); g.stroke();

  // ── Direction labels ──
  g.fillStyle = 'rgba(61,96,128,0.6)';
  g.font = '8px "Share Tech Mono"';
  g.textAlign = 'center';
  g.fillText('PRO', cx, cy - maxR - 6);
  g.fillText('RETRO', cx, cy + maxR + 14);
  g.fillText('+R', cx + maxR + 3, cy + 3);
  g.fillText('-R', cx - maxR - 3, cy + 3);
  g.textAlign = 'left';

  const sat = state.satellites.find(s => s.id === state.selectedSat);
  if (!sat) {
    // No satellite selected — show placeholder
    g.fillStyle = 'rgba(61,96,128,0.4)';
    g.font = '10px "Share Tech Mono"';
    g.textAlign = 'center';
    g.fillText('SELECT A SATELLITE', cx, cy - 8);
    g.fillText('TO VIEW CONJUNCTIONS', cx, cy + 8);
    g.textAlign = 'left';

    // Satellite dot
    g.beginPath(); g.arc(cx, cy, 5, 0, Math.PI * 2);
    g.fillStyle = 'rgba(0,229,255,0.3)'; g.fill();
    return;
  }

  // ── Generate nearby debris for the selected satellite ──
  // In production this comes from the CDM endpoint.
  // Here we compute proximity from the debris cloud snapshot.
  const conjunctions = generateConjunctionData(sat);

  // ── Plot debris markers ──
  for (const conj of conjunctions) {
    // r = TCA-based radial distance (closer TCA = smaller r = closer to center)
    const radiusFrac = Math.min(conj.tca_hours / 24, 1);
    const plotR = radiusFrac * maxR;

    // Angle = approach bearing (0 = prograde/top)
    const angle = conj.bearing_rad - Math.PI / 2;
    const px = cx + Math.cos(angle) * plotR;
    const py = cy + Math.sin(angle) * plotR;

    // Color by miss distance
    let color, glow;
    if (conj.miss_km < 0.1) {
      color = 'rgba(255,59,82,1)'; glow = 'rgba(255,59,82,0.6)';
    } else if (conj.miss_km < 1.0) {
      color = 'rgba(255,120,50,1)'; glow = 'rgba(255,120,50,0.4)';
    } else if (conj.miss_km < 5.0) {
      color = 'rgba(255,184,48,1)'; glow = 'rgba(255,184,48,0.3)';
    } else {
      color = 'rgba(57,255,122,0.7)'; glow = 'none';
    }

    const dotR = conj.miss_km < 0.1 ? 5 : conj.miss_km < 5 ? 3.5 : 2.5;

    if (glow !== 'none') {
      g.shadowBlur = 8; g.shadowColor = glow;
    }
    g.beginPath(); g.arc(px, py, dotR, 0, Math.PI * 2);
    g.fillStyle = color; g.fill();
    g.shadowBlur = 0;

    // Label the most critical ones
    if (conj.miss_km < 1.0) {
      g.fillStyle = color;
      g.font = '7px "Share Tech Mono"';
      g.fillText(conj.id.slice(-5), px + 5, py - 3);
    }
  }

  // ── Selected satellite at center ──
  g.beginPath(); g.arc(cx, cy, 6, 0, Math.PI * 2);
  g.fillStyle = 'rgba(0,229,255,0.9)';
  g.shadowBlur = 14; g.shadowColor = 'rgba(0,229,255,0.7)';
  g.fill(); g.shadowBlur = 0;
  // Crosshair lines on center dot
  g.strokeStyle = 'rgba(0,229,255,0.5)';
  g.lineWidth = 1;
  g.beginPath(); g.moveTo(cx-10,cy); g.lineTo(cx+10,cy); g.stroke();
  g.beginPath(); g.moveTo(cx,cy-10); g.lineTo(cx,cy+10); g.stroke();

  // Label
  g.fillStyle = 'rgba(0,229,255,0.8)';
  g.font = '8px "Share Tech Mono"';
  g.textAlign = 'center';
  g.fillText(sat.id, cx, cy + 20);
  g.fillText(`${conjunctions.filter(c=>c.miss_km<0.1).length} CRITICAL`, cx, H - 12);
  g.textAlign = 'left';
}

function generateConjunctionData(sat) {
  /**
   * Synthesize conjunction data from the debris cloud.
   * We compute a rough angular distance between the satellite's
   * lat/lon and each debris piece, then classify by proximity.
   * TCA is estimated from angular separation / orbital velocity.
   */
  const results = [];
  const sample = state.debrisCloud.slice(0, 200); // sample for performance

  for (const d of sample) {
    const [id, dlat, dlon, dalt] = d;
    const dlat_diff = dlat - sat.lat;
    const dlon_diff = dlon - sat.lon;
    const angDist = Math.sqrt(dlat_diff*dlat_diff + dlon_diff*dlon_diff);

    if (angDist > 15) continue; // Only show relatively nearby debris

    // Rough miss distance estimate (not real physics — just for visualization)
    const alt_diff = Math.abs((dalt - 550)) * 0.1; // altitude separation
    const miss_km = angDist * 111 * 0.01 + alt_diff; // very rough

    // Bearing angle
    const bearing = Math.atan2(dlon_diff, dlat_diff);

    // TCA estimate: debris at ~111km per degree, relative velocity ~1km/s
    const tca_hours = (angDist * 111) / 3600 + Math.random() * 4;

    results.push({ id, miss_km, bearing_rad: bearing, tca_hours });
  }

  // Sort by miss distance so critical ones render on top
  return results.sort((a, b) => b.miss_km - a.miss_km);
}

// Satellite selector
els.satSelector.addEventListener('change', (e) => {
  state.selectedSat = e.target.value || null;
});


// ═══════════════════════════════════════════════════════════════════
// MODULE 3: FLEET FUEL STATUS HEATMAP
// ═══════════════════════════════════════════════════════════════════

/**
 * Renders a grid of fuel gauges — one per satellite.
 * Each gauge shows:
 *   - Colored bar proportional to fuel remaining
 *   - Color gradient: green → amber → red as fuel depletes
 *   - Satellite ID label
 *
 * This gives operators an at-a-glance view of the fleet's propellant budget.
 */

function drawFuelHeatmap() {
  const c = canvases.fuel;
  const g = ctx.fuel;
  const W = c.width, H = c.height;

  g.fillStyle = '#080f1a';
  g.fillRect(0, 0, W, H);

  if (state.satellites.length === 0) return;

  const n = state.satellites.length;
  const cols = Math.ceil(Math.sqrt(n * (W / H)));
  const rows = Math.ceil(n / cols);
  const cellW = W / cols;
  const cellH = H / rows;
  const padding = 3;

  let totalFuel = 0;
  const INITIAL_FUEL = 50.0;

  for (let i = 0; i < n; i++) {
    const sat = state.satellites[i];
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = col * cellW + padding;
    const y = row * cellH + padding;
    const w = cellW - padding * 2;
    const h = cellH - padding * 2;

    const fuelFrac = Math.max(0, Math.min(1, sat.fuel_kg / INITIAL_FUEL));
    totalFuel += fuelFrac;

    // Cell background
    g.fillStyle = 'rgba(12,20,32,0.8)';
    g.fillRect(x, y, w, h);

    // Fuel bar (full height left-to-right fill)
    const fuelColor = fuelFrac > 0.5
      ? `rgba(57,255,122,${0.6 + fuelFrac * 0.4})`
      : fuelFrac > 0.2
      ? `rgba(255,184,48,${0.7 + fuelFrac * 0.3})`
      : `rgba(255,59,82,${0.8})`;

    g.fillStyle = fuelColor;
    g.fillRect(x, y + h * (1 - fuelFrac), w, h * fuelFrac);

    // Status overlay color (top strip)
    const statusColors = {
      NOMINAL: 'rgba(57,255,122,0.8)',
      EVADING: 'rgba(255,184,48,0.8)',
      RECOVERING: 'rgba(59,139,255,0.8)',
      EOL: 'rgba(168,85,247,0.8)',
      DEAD: 'rgba(255,59,82,0.8)',
    };
    g.fillStyle = statusColors[sat.status] || 'rgba(57,255,122,0.8)';
    g.fillRect(x, y, w, 2);

    // ID label (if cell big enough)
    if (cellH > 24) {
      g.fillStyle = 'rgba(255,255,255,0.7)';
      g.font = `${Math.min(8, cellH * 0.22)}px "Share Tech Mono"`;
      g.textAlign = 'center';
      const shortId = sat.id.replace('SAT-', '');
      g.fillText(shortId, x + w/2, y + h - 3);
      g.textAlign = 'left';
    }

    // Fuel % text
    if (cellH > 38) {
      g.fillStyle = fuelFrac > 0.2 ? 'rgba(255,255,255,0.9)' : 'rgba(255,59,82,1)';
      g.font = `bold ${Math.min(10, cellH * 0.28)}px "Share Tech Mono"`;
      g.textAlign = 'center';
      g.fillText(`${Math.round(fuelFrac * 100)}%`, x + w/2, y + h/2 + 3);
      g.textAlign = 'left';
    }

    // Cell border
    g.strokeStyle = sat.id === state.selectedSat
      ? 'rgba(0,229,255,0.7)'
      : 'rgba(26,45,69,0.5)';
    g.lineWidth = sat.id === state.selectedSat ? 1.5 : 0.5;
    g.strokeRect(x, y, w, h);
  }

  // Fleet average
  const avgFuel = (totalFuel / n) * 100;
  els.fleetFuelAvg.textContent = `AVG: ${avgFuel.toFixed(1)}%`;
  els.fleetFuelAvg.style.color = avgFuel > 50 ? '#39ff7a' : avgFuel > 20 ? '#ffb830' : '#ff3b52';
}


// ═══════════════════════════════════════════════════════════════════
// MODULE 4: MANEUVER TIMELINE (Gantt Chart)
// ═══════════════════════════════════════════════════════════════════

/**
 * A horizontal timeline showing past and future burns for each satellite.
 * - X axis = simulation time (scrollable)
 * - Y axis = satellite ID
 * - Blocks: EVASION (amber), RECOVERY (blue), COOLDOWN (dark)
 *
 * Cooldown periods (600s) are shown as hatched grey blocks between burns.
 */

let ganttScrollOffset = 0; // pixels

function drawGantt() {
  const c = canvases.gantt;
  const g = ctx.gantt;
  const W = c.width, H = c.height;

  g.fillStyle = '#060c14';
  g.fillRect(0, 0, W, H);

  if (state.maneuverLog.length === 0 && state.satellites.length === 0) return;

  const sats = state.satellites.slice(0, 20); // show first 20
  const rowH = Math.max(14, (H - 20) / Math.max(sats.length, 1));
  const labelW = 72;
  const timelineW = W - labelW;

  // Time window: show 2h around current sim time
  const windowSec = 7200;
  const tStart = state.simTimeSec - windowSec * 0.3;
  const tEnd = tStart + windowSec;

  function timeToX(t) {
    return labelW + ((t - tStart) / (tEnd - tStart)) * timelineW;
  }

  // ── Time axis ──
  g.strokeStyle = 'rgba(26,45,69,0.6)';
  g.lineWidth = 0.5;
  const tickIntervalSec = 600; // every 10 min
  for (let t = Math.ceil(tStart / tickIntervalSec) * tickIntervalSec; t <= tEnd; t += tickIntervalSec) {
    const x = timeToX(t);
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
    const mins = Math.round(t / 60);
    g.fillStyle = 'rgba(61,96,128,0.5)';
    g.font = '7px "Share Tech Mono"';
    g.fillText(`T+${mins}m`, x + 2, H - 2);
  }

  // ── "Now" line ──
  const nowX = timeToX(state.simTimeSec);
  g.strokeStyle = 'rgba(0,229,255,0.6)';
  g.lineWidth = 1.5;
  g.setLineDash([4, 3]);
  g.beginPath(); g.moveTo(nowX, 0); g.lineTo(nowX, H - 14); g.stroke();
  g.setLineDash([]);
  g.fillStyle = 'rgba(0,229,255,0.7)';
  g.font = '7px "Share Tech Mono"';
  g.fillText('NOW', nowX + 2, 10);

  // ── Rows ──
  for (let i = 0; i < sats.length; i++) {
    const sat = sats[i];
    const rowY = i * rowH;

    // Row background
    g.fillStyle = i % 2 === 0 ? 'rgba(8,15,26,0.8)' : 'rgba(12,20,32,0.6)';
    g.fillRect(labelW, rowY, timelineW, rowH - 1);

    // Satellite label
    g.fillStyle = sat.id === state.selectedSat ? 'rgba(0,229,255,0.9)' : 'rgba(100,160,200,0.7)';
    g.font = `${Math.min(8, rowH * 0.6)}px "Share Tech Mono"`;
    g.textAlign = 'right';
    g.fillText(sat.id.replace('SAT-', ''), labelW - 4, rowY + rowH * 0.65);
    g.textAlign = 'left';

    // Draw maneuver blocks for this satellite
    const satBurns = state.maneuverLog.filter(b => b.satId === sat.id);
    for (const burn of satBurns) {
      const bx = timeToX(burn.startTime);
      const bw = Math.max(3, timeToX(burn.endTime) - bx);

      if (bx > W || bx + bw < labelW) continue; // Off-screen

      const burnColors = {
        EVASION:  { fill: 'rgba(255,184,48,0.8)',  stroke: 'rgba(255,184,48,1)' },
        RECOVERY: { fill: 'rgba(59,139,255,0.8)',   stroke: 'rgba(59,139,255,1)' },
        EOL:      { fill: 'rgba(168,85,247,0.8)',   stroke: 'rgba(168,85,247,1)' },
        MANUAL:   { fill: 'rgba(57,255,122,0.7)',   stroke: 'rgba(57,255,122,1)' },
        COOLDOWN: { fill: 'rgba(26,45,69,0.5)',     stroke: 'rgba(26,45,69,0.8)' },
      };
      const col = burnColors[burn.type] || burnColors.MANUAL;

      g.fillStyle = col.fill;
      g.fillRect(bx, rowY + 1, bw, rowH - 3);
      g.strokeStyle = col.stroke;
      g.lineWidth = 0.5;
      g.strokeRect(bx, rowY + 1, bw, rowH - 3);

      // Cooldown block after burn (600s hatched)
      const cooldownX = bx + bw;
      const cooldownW = timeToX(burn.endTime + 600) - cooldownX;
      if (cooldownW > 0 && burn.type !== 'COOLDOWN') {
        g.save();
        g.fillStyle = 'rgba(26,45,69,0.4)';
        g.fillRect(cooldownX, rowY + 1, Math.min(cooldownW, W - cooldownX), rowH - 3);
        // Hatch pattern
        g.strokeStyle = 'rgba(26,45,69,0.6)';
        g.lineWidth = 0.5;
        for (let hx = cooldownX; hx < cooldownX + cooldownW && hx < W; hx += 4) {
          g.beginPath();
          g.moveTo(hx, rowY + 1);
          g.lineTo(hx - (rowH - 3), rowY + rowH - 2);
          g.stroke();
        }
        g.restore();
      }
    }
  }

  // Left border
  g.strokeStyle = 'rgba(26,45,69,0.8)';
  g.lineWidth = 1;
  g.beginPath(); g.moveTo(labelW, 0); g.lineTo(labelW, H); g.stroke();
}

// ═══════════════════════════════════════════════════════════════════
// MODULE 5: ΔV EFFICIENCY GRAPH (Fuel vs Collisions Avoided)
// ═══════════════════════════════════════════════════════════════════

function drawDVGraph() {
  const c = canvases.dv;
  const g = ctx.dv;
  const W = c.width, H = c.height;

  g.fillStyle = '#060c14';
  g.fillRect(0, 0, W, H);

  const MARGIN = { top: 12, right: 16, bottom: 28, left: 44 };
  const plotW = W - MARGIN.left - MARGIN.right;
  const plotH = H - MARGIN.top - MARGIN.bottom;

  if (state.dvHistory.length < 2) {
    g.fillStyle = 'rgba(61,96,128,0.4)';
    g.font = '9px "Share Tech Mono"';
    g.textAlign = 'center';
    g.fillText('AWAITING DATA...', W/2, H/2);
    g.textAlign = 'left';
    return;
  }

  // Axes
  g.strokeStyle = 'rgba(26,60,90,0.8)';
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(MARGIN.left, MARGIN.top);
  g.lineTo(MARGIN.left, MARGIN.top + plotH);
  g.lineTo(MARGIN.left + plotW, MARGIN.top + plotH);
  g.stroke();

  // Labels
  g.fillStyle = 'rgba(61,96,128,0.7)';
  g.font = '8px "Share Tech Mono"';
  g.textAlign = 'center';
  g.fillText('TIME →', MARGIN.left + plotW/2, H - 4);
  g.save();
  g.translate(10, MARGIN.top + plotH/2);
  g.rotate(-Math.PI/2);
  g.fillText('ΔV kg', 0, 0);
  g.restore();
  g.textAlign = 'left';

  const maxFuel = Math.max(...state.dvHistory.map(d => d.fuel_used), 1);
  const maxTime = state.dvHistory.length;

  function toXY(i, val, maxVal) {
    const x = MARGIN.left + (i / (maxTime - 1)) * plotW;
    const y = MARGIN.top + plotH - (val / maxVal) * plotH;
    return [x, y];
  }

  // Fuel consumed line (amber)
  g.strokeStyle = 'rgba(255,184,48,0.8)';
  g.lineWidth = 1.5;
  g.beginPath();
  state.dvHistory.forEach((d, i) => {
    const [x, y] = toXY(i, d.fuel_used, maxFuel);
    i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
  });
  g.stroke();

  // Area fill under fuel line
  g.save();
  const lastPt = toXY(state.dvHistory.length - 1, state.dvHistory[state.dvHistory.length-1].fuel_used, maxFuel);
  const firstPt = toXY(0, state.dvHistory[0].fuel_used, maxFuel);
  g.lineTo(lastPt[0], MARGIN.top + plotH);
  g.lineTo(firstPt[0], MARGIN.top + plotH);
  g.closePath();
  g.fillStyle = 'rgba(255,184,48,0.06)';
  g.fill();
  g.restore();

  // Collisions avoided line (green — if we have it)
  const maxAvoid = Math.max(...state.dvHistory.map(d => d.collisions_avoided), 1);
  if (maxAvoid > 0) {
    g.strokeStyle = 'rgba(57,255,122,0.7)';
    g.lineWidth = 1.5;
    g.beginPath();
    state.dvHistory.forEach((d, i) => {
      const [x, y] = toXY(i, d.collisions_avoided, maxAvoid);
      i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
    });
    g.stroke();
  }

  // Legend
  g.fillStyle = 'rgba(255,184,48,0.8)'; g.fillRect(MARGIN.left, MARGIN.top + 2, 12, 2);
  g.fillStyle = 'rgba(255,184,48,0.7)'; g.font = '7px "Share Tech Mono"';
  g.fillText('Fuel kg', MARGIN.left + 15, MARGIN.top + 6);

  g.fillStyle = 'rgba(57,255,122,0.8)'; g.fillRect(MARGIN.left + 55, MARGIN.top + 2, 12, 2);
  g.fillStyle = 'rgba(57,255,122,0.7)';
  g.fillText('Avoided', MARGIN.left + 70, MARGIN.top + 6);
}


// ═══════════════════════════════════════════════════════════════════
// API POLLING
// ═══════════════════════════════════════════════════════════════════

async function fetchSnapshot() {
  try {
    const resp = await fetch(`${API_BASE}/api/visualization/snapshot`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    // Update satellite list
    state.satellites = data.satellites || [];
    state.debrisCloud = data.debris_cloud || [];

    // Update trail history (keep last 90 minutes = ~90 positions at 60s intervals)
    for (const sat of state.satellites) {
      if (!state.trailHistory[sat.id]) state.trailHistory[sat.id] = [];
      state.trailHistory[sat.id].push({ lat: sat.lat, lon: sat.lon });
      if (state.trailHistory[sat.id].length > 90) {
        state.trailHistory[sat.id].shift();
      }
    }

    // Update selector
    updateSatSelector();

    // Update stats
    els.statSatCount.textContent = state.satellites.length;
    els.statDebrisCount.textContent = state.debrisCloud.length;

    // Use authoritative sim time from backend if available
    if (data.sim_time_s !== undefined) {
      state.simTimeSec = data.sim_time_s;
    } else {
      state.simTimeSec += POLL_INTERVAL_MS / 1000;
    }
    updateClocks();

    // Mark connected
    setConnected(true);

    // Check for critical fuel
    const criticalSats = state.satellites.filter(s => s.fuel_kg < 2.5);
    if (criticalSats.length > 0) {
      showAlert(`FUEL CRITICAL: ${criticalSats.map(s=>s.id).join(', ')}`);
    }

    return true;
  } catch (err) {
    setConnected(false);
    return false;
  }
}

async function fetchHealth() {
  try {
    const resp = await fetch(`${API_BASE}/health`);
    if (!resp.ok) throw new Error();
    const data = await resp.json();
    els.statCDMCount.textContent = data.active_cdms || 0;

    if ((data.active_cdms || 0) > 0) {
      document.getElementById('statCDM').classList.add('alert');
    }

    // Add ΔV history point
    if (state.dvHistory.length === 0 || state.simTimeSec % 30 < 2) {
      const prevFuel = state.dvHistory.length > 0
        ? state.dvHistory[state.dvHistory.length - 1].fuel_used
        : 0;
      const totalFuelLeft = (state.satellites.reduce((sum, s) => sum + s.fuel_kg, 0));
      const totalFuelUsed = state.satellites.length * 50 - totalFuelLeft;
      state.dvHistory.push({
        fuel_used: Math.max(0, totalFuelUsed),
        collisions_avoided: data.total_collisions || 0,
        t: state.simTimeSec
      });
      if (state.dvHistory.length > 60) state.dvHistory.shift();
    }

    // Inject some demo maneuver data so the Gantt isn't empty on load
    if (state.maneuverLog.length === 0 && state.satellites.length > 0) {
      seedDemoManeuvers();
    }

  } catch {}
}

function seedDemoManeuvers() {
  const types = ['EVASION', 'RECOVERY', 'MANUAL'];
  for (let i = 0; i < Math.min(state.satellites.length, 15); i++) {
    const sat = state.satellites[i];
    const offset = (Math.random() - 0.3) * 3600;
    state.maneuverLog.push({
      satId: sat.id,
      burnId: `BURN_${i}`,
      startTime: state.simTimeSec + offset,
      endTime: state.simTimeSec + offset + 60 + Math.random() * 120,
      type: types[i % 3],
    });
  }
}

function updateSatSelector() {
  const current = els.satSelector.value;
  els.satSelector.innerHTML = '<option value="">— SELECT SAT —</option>';
  for (const sat of state.satellites) {
    const opt = document.createElement('option');
    opt.value = sat.id;
    opt.textContent = sat.id;
    if (sat.status !== 'NOMINAL') opt.textContent += ` [${sat.status}]`;
    els.satSelector.appendChild(opt);
  }
  if (current) els.satSelector.value = current;

  // Auto-select first satellite if none selected
  if (!state.selectedSat && state.satellites.length > 0) {
    state.selectedSat = state.satellites[0].id;
    els.satSelector.value = state.selectedSat;
  }
}

function updateClocks() {
  const h = Math.floor(state.simTimeSec / 3600);
  const m = Math.floor((state.simTimeSec % 3600) / 60);
  const s = Math.floor(state.simTimeSec % 60);
  els.simClock.textContent = `T+${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;

  const epoch = new Date(state.epochDate.getTime() + state.simTimeSec * 1000);
  els.epochClock.textContent = epoch.toISOString().replace('T',' ').slice(0,19);
}

function setConnected(online) {
  state.isConnected = online;
  els.connDot.classList.toggle('online', online);
  els.connLabel.textContent = online ? 'ONLINE' : 'OFFLINE';
}

function showAlert(msg) {
  els.alertText.textContent = msg;
  els.alertBanner.classList.remove('hidden');
  setTimeout(() => els.alertBanner.classList.add('hidden'), 5000);
}


// ═══════════════════════════════════════════════════════════════════
// RENDER LOOP (60 FPS via requestAnimationFrame)
// ═══════════════════════════════════════════════════════════════════

function renderFrame() {
  drawGroundTrack();
  drawBullseye();
  drawFuelHeatmap();
  drawGantt();
  drawDVGraph();
  requestAnimationFrame(renderFrame);
}


// ═══════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════

async function init() {
  resizeAll();

  // Try to connect to API
  const connected = await fetchSnapshot();
  await fetchHealth();

  if (!connected) {
    // Load demo data so the dashboard looks alive without an API
    console.warn('API not reachable — loading demo data');
    loadDemoData();
  }

  // Poll API every 2 seconds
  setInterval(async () => {
    await fetchSnapshot();
    await fetchHealth();
  }, POLL_INTERVAL_MS);

  // Start render loop
  requestAnimationFrame(renderFrame);
}

function loadDemoData() {
  /**
   * Generates a realistic-looking demo dataset so the dashboard
   * renders properly even before the backend is running.
   * This is useful during frontend development.
   */
  const statuses = ['NOMINAL','NOMINAL','NOMINAL','EVADING','RECOVERING','EOL'];
  for (let i = 0; i < 50; i++) {
    const plane = Math.floor(i / 10);
    const slot = i % 10;
    const lat = Math.sin(plane * 1.256 + slot * 0.628) * 53;
    const lon = ((plane * 72 + slot * 36 + state.simTimeSec * 0.004) % 360) - 180;
    state.satellites.push({
      id: `SAT-P${plane+1}-${String(slot+1).padStart(2,'0')}`,
      lat, lon,
      fuel_kg: 50 - Math.random() * 15,
      status: statuses[Math.floor(Math.random() * statuses.length)],
    });
  }

  for (let i = 0; i < 2000; i++) {
    const lat = (Math.random() - 0.5) * 160;
    const lon = (Math.random() - 0.5) * 360;
    const alt = 400 + Math.random() * 400;
    state.debrisCloud.push([`DEB-${String(i).padStart(5,'0')}`, lat, lon, alt]);
  }

  updateSatSelector();
  seedDemoManeuvers();

  // Seed ΔV history
  for (let i = 0; i < 30; i++) {
    state.dvHistory.push({
      fuel_used: i * 0.08 + Math.random() * 0.2,
      collisions_avoided: Math.floor(i * 0.3),
      t: i * 60
    });
  }

  els.statSatCount.textContent = state.satellites.length;
  els.statDebrisCount.textContent = state.debrisCloud.length;
  els.statCDMCount.textContent = Math.floor(Math.random() * 5);
  setConnected(false);
}

// Animate demo satellites even without API
setInterval(() => {
  if (!state.isConnected) {
    for (const sat of state.satellites) {
      sat.lon = ((sat.lon + 0.12) % 360 + 360) % 360;
      if (sat.lon > 180) sat.lon -= 360;
      sat.lat += (Math.random() - 0.5) * 0.02;
      if (!state.trailHistory[sat.id]) state.trailHistory[sat.id] = [];
      state.trailHistory[sat.id].push({ lat: sat.lat, lon: sat.lon });
      if (state.trailHistory[sat.id].length > 90) state.trailHistory[sat.id].shift();
    }
    state.simTimeSec += 30;
    updateClocks();
  }
}, 500);

// Start
init();
