from enum import Enum
import numpy as np

# ─── Satellite Status ─────────────────────────────

class SatelliteStatus(str, Enum):
    NOMINAL = "NOMINAL"
    EVADING = "EVADING"
    RECOVERING = "RECOVERING"
    EOL = "EOL"
    DEAD = "DEAD"


# ─── Satellite State ─────────────────────────────

class SatelliteState:
    def __init__(self, sat_id: str, state: np.ndarray):
        self.id = sat_id
        self.state = state
        self.nominal_state = state.copy()  # Reference slot for station-keeping
        self.m_fuel = 50.0
        self.m_dry = 500.0
        self.status = SatelliteStatus.NOMINAL
        self.scheduled_burns = []
        self.last_burn_time = None
        self.collision_count = 0
        self.outage_seconds = 0

    @property
    def fuel_fraction(self):
        return self.m_fuel / 50.0

    @property
    def m_total(self):
        return self.m_dry + self.m_fuel

    @property
    def is_eol(self):
        return self.m_fuel <= (50.0 * 0.05)  # 5% of initial fuel


# ─── Debris State ─────────────────────────────

class DebrisState:
    def __init__(self, deb_id: str, state: np.ndarray):
        self.id = deb_id
        self.state = state


# ─── CDM Warning ─────────────────────────────

class CDMWarning:
    def __init__(self, sat_id, deb_id, tca_time, miss_distance_km):
        self.sat_id = sat_id
        self.deb_id = deb_id
        self.tca_sim_time = tca_time
        self.miss_distance_km = miss_distance_km
        self.is_critical = miss_distance_km < 0.1
        self.evasion_scheduled = False


# ─── Ground Station ─────────────────────────────

class GroundStation:
    def __init__(self, gs_id, name, lat, lon, alt_m, min_elev_deg):
        self.id = gs_id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.alt_m = alt_m
        self.min_elev_deg = min_elev_deg