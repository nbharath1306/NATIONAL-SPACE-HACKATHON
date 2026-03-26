# Autonomous Constellation Manager (ACM)

**National Space Hackathon 2026 | IIT Delhi**

Orbital Debris Avoidance & Constellation Management System — a backend + frontend system that autonomously manages 50+ LEO satellites, detects conjunctions against 10,000+ debris objects, and executes collision avoidance maneuvers.

---

## Quick Start (Docker)

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Python 3.8+ (for the test simulator)

### Step 1: Build the Docker image
```bash
cd ~/Downloads/IIT-DELHI--main
docker build -t acm .
```
Takes 2-3 minutes on first build.

### Step 2: Run the container
```bash
docker run -p 8000:8000 acm
```
You should see:
```
Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Open the dashboard
Open your browser and go to:
```
http://localhost:8000/dashboard
```

### Step 4: Run the test simulator
Open a **new terminal tab** (Cmd+T / Ctrl+Shift+T) and run:
```bash
cd ~/Downloads/IIT-DELHI--main
pip install numpy requests
python3 realsim.py
```
This sends 15 satellites + 500 debris into the backend. The dashboard will light up.

### Step 5: Stop everything
- Press `Ctrl+C` in the simulator terminal
- Press `Ctrl+C` in the Docker terminal

---

## Running Without Docker (Development)

```bash
cd ~/Downloads/IIT-DELHI--main
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Then in another terminal:
```bash
python3 realsim.py
```
Dashboard at: `http://localhost:8000/dashboard`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/telemetry` | Ingest satellite/debris state vectors |
| POST | `/api/maneuver/schedule` | Schedule burn sequences |
| POST | `/api/simulate/step` | Advance simulation clock |
| GET | `/api/visualization/snapshot` | Compact data for frontend |
| GET | `/api/predict/trajectory/{sat_id}` | RK4-propagated ground track |
| GET | `/health` | Backend health check |
| GET | `/api/db/stats` | Database statistics |
| GET | `/api/db/maneuvers` | Maneuver history |
| GET | `/api/db/collisions` | Collision history |
| GET | `/api/db/cdms` | CDM warning history |
| GET | `/api/debug/satellites` | All satellite states |
| GET | `/api/debug/cdms` | Active CDM warnings |
| GET | `/dashboard` | Frontend dashboard |

---

## Project Structure

```
├── Dockerfile                 Ubuntu 22.04, port 8000
├── requirements.txt           Python dependencies
├── ground_stations.csv        6 ground stations
├── realsim.py                 Test simulator (15 sats + 500 debris)
│
├── app/                       BACKEND (FastAPI)
│   ├── main.py                App init, CORS, static files
│   ├── core/
│   │   ├── physics.py         RK4 + J2 propagation, RTN maneuvers
│   │   ├── simulation.py      Simulation orchestrator, KD-Tree
│   │   └── database.py        SQLite persistence
│   ├── models/
│   │   └── state.py           Data classes
│   └── api/
│       └── routes.py          REST endpoints
│
├── frontend/                  FRONTEND (Canvas Dashboard)
│   ├── index.html             Page layout
│   └── dashboard.js           5 visualization modules @ 60 FPS
│
├── ACM_Technical_Report.pdf   Technical report
└── NSH_PS.pdf                 Problem statement
```

---

## Key Algorithms

- **Orbital Propagation**: RK4 integrator with J2 perturbation (not simple Keplerian)
- **Conjunction Detection**: KD-Tree spatial index — O(N log M) instead of O(N*M)
- **TCA Computation**: Two-pass (coarse 60s + fine 5s) over 24-hour horizon
- **Evasion Maneuvers**: Transverse burns in RTN frame, converted to ECI
- **Fuel Tracking**: Tsiolkovsky rocket equation with dynamic mass updates
- **Station-Keeping**: 10 km drift tolerance with automatic recovery burns

## Frontend Modules

1. **Ground Track Map** — Mercator projection with satellite trails, terminator line, ground stations
2. **Conjunction Bullseye** — Polar chart showing nearby debris risk (color-coded)
3. **Fleet Fuel Heatmap** — Per-satellite fuel gauges with status indicators
4. **Maneuver Timeline** — Gantt chart of burns and cooldowns
5. **Delta-V History** — Cumulative fuel usage vs collisions avoided
