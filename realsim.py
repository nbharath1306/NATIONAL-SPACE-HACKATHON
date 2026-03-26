#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          ACM TEST SIMULATOR — National Space Hackathon 2026                 ║
║          Feeds 15 satellites + debris to your ACM backend                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

HOW TO TEST YOUR ACM:
──────────────────────
  Step 1:  Start the ACM backend
           uvicorn app.main:app --host 0.0.0.0 --port 8000

  Step 2:  Run this simulator (in a second terminal)
           python3 simulator.py

  Step 3:  Open the dashboard
           frontend/index.html  in your browser

What this simulator does:
  ✓ Generates 15 satellites in realistic LEO orbits (ISS-like altitudes)
  ✓ Generates 500 debris objects scattered through LEO
  ✓ Injects 3 "close-approach" debris on deliberate collision courses
  ✓ Sends POST /api/telemetry every 2 seconds (real-time orbit propagation)
  ✓ Sends POST /api/simulate/step to advance sim clock
  ✓ Randomly schedules maneuvers via POST /api/maneuver/schedule
  ✓ Polls GET /api/visualization/snapshot and prints a live console view
  ✓ Logs everything to simulator.log for review
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import requests
import time
import json
import logging
import threading
import math
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from dataclasses import dataclass, field

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("simulator.log", mode="w"),
    ]
)
log = logging.getLogger("SIM")

# ─── Simulator Configuration ─────────────────────────────────────────────────
ACM_BASE_URL      = "http://127.0.0.1:8000"
EPOCH             = datetime(2026, 3, 12, 8, 0, 0, tzinfo=timezone.utc)
N_SATELLITES      = 15
N_DEBRIS          = 500
N_CLOSE_APPROACH  = 3        # Debris injected on near-collision courses
TELEMETRY_HZ      = 0.5      # Telemetry sends per second (every 2s)
SIM_STEP_SEC      = 60       # Simulated seconds per real tick
REAL_TICK_SEC     = 2.0      # Real-time seconds between ticks
MAX_TICKS         = 200      # Stop after this many ticks (~6 min 40s real time)

# Physics constants (must match ACM backend)
MU  = 398600.4418   # km³/s²
RE  = 6378.137      # km
J2  = 1.08263e-3
G0  = 9.80665e-3    # km/s²  (standard gravity, km units)
ISP = 300.0         # s


# ═══════════════════════════════════════════════════════════════════════════════
# ORBITAL MECHANICS (standalone, no backend dependency)
# ═══════════════════════════════════════════════════════════════════════════════

def keplerian_to_eci(a, e, inc_deg, raan_deg, argp_deg, nu_deg):
    """
    Convert Keplerian orbital elements to ECI state vector.

    Parameters:
        a       : semi-major axis [km]
        e       : eccentricity [0 = circular]
        inc_deg : inclination [degrees]
        raan_deg: Right Ascension of Ascending Node [degrees]
        argp_deg: argument of perigee [degrees]
        nu_deg  : true anomaly [degrees] — where the satellite is in its orbit

    Returns:
        state: [x, y, z, vx, vy, vz] in km and km/s
    """
    inc  = math.radians(inc_deg)
    raan = math.radians(raan_deg)
    argp = math.radians(argp_deg)
    nu   = math.radians(nu_deg)

    # Distance from Earth center at this point in orbit
    p = a * (1 - e**2)          # semi-latus rectum
    r = p / (1 + e * math.cos(nu))

    # Position and velocity in perifocal frame (orbital plane, x toward perigee)
    r_pqw = np.array([r * math.cos(nu), r * math.sin(nu), 0.0])
    v_pqw = np.array([
        -math.sqrt(MU / p) * math.sin(nu),
         math.sqrt(MU / p) * (e + math.cos(nu)),
         0.0
    ])

    # Rotation matrix: perifocal → ECI
    # R = Rz(-Ω) · Rx(-i) · Rz(-ω)
    def Rz(angle):
        c, s = math.cos(angle), math.sin(angle)
        return np.array([[c,-s,0],[s,c,0],[0,0,1]])
    def Rx(angle):
        c, s = math.cos(angle), math.sin(angle)
        return np.array([[1,0,0],[0,c,-s],[0,s,c]])

    R = Rz(-raan) @ Rx(-inc) @ Rz(-argp)

    r_eci = R @ r_pqw
    v_eci = R @ v_pqw

    return np.concatenate([r_eci, v_eci])


