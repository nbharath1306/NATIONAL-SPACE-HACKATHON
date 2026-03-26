#!/usr/bin/env python3
"""Generate Technical Report PDF for ACM submission."""
from fpdf import FPDF


class TechReport(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, "ACM Technical Report | National Space Hackathon 2026", align="R")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def stitle(self, num, t):
        self.ln(3)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(20, 40, 80)
        self.set_x(self.l_margin)
        self.cell(0, 10, f"{num}. {t}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(20, 40, 80)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def stitle2(self, t):
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(40, 70, 120)
        self.set_x(self.l_margin)
        self.cell(0, 8, t, new_x="LMARGIN", new_y="NEXT")

    def txt(self, t):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5.5, t)
        self.ln(1)

    def bul(self, t):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5.5, "    - " + t)

    def eq(self, t):
        self.set_font("Courier", "", 9)
        self.set_fill_color(240, 242, 245)
        self.set_text_color(30, 30, 30)
        self.set_x(self.l_margin)
        for line in t.strip().split("\n"):
            self.cell(0, 5, "    " + line, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def trow(self, cols, widths, hdr=False):
        s = "B" if hdr else ""
        self.set_font("Helvetica", s, 8.5)
        self.set_text_color(30, 30, 30)
        if hdr:
            self.set_fill_color(215, 225, 240)
        for i, c in enumerate(cols):
            self.cell(widths[i], 6.5, str(c), border=1, fill=hdr)
        self.ln(6.5)


def build():
    p = TechReport()
    p.set_auto_page_break(auto=True, margin=20)

    # ── COVER ──
    p.add_page()
    p.ln(40)
    p.set_font("Helvetica", "B", 26)
    p.set_text_color(20, 40, 80)
    p.cell(0, 14, "Technical Report", align="C", new_x="LMARGIN", new_y="NEXT")
    p.ln(8)
    p.set_font("Helvetica", "B", 18)
    p.cell(0, 12, "Autonomous Constellation Manager", align="C", new_x="LMARGIN", new_y="NEXT")
    p.ln(15)
    p.set_draw_color(20, 40, 80)
    p.line(60, p.get_y(), 150, p.get_y())
    p.ln(15)
    p.set_font("Helvetica", "", 14)
    p.set_text_color(60, 60, 60)
    p.cell(0, 10, "Orbital Debris Avoidance & Constellation Management", align="C", new_x="LMARGIN", new_y="NEXT")
    p.ln(8)
    p.set_font("Helvetica", "B", 12)
    p.set_text_color(40, 70, 120)
    p.cell(0, 8, "National Space Hackathon 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    p.set_font("Helvetica", "", 11)
    p.set_text_color(100, 100, 100)
    p.cell(0, 8, "Indian Institute of Technology, Delhi", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── 1. ABSTRACT ──
    p.add_page()
    p.stitle(1, "Abstract")
    p.txt(
        "This report details the architecture, numerical methods, and optimization algorithms "
        "employed in our Autonomous Constellation Manager (ACM). The system autonomously manages "
        "a 50-satellite Walker-Delta constellation in Low Earth Orbit, performing real-time "
        "conjunction assessment against 10,000+ debris objects, autonomous collision avoidance "
        "maneuver planning, and station-keeping recovery. The backend uses a FastAPI server with "
        "RK4+J2 orbital propagation, KD-Tree spatial indexing for O(N log M) conjunction search, "
        "and RTN-frame maneuver planning. The frontend provides a Canvas-based 60 FPS dashboard "
        "with 5 visualization modules. All data is persisted in SQLite for audit and scoring."
    )

    # ── 2. SYSTEM ARCHITECTURE ──
    p.stitle(2, "System Architecture")
    p.txt(
        "The ACM follows a three-tier architecture: (1) a FastAPI REST backend serving as the "
        "physics engine and decision-making core, (2) a SQLite database for persistent event "
        "logging, and (3) a Canvas-based JavaScript frontend for situational awareness."
    )

    p.stitle2("2.1 Backend (FastAPI + Python)")
    p.bul("Physics Engine (physics.py, ~620 lines): RK4 integrator with J2 perturbation")
    p.bul("Simulation Manager (simulation.py, ~650 lines): Central orchestrator with KD-Tree")
    p.bul("REST API (routes.py, ~330 lines): 4 primary + trajectory prediction + DB query endpoints")
    p.bul("Database Layer (database.py): SQLite persistence for maneuvers, collisions, CDMs")

    p.stitle2("2.2 Frontend (Canvas Dashboard)")
    p.bul("5 visualization modules rendered at 60 FPS via Canvas API")
    p.bul("Polls /api/visualization/snapshot every 2 seconds")
    p.bul("Compact tuple format for debris: [id, lat, lon, alt] reduces JSON payload 5x")

    p.stitle2("2.3 Deployment")
    p.bul("Single Dockerfile using ubuntu:22.04 base image")
    p.bul("Backend + frontend served on port 8000 (0.0.0.0 binding)")
    p.bul("Frontend served as static files from /dashboard endpoint")

    # ── 3. NUMERICAL METHODS ──
    p.add_page()
    p.stitle(3, "Numerical Methods")

    p.stitle2("3.1 Orbital Propagation: RK4 with J2 Perturbation")
    p.txt(
        "Orbits are propagated using the Runge-Kutta 4th-order method applied to the "
        "two-body problem with J2 oblateness correction. The state vector "
        "S = [x, y, z, vx, vy, vz] evolves according to:"
    )
    p.eq("d^2r/dt^2 = -mu/|r|^3 * r + a_J2(r)")
    p.txt("where the J2 perturbation acceleration is:")
    p.eq(
        "a_J2 = (3/2) * J2 * mu * RE^2 / |r|^5 *\n"
        "  [ x*(5*z^2/r^2 - 1),\n"
        "    y*(5*z^2/r^2 - 1),\n"
        "    z*(5*z^2/r^2 - 3) ]"
    )
    p.txt("The RK4 scheme provides O(dt^4) per-step accuracy:")
    p.eq(
        "k1 = f(t, y)\n"
        "k2 = f(t + dt/2, y + k1*dt/2)\n"
        "k3 = f(t + dt/2, y + k2*dt/2)\n"
        "k4 = f(t + dt, y + k3*dt)\n"
        "y(t+dt) = y(t) + (dt/6)*(k1 + 2*k2 + 2*k3 + k4)"
    )
    p.txt("We use a 30-second integration step for the main simulation loop, providing "
          "a good balance between accuracy and computational speed for LEO orbits at ~7.5 km/s.")

    p.stitle2("3.2 Tsiolkovsky Rocket Equation")
    p.txt("Fuel consumption for each impulsive burn follows:")
    p.eq("dm = m_current * (1 - exp(-|dV| / (Isp * g0)))")
    p.txt(
        "where Isp = 300s, g0 = 9.80665 m/s^2. As fuel depletes, the satellite mass decreases, "
        "making subsequent burns marginally more fuel-efficient. The simulation dynamically "
        "tracks mass changes after each burn."
    )

    p.stitle2("3.3 ECI to Geodetic Conversion")
    p.txt(
        "Position vectors in the Earth-Centered Inertial (ECI) frame are converted to "
        "latitude/longitude using the Greenwich Mean Sidereal Time (GMST) to account for "
        "Earth's rotation. GMST advances at 7.292115e-5 rad/s from the epoch."
    )

    # ── 4. SPATIAL OPTIMIZATION ──
    p.add_page()
    p.stitle(4, "Spatial Optimization Algorithms")

    p.stitle2("4.1 KD-Tree for Conjunction Filtering")
    p.txt(
        "Naively checking every satellite against every debris object is O(N*M) = O(500,000) "
        "per timestep with 50 satellites and 10,000 debris. We use a scipy KD-Tree to partition "
        "the 3D debris position space into a binary space-partitioning tree."
    )
    p.txt("For each satellite, we query the KD-Tree for all debris within a 500 km search radius. "
          "This runs in O(log M + k) where k is the number of results. Total complexity becomes "
          "O(N * (log M + k * T_tca)) where T_tca is the constant cost of TCA computation.")
    p.txt("The KD-Tree is rebuilt lazily: a dirty flag is set when debris positions change "
          "(via telemetry or propagation), and the tree is rebuilt only before the next "
          "conjunction assessment scan.")

    p.stitle2("4.2 Two-Pass TCA Computation")
    p.txt("The Time of Closest Approach is found using a two-pass algorithm:")
    p.bul("Coarse pass: Propagate both satellite and debris in 60-second steps over a "
          "24-hour horizon. Record the time with minimum distance.")
    p.bul("Fine pass: Re-propagate a 120-second window around the coarse minimum at "
          "5-second resolution for accurate TCA determination.")
    p.txt("This avoids missing close approaches that peak between coarse steps while "
          "keeping the total computation tractable.")

    # ── 5. MANEUVER PLANNING ──
    p.stitle(5, "Maneuver Planning Strategy")

    p.stitle2("5.1 RTN Frame Evasion Burns")
    p.txt(
        "Maneuvers are planned in the satellite's local Radial-Transverse-Normal (RTN) frame, "
        "then converted to ECI via rotation matrix for API submission."
    )
    p.bul("R (Radial): r/|r| - points from Earth center through satellite")
    p.bul("T (Transverse): along-track, perpendicular to R in orbital plane")
    p.bul("N (Normal): cross-track, perpendicular to orbital plane")
    p.txt(
        "Evasion burns are applied in the Transverse (prograde) direction as this is the "
        "most fuel-efficient way to change along-track phasing. The required dV is estimated "
        "from the phasing approximation:"
    )
    p.eq("dV_T = (D_target - D_current) / (2 * TCA / 1000)")
    p.txt("where D_target = 500m (5x safety margin over the 100m threshold). "
          "Burns are clamped to 80% of the 15 m/s maximum to preserve margin.")

    p.stitle2("5.2 Recovery Burns")
    p.txt(
        "After the conjunction threat passes, a recovery burn corrects the velocity difference "
        "between the satellite's perturbed state and its nominal orbital slot. This is a "
        "simplified instantaneous correction clamped to 90% of maximum thrust."
    )

    p.stitle2("5.3 Autonomous Decision Pipeline")
    p.txt("When a critical CDM (miss < 100m) is detected:")
    p.bul("1. Check satellite has fuel and line-of-sight to a ground station")
    p.bul("2. Plan evasion burn at earliest possible time (now + 10s signal + cooldown)")
    p.bul("3. Plan recovery burn after TCA + 600s cooldown + 60s margin")
    p.bul("4. Queue both burns to the satellite's maneuver schedule")
    p.bul("5. Set satellite status to EVADING")

    # ── 6. CONSTRAINTS ──
    p.add_page()
    p.stitle(6, "Constraint Enforcement")

    w = [55, 135]
    p.trow(["Constraint", "Implementation"], w, hdr=True)
    p.trow(["dV <= 15 m/s", "validate_burn() checks magnitude before scheduling"], w)
    p.trow(["600s cooldown", "Verified against last_burn_time at schedule and execution"], w)
    p.trow(["10s signal delay", "Burns must be >= sim_time + 10s (enforced in schedule_maneuver)"], w)
    p.trow(["Station-keeping 10km", "Checked every sub-step; outage_seconds logged"], w)
    p.trow(["EOL at 5% fuel", "Triggers automatic graveyard retrograde burn"], w)
    p.trow(["Ground station LOS", "Elevation angle check against 6 stations with min mask"], w)
    p.trow(["Fuel depletion", "Tsiolkovsky equation applied per burn, mass tracked dynamically"], w)

    # ── 7. FRONTEND ──
    p.stitle(7, "Frontend Visualization")
    p.txt("The Orbital Insight dashboard provides 5 Canvas-rendered modules at 60 FPS:")
    p.ln(1)
    w2 = [45, 145]
    p.trow(["Module", "Description"], w2, hdr=True)
    p.trow(["Ground Track", "Mercator map with sat positions, 90-min trails, terminator, debris, stations"], w2)
    p.trow(["Bullseye Plot", "Polar chart: TCA rings (6/12/18/24h), color-coded risk levels"], w2)
    p.trow(["Fuel Heatmap", "Grid of fuel gauges with green/amber/red gradient, fleet average"], w2)
    p.trow(["Gantt Timeline", "Burn blocks (evasion/recovery/cooldown) per satellite, NOW line"], w2)
    p.trow(["dV History", "Cumulative fuel used vs collisions avoided over time"], w2)

    p.ln(3)
    p.txt("Performance optimizations:")
    p.bul("Canvas API instead of DOM manipulation (10x faster at 50+ objects)")
    p.bul("Debris rendered as compact tuples [id, lat, lon, alt] - 5x JSON compression")
    p.bul("API polling at 2s intervals with requestAnimationFrame for rendering")
    p.bul("Trajectory prediction via /api/predict/trajectory endpoint (RK4-propagated)")

    # ── 8. DATABASE ──
    p.stitle(8, "Data Persistence (SQLite)")
    p.txt("All operational events are logged to a SQLite database for audit and scoring:")
    p.bul("maneuvers table: every burn with satellite ID, type, dV, fuel consumed/remaining")
    p.bul("collisions table: every collision with satellite ID, debris ID, distance")
    p.bul("cdm_warnings table: every conjunction warning with TCA, miss distance, criticality")
    p.bul("simulation_snapshots table: periodic fleet status (avg fuel, total collisions)")
    p.txt("Query endpoints (/api/db/stats, /api/db/maneuvers, /api/db/collisions) expose this data.")

    # ── 9. PERFORMANCE ──
    p.add_page()
    p.stitle(9, "Performance Analysis")

    w3 = [60, 50, 80]
    p.trow(["Operation", "Complexity", "Notes"], w3, hdr=True)
    p.trow(["KD-Tree build", "O(M log M)", "Rebuilt lazily on dirty flag"], w3)
    p.trow(["KD-Tree query", "O(log M + k)", "k = nearby debris, typically < 100"], w3)
    p.trow(["Conjunction scan", "O(N*(log M+k*T))", "N=50 sats, M=10K debris"], w3)
    p.trow(["RK4 per step", "O(1)", "4 derivative evaluations per step"], w3)
    p.trow(["Propagation", "O(duration/dt)", "30s steps for sim, 60s for trajectory"], w3)
    p.trow(["TCA (two-pass)", "O(H/dt_c + dt_c/dt_f)", "H=86400s, dt_c=60s, dt_f=5s"], w3)
    p.trow(["JSON snapshot", "O(N + M)", "Linear scan of all objects"], w3)

    p.ln(3)
    p.txt("A 3600-second simulation step with 50 satellites and 10,000 debris objects "
          "completes well under the 1-second wall-clock target.")

    # ── 10. CONCLUSION ──
    p.stitle(10, "Conclusion")
    p.txt(
        "Our ACM demonstrates a complete autonomous constellation management pipeline: "
        "from high-frequency telemetry ingestion through J2-perturbed orbital propagation, "
        "efficient KD-Tree conjunction detection, autonomous RTN-frame evasion maneuver "
        "planning, station-keeping recovery, and fuel-aware EOL management. The system "
        "enforces all physical constraints (thrust limits, cooldowns, signal delay, LOS) "
        "while optimizing the trade-off between collision safety and fuel efficiency. "
        "The Canvas-based frontend provides real-time situational awareness at 60 FPS, "
        "and all events are persisted in SQLite for complete audit capability."
    )

    out = "/Users/nbharath/Downloads/IIT-DELHI--main/ACM_Technical_Report.pdf"
    p.output(out)
    print(f"Technical Report saved: {out}")


if __name__ == "__main__":
    build()
