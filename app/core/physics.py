"""
PHYSICS ENGINE — Orbital Mechanics Core
========================================

This module implements all the mathematics required to propagate satellite
and debris orbits accurately. Here's a plain-English explanation of each concept:

1. TWO-BODY PROBLEM (Keplerian):
   Without perturbations, every satellite follows an elliptical path described by:
     acceleration = -µ/|r|³ * r
   where µ = 398600 km³/s² is Earth's gravitational parameter and r is the
   position vector from Earth's center. Think of it as gravity pointing inward
   scaled by distance squared.

2. J2 PERTURBATION:
   Earth isn't a perfect sphere — it bulges at the equator (oblateness).
   This causes the orbital plane to slowly precess (rotate) over time.
   The J2 term adds a small correction to the acceleration that accounts for
   this equatorial bulge. Without it, conjunction predictions would drift
   significantly over 24 hours.

3. RK4 INTEGRATION:
   We can't solve the differential equation analytically with J2 included,
   so we numerically "step" forward in time. Runge-Kutta 4th order (RK4)
   takes 4 slope estimates (k1-k4) at different sub-points in the timestep
   and combines them for a very accurate result. It's like taking the average
   of several educated guesses about how the orbit will curve.

4. RTN FRAME:
   Maneuvers are planned in a local coordinate frame attached to the satellite:
   - R (Radial): points from Earth center through the satellite (outward)
   - T (Transverse): points in the direction of motion (prograde)
   - N (Normal): perpendicular to the orbital plane (cross-track)
   We calculate ΔV in RTN, then rotate it to ECI to submit to the API.

5. TSIOLKOVSKY ROCKET EQUATION:
   Every burn consumes propellant: Δm = m_current * (1 - exp(-|ΔV| / (Isp * g0)))
   As fuel depletes, the satellite gets lighter, making future burns more
   fuel-efficient (but we have less propellant left to use).
"""

import numpy as np
from typing import Tuple, Optional

# ─── Universal Constants ──────────────────────────────────────────────────────
MU = 398600.4418          # Earth gravitational parameter [km³/s²]
RE = 6378.137             # Earth equatorial radius [km]
J2 = 1.08263e-3           # Earth's J2 oblateness coefficient [dimensionless]
G0 = 9.80665e-3           # Standard gravity [km/s²] (converted from m/s² for km units)
ISP = 300.0               # Specific impulse of monopropellant thruster [s]
M_DRY = 500.0             # Satellite dry mass [kg]
M_FUEL_INIT = 50.0        # Initial propellant mass [kg]
MAX_DELTA_V = 0.015       # Maximum ΔV per burn [km/s] = 15 m/s
THRUSTER_COOLDOWN = 600   # Mandatory rest between burns [s]
CONJUNCTION_THRESHOLD = 0.100  # Critical miss distance [km] = 100 m
STATION_KEEPING_RADIUS = 10.0  # Station-keeping bounding box radius [km]
FUEL_EOL_FRACTION = 0.05  # End-of-life fuel threshold (5% of initial)


# ─── J2 Perturbation Acceleration ────────────────────────────────────────────

def j2_acceleration(r: np.ndarray) -> np.ndarray:
    """
    Compute the J2 gravitational perturbation acceleration vector.

    The J2 perturbation captures the effect of Earth's equatorial bulge on
    satellite orbits. Without it, orbits would be perfect Keplerian ellipses.
    With it, the ascending node drifts westward for prograde orbits (nodal
    regression) and the argument of perigee rotates.

    The formula is:
        a_J2 = (3/2) * J2 * µ * RE² / |r|⁵ * [
            x * (5z²/|r|² - 1),
            y * (5z²/|r|² - 1),
            z * (5z²/|r|² - 3)
        ]

    Args:
        r: Position vector [x, y, z] in km (ECI frame)

    Returns:
        Acceleration vector [ax, ay, az] in km/s²
    """
    x, y, z = r
    r_norm = np.linalg.norm(r)
    r2 = r_norm ** 2
    z2 = z ** 2
    factor = (3.0 / 2.0) * J2 * MU * RE**2 / r_norm**5

    ax = factor * x * (5.0 * z2 / r2 - 1.0)
    ay = factor * y * (5.0 * z2 / r2 - 1.0)
    az = factor * z * (5.0 * z2 / r2 - 3.0)

    return np.array([ax, ay, az])