def j2_accel(r):
    x, y, z = r
    rn = np.linalg.norm(r)
    f = 1.5 * J2 * MU * RE**2 / rn**5
    return np.array([
        f * x * (5*z**2/rn**2 - 1),
        f * y * (5*z**2/rn**2 - 1),
        f * z * (5*z**2/rn**2 - 3),
    ])


def state_deriv(s):
    r, v = s[:3], s[3:]
    rn = np.linalg.norm(r)
    a = -(MU / rn**3) * r + j2_accel(r)
    return np.concatenate([v, a])


def rk4(state, dt):
    k1 = state_deriv(state)
    k2 = state_deriv(state + 0.5*dt*k1)
    k3 = state_deriv(state + 0.5*dt*k2)
    k4 = state_deriv(state + dt*k3)
    return state + (dt/6.0) * (k1 + 2*k2 + 2*k3 + k4)


# ═══════════════════════════════════════════════════════════════════════════════
# SATELLITE & DEBRIS DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SimObject:
    obj_id:  str
    obj_type: str          # "SATELLITE" or "DEBRIS"
    state:   np.ndarray    # [x,y,z,vx,vy,vz]
    fuel_kg: float = 50.0  # only used for satellites

    def propagate(self, dt_sec: float):
        self.state = rk4(self.state, dt_sec)

    def to_telemetry_dict(self, timestamp: datetime) -> dict:
        r, v = self.state[:3], self.state[3:]
        return {
            "id":   self.obj_id,
            "type": self.obj_type,
            "r":    {"x": float(r[0]), "y": float(r[1]), "z": float(r[2])},
            "v":    {"x": float(v[0]), "y": float(v[1]), "z": float(v[2])},
        }


def build_15_satellites() -> List[SimObject]:
    """
    Create 15 satellites modelled after real LEO mission profiles.

    Orbit assignments:
    ┌──────┬─────────────────────────────┬────────┬──────┬───────┐
    │  ID  │  Name / Mission Type        │ Alt km │ Inc° │ RAAN° │
    ├──────┼─────────────────────────────┼────────┼──────┼───────┤
    │  1   │ Alpha-01  (Earth Obs)       │  550   │  53  │   0   │
    │  2   │ Alpha-02  (Earth Obs)       │  550   │  53  │   0   │
    │  3   │ Alpha-03  (Earth Obs)       │  550   │  53  │   0   │
    │  4   │ Beta-01   (Comms relay)     │  600   │  45  │  72   │
    │  5   │ Beta-02   (Comms relay)     │  600   │  45  │  72   │
    │  6   │ Beta-03   (Comms relay)     │  600   │  45  │  72   │
    │  7   │ Gamma-01  (SAR radar)       │  500   │  97  │ 144   │
    │  8   │ Gamma-02  (SAR radar)       │  500   │  97  │ 144   │
    │  9   │ Gamma-03  (SAR radar)       │  500   │  97  │ 144   │
    │ 10   │ Delta-01  (Nav/Timing)      │  560   │  55  │ 216   │
    │ 11   │ Delta-02  (Nav/Timing)      │  560   │  55  │ 216   │
    │ 12   │ Delta-03  (Nav/Timing)      │  560   │  55  │ 216   │
    │ 13   │ Epsilon-01 (Tech Demo)      │  480   │  28  │ 288   │
    │ 14   │ Epsilon-02 (Tech Demo)      │  480   │  28  │ 288   │
    │ 15   │ Epsilon-03 (Tech Demo)      │  480   │  28  │ 288   │
    └──────┴─────────────────────────────┴────────┴──────┴───────┘
    """
    configs = [
        # Plane A — Earth Observation (Sun-synchronous-ish, 53° inc)
        ("SAT-Alpha-01", 550, 53.0,   0.0,   0,   0),
        ("SAT-Alpha-02", 550, 53.0,   0.0,   0, 120),
        ("SAT-Alpha-03", 550, 53.0,   0.0,   0, 240),
        # Plane B — Communications (medium inclination)
        ("SAT-Beta-01",  600, 45.0,  72.0,   0,   0),
        ("SAT-Beta-02",  600, 45.0,  72.0,   0, 120),
        ("SAT-Beta-03",  600, 45.0,  72.0,   0, 240),
        # Plane C — SAR Radar (near-polar, 97° retrograde)
        ("SAT-Gamma-01", 500, 97.0, 144.0,   0,   0),
        ("SAT-Gamma-02", 500, 97.0, 144.0,   0, 120),
        ("SAT-Gamma-03", 500, 97.0, 144.0,   0, 240),
        # Plane D — Navigation & Timing
        ("SAT-Delta-01", 560, 55.0, 216.0,   0,   0),
        ("SAT-Delta-02", 560, 55.0, 216.0,   0, 120),
        ("SAT-Delta-03", 560, 55.0, 216.0,   0, 240),
        # Plane E — Tech Demonstration (low inclination)
        ("SAT-Eps-01",   480, 28.0, 288.0,   0,   0),
        ("SAT-Eps-02",   480, 28.0, 288.0,   0, 120),
        ("SAT-Eps-03",   480, 28.0, 288.0,   0, 240),
    ]

    sats = []
    for sat_id, alt, inc, raan, argp, nu in configs:
        a = RE + alt       # semi-major axis
        state = keplerian_to_eci(a, 0.0001, inc, raan, argp, nu)
        sats.append(SimObject(sat_id, "SATELLITE", state, fuel_kg=50.0))
        log.info(
            f"  {sat_id:18s} | alt={alt}km inc={inc}° RAAN={raan}° "
            f"r={np.linalg.norm(state[:3]):.1f}km v={np.linalg.norm(state[3:]):.3f}km/s"
        )
    return sats


