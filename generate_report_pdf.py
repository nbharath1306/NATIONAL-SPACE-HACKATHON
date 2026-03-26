#!/usr/bin/env python3
"""Generate ACM Codebase Report as PDF."""
from fpdf import FPDF


class ReportPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, "National Space Hackathon 2026 | ACM Codebase Report", align="R")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def stitle(self, t):
        self.ln(3)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(20, 40, 80)
        self.cell(0, 10, t, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(20, 40, 80)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def stitle2(self, t):
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(40, 70, 120)
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

    def mono(self, t):
        self.set_font("Courier", "", 8)
        self.set_fill_color(240, 242, 245)
        self.set_text_color(30, 30, 30)
        for line in t.strip().split("\n"):
            self.cell(0, 4.5, "  " + line, fill=True, new_x="LMARGIN", new_y="NEXT")
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
    p = ReportPDF()
    p.set_auto_page_break(auto=True, margin=20)

    # COVER
    p.add_page()
    p.ln(50)
    p.set_font("Helvetica", "B", 28)
    p.set_text_color(20, 40, 80)
    p.cell(0, 15, "Autonomous Constellation", align="C", new_x="LMARGIN", new_y="NEXT")
    p.cell(0, 15, "Manager (ACM)", align="C", new_x="LMARGIN", new_y="NEXT")
    p.ln(20)
    p.set_font("Helvetica", "", 16)
    p.set_text_color(80, 80, 80)
    p.cell(0, 10, "Full Codebase & Problem Statement Report", align="C", new_x="LMARGIN", new_y="NEXT")
    p.ln(15)
    p.set_draw_color(20, 40, 80)
    p.line(60, p.get_y(), 150, p.get_y())
    p.ln(15)
    p.set_font("Helvetica", "B", 13)
    p.set_text_color(40, 70, 120)
    p.cell(0, 10, "National Space Hackathon 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    p.set_font("Helvetica", "", 12)
    p.set_text_color(100, 100, 100)
    p.cell(0, 8, "Indian Institute of Technology, Delhi", align="C", new_x="LMARGIN", new_y="NEXT")
    p.cell(0, 8, "Generated: 2026-03-26", align="C", new_x="LMARGIN", new_y="NEXT")

    # 1. PROBLEM STATEMENT
    p.add_page()
    p.stitle("1. Problem Statement Summary")
    p.txt("The hackathon requires building an Autonomous Constellation Manager (ACM) - a backend system acting as the brain for 50+ LEO satellites navigating through tens of thousands of tracked space debris fragments.")

    p.stitle2("Core Objectives")
    p.bul("High-Frequency Telemetry Ingestion - ECI state vectors (position + velocity)")
    p.bul("Predictive Conjunction Assessment - forecast collisions up to 24h ahead using spatial indexing")
    p.bul("Autonomous Collision Avoidance (COLA) - auto-schedule evasion when miss distance < 100m")
    p.bul("Station-Keeping & Recovery - return satellites to 10 km bounding box")
    p.bul("Propellant Budgeting & EOL - Tsiolkovsky fuel tracking, graveyard orbit at 5%")
    p.bul("Multi-Objective Optimization - maximize uptime, minimize fuel expenditure")

    p.stitle2("Physics Requirements")
    p.bul("ECI (J2000) coordinate system")
    p.bul("J2 perturbation model (not simple Keplerian)")
    p.bul("RK4 numerical integration")
    p.bul("RTN frame for maneuver planning")
    p.bul("mu=398600.4418, RE=6378.137, J2=1.08263e-3")

    p.stitle2("API Requirements (RESTful on port 8000)")
    p.bul("POST /api/telemetry - ingest state vectors")
    p.bul("POST /api/maneuver/schedule - schedule burn sequences")
    p.bul("POST /api/simulate/step - advance simulation clock")
    p.bul("GET /api/visualization/snapshot - compact data for frontend")

    p.stitle2("Spacecraft Constants")
    w = [65, 55]
    p.trow(["Parameter", "Value"], w, hdr=True)
    for r in [("Dry Mass", "500.0 kg"), ("Initial Fuel", "50.0 kg (wet = 550 kg)"),
              ("Specific Impulse", "300.0 s"), ("Max Delta-V/burn", "15.0 m/s"),
              ("Thruster Cooldown", "600 seconds"), ("Collision Threshold", "100 meters"),
              ("Station-Keeping Box", "10 km radius")]:
        p.trow(r, w)

    p.stitle2("Evaluation Criteria")
    w2 = [60, 20, 110]
    p.trow(["Criteria", "Weight", "Description"], w2, hdr=True)
    for r in [("Safety Score", "25%", "Collisions successfully avoided"),
              ("Fuel Efficiency", "20%", "Total delta-V consumed across fleet"),
              ("Constellation Uptime", "15%", "Time satellites in nominal slots"),
              ("Algorithmic Speed", "15%", "Backend API performance"),
              ("UI/UX & Visualization", "15%", "Dashboard clarity and frame rate"),
              ("Code Quality & Logging", "10%", "Modularity and logging accuracy")]:
        p.trow(r, w2)

    # 2. FILE STRUCTURE
    p.add_page()
    p.stitle("2. Project File Structure")
    p.mono(
        "IIT-DELHI--main/\n"
        "|-- realsim.py                  Test simulator\n"
        "|-- simulator.log               Last run log\n"
        "|-- NSH_PS.pdf                  Problem statement\n"
        "|\n"
        "|-- app/                        BACKEND (FastAPI)\n"
        "|   |-- main.py                 App init, CORS\n"
        "|   |-- core/\n"
        "|   |   |-- physics.py          Orbital mechanics (~620 lines)\n"
        "|   |   |-- simulation.py       Simulation manager (~638 lines)\n"
        "|   |-- models/\n"
        "|   |   |-- state.py            Data classes (~62 lines)\n"
        "|   |-- api/\n"
        "|       |-- routes.py           REST endpoints (~255 lines)\n"
        "|\n"
        "|-- frontend/                   FRONTEND (Canvas)\n"
        "    |-- index.html              Page layout (~186 lines)\n"
        "    |-- dashboard.js            Rendering engine (~1000+ lines)"
    )

    # 3. BACKEND
    p.stitle("3. Backend Detailed Breakdown")

    p.stitle2("3.1 app/main.py - Entry Point")
    p.bul("Framework: FastAPI")
    p.bul("CORS middleware enabled for all origins")
    p.bul("Routes included from app.api.routes")
    p.bul("Health check: GET / -> {message: ACM Backend Running}")

    p.stitle2("3.2 app/models/state.py - Data Models")
    p.bul("SatelliteStatus (Enum): NOMINAL, EVADING, RECOVERING, EOL, DEAD")
    p.bul("SatelliteState: id, state (6D), m_fuel, m_dry, status, scheduled_burns, last_burn_time")
    p.bul("DebrisState: id, state (6D vector)")
    p.bul("CDMWarning: sat_id, deb_id, tca_sim_time, miss_distance_km, is_critical, evasion_scheduled")
    p.bul("GroundStation: id, name, lat, lon, alt_m, min_elev_deg")

    p.stitle2("3.3 app/core/physics.py - Orbital Mechanics (~620 lines)")
    p.txt("All physical constants match the problem statement. Core functions:")
    w3 = [60, 130]
    p.trow(["Function", "Description"], w3, hdr=True)
    for r in [
        ("j2_acceleration(r)", "J2 perturbation acceleration from Earth oblateness"),
        ("state_derivative(state)", "d/dt of 6D state (two-body + J2)"),
        ("rk4_step(state, dt)", "RK4 integration step, O(dt^4) accuracy"),
        ("propagate(state, dur, dt)", "Propagate state forward via repeated RK4"),
        ("propagate_trajectory(...)", "Full trajectory array for visualization"),
        ("eci_to_rtn_matrix(r, v)", "Rotation matrix ECI to RTN frame"),
        ("rtn_to_eci(dv_rtn, r, v)", "Convert delta-V from RTN to ECI"),
        ("compute_fuel_consumed(m,dv)", "Tsiolkovsky: dm = m*(1-exp(-dV/(Isp*g0)))"),
        ("validate_burn(dv, fuel, m)", "Check dV <= 15 m/s and sufficient fuel"),
        ("eci_to_geodetic(r, gmst)", "ECI position to lat/lon/alt"),
        ("compute_gmst(elapsed_s)", "Greenwich Mean Sidereal Time"),
        ("check_line_of_sight(...)", "Satellite visibility from ground station"),
        ("find_closest_approach(...)", "Two-pass TCA: 60s coarse then 5s fine"),
        ("plan_evasion_burn(...)", "Transverse RTN burn, 500m target separation"),
        ("plan_recovery_burn(...)", "Velocity correction to return to nominal slot"),
        ("graveyard_burn(state)", "Max retrograde burn for EOL deorbit"),
    ]:
        p.trow(r, w3)

    p.add_page()
    p.stitle2("3.4 app/core/simulation.py - SimulationManager (~638 lines)")
    p.txt("Central orchestration class (singleton). Manages all satellites, debris, CDMs, and burns.")
    p.ln(1)
    p.txt("Initialization:")
    p.bul("Epoch: 2026-03-12T08:00:00Z")
    p.bul("Walker-Delta: 5 planes x 10 sats = 50 satellites, 550 km, 53 deg inc")
    p.bul("72 deg RAAN spacing, 36 deg true anomaly spacing")
    p.bul("6 ground stations from problem statement")
    p.bul("KD-Tree (scipy) for O(log N) debris spatial queries")
    p.ln(2)

    w4 = [60, 130]
    p.trow(["Method", "Description"], w4, hdr=True)
    for r in [
        ("_rebuild_debris_tree()", "Rebuild scipy KD-Tree from debris positions"),
        ("_get_nearby_debris(pos,r)", "O(log N) query for debris within radius"),
        ("ingest_telemetry(ts, objs)", "Update state vectors, flag KD-Tree dirty"),
        ("run_conjunction_assessment()", "KD-Tree + TCA scan, auto-schedule evasion"),
        ("_auto_schedule_evasion(id,cdm)", "Plan evasion + recovery burn pair"),
        ("schedule_maneuver(id, seq)", "Validate burn sequence: dV, fuel, LOS, cooldown"),
        ("step(step_seconds)", "Main loop: RK4, burns, collision check, EOL"),
        ("get_snapshot()", "JSON with lat/lon/alt for frontend"),
    ]:
        p.trow(r, w4)

    p.ln(2)
    p.txt("step() simulation loop (per 30s sub-step):")
    p.bul("1. Propagate all debris via RK4")
    p.bul("2. Propagate all satellites via RK4")
    p.bul("3. Execute scheduled burns within [t, t+dt]")
    p.bul("4. Check station-keeping (10 km drift tolerance)")
    p.bul("5. Collision detection (< 100m = collision logged)")
    p.bul("6. EOL check (fuel <= 5% triggers graveyard burn)")

    p.stitle2("3.5 app/api/routes.py - REST Endpoints (~255 lines)")
    w5 = [55, 40, 95]
    p.trow(["Endpoint", "Purpose", "Response"], w5, hdr=True)
    for r in [
        ("POST /api/telemetry", "Ingest states", "status, processed_count, cdm_warnings"),
        ("POST /api/maneuver/schedule", "Schedule burns", "status, validation{los,fuel,mass}"),
        ("POST /api/simulate/step", "Advance clock", "status, timestamp, collisions, maneuvers"),
        ("GET /api/visualization/snapshot", "Frontend data", "timestamp, satellites[], debris[]"),
        ("GET /health", "Health check", "status: ok"),
        ("GET /api/debug/satellites", "Debug sats", "[satellite states]"),
        ("GET /api/debug/cdms", "Debug CDMs", "[cdm warnings]"),
    ]:
        p.trow(r, w5)

    # 4. FRONTEND
    p.add_page()
    p.stitle("4. Frontend Detailed Breakdown")
    p.txt("Pure Canvas-based dashboard (no framework), 5 visualization modules. Polls backend every 2s, renders at 60 FPS via Canvas API.")

    p.stitle2("Module 1: Ground Track Map (Mercator Projection)")
    p.bul("Lat/lon grid with equator highlight")
    p.bul("Terminator line (day/night boundary based on sim time)")
    p.bul("Debris cloud rendered as small red squares")
    p.bul("6 ground stations with labels and circles")
    p.bul("Satellite markers with solar panel shape")
    p.bul("90-minute historical trails with fading alpha")
    p.bul("Dashed predicted trajectory line")
    p.bul("Click to select satellite, hover for tooltip")

    p.stitle2("Module 2: Conjunction Bullseye (Polar Chart)")
    p.bul("Centered on selected satellite")
    p.bul("Radial distance = Time to Closest Approach (6h/12h/18h/24h rings)")
    p.bul("Angle = relative approach bearing")
    p.bul("Color: Green (safe), Yellow (<5km), Orange (<1km), Red (<100m)")
    p.bul("Critical debris labeled with ID")

    p.stitle2("Module 3: Fleet Fuel Heatmap")
    p.bul("Grid of fuel gauge cells (one per satellite)")
    p.bul("Bar height proportional to fuel (0-50 kg)")
    p.bul("Color gradient: green (>50%) -> amber (20-50%) -> red (<20%)")
    p.bul("Status stripe and fleet average fuel percentage")

    p.stitle2("Module 4: Maneuver Timeline (Gantt Chart)")
    p.bul("Y-axis: satellite rows, X-axis: 2-hour time window")
    p.bul("Burn blocks: amber (evasion), blue (recovery), grey (cooldown)")
    p.bul("NOW marker as cyan dashed line")

    p.stitle2("Module 5: Delta-V History Graph")
    p.bul("Line chart of cumulative delta-V over simulation time")
    p.bul("Tracks total collisions avoided counter")

    # 5. SIMULATOR
    p.add_page()
    p.stitle("5. Test Simulator (realsim.py)")
    p.txt("Standalone simulator feeding 15 test satellites and 500+ debris objects to the ACM backend.")

    p.stitle2("Test Satellite Fleet (15 satellites)")
    w6 = [25, 40, 25, 25, 25, 50]
    p.trow(["Plane", "Mission", "Inc", "Alt", "RAAN", "Satellites"], w6, hdr=True)
    p.trow(["A", "Earth Observation", "53 deg", "550 km", "0 deg", "SAT-Alpha-01/02/03"], w6)
    p.trow(["B", "Communications", "45 deg", "600 km", "72 deg", "SAT-Beta-01/02/03"], w6)
    p.trow(["C", "SAR Radar", "97 deg", "500 km", "144 deg", "SAT-Gamma-01/02/03"], w6)
    p.trow(["D", "Nav / Timing", "55 deg", "560 km", "216 deg", "SAT-Delta-01/02/03"], w6)
    p.trow(["E", "Tech Demo", "28 deg", "480 km", "288 deg", "SAT-Eps-01/02/03"], w6)

    p.stitle2("Close-Approach Debris (3 objects)")
    p.bul("Placed 200 km ahead of Alpha-01, Gamma-01, Delta-02")
    p.bul("0.2% lower velocity to create convergent trajectories")
    p.bul("Designed to trigger conjunction detection and evasion")

    p.stitle2("Simulation Configuration")
    p.bul("Backend URL: http://127.0.0.1:8000")
    p.bul("Epoch: 2026-03-12 08:00:00 UTC")
    p.bul("Telemetry rate: every 2 seconds real-time")
    p.bul("Sim step: 60 seconds per tick, Max ticks: 200 (~3.3 sim-hours)")
    p.bul("Every 20 ticks: schedules a demo test maneuver")

    # 6. DATA FLOW
    p.add_page()
    p.stitle("6. Data Flow Architecture")
    p.mono(
        "realsim.py (External Simulator)\n"
        "     |\n"
        "     |-- POST /api/telemetry ---------> SimulationManager\n"
        "     |-- POST /api/simulate/step -----> RK4 + burns + CDM scan\n"
        "     |-- POST /api/maneuver/schedule -> validation + queueing\n"
        "     |\n"
        "     |-- GET /api/visualization/snapshot\n"
        "     |                                      ^\n"
        "     |                                      |\n"
        "frontend/dashboard.js (polls every 2s) -----+\n"
        "     |\n"
        "     +-- Canvas rendering at 60 FPS\n"
        "         |-- Ground Track Map\n"
        "         |-- Conjunction Bullseye\n"
        "         |-- Fuel Heatmap\n"
        "         |-- Maneuver Timeline\n"
        "         +-- Delta-V History"
    )

    # 7. ALGORITHMS
    p.stitle("7. Key Algorithms")

    p.stitle2("7.1 Orbital Propagation (RK4 + J2)")
    p.txt("State: s = [x, y, z, vx, vy, vz]")
    p.txt("ds/dt = [v, -mu/|r|^3 * r + a_J2(r)]")
    p.txt("s(t+dt) = s(t) + (dt/6) * (k1 + 2*k2 + 2*k3 + k4)")

    p.stitle2("7.2 Tsiolkovsky Rocket Equation")
    p.txt("fuel_consumed = m_current * (1 - exp(-|dV| / (Isp * g0)))")

    p.stitle2("7.3 TCA Computation (Two-Pass)")
    p.bul("Pass 1: 60s steps over 86400s horizon -> approximate minimum")
    p.bul("Pass 2: 5s steps around coarse minimum -> refined TCA")

    p.stitle2("7.4 KD-Tree Conjunction Search")
    p.bul("Build KD-Tree from all debris 3D positions")
    p.bul("Query debris within 500 km per satellite -> O(log N)")
    p.bul("Detailed TCA only on nearby debris -> avoids O(N^2)")

    p.stitle2("7.5 Evasion Maneuver (RTN Frame)")
    p.bul("Target: 500m separation (5x safety margin)")
    p.bul("Transverse dV = delta_sep / (2 * TCA/1000), clamped to 80% max")
    p.bul("Convert RTN -> ECI via rotation matrix")

    p.stitle2("7.6 Line-of-Sight Check")
    p.bul("Ground station geodetic -> ECI using GMST rotation")
    p.bul("Elevation = arcsin((r_sat - r_gs) . r_gs_hat / |r_sat - r_gs|)")
    p.bul("Valid if elevation >= min_elevation_mask")

    # 8. CONSTANTS
    p.add_page()
    p.stitle("8. Physical Constants Verification")
    p.txt("All constants verified against the problem statement PDF:")
    p.ln(1)
    w7 = [45, 45, 45, 20]
    p.trow(["Constant", "Code Value", "PDF Value", "Match"], w7, hdr=True)
    for r in [
        ("mu (gravity)", "398600.4418", "398600.4418", "YES"),
        ("RE (Earth radius)", "6378.137 km", "6378.137 km", "YES"),
        ("J2 (oblateness)", "1.08263e-3", "1.08263e-3", "YES"),
        ("Dry mass", "500.0 kg", "500.0 kg", "YES"),
        ("Initial fuel", "50.0 kg", "50.0 kg", "YES"),
        ("Isp", "300.0 s", "300.0 s", "YES"),
        ("Max dV/burn", "15.0 m/s", "15.0 m/s", "YES"),
        ("Thruster cooldown", "600 s", "600 s", "YES"),
        ("Collision threshold", "100 m", "100 m", "YES"),
        ("Station-keeping box", "10 km", "10 km", "YES"),
        ("Signal delay", "10 s", "10 s", "YES"),
    ]:
        p.trow(r, w7)
    p.ln(3)
    p.set_font("Helvetica", "B", 12)
    p.set_text_color(0, 120, 0)
    p.cell(0, 8, "ALL CONSTANTS MATCH.", align="C", new_x="LMARGIN", new_y="NEXT")

    # 9. GAPS
    p.ln(5)
    p.stitle("9. Gaps & Missing Items")
    w8 = [42, 48, 100]
    p.trow(["Item", "Required By PDF", "Status"], w8, hdr=True)
    for r in [
        ("Dockerfile", "HARD REQUIREMENT", "MISSING - disqualification risk"),
        ("ubuntu:22.04 base", "HARD REQUIREMENT", "MISSING"),
        ("Port 8000 binding", "HARD REQUIREMENT", "Backend does it, no Dockerfile"),
        ("Database", "Expected deliverable", "NOT PRESENT (all in-memory)"),
        ("Structured logging", "10% of score", "BASIC ONLY"),
        ("Predicted trajectory", "Dashed line 90min", "SIMPLIFIED (sinusoidal approx)"),
        ("WebGL rendering", "Recommended 10K+", "CANVAS 2D ONLY"),
        ("Signal delay", "10s min manual sched", "NOT STRICTLY ENFORCED"),
        ("Ground stations CSV", "Provided dataset", "HARDCODED IN CODE"),
    ]:
        p.trow(r, w8)

    # 10. HOW TO RUN
    p.ln(5)
    p.stitle("10. How to Run")
    p.stitle2("Step 1: Start Backend")
    p.mono("cd IIT-DELHI--main\npip install fastapi uvicorn scipy numpy\nuvicorn app.main:app --host 0.0.0.0 --port 8000")
    p.stitle2("Step 2: Start Simulator")
    p.mono("python realsim.py")
    p.stitle2("Step 3: Open Frontend")
    p.mono("Open frontend/index.html in a web browser")

    out = "/Users/nbharath/Downloads/IIT-DELHI--main/ACM_Codebase_Report.pdf"
    p.output(out)
    print(f"PDF saved: {out}")


if __name__ == "__main__":
    build()