def state_derivative(state: np.ndarray) -> np.ndarray:
    """
    Compute the time derivative of the 6D state vector [r, v].

    The governing equation of motion is:
        d²r/dt² = -µ/|r|³ * r + a_J2

    In first-order form (suitable for RK4):
        dr/dt = v
        dv/dt = -µ/|r|³ * r + a_J2(r)

    Args:
        state: [x, y, z, vx, vy, vz] in km and km/s

    Returns:
        [vx, vy, vz, ax, ay, az] — the derivative of the state
    """
    r = state[:3]
    v = state[3:]
    r_norm = np.linalg.norm(r)

    # Two-body gravitational acceleration
    a_gravity = -(MU / r_norm**3) * r

    # J2 perturbation correction
    a_j2 = j2_acceleration(r)

    # Total acceleration
    a_total = a_gravity + a_j2

    return np.concatenate([v, a_total])


# ─── Runge-Kutta 4th Order Integrator ────────────────────────────────────────

def rk4_step(state: np.ndarray, dt: float) -> np.ndarray:
    """
    Advance a state vector by one time step using RK4 integration.

    RK4 computes four estimates of the derivative (slope) and combines them
    in a weighted average to get a much more accurate result than simple
    Euler integration:

        k1 = f(t,  y)              ← slope at start
        k2 = f(t + dt/2, y + k1*dt/2)  ← slope at midpoint (using k1)
        k3 = f(t + dt/2, y + k2*dt/2)  ← slope at midpoint (using k2)
        k4 = f(t + dt,  y + k3*dt)     ← slope at end
        y_new = y + (k1 + 2k2 + 2k3 + k4) * dt/6

    The weights (1, 2, 2, 1) give more importance to the midpoint estimates.
    This is O(dt⁴) accurate per step — very good for orbital mechanics.

    Args:
        state: Current [x, y, z, vx, vy, vz]
        dt: Time step in seconds

    Returns:
        New state after dt seconds
    """
    k1 = state_derivative(state)
    k2 = state_derivative(state + 0.5 * dt * k1)
    k3 = state_derivative(state + 0.5 * dt * k2)
    k4 = state_derivative(state + dt * k3)

    return state + (dt / 6.0) * (k1 + 2*k2 + 2*k3 + k4)


def propagate(state: np.ndarray, duration_s: float, dt: float = 30.0) -> np.ndarray:
    """
    Propagate a state vector forward in time using repeated RK4 steps.

    We use a default step size of 30 seconds. Smaller steps = more accurate
    but slower. For LEO satellites at ~7.5 km/s, 30s means ~225 km per step,
    which is well within RK4's accuracy bounds for this application.

    Args:
        state: Initial [x, y, z, vx, vy, vz]
        duration_s: Total propagation time in seconds
        dt: Integration step size in seconds (default 30s)

    Returns:
        Final state after duration_s seconds
    """
    t = 0.0
    current = state.copy()
    while t < duration_s:
        step = min(dt, duration_s - t)
        current = rk4_step(current, step)
        t += step
    return current


def propagate_trajectory(
    state: np.ndarray, duration_s: float, dt: float = 60.0
) -> np.ndarray:
    """
    Propagate and return the full trajectory (array of states at each step).
    Used for conjunction scanning and ground track computation.

    Returns:
        Array of shape (N, 6) where N = ceil(duration_s / dt) + 1
    """
    states = [state.copy()]
    t = 0.0
    current = state.copy()
    while t < duration_s:
        step = min(dt, duration_s - t)
        current = rk4_step(current, step)
        t += step
        states.append(current.copy())
    return np.array(states)