def build_debris_field(satellites: List[SimObject], n_random=500, n_close=3) -> List[SimObject]:
    """
    Build a realistic debris field:
    - n_random: debris scattered across 400–900 km altitude band
    - n_close:  debris on deliberate near-collision trajectories (test COLA)

    The "close-approach" debris are placed just ahead of specific satellites
    in their orbital plane with a slightly lower velocity, so they'll converge
    within the 24-hour conjunction window.
    """
    debris = []
    rng = np.random.default_rng(seed=42)  # reproducible

    # ── Random background debris ──────────────────────────────────────────────
    log.info(f"Generating {n_random} background debris objects...")
    for i in range(n_random):
        alt   = rng.uniform(400, 900)       # km
        inc   = rng.uniform(0, 110)         # degrees
        raan  = rng.uniform(0, 360)
        argp  = rng.uniform(0, 360)
        nu    = rng.uniform(0, 360)
        a     = RE + alt
        e     = rng.uniform(0.0, 0.02)      # slight eccentricity (realistic for debris)

        state = keplerian_to_eci(a, e, inc, raan, argp, nu)
        debris.append(SimObject(f"DEB-{i+1:05d}", "DEBRIS", state))

    # ── Close-approach debris (deliberate near-misses) ────────────────────────
    # We target Alpha-01, Gamma-01, and Delta-02 for conjunction scenarios
    target_ids = ["SAT-Alpha-01", "SAT-Gamma-01", "SAT-Delta-02"]
    targets    = [s for s in satellites if s.obj_id in target_ids]

    log.info(f"Generating {n_close} close-approach debris targeting: {target_ids}")
    for i, target in enumerate(targets[:n_close]):
        # Start 200km "ahead" in orbit (prograde direction) with ~1 m/s lower speed
        # This creates a slow convergence over ~2 hours
        r = target.state[:3].copy()
        v = target.state[3:].copy()

        # Move 200 km along the velocity direction
        v_hat = v / np.linalg.norm(v)
        r_ca = r + v_hat * 200.0

        # Slightly lower velocity → falls behind → approaches the satellite
        v_ca = v * 0.9998   # 0.02% slower ≈ ~1.5 m/s retrograde

        # Add a small radial offset so they don't start coincident
        r_hat = r / np.linalg.norm(r)
        r_ca += r_hat * 0.050   # 50 m radial offset (will close over time)

        state = np.concatenate([r_ca, v_ca])
        deb_id = f"DEB-CLOSE-{i+1:02d}"
        debris.append(SimObject(deb_id, "DEBRIS", state))
        log.warning(
            f"  {deb_id} → targeting {target.obj_id} "
            f"(initial separation: {np.linalg.norm(r_ca - r)*1000:.0f} m)"
        )

    return debris


