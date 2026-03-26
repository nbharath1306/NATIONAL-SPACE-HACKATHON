"""
DATABASE LAYER — SQLite Persistence
====================================
Stores maneuver logs, collision events, and CDM history for
post-simulation analysis and scoring verification.

Uses SQLite (no external DB server needed) — the DB file is
created automatically at startup.
"""

import sqlite3
import os
import logging
import threading
from datetime import datetime

logger = logging.getLogger("acm.database")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "acm_data.db")


class ACMDatabase:
    """Thread-safe SQLite database for ACM event logging."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._init_tables()
        logger.info(f"Database initialized at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS maneuvers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sim_time_s REAL NOT NULL,
                satellite_id TEXT NOT NULL,
                burn_id TEXT NOT NULL,
                burn_type TEXT NOT NULL,
                delta_v_ms REAL NOT NULL,
                fuel_consumed_kg REAL NOT NULL,
                fuel_remaining_kg REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sim_time_s REAL NOT NULL,
                satellite_id TEXT NOT NULL,
                debris_id TEXT NOT NULL,
                distance_m REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cdm_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sim_time_s REAL NOT NULL,
                satellite_id TEXT NOT NULL,
                debris_id TEXT NOT NULL,
                tca_sim_time_s REAL NOT NULL,
                miss_distance_m REAL NOT NULL,
                is_critical INTEGER NOT NULL,
                evasion_scheduled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS simulation_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sim_time_s REAL NOT NULL,
                total_satellites INTEGER NOT NULL,
                total_debris INTEGER NOT NULL,
                total_collisions INTEGER NOT NULL,
                total_maneuvers INTEGER NOT NULL,
                fleet_avg_fuel_kg REAL NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    def log_maneuver(self, sim_time: float, sat_id: str, burn_id: str,
                     burn_type: str, dv_ms: float, fuel_consumed: float,
                     fuel_remaining: float):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO maneuvers (timestamp, sim_time_s, satellite_id, burn_id, "
            "burn_type, delta_v_ms, fuel_consumed_kg, fuel_remaining_kg) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), sim_time, sat_id, burn_id,
             burn_type, dv_ms, fuel_consumed, fuel_remaining)
        )
        conn.commit()

    def log_collision(self, sim_time: float, sat_id: str, deb_id: str, distance_m: float):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO collisions (timestamp, sim_time_s, satellite_id, debris_id, distance_m) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), sim_time, sat_id, deb_id, distance_m)
        )
        conn.commit()

    def log_cdm(self, sim_time: float, sat_id: str, deb_id: str,
                tca_sim_time: float, miss_distance_m: float, is_critical: bool):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO cdm_warnings (timestamp, sim_time_s, satellite_id, debris_id, "
            "tca_sim_time_s, miss_distance_m, is_critical) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), sim_time, sat_id, deb_id,
             tca_sim_time, miss_distance_m, 1 if is_critical else 0)
        )
        conn.commit()

    def log_snapshot(self, sim_time: float, n_sats: int, n_debris: int,
                     total_collisions: int, total_maneuvers: int, avg_fuel: float):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO simulation_snapshots (timestamp, sim_time_s, total_satellites, "
            "total_debris, total_collisions, total_maneuvers, fleet_avg_fuel_kg) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), sim_time, n_sats, n_debris,
             total_collisions, total_maneuvers, avg_fuel)
        )
        conn.commit()

    def get_maneuver_history(self, limit: int = 100) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM maneuvers ORDER BY sim_time_s DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_collision_history(self, limit: int = 100) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM collisions ORDER BY sim_time_s DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cdm_history(self, limit: int = 100) -> list:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM cdm_warnings ORDER BY sim_time_s DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        conn = self._get_conn()
        maneuvers = conn.execute("SELECT COUNT(*) as c FROM maneuvers").fetchone()["c"]
        collisions = conn.execute("SELECT COUNT(*) as c FROM collisions").fetchone()["c"]
        cdms = conn.execute("SELECT COUNT(*) as c FROM cdm_warnings").fetchone()["c"]
        critical = conn.execute("SELECT COUNT(*) as c FROM cdm_warnings WHERE is_critical=1").fetchone()["c"]
        total_dv = conn.execute("SELECT COALESCE(SUM(delta_v_ms), 0) as s FROM maneuvers").fetchone()["s"]
        total_fuel = conn.execute("SELECT COALESCE(SUM(fuel_consumed_kg), 0) as s FROM maneuvers").fetchone()["s"]
        return {
            "total_maneuvers": maneuvers,
            "total_collisions": collisions,
            "total_cdms": cdms,
            "critical_cdms": critical,
            "total_delta_v_ms": round(total_dv, 4),
            "total_fuel_consumed_kg": round(total_fuel, 4),
        }


# Singleton
_db: ACMDatabase = None

def get_database() -> ACMDatabase:
    global _db
    if _db is None:
        _db = ACMDatabase()
    return _db
