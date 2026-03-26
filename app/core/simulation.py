"""
SIMULATION STATE MANAGER
=========================

This is the "brain" of the ACM. It holds all orbital objects in memory,
runs the physics, detects conjunctions efficiently, and executes maneuvers.

KEY DESIGN DECISIONS:

1. KD-TREE for O(N log N) conjunction search:
   Naively checking every satellite against every debris piece is O(N²).
   With 50 satellites and 10,000 debris → 500,000 checks per timestep.
   A KD-Tree partitions 3D space into a binary tree so we can query
   "all debris within X km of this satellite" in O(log N) time per query.
   Total complexity: O(N log M) where N=satellites, M=debris.

2. ASYNC TELEMETRY UPDATES:
   Telemetry arrives continuously from the simulation engine. We update
   object states immediately and re-trigger conjunction assessment only
   for affected objects (not the whole fleet) to avoid bottlenecks.

3. SCHEDULED MANEUVER QUEUE:
   Burns are stored with their target simulation time and executed during
   the simulate/step tick in chronological order. The cooldown constraint
   is enforced at scheduling time (not execution time).
"""

import numpy as np
from scipy.spatial import KDTree
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import asyncio
import csv
import os

from app.core.physics import (
    propagate, propagate_trajectory, rk4_step,
    find_closest_approach, plan_evasion_burn, plan_recovery_burn,
    rtn_to_eci, compute_fuel_consumed, validate_burn,
    eci_to_geodetic, compute_gmst, check_line_of_sight,
    graveyard_burn,
    CONJUNCTION_THRESHOLD, STATION_KEEPING_RADIUS,
    THRUSTER_COOLDOWN, MAX_DELTA_V, M_DRY, G0, ISP
)
from app.models.state import (
    SatelliteState, DebrisState, CDMWarning, GroundStation, SatelliteStatus
)
from app.core.database import get_database

logger = logging.getLogger("acm.simulation")
maneuver_logger = logging.getLogger("acm.maneuvers")
collision_logger = logging.getLogger("acm.collisions")

SIGNAL_LATENCY = 10.0  # Hardcoded 10-second signal delay


# ─── Ground Station Network (loaded from CSV, fallback to hardcoded) ─────────
def _load_ground_stations() -> List[GroundStation]:
    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ground_stations.csv")
    stations = []
    try:
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stations.append(GroundStation(
                    row["Station_ID"],
                    row["Station_Name"],
                    float(row["Latitude"]),
                    float(row["Longitude"]),
                    float(row["Elevation_m"]),
                    float(row["Min_Elevation_Angle_deg"]),
                ))
        logger.info(f"Loaded {len(stations)} ground stations from {csv_path}")
    except FileNotFoundError:
        logger.warning("ground_stations.csv not found, using hardcoded stations")
        stations = [
            GroundStation("GS-001", "ISTRAC_Bengaluru",       13.0333,  77.5167,  820, 5.0),
            GroundStation("GS-002", "Svalbard_Sat_Station",   78.2297,  15.4077,  400, 5.0),
            GroundStation("GS-003", "Goldstone_Tracking",     35.4266, -116.890, 1000, 10.0),
            GroundStation("GS-004", "Punta_Arenas",          -53.1500,  -70.917,   30, 5.0),
            GroundStation("GS-005", "IIT_Delhi_Ground_Node",  28.5450,   77.193,  225, 15.0),
            GroundStation("GS-006", "McMurdo_Station",       -77.8463,  166.668,   10, 5.0),
        ]
    return stations

GROUND_STATIONS = _load_ground_stations()


class SimulationManager:
    """
    Central simulation state and orchestration manager.

    Attributes:
        sim_time: Current simulation time in seconds from epoch
        epoch: The datetime corresponding to sim_time = 0
        satellites: Dict[id → SatelliteState]
        debris: Dict[id → DebrisState]
        active_cdms: List of active Conjunction Data Message warnings
        _debris_tree: KD-Tree over debris positions for fast spatial lookup
        _tree_dirty: Flag to rebuild KD-Tree when debris states change
    """

    def __init__(self):
        self.sim_time: float = 0.0
        self.epoch: datetime = datetime(2026, 3, 12, 8, 0, 0)
        self.satellites: Dict[str, SatelliteState] = {}
        self.debris: Dict[str, DebrisState] = {}
        self.active_cdms: List[CDMWarning] = []
        self._debris_tree: Optional[KDTree] = None
        self._debris_ids: List[str] = []  # Ordered IDs matching KD-Tree nodes
        self._tree_dirty: bool = True
        self._lock = asyncio.Lock()

        # Statistics
        self.total_collisions = 0
        self.total_maneuvers_executed = 0

        # Database
        self.db = get_database()

        # Initialize with some representative satellites if none provided
        self._initialize_default_constellation()

    def _initialize_default_constellation(self):
        """
        Seed 50 satellites in a Walker-Delta constellation pattern.

        A Walker-Delta constellation distributes satellites evenly across
        multiple orbital planes to provide global coverage. We use 5 planes
        with 10 satellites each, all at ~550 km altitude (like Starlink).

        Orbital elements to ECI conversion:
        Given semi-major axis a, inclination i, RAAN Ω, mean anomaly M:
            - r = a (circular orbit, so altitude = a - RE)
            - velocity = √(µ/a) tangential
        """
        n_planes = 5
        n_per_plane = 10
        altitude_km = 550.0
        inclination_deg = 53.0  # Moderate inclination for good coverage
        a = 6378.137 + altitude_km  # Semi-major axis [km]
        v_circ = np.sqrt(398600.4418 / a)  # Circular orbital speed [km/s]

        sat_idx = 0
        for plane in range(n_planes):
            raan = np.radians(plane * 360.0 / n_planes)  # Spread planes evenly
            inc = np.radians(inclination_deg)

            for slot in range(n_per_plane):
                ta = np.radians(slot * 360.0 / n_per_plane)  # True anomaly

                # Position in orbital plane
                r_orb = np.array([a * np.cos(ta), a * np.sin(ta), 0.0])
                v_orb = np.array([-v_circ * np.sin(ta), v_circ * np.cos(ta), 0.0])

                # Rotate by inclination (about X axis)
                Rx = np.array([
                    [1, 0, 0],
                    [0, np.cos(inc), -np.sin(inc)],
                    [0, np.sin(inc),  np.cos(inc)]
                ])
                # Rotate by RAAN (about Z axis)
                Rz = np.array([
                    [np.cos(raan), -np.sin(raan), 0],
                    [np.sin(raan),  np.cos(raan), 0],
                    [0, 0, 1]
                ])
                R = Rz @ Rx
                r_eci = R @ r_orb
                v_eci = R @ v_orb

                state = np.concatenate([r_eci, v_eci])
                sat_id = f"SAT-P{plane+1}-{slot+1:02d}"
                sat = SatelliteState(sat_id, state)
                self.satellites[sat_id] = sat
                sat_idx += 1

        logger.info(f"Initialized {len(self.satellites)} satellites in Walker-Delta constellation")

    # ─── KD-Tree Management ───────────────────────────────────────────────────

    def _rebuild_debris_tree(self):
        """
        Rebuild the KD-Tree from current debris positions.

        A KD-Tree is a binary space-partitioning tree. Each node splits
        the debris cloud along the axis with highest variance, alternating
        through x, y, z. Querying "all points within radius R" runs in
        O(log N + k) where k is the number of results returned.

        We rebuild on demand (lazy) rather than every timestep — the tree
        is flagged dirty when telemetry updates arrive and rebuilt once
        before the next conjunction scan.
        """
        if not self.debris:
            self._debris_tree = None
            self._debris_ids = []
            return

        self._debris_ids = list(self.debris.keys())
        positions = np.array([self.debris[d].state[:3] for d in self._debris_ids])
        self._debris_tree = KDTree(positions)
        self._tree_dirty = False
        logger.debug(f"KD-Tree rebuilt with {len(self._debris_ids)} debris objects")

    def _get_nearby_debris(
        self, sat_position: np.ndarray, search_radius_km: float = 500.0
    ) -> List[str]:
        """
        Find all debris within search_radius_km of a satellite position.

        The 500km search radius is conservative — we only need to run
        detailed TCA analysis on debris that could plausibly reach the
        satellite within 24 hours. At 7-8 km/s relative velocity, the
        maximum travel distance in 24h is ~648,000 km, but we filter
        coarsely at 500 km and rely on TCA calculation for accuracy.

        Returns:
            List of debris IDs within search radius
        """
        if self._tree_dirty:
            self._rebuild_debris_tree()

        if self._debris_tree is None:
            return []

        indices = self._debris_tree.query_ball_point(sat_position, search_radius_km)
        return [self._debris_ids[i] for i in indices]

    # ─── Telemetry Ingestion ──────────────────────────────────────────────────

    async def ingest_telemetry(self, timestamp: datetime, objects: list) -> int:
        """
        Process incoming telemetry updates for satellites and debris.

        We update each object's state vector from the received telemetry.
        This replaces our propagated estimate with the ground truth from
        the simulation engine, correcting any integration drift.

        After updating debris positions, we flag the KD-Tree as dirty
        so it gets rebuilt on the next conjunction scan.
        """
        processed = 0
        debris_updated = False

        async with self._lock:
            for obj in objects:
                state_vec = np.array([
                    obj.r.x, obj.r.y, obj.r.z,
                    obj.v.x, obj.v.y, obj.v.z
                ])

                if obj.type == "SATELLITE":
                    if obj.id in self.satellites:
                        self.satellites[obj.id].state = state_vec
                    else:
                        # New satellite — add it
                        self.satellites[obj.id] = SatelliteState(obj.id, state_vec)
                else:  # DEBRIS
                    if obj.id in self.debris:
                        self.debris[obj.id].state = state_vec
                    else:
                        self.debris[obj.id] = DebrisState(obj.id, state_vec)
                    debris_updated = True

                processed += 1

            if debris_updated:
                self._tree_dirty = True

        return processed

    # ─── Conjunction Assessment ───────────────────────────────────────────────

    async def run_conjunction_assessment(self, horizon_s: float = 86400.0):
        """
        Scan for conjunctions between all satellites and nearby debris.

        Algorithm:
        1. For each satellite, use KD-Tree to find debris within 500 km
        2. For each nearby debris, run TCA calculation (two-pass coarse/fine)
        3. If predicted miss distance < 100m → issue CDM and plan evasion
        4. Deduplicate against existing CDMs to avoid re-issuing

        The combination of KD-Tree filtering + TCA calculation gives us
        O(N log M + N * k * T) complexity where:
        - N = number of satellites (50)
        - M = number of debris (10,000)
        - k = average nearby debris per satellite (usually <100 after KD filter)
        - T = TCA computation cost (roughly constant)

        This is vastly better than O(N * M * T) brute force.
        """
        if self._tree_dirty:
            self._rebuild_debris_tree()

        new_cdms = []
        existing_pairs = {(c.sat_id, c.deb_id) for c in self.active_cdms}

        for sat_id, sat in self.satellites.items():
            if sat.status == SatelliteStatus.DEAD:
                continue

            # KD-Tree query: debris within 500 km
            nearby_ids = self._get_nearby_debris(sat.state[:3], search_radius_km=500.0)

            for deb_id in nearby_ids:
                if (sat_id, deb_id) in existing_pairs:
                    continue  # Already tracking this conjunction

                deb = self.debris[deb_id]
                tca_s, miss_dist = find_closest_approach(
                    sat.state, deb.state, horizon_s=horizon_s
                )

                if miss_dist < CONJUNCTION_THRESHOLD:
                    cdm = CDMWarning(sat_id, deb_id, self.sim_time + tca_s, miss_dist)
                    new_cdms.append(cdm)
                    logger.warning(
                        f"CDM: {sat_id} ↔ {deb_id} | TCA in {tca_s/60:.1f}min | "
                        f"Miss dist: {miss_dist*1000:.1f}m"
                    )
                    self.db.log_cdm(
                        self.sim_time, sat_id, deb_id,
                        self.sim_time + tca_s, miss_dist * 1000,
                        miss_dist < CONJUNCTION_THRESHOLD
                    )

        async with self._lock:
            # Purge expired CDMs (TCA in the past)
            self.active_cdms = [
                c for c in self.active_cdms
                if c.tca_sim_time > self.sim_time
            ]
            self.active_cdms.extend(new_cdms)

        # Auto-schedule evasion maneuvers for new critical CDMs
        for cdm in new_cdms:
            if cdm.is_critical and not cdm.evasion_scheduled:
                await self._auto_schedule_evasion(cdm)

        return len(self.active_cdms)

    # ─── Autonomous Maneuver Planning ─────────────────────────────────────────

    async def _auto_schedule_evasion(self, cdm: CDMWarning):
        """
        Autonomously plan and schedule an evasion + recovery maneuver pair.

        Timing:
        - Evasion burn: Schedule as early as possible (now + 10s for signal
          latency + any remaining cooldown)
        - Recovery burn: Schedule after the TCA has passed + cooldown

        The two burns are submitted as a sequence to the maneuver queue so
        the satellite automatically returns to its nominal slot.
        """
        sat = self.satellites.get(cdm.sat_id)
        if not sat or sat.is_eol:
            return

        # Check if satellite has LOS to any ground station
        gmst = compute_gmst(self.sim_time)
        has_los = any(
            check_line_of_sight(
                sat.state[:3], gs.lat, gs.lon, gs.alt_m, gs.min_elev_deg, gmst
            )
            for gs in GROUND_STATIONS
        )

        if not has_los:
            logger.warning(
                f"Cannot schedule evasion for {cdm.sat_id}: no ground station LOS"
            )
            return

        # Signal latency: 10 seconds minimum before burn can execute
        SIGNAL_LATENCY = 10.0

        # Cooldown constraint: respect 600s between burns
        cooldown_remaining = 0.0
        if sat.last_burn_time is not None:
            elapsed_since_burn = self.sim_time - sat.last_burn_time
            cooldown_remaining = max(0.0, THRUSTER_COOLDOWN - elapsed_since_burn)

        burn1_time = self.sim_time + SIGNAL_LATENCY + cooldown_remaining

        # Time until TCA
        tca_seconds = cdm.tca_sim_time - self.sim_time

        # Plan evasion ΔV in RTN frame
        dv_rtn = plan_evasion_burn(sat.state, tca_seconds, cdm.miss_distance_km)
        dv_eci = rtn_to_eci(dv_rtn, sat.state[:3], sat.state[3:])

        # Validate the burn
        is_valid, reason = validate_burn(dv_eci, sat.m_fuel, sat.m_dry)
        if not is_valid:
            logger.error(f"Evasion burn invalid for {cdm.sat_id}: {reason}")
            return

        # Plan recovery burn (after TCA + cooldown)
        burn2_time = cdm.tca_sim_time + THRUSTER_COOLDOWN + 60.0
        dv_recovery = plan_recovery_burn(
            propagate(sat.state, burn2_time - self.sim_time),
            propagate(sat.nominal_state, burn2_time - self.sim_time)
        )

        # Schedule both burns
        async with self._lock:
            sat.scheduled_burns.append({
                "burn_id": f"EVASION_{cdm.deb_id}",
                "burn_time": burn1_time,
                "dv_eci": dv_eci,
                "type": "EVASION"
            })
            sat.scheduled_burns.append({
                "burn_id": f"RECOVERY_{cdm.deb_id}",
                "burn_time": burn2_time,
                "dv_eci": dv_recovery,
                "type": "RECOVERY"
            })
            sat.status = SatelliteStatus.EVADING
            cdm.evasion_scheduled = True

        logger.info(
            f"Evasion scheduled for {cdm.sat_id}: "
            f"burn1 at T+{burn1_time - self.sim_time:.0f}s, "
            f"ΔV={np.linalg.norm(dv_eci)*1000:.2f} m/s"
        )

    async def schedule_maneuver(
        self, sat_id: str, burn_sequence: list
    ) -> Tuple[bool, float]:
        """
        Validate and schedule a maneuver sequence submitted via the API.

        Validation checks:
        1. Satellite exists and is controllable
        2. Each burn: ΔV within limits, sufficient fuel, LOS to ground station
        3. Cooldown: 600s between consecutive burns on same satellite

        Returns:
            (success, projected_mass_remaining_kg)
        """
        sat = self.satellites.get(sat_id)
        if not sat:
            return False, 0.0

        gmst = compute_gmst(self.sim_time)
        has_los = any(
            check_line_of_sight(
                sat.state[:3], gs.lat, gs.lon, gs.alt_m, gs.min_elev_deg, gmst
            )
            for gs in GROUND_STATIONS
        )

        # Simulate fuel usage across the sequence
        m_remaining = sat.m_total
        last_burn_time = sat.last_burn_time or (self.sim_time - THRUSTER_COOLDOWN)

        for burn in burn_sequence:
            # Parse burn time (convert to sim_time seconds)
            burn_epoch = (burn.burnTime - self.epoch).total_seconds()

            # Signal delay check: burn must be at least 10s in the future
            if burn_epoch < self.sim_time + SIGNAL_LATENCY:
                logger.warning(f"Burn {burn.burn_id} violates 10s signal delay constraint")
                return False, m_remaining

            # Cooldown check
            if burn_epoch - last_burn_time < THRUSTER_COOLDOWN:
                logger.warning(f"Burn {burn.burn_id} violates cooldown constraint")
                return False, m_remaining

            dv_vec = burn.deltaV_vector.to_numpy()
            is_valid, reason = validate_burn(dv_vec, m_remaining - M_DRY, M_DRY)
            if not is_valid:
                logger.warning(f"Burn {burn.burn_id} invalid: {reason}")
                return False, m_remaining

            # Deduct fuel for this burn
            dv_mag = np.linalg.norm(dv_vec)
            fuel_used = compute_fuel_consumed(m_remaining, dv_mag)
            m_remaining -= fuel_used
            last_burn_time = burn_epoch

        # All valid — add to queue
        async with self._lock:
            for burn in burn_sequence:
                burn_epoch = (burn.burnTime - self.epoch).total_seconds()
                dv_vec = burn.deltaV_vector.to_numpy()
                sat.scheduled_burns.append({
                    "burn_id": burn.burn_id,
                    "burn_time": burn_epoch,
                    "dv_eci": dv_vec,
                    "type": "MANUAL"
                })
            # Sort by execution time
            sat.scheduled_burns.sort(key=lambda b: b["burn_time"])

        return has_los, m_remaining

    # ─── Simulation Step (Tick) ───────────────────────────────────────────────

    async def step(self, step_seconds: float) -> Tuple[int, int]:
        """
        Advance the simulation by step_seconds.

        During each tick:
        1. For each object, integrate the orbit forward using RK4
        2. Execute any scheduled burns that fall within this time window
        3. Check for actual collisions (miss distance < 100m at current time)
        4. Update station-keeping status and log outages
        5. Trigger EOL graveyard maneuvers for fuel-critical satellites
        6. Run conjunction assessment for the next 24 hours

        Args:
            step_seconds: How far to advance simulation time

        Returns:
            (collisions_detected, maneuvers_executed)
        """
        collisions = 0
        maneuvers = 0
        end_time = self.sim_time + step_seconds

        # Sub-step size: use 30s integration steps within the tick
        SUB_STEP = 30.0
        t = self.sim_time

        while t < end_time:
            dt = min(SUB_STEP, end_time - t)

            async with self._lock:
                # --- Propagate all debris ---
                for deb in self.debris.values():
                    deb.state = rk4_step(deb.state, dt)

                # --- Propagate all satellites and execute burns ---
                for sat_id, sat in self.satellites.items():
                    if sat.status == SatelliteStatus.DEAD:
                        continue

                    # Execute burns scheduled within [t, t+dt]
                    burns_this_step = [
                        b for b in sat.scheduled_burns
                        if t <= b["burn_time"] < t + dt
                    ]
                    burns_this_step.sort(key=lambda b: b["burn_time"])

                    for burn in burns_this_step:
                        # Propagate to exact burn time
                        dt_to_burn = burn["burn_time"] - t
                        if dt_to_burn > 0:
                            sat.state = propagate(sat.state, dt_to_burn)

                        dv = burn["dv_eci"]
                        dv_mag = np.linalg.norm(dv)
                        fuel_consumed = compute_fuel_consumed(sat.m_total, dv_mag)

                        # Apply ΔV (instantaneous burn)
                        sat.state[3:] += dv
                        sat.m_fuel -= fuel_consumed
                        sat.last_burn_time = burn["burn_time"]
                        sat.scheduled_burns.remove(burn)
                        maneuvers += 1

                        logger.info(
                            f"Burn executed: {sat_id} | "
                            f"ΔV={dv_mag*1000:.3f} m/s | "
                            f"Fuel remaining: {sat.m_fuel:.2f} kg"
                        )
                        maneuver_logger.info(
                            f"BURN | sat={sat_id} | burn_id={burn['burn_id']} | "
                            f"type={burn['type']} | dv_ms={dv_mag*1000:.4f} | "
                            f"fuel_used_kg={fuel_consumed:.4f} | fuel_remaining_kg={sat.m_fuel:.4f} | "
                            f"sim_time={burn['burn_time']:.1f}"
                        )
                        self.db.log_maneuver(
                            burn["burn_time"], sat_id, burn["burn_id"],
                            burn["type"], dv_mag * 1000, fuel_consumed, sat.m_fuel
                        )

                        if burn["type"] == "RECOVERY":
                            sat.status = SatelliteStatus.NOMINAL

                    # Propagate satellite for full dt
                    sat.state = rk4_step(sat.state, dt)
                    sat.nominal_state = rk4_step(sat.nominal_state, dt)

                    # --- Station-keeping check ---
                    slot_error = np.linalg.norm(sat.state[:3] - sat.nominal_state[:3])
                    if slot_error > STATION_KEEPING_RADIUS:
                        sat.status = SatelliteStatus.RECOVERING
                        sat.outage_seconds += dt

                    # --- Collision detection ---
                    for deb in self.debris.values():
                        dist = np.linalg.norm(sat.state[:3] - deb.state[:3])
                        if dist < CONJUNCTION_THRESHOLD:
                            collisions += 1
                            sat.collision_count += 1
                            logger.error(
                                f"COLLISION: {sat_id} ↔ {deb.id} | "
                                f"Distance: {dist*1000:.1f}m"
                            )
                            collision_logger.info(
                                f"COLLISION | sat={sat_id} | debris={deb.id} | "
                                f"dist_m={dist*1000:.2f} | sim_time={t:.1f}"
                            )
                            self.db.log_collision(t, sat_id, deb.id, dist * 1000)

                    # --- EOL graveyard check ---
                    if sat.is_eol and sat.status != SatelliteStatus.EOL:
                        sat.status = SatelliteStatus.EOL
                        dv_rtn = graveyard_burn(sat.state)
                        dv_eci = rtn_to_eci(dv_rtn, sat.state[:3], sat.state[3:])
                        burn_time = t + dt + 10.0  # 10s signal latency
                        sat.scheduled_burns.append({
                            "burn_id": f"GRAVEYARD_{sat_id}",
                            "burn_time": burn_time,
                            "dv_eci": dv_eci,
                            "type": "EOL"
                        })
                        logger.warning(f"EOL triggered for {sat_id}: fuel critical")

            t += dt

        self.sim_time = end_time
        self.total_collisions += collisions
        self.total_maneuvers_executed += maneuvers

        # Flag KD-Tree dirty (debris positions changed)
        self._tree_dirty = True

        # Run conjunction assessment for next 24 hours
        await self.run_conjunction_assessment()

        # Log snapshot to DB
        avg_fuel = sum(s.m_fuel for s in self.satellites.values()) / max(len(self.satellites), 1)
        self.db.log_snapshot(
            self.sim_time, len(self.satellites), len(self.debris),
            self.total_collisions, self.total_maneuvers_executed, avg_fuel
        )

        return collisions, maneuvers

    # ─── Visualization Snapshot ───────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """
        Generate the optimized visualization snapshot.

        For performance, the debris cloud uses a compact tuple format:
        [id, lat, lon, alt_km] — this dramatically reduces JSON payload size
        compared to nested objects.

        GMST is computed from elapsed simulation time to correctly convert
        ECI → lat/lon as Earth rotates.
        """
        gmst = compute_gmst(self.sim_time)

        satellites_out = []
        for sat_id, sat in self.satellites.items():
            lat, lon, alt = eci_to_geodetic(sat.state[:3], gmst)
            satellites_out.append({
                "id": sat_id,
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "fuel_kg": round(sat.m_fuel, 3),
                "status": sat.status.value
            })

        debris_out = []
        for deb_id, deb in self.debris.items():
            lat, lon, alt = eci_to_geodetic(deb.state[:3], gmst)
            debris_out.append([deb_id, round(lat, 3), round(lon, 3), round(alt, 1)])

        current_dt = self.epoch + timedelta(seconds=self.sim_time)

        return {
            "timestamp": current_dt.isoformat() + "Z",
            "sim_time_s": self.sim_time,
            "satellites": satellites_out,
            "debris_cloud": debris_out
        }


# ─── Singleton instance ───────────────────────────────────────────────────────
_sim_manager: Optional[SimulationManager] = None


def get_sim_manager() -> SimulationManager:
    """FastAPI dependency injection: get or create the singleton SimulationManager."""
    global _sim_manager
    if _sim_manager is None:
        _sim_manager = SimulationManager()
    return _sim_manager