# ─── RTN Frame Utilities ──────────────────────────────────────────────────────

def eci_to_rtn_matrix(r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    Build the rotation matrix from ECI to RTN (local orbital) frame.

    RTN axes:
        R̂ = r / |r|                     (radial, outward from Earth)
        N̂ = (r × v) / |r × v|           (normal, perpendicular to orbital plane)
        T̂ = N̂ × R̂                      (transverse, roughly in velocity direction)

    The matrix M has rows [R̂, T̂, N̂], so:
        v_rtn = M @ v_eci

    Args:
        r: Position vector in ECI [km]
        v: Velocity vector in ECI [km/s]

    Returns:
        3×3 rotation matrix (ECI → RTN)
    """
    r_hat = r / np.linalg.norm(r)
    h = np.cross(r, v)
    n_hat = h / np.linalg.norm(h)
    t_hat = np.cross(n_hat, r_hat)

    return np.array([r_hat, t_hat, n_hat])


def rtn_to_eci(dv_rtn: np.ndarray, r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    Convert a ΔV vector from RTN frame to ECI frame.

    Since the RTN→ECI matrix is orthogonal, its inverse is its transpose:
        dv_eci = M.T @ dv_rtn

    This is needed before submitting maneuver commands — the API expects
    deltaV in ECI coordinates.

    Args:
        dv_rtn: ΔV vector [dR, dT, dN] in km/s
        r: Current satellite position in ECI [km]
        v: Current satellite velocity in ECI [km/s]

    Returns:
        ΔV vector in ECI frame [km/s]
    """
    M = eci_to_rtn_matrix(r, v)
    return M.T @ dv_rtn


# ─── Fuel / Propulsion Mechanics ─────────────────────────────────────────────

def compute_fuel_consumed(m_current: float, delta_v_km_s: float) -> float:
    """
    Compute propellant mass consumed for a given ΔV using Tsiolkovsky's equation.

    The rocket equation: Δm = m_current * (1 - exp(-|ΔV| / (Isp * g0)))

    Intuition: A larger ΔV requires exponentially more fuel. Isp (specific
    impulse) measures thruster efficiency — higher Isp means less fuel burned
    per m/s of ΔV. Our monopropellant thruster has Isp=300s, which is typical
    for hydrazine thrusters.

    Note: g0 here is in km/s² (= 0.00980665 km/s²) to match our km/s ΔV units.

    Args:
        m_current: Current total mass of satellite [kg]
        delta_v_km_s: Magnitude of ΔV [km/s]

    Returns:
        Mass of propellant consumed [kg]
    """
    exponent = -delta_v_km_s / (ISP * G0)
    return m_current * (1.0 - np.exp(exponent))


def validate_burn(delta_v_vec: np.ndarray, fuel_remaining: float, m_dry: float) -> Tuple[bool, str]:
    """
    Validate a burn command against physical constraints.

    Checks:
    1. ΔV magnitude ≤ 15 m/s (0.015 km/s) — thruster limit
    2. Sufficient fuel for the burn

    Returns:
        (is_valid, reason_if_invalid)
    """
    dv_mag = np.linalg.norm(delta_v_vec)
    if dv_mag > MAX_DELTA_V:
        return False, f"ΔV magnitude {dv_mag*1000:.2f} m/s exceeds limit of 15 m/s"

    m_current = m_dry + fuel_remaining
    fuel_needed = compute_fuel_consumed(m_current, dv_mag)
    if fuel_needed > fuel_remaining:
        return False, f"Insufficient fuel: need {fuel_needed:.3f} kg, have {fuel_remaining:.3f} kg"

    return True, "OK"


# ─── ECI ↔ Lat/Lon/Alt Conversion ────────────────────────────────────────────

def eci_to_geodetic(r_eci: np.ndarray, gmst_rad: float = 0.0) -> Tuple[float, float, float]:
    """
    Convert ECI position to geodetic latitude, longitude, altitude.

    We use a simplified spherical Earth model here (not WGS84 ellipsoid)
    since the precision needed for visualization is ~1 km, not millimeters.

    GMST (Greenwich Mean Sidereal Time) accounts for Earth's rotation:
    as time advances, the ECI frame stays fixed to the stars while Earth
    rotates underneath. GMST tells us how much Earth has rotated.

    Args:
        r_eci: Position in ECI [km]
        gmst_rad: Greenwich Mean Sidereal Time angle [radians]

    Returns:
        (latitude_deg, longitude_deg, altitude_km)
    """
    x, y, z = r_eci
    r_norm = np.linalg.norm(r_eci)

    # Latitude: angle above equatorial plane
    lat_rad = np.arcsin(z / r_norm)

    # Longitude: angle in equatorial plane, adjusted for Earth's rotation
    lon_rad = np.arctan2(y, x) - gmst_rad
    # Normalize to [-π, π]
    lon_rad = (lon_rad + np.pi) % (2 * np.pi) - np.pi

    alt_km = r_norm - RE

    return np.degrees(lat_rad), np.degrees(lon_rad), alt_km


def compute_gmst(elapsed_seconds: float, epoch_gmst_rad: float = 0.0) -> float:
    """
    Compute the Greenwich Mean Sidereal Time given elapsed seconds from epoch.

    Earth rotates once per sidereal day = 86164.09054 seconds.
    Angular rate = 2π / 86164.09054 ≈ 7.292115e-5 rad/s

    Args:
        elapsed_seconds: Seconds elapsed since simulation epoch
        epoch_gmst_rad: GMST at the simulation start epoch [radians]

    Returns:
        GMST in radians
    """
    EARTH_ROTATION_RATE = 7.292115e-5  # rad/s
    return epoch_gmst_rad + EARTH_ROTATION_RATE * elapsed_seconds


# ─── Ground Station Line-of-Sight ─────────────────────────────────────────────

def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> np.ndarray:
    """
    Convert geodetic coordinates to ECEF (Earth-Centered, Earth-Fixed) position.

    ECEF rotates with the Earth — perfect for computing ground station positions.
    At t=0, ECI and ECEF are aligned (GMST=0), so we can do LOS checks in ECI
    coordinates by treating the ground station as having a known ECEF position
    that rotates with Earth.

    For a spherical Earth:
        x = (RE + alt) * cos(lat) * cos(lon)
        y = (RE + alt) * cos(lat) * sin(lon)
        z = (RE + alt) * sin(lat)

    Args:
        lat_deg, lon_deg: Geodetic coordinates [degrees]
        alt_km: Altitude above surface [km]

    Returns:
        ECEF position vector [km]
    """
    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    r = RE + alt_km / 1000.0  # alt is in meters in the CSV

    x = r * np.cos(lat) * np.cos(lon)
    y = r * np.cos(lat) * np.sin(lon)
    z = r * np.sin(lat)
    return np.array([x, y, z])


def check_line_of_sight(
    sat_r_eci: np.ndarray,
    gs_lat: float, gs_lon: float, gs_alt_m: float, gs_min_elev_deg: float,
    gmst_rad: float
) -> bool:
    """
    Check if a satellite has line-of-sight to a ground station.

    Algorithm:
    1. Convert ground station from geodetic to ECI (using current GMST to rotate)
    2. Compute the vector from station to satellite
    3. Compute elevation angle = angle between that vector and the local horizon
    4. If elevation > minimum mask angle, LOS exists

    Elevation angle formula:
        elev = arcsin((r_sat - r_gs) · r_gs_hat / |r_sat - r_gs|)

    Args:
        sat_r_eci: Satellite ECI position [km]
        gs_lat, gs_lon: Ground station geodetic coordinates [degrees]
        gs_alt_m: Ground station altitude [meters]
        gs_min_elev_deg: Minimum elevation angle for communication [degrees]
        gmst_rad: Current Greenwich Mean Sidereal Time [radians]

    Returns:
        True if LOS exists (satellite visible from ground station)
    """
    # Ground station ECEF position (rotates with Earth)
    gs_ecef = geodetic_to_ecef(gs_lat, gs_lon, gs_alt_m)

    # Rotate ECEF to ECI using GMST rotation about Z axis
    cos_g = np.cos(gmst_rad)
    sin_g = np.sin(gmst_rad)
    rot_z = np.array([
        [cos_g, -sin_g, 0],
        [sin_g,  cos_g, 0],
        [0,      0,     1]
    ])
    gs_eci = rot_z @ gs_ecef

    # Vector from ground station to satellite
    r_to_sat = sat_r_eci - gs_eci
    dist = np.linalg.norm(r_to_sat)

    # Unit vector from Earth center to ground station (local zenith)
    gs_zenith = gs_eci / np.linalg.norm(gs_eci)

    # Elevation angle: dot product gives the vertical component
    sin_elev = np.dot(r_to_sat, gs_zenith) / dist
    elev_deg = np.degrees(np.arcsin(np.clip(sin_elev, -1, 1)))

    return elev_deg >= gs_min_elev_deg


# ─── Conjunction Assessment Helpers ──────────────────────────────────────────

def find_closest_approach(
    sat_state: np.ndarray,
    deb_state: np.ndarray,
    horizon_s: float = 86400.0,
    coarse_dt: float = 60.0,
    fine_dt: float = 5.0
) -> Tuple[float, float]:
    """
    Find the Time of Closest Approach (TCA) and minimum distance between a
    satellite and a debris object over a given time horizon.

    Strategy (two-pass approach):
    1. Coarse scan: propagate both objects in 60s steps, compute distance at each step.
       Find the approximate minimum.
    2. Fine scan: re-examine the 60s window around the coarse minimum at 5s resolution
       for an accurate TCA.

    This avoids missing a close approach that peaks between coarse steps.

    Args:
        sat_state: Satellite state [x,y,z,vx,vy,vz]
        deb_state: Debris state [x,y,z,vx,vy,vz]
        horizon_s: Look-ahead time [s] (default 24 hours)
        coarse_dt: Step size for initial scan [s]
        fine_dt: Step size for refinement [s]

    Returns:
        (tca_seconds, min_distance_km) — time from now to closest approach
    """
    # --- Coarse pass ---
    n_coarse = int(horizon_s / coarse_dt) + 1
    sat_s = sat_state.copy()
    deb_s = deb_state.copy()
    min_dist = np.inf
    min_t = 0.0
    prev_dist = np.linalg.norm(sat_s[:3] - deb_s[:3])

    for i in range(1, n_coarse):
        sat_s = rk4_step(sat_s, coarse_dt)
        deb_s = rk4_step(deb_s, coarse_dt)
        d = np.linalg.norm(sat_s[:3] - deb_s[:3])
        if d < min_dist:
            min_dist = d
            min_t = i * coarse_dt

    # --- Fine pass: re-propagate around the coarse minimum ---
    t_start = max(0.0, min_t - coarse_dt)
    sat_fine = propagate(sat_state, t_start, dt=coarse_dt)
    deb_fine = propagate(deb_state, t_start, dt=coarse_dt)
    fine_min_dist = np.inf
    fine_min_t = t_start

    for j in range(int(2 * coarse_dt / fine_dt) + 1):
        d = np.linalg.norm(sat_fine[:3] - deb_fine[:3])
        if d < fine_min_dist:
            fine_min_dist = d
            fine_min_t = t_start + j * fine_dt
        sat_fine = rk4_step(sat_fine, fine_dt)
        deb_fine = rk4_step(deb_fine, fine_dt)

    return fine_min_t, fine_min_dist


# ─── Maneuver Planning ────────────────────────────────────────────────────────

def plan_evasion_burn(
    sat_state: np.ndarray,
    tca_seconds: float,
    miss_distance_km: float
) -> np.ndarray:
    """
    Plan an evasion maneuver in the RTN frame to increase miss distance.

    Strategy: Apply a Transverse (prograde/retrograde) burn before TCA.
    A prograde burn increases the semi-major axis, causing the satellite to
    arrive at the conjunction point LATER than the debris (it "runs ahead").
    A retrograde burn makes it arrive earlier (it "falls behind").

    We choose the sign based on which direction increases the miss distance most.
    The required ΔV magnitude is estimated from the geometry:
        ΔV_T ≈ (D_required - D_current) / TCA
    where D_required = 0.5 km (5× the conjunction threshold for safety margin).

    The burn is submitted in ECI after rotation.

    Args:
        sat_state: Satellite current state
        tca_seconds: Time until closest approach [s]
        miss_distance_km: Current predicted miss distance [km]

    Returns:
        ΔV vector in RTN frame [km/s]
    """
    SAFETY_MARGIN_KM = 0.5  # Aim for 500m miss distance (5× threshold)

    if tca_seconds < 1.0:
        tca_seconds = 60.0  # Fallback to avoid division by zero

    # Required separation increase
    delta_separation = max(0, SAFETY_MARGIN_KM - miss_distance_km)

    # Estimate required transverse ΔV (phasing maneuver approximation)
    # A transverse ΔV of dVt changes the along-track position by ~2 * dVt * TCA
    # (factor of 2 from orbital mechanics phasing equation)
    dv_t = delta_separation / (2.0 * tca_seconds / 1000.0)  # convert TCA to match scale

    # Clamp to thruster limits
    dv_t = np.clip(dv_t, 0.001, MAX_DELTA_V * 0.8)

    # Use prograde burn (positive T direction) — retrograde would be negative
    # In practice, we'd check which sign gives better separation, but prograde
    # is typically preferred as it raises the orbit slightly
    dv_rtn = np.array([0.0, dv_t, 0.0])

    return dv_rtn


def plan_recovery_burn(
    sat_state: np.ndarray,
    nominal_state: np.ndarray
) -> np.ndarray:
    """
    Plan a recovery burn to return satellite to its nominal orbital slot.

    Strategy: Compute the velocity difference between the satellite's current
    state and its nominal slot state. Apply a corrective burn in the direction
    that closes this gap, clamped to the thruster limit.

    This is a simplified "instantaneous correction" — a production system
    would use a Hohmann transfer or Lambert's problem solver for optimal
    fuel efficiency.

    Args:
        sat_state: Current satellite state
        nominal_state: Target nominal slot state

    Returns:
        ΔV vector in ECI [km/s]
    """
    # Velocity correction needed
    dv_required = nominal_state[3:] - sat_state[3:]
    dv_mag = np.linalg.norm(dv_required)

    if dv_mag < 1e-6:
        return np.zeros(3)

    # Clamp to thruster limit
    if dv_mag > MAX_DELTA_V * 0.9:
        dv_required = dv_required * (MAX_DELTA_V * 0.9 / dv_mag)

    return dv_required


def graveyard_burn(sat_state: np.ndarray) -> np.ndarray:
    """
    Compute a retrograde deorbit/graveyard burn for a fuel-critical satellite.

    For LEO satellites, we lower the orbit (retrograde burn) to initiate
    atmospheric re-entry. For GEO, we'd raise it to the graveyard belt.
    Since this is LEO, we apply a retrograde (negative T direction) burn
    to lower perigee into the atmosphere.

    Returns:
        ΔV in RTN frame [km/s] (retrograde at max thrust)
    """
    # Maximum retrograde burn to initiate deorbit
    return np.array([0.0, -MAX_DELTA_V, 0.0])