# ═══════════════════════════════════════════════════════════════════════════════
# ACM API CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class ACMClient:
    """HTTP client for the ACM backend API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session  = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def health(self) -> dict | None:
        try:
            r = self.session.get(f"{self.base_url}/health", timeout=3)
            return r.json() if r.ok else None
        except Exception:
            return None

    def send_telemetry(self, timestamp: datetime, objects: List[SimObject]) -> dict | None:
        """POST /api/telemetry"""
        payload = {
            "timestamp": timestamp.isoformat(),
            "objects": [o.to_telemetry_dict(timestamp) for o in objects],
        }
        try:
            r = self.session.post(
                f"{self.base_url}/api/telemetry",
                data=json.dumps(payload),
                timeout=5
            )
            return r.json() if r.ok else None
        except Exception as e:
            log.error(f"Telemetry send failed: {e}")
            return None

    def simulate_step(self, step_seconds: float) -> dict | None:
        """POST /api/simulate/step"""
        try:
            r = self.session.post(
                f"{self.base_url}/api/simulate/step",
                data=json.dumps({"step_seconds": step_seconds}),
                timeout=15
            )
            return r.json() if r.ok else None
        except Exception as e:
            log.error(f"Simulate step failed: {e}")
            return None

    def schedule_maneuver(self, sat_id: str, burns: list) -> dict | None:
        """POST /api/maneuver/schedule"""
        payload = {"satelliteId": sat_id, "maneuver_sequence": burns}
        try:
            r = self.session.post(
                f"{self.base_url}/api/maneuver/schedule",
                data=json.dumps(payload),
                timeout=5
            )
            return r.json() if r.ok else None
        except Exception as e:
            log.error(f"Maneuver schedule failed: {e}")
            return None

    def get_snapshot(self) -> dict | None:
        """GET /api/visualization/snapshot"""
        try:
            r = self.session.get(f"{self.base_url}/api/visualization/snapshot", timeout=5)
            return r.json() if r.ok else None
        except Exception:
            return None

    def get_cdms(self) -> dict | None:
        """GET /api/debug/cdms"""
        try:
            r = self.session.get(f"{self.base_url}/api/debug/cdms", timeout=5)
            return r.json() if r.ok else None
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# CONSOLE DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
CLEAR  = "\033[2J\033[H"

STATUS_COLORS = {
    "NOMINAL":    GREEN,
    "EVADING":    YELLOW,
    "RECOVERING": CYAN,
    "EOL":        "\033[95m",
    "DEAD":       RED,
}

def print_dashboard(tick: int, sim_time_sec: float, satellites: list,
                    cdms: list, health: dict, last_step: dict):
    """Print a live terminal dashboard."""
    print(CLEAR, end="")

    elapsed_h = int(sim_time_sec // 3600)
    elapsed_m = int((sim_time_sec % 3600) // 60)
    elapsed_s = int(sim_time_sec % 60)
    epoch_now = EPOCH + timedelta(seconds=sim_time_sec)

    print(f"{CYAN}{BOLD}{'═'*72}{RESET}")
    print(f"{CYAN}{BOLD}  ◈  ORBITAL INSIGHT — ACM TEST SIMULATOR{RESET}  {DIM}NSH 2026{RESET}")
    print(f"{CYAN}{BOLD}{'═'*72}{RESET}")
    print(
        f"  Tick: {BOLD}{tick:4d}{RESET}  │  "
        f"Sim Time: {CYAN}T+{elapsed_h:02d}:{elapsed_m:02d}:{elapsed_s:02d}{RESET}  │  "
        f"Epoch: {DIM}{epoch_now.strftime('%Y-%m-%d %H:%M:%S')} UTC{RESET}"
    )
    print()

    # ── Health stats ──────────────────────────────────────────────────────────
    if health:
        cdm_count = health.get('active_cdms', 0)
        cdm_color = RED if cdm_count > 0 else GREEN
        print(
            f"  Backend  │  Sats: {GREEN}{health.get('satellites','?')}{RESET}"
            f"  Debris: {health.get('debris','?')}"
            f"  CDMs: {cdm_color}{cdm_count}{RESET}"
            f"  Collisions: {RED if health.get('total_collisions',0) > 0 else GREEN}"
            f"{health.get('total_collisions',0)}{RESET}"
            f"  Maneuvers: {CYAN}{health.get('total_maneuvers',0)}{RESET}"
        )
    print()

    # ── Last step result ──────────────────────────────────────────────────────
    if last_step:
        col = RED if last_step.get('collisions_detected', 0) > 0 else GREEN
        print(
            f"  Last Step │  +{SIM_STEP_SEC}s  │  "
            f"Collisions: {col}{last_step.get('collisions_detected', 0)}{RESET}  │  "
            f"Maneuvers Executed: {CYAN}{last_step.get('maneuvers_executed', 0)}{RESET}"
        )
    print()

    # ── Satellite table ───────────────────────────────────────────────────────
    print(f"  {BOLD}{'SATELLITE':<20} {'STATUS':<12} {'FUEL':>8} {'LAT':>8} {'LON':>8} {'ALT km':>8}{RESET}")
    print(f"  {'─'*66}")
    for sat in satellites[:15]:
        status = sat.get('status', 'NOMINAL')
        color  = STATUS_COLORS.get(status, GREEN)
        fuel   = sat.get('fuel_kg', 50)
        fuel_s = f"{fuel:.1f}kg"
        fuel_color = GREEN if fuel > 25 else YELLOW if fuel > 5 else RED
        print(
            f"  {sat.get('id','?'):<20} "
            f"{color}{status:<12}{RESET} "
            f"{fuel_color}{fuel_s:>8}{RESET} "
            f"{sat.get('lat', 0):>8.2f}° "
            f"{sat.get('lon', 0):>8.2f}° "
            f"{sat.get('alt', 0) if 'alt' in sat else '~550':>8}"
        )
    print()

    # ── Active CDMs ───────────────────────────────────────────────────────────
    if cdms:
        print(f"  {RED}{BOLD}⚠  ACTIVE CONJUNCTION WARNINGS ({len(cdms)}){RESET}")
        for cdm in cdms[:5]:
            miss_m = cdm.get('miss_distance_m', 0)
            color = RED if miss_m < 100 else YELLOW
            print(
                f"  {color}  {cdm['sat_id']:<20} ↔ {cdm['deb_id']:<15} "
                f"Miss: {miss_m:.1f}m  "
                f"{'[CRITICAL]' if cdm.get('is_critical') else '[WARNING]'}{RESET}"
            )
    else:
        print(f"  {GREEN}✓  No active conjunction warnings{RESET}")

    print()
    print(f"  {DIM}Telemetry → POST /api/telemetry  │  Step → POST /api/simulate/step")
    print(f"  Dashboard → frontend/index.html  │  Logs → simulator.log{RESET}")
    print(f"{CYAN}{'═'*72}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SIMULATOR LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_simulator():
    print(f"{CYAN}{BOLD}")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║         ACM TEST SIMULATOR — STARTING UP                        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(RESET)

    client = ACMClient(ACM_BASE_URL)

    # ── Wait for backend to be ready ─────────────────────────────────────────
    log.info(f"Connecting to ACM backend at {ACM_BASE_URL} ...")
    for attempt in range(15):
        health = client.health()
        if health:
            log.info(f"Backend online! {health}")
            break
        log.warning(f"Attempt {attempt+1}/15: backend not ready, retrying in 2s...")
        time.sleep(2)
    else:
        log.error(
            "\n\n  ❌  Cannot reach ACM backend!\n"
            "  Make sure it's running:\n"
            "    uvicorn app.main:app --host 0.0.0.0 --port 8000\n"
            "  Or with Docker:\n"
            "    docker-compose up\n"
        )
        sys.exit(1)

    # ── Build simulation objects ──────────────────────────────────────────────
    log.info("═" * 60)
    log.info("INITIALIZING 15 SATELLITES")
    log.info("═" * 60)
    satellites = build_15_satellites()

    log.info("═" * 60)
    log.info(f"GENERATING DEBRIS FIELD ({N_DEBRIS} objects + {N_CLOSE_APPROACH} close-approach)")
    log.info("═" * 60)
    debris = build_debris_field(satellites, N_DEBRIS, N_CLOSE_APPROACH)

    all_objects = satellites + debris
    log.info(f"Total objects in simulation: {len(all_objects)}")

    sim_time_sec = 0.0
    last_step_result = {}
    maneuver_tick_counter = 0

    log.info("═" * 60)
    log.info("STARTING SIMULATION LOOP")
    log.info(f"  Real-time tick: every {REAL_TICK_SEC}s")
    log.info(f"  Simulated time per tick: {SIM_STEP_SEC}s")
    log.info(f"  Max ticks: {MAX_TICKS} ({MAX_TICKS * SIM_STEP_SEC / 3600:.1f} sim-hours)")
    log.info("═" * 60)

    for tick in range(1, MAX_TICKS + 1):
        tick_start = time.time()

        # ── Propagate all objects forward by SIM_STEP_SEC ─────────────────────
        for obj in all_objects:
            obj.propagate(SIM_STEP_SEC)
        sim_time_sec += SIM_STEP_SEC

        current_epoch = EPOCH + timedelta(seconds=sim_time_sec)

        # ── Send telemetry to ACM ─────────────────────────────────────────────
        # We batch all objects in one request for efficiency
        telem_resp = client.send_telemetry(current_epoch, all_objects)
        if telem_resp:
            active_cdms = telem_resp.get("active_cdm_warnings", 0)
            if active_cdms > 0:
                log.warning(f"Tick {tick}: {active_cdms} active CDM warnings!")

        # ── Advance ACM simulation clock ──────────────────────────────────────
        step_resp = client.simulate_step(SIM_STEP_SEC)
        if step_resp:
            last_step_result = step_resp
            if step_resp.get("collisions_detected", 0) > 0:
                log.error(
                    f"COLLISION DETECTED at tick {tick}! "
                    f"Count: {step_resp['collisions_detected']}"
                )
            if step_resp.get("maneuvers_executed", 0) > 0:
                log.info(
                    f"Tick {tick}: {step_resp['maneuvers_executed']} maneuver(s) executed"
                )

        # ── Demo: Schedule a test maneuver every 20 ticks ────────────────────
        # This tests the /api/maneuver/schedule endpoint with real satellite IDs
        maneuver_tick_counter += 1
        if maneuver_tick_counter >= 20:
            maneuver_tick_counter = 0
            _schedule_demo_maneuver(client, satellites, current_epoch, sim_time_sec)

        # ── Fetch state for display ───────────────────────────────────────────
        snapshot = client.get_snapshot()
        health   = client.health()
        cdms_data = client.get_cdms()

        snap_sats = snapshot.get("satellites", []) if snapshot else []
        cdm_list  = cdms_data.get("active_cdms", []) if cdms_data else []

        # ── Terminal dashboard ────────────────────────────────────────────────
        print_dashboard(tick, sim_time_sec, snap_sats, cdm_list, health, last_step_result)

        # ── Log key events ────────────────────────────────────────────────────
        if tick % 10 == 0:
            _log_fleet_summary(tick, sim_time_sec, snap_sats, health)

        # ── Pacing: wait out the remaining real-time tick duration ────────────
        elapsed_real = time.time() - tick_start
        sleep_time = max(0.0, REAL_TICK_SEC - elapsed_real)
        if sleep_time > 0:
            time.sleep(sleep_time)

    log.info("═" * 60)
    log.info(f"Simulation complete after {MAX_TICKS} ticks ({MAX_TICKS * SIM_STEP_SEC / 3600:.1f} sim-hours)")
    log.info("Final health state:")
    final_health = client.health()
    if final_health:
        log.info(json.dumps(final_health, indent=2))


def _schedule_demo_maneuver(
    client: ACMClient,
    satellites: List[SimObject],
    current_epoch: datetime,
    sim_time_sec: float
):
    """
    Schedule a small test maneuver on a randomly selected satellite.
    Demonstrates the full /api/maneuver/schedule flow including:
      - Prograde evasion burn (+T direction)
      - Matching recovery burn 11 minutes later (> 600s cooldown)
    """
    import random
    sat = random.choice(satellites[:10])  # pick from first 10 sats

    # Burn times: 30s from now, recovery burn 11 min later
    burn1_time = (current_epoch + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    burn2_time = (current_epoch + timedelta(seconds=690)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Small prograde burn: 5 m/s = 0.005 km/s in transverse direction
    # (simplified: we use the y-component as a proxy for prograde here)
    burns = [
        {
            "burn_id":       f"TEST_EVA_{int(sim_time_sec)}",
            "burnTime":      burn1_time,
            "deltaV_vector": {"x": 0.001, "y": 0.004, "z": 0.001},
        },
        {
            "burn_id":       f"TEST_REC_{int(sim_time_sec)}",
            "burnTime":      burn2_time,
            "deltaV_vector": {"x": -0.001, "y": -0.004, "z": -0.001},
        },
    ]

    resp = client.schedule_maneuver(sat.obj_id, burns)
    if resp and resp.get("status") == "SCHEDULED":
        fuel_left = resp["validation"]["projected_mass_remaining_kg"]
        log.info(
            f"Demo maneuver scheduled: {sat.obj_id} | "
            f"Fuel after: {fuel_left:.2f} kg"
        )
    elif resp:
        log.warning(f"Maneuver not scheduled for {sat.obj_id}: {resp}")


def _log_fleet_summary(tick, sim_time_sec, snap_sats, health):
    """Log a compact fleet summary every 10 ticks."""
    log.info(f"─── Fleet Summary @ tick {tick} (T+{sim_time_sec/3600:.2f}h) ───")
    if health:
        log.info(
            f"  Satellites={health.get('satellites')} "
            f"Debris={health.get('debris')} "
            f"CDMs={health.get('active_cdms')} "
            f"Collisions={health.get('total_collisions')} "
            f"Maneuvers={health.get('total_maneuvers')}"
        )
    nominal = sum(1 for s in snap_sats if s.get('status') == 'NOMINAL')
    evading = sum(1 for s in snap_sats if s.get('status') == 'EVADING')
    log.info(f"  Nominal={nominal} Evading={evading} Other={len(snap_sats)-nominal-evading}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ACM Test Simulator — feeds 15 satellites to your ACM backend"
    )
    parser.add_argument(
        "--url", default=ACM_BASE_URL,
        help=f"ACM backend URL (default: {ACM_BASE_URL})"
    )
    parser.add_argument(
        "--ticks", type=int, default=MAX_TICKS,
        help=f"Number of simulation ticks to run (default: {MAX_TICKS})"
    )
    parser.add_argument(
        "--step", type=float, default=SIM_STEP_SEC,
        help=f"Simulated seconds per tick (default: {SIM_STEP_SEC})"
    )
    parser.add_argument(
        "--debris", type=int, default=N_DEBRIS,
        help=f"Number of background debris objects (default: {N_DEBRIS})"
    )
    parser.add_argument(
        "--print-input", action="store_true",
        help="Print the full initial state vectors for all 15 satellites and exit"
    )
    args = parser.parse_args()

    # ── --print-input mode: show all state vectors and exit ──────────────────
    if args.print_input:
        print(f"\n{'═'*72}")
        print("  INITIAL STATE VECTORS — 15 SATELLITES (ECI frame, J2000)")
        print(f"  Epoch: {EPOCH.isoformat()}")
        print(f"{'═'*72}")
        sats = build_15_satellites()
        for sat in sats:
            r, v = sat.state[:3], sat.state[3:]
            print(f"\n  {sat.obj_id}")
            print(f"    Position [km]: x={r[0]:>12.4f}  y={r[1]:>12.4f}  z={r[2]:>12.4f}")
            print(f"    Velocity [km/s]: vx={v[0]:>9.6f}  vy={v[1]:>9.6f}  vz={v[2]:>9.6f}")
            print(f"    |r| = {np.linalg.norm(r):.2f} km  (alt ≈ {np.linalg.norm(r)-RE:.1f} km)")
            print(f"    |v| = {np.linalg.norm(v):.4f} km/s")
        print(f"\n{'═'*72}")
        print("  TELEMETRY JSON SAMPLE (first satellite):")
        print(f"{'═'*72}")
        sample = {
            "timestamp": EPOCH.isoformat(),
            "objects": [sats[0].to_telemetry_dict(EPOCH)]
        }
        print(json.dumps(sample, indent=2))
        sys.exit(0)

    # Override defaults from args
    ACM_BASE_URL_RUNTIME = args.url
    MAX_TICKS_RUNTIME = args.ticks
    SIM_STEP_SEC_RUNTIME = args.step
    N_DEBRIS_RUNTIME = args.debris

    try:
        run_simulator()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Simulator stopped by user.{RESET}")
        log.info("Simulator interrupted by user.")
