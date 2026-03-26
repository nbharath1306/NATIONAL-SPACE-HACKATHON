# Autonomous Constellation Manager (ACM)

**National Space Hackathon 2026 | IIT Delhi**

Orbital Debris Avoidance & Constellation Management System — a backend + frontend system that autonomously manages 50+ LEO satellites, detects conjunctions against 10,000+ debris objects, and executes collision avoidance maneuvers.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Option A: Run with Docker (Recommended)](#option-a-run-with-docker-recommended)
3. [Option B: Run without Docker (Manual Setup)](#option-b-run-without-docker-manual-setup)
4. [Opening the Dashboard](#opening-the-dashboard)
5. [Running the Test Simulator](#running-the-test-simulator)
6. [Stopping Everything](#stopping-everything)
7. [Troubleshooting](#troubleshooting)
8. [API Endpoints](#api-endpoints)
9. [Project Structure](#project-structure)
10. [Key Algorithms](#key-algorithms)
11. [Frontend Modules](#frontend-modules)

---

## Prerequisites

### For Docker setup (Option A)
| Software | How to Install |
|----------|---------------|
| **Git** | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **Docker Desktop** | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Python 3.8+** | [python.org/downloads](https://www.python.org/downloads/) (only needed for test simulator) |

### For manual setup (Option B)
| Software | How to Install |
|----------|---------------|
| **Git** | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **Python 3.8+** | [python.org/downloads](https://www.python.org/downloads/) |
| **pip** | Comes with Python. Run `pip --version` to verify |

---

## Step 0: Clone the Repository (All Platforms)

Open a terminal (or Command Prompt / PowerShell on Windows) and run:

```bash
git clone https://github.com/nbharath1306/NATIONAL-SPACE-HACKATHON.git
cd NATIONAL-SPACE-HACKATHON
```

All remaining commands should be run from inside this folder.

---

## Option A: Run with Docker (Recommended)

Docker works identically on **macOS, Windows, and Linux**. This is the recommended method because it handles all dependencies automatically.

### 1. Start Docker Desktop

- **macOS**: Open Docker Desktop from Applications. Wait for the whale icon in the menu bar to stop animating.
- **Windows**: Open Docker Desktop from the Start menu. Wait for "Docker Desktop is running" in the system tray.
- **Linux**: Start the Docker daemon:
  ```bash
  sudo systemctl start docker
  ```

### 2. Build the Docker image

```bash
docker build -t acm .
```

**What this does**: Downloads Ubuntu 22.04, installs Python 3.10, installs all dependencies, copies your code into the container.

**Expected output** (last few lines):
```
Successfully built xxxxxxxxxx
Successfully tagged acm:latest
```

**First build takes 2-3 minutes** (downloads ~200MB). Subsequent builds are cached and take seconds.

### 3. Run the container

```bash
docker run -p 8000:8000 acm
```

**What this does**: Starts the backend server inside the container and maps port 8000 from the container to your machine.

**Expected output**:
```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
ACM Backend started on port 8000
Frontend served at /dashboard
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**Leave this terminal running.** The server must stay alive.

### 4. Verify it works

Open a **new terminal tab/window** and run:

```bash
curl http://localhost:8000/health
```

**Windows (PowerShell)**:
```powershell
Invoke-WebRequest http://localhost:8000/health | Select-Object -ExpandProperty Content
```

**Expected output**:
```json
{"status":"healthy","sim_time_s":0.0,"satellites":50,"debris":0,"active_cdms":0}
```

If you see this, the backend is working. Skip to [Opening the Dashboard](#opening-the-dashboard).

---

## Option B: Run without Docker (Manual Setup)

Use this if you can't install Docker or prefer running natively.

### macOS / Linux

```bash
# 1. Create a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the backend server
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Windows (Command Prompt)

```cmd
:: 1. Create a virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate

:: 2. Install dependencies
pip install -r requirements.txt

:: 3. Start the backend server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Windows (PowerShell)

```powershell
# 1. Create a virtual environment (optional but recommended)
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the backend server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Expected output** is the same as the Docker method — you should see `Uvicorn running on http://0.0.0.0:8000`.

**Leave this terminal running.**

---

## Opening the Dashboard

Once the backend is running (via either method), open your web browser and go to:

```
http://localhost:8000/dashboard
```

You should see the **Orbital Insight** dashboard with:
- A dark space-themed UI with cyan accents
- 5 visualization panels (Ground Track Map, Bullseye, Fuel Heatmap, Gantt, Delta-V)
- 50 demo satellites moving across the map (even without the simulator)

**If you see a blank/black screen**: Hard refresh with `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (macOS).

---

## Running the Test Simulator

The test simulator (`realsim.py`) sends realistic satellite and debris data to the backend. The dashboard switches from demo mode to live data automatically.

### Open a NEW terminal tab/window

**macOS**: `Cmd + T`
**Windows**: Right-click terminal title bar > New Tab, or open a new Command Prompt
**Linux**: `Ctrl + Shift + T`

### Run the simulator

```bash
cd NATIONAL-SPACE-HACKATHON

# Install simulator dependencies (only needed once)
pip install numpy requests

# Run the simulator
python3 realsim.py
```

**Windows**:
```cmd
cd NATIONAL-SPACE-HACKATHON
pip install numpy requests
python realsim.py
```

**Expected output**: A colored terminal dashboard showing satellite positions, fuel levels, and CDM warnings updating every 2 seconds.

**Watch the browser dashboard** — it should now show live data with satellites, debris clouds, and conjunction alerts.

---

## Stopping Everything

### Stop the simulator
Press `Ctrl+C` in the simulator terminal.

### Stop the backend

**If using Docker**:
Press `Ctrl+C` in the Docker terminal. Or from any terminal:
```bash
docker stop $(docker ps -q)
```

**If running without Docker**:
Press `Ctrl+C` in the uvicorn terminal.

### Clean up Docker resources (optional)
```bash
# Remove the container
docker rm $(docker ps -aq)

# Remove the image (to free disk space)
docker rmi acm
```

---

## Troubleshooting

### "Port 8000 is already allocated"

Something else is using port 8000. Kill it:

**macOS / Linux**:
```bash
# Kill whatever is on port 8000
lsof -ti:8000 | xargs kill -9

# Also stop any running Docker containers
docker kill $(docker ps -q) 2>/dev/null
```

**Windows (PowerShell as Admin)**:
```powershell
# Find the process using port 8000
netstat -ano | findstr :8000

# Kill it (replace 12345 with the actual PID from above)
taskkill /PID 12345 /F
```

Then try `docker run -p 8000:8000 acm` again.

### "Cannot connect to the Docker daemon"

Docker Desktop is not running. Open it and wait until it says "Docker Desktop is running", then try again.

### "docker: command not found"

Docker is not installed. Download it from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/).

### Dashboard shows blank/black screen

1. Open browser DevTools (`F12` or `Ctrl+Shift+I`)
2. Go to the **Console** tab
3. Check for red error messages
4. Try hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (macOS)
5. Make sure the backend is still running (check the terminal)

### "python3: command not found" (Windows)

Use `python` instead of `python3`:
```cmd
python realsim.py
```

### "pip: command not found"

Try `pip3` instead of `pip`, or:
```bash
python3 -m pip install -r requirements.txt
```

### Simulator says "Connection refused"

The backend is not running. Start it first (Step 3 in Docker setup, or Step 3 in manual setup), then run the simulator.

### Docker build fails on Apple Silicon (M1/M2/M3)

Add the platform flag:
```bash
docker build --platform linux/amd64 -t acm .
docker run --platform linux/amd64 -p 8000:8000 acm
```

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
NATIONAL-SPACE-HACKATHON/
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
│   ├── index.html             Page layout + CSS
│   └── dashboard.js           5 visualization modules @ 60 FPS
│
├── ACM_Technical_Report.pdf   Technical report
├── ACM_Codebase_Report.pdf    Full codebase analysis
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

---

## Frontend Modules

1. **Ground Track Map** — Mercator projection with satellite trails, terminator line, ground stations
2. **Conjunction Bullseye** — Polar chart showing nearby debris risk (color-coded by severity)
3. **Fleet Fuel Heatmap** — Per-satellite fuel gauges with green/amber/red status
4. **Maneuver Timeline** — Gantt chart of evasion/recovery burns and cooldowns
5. **Delta-V History** — Cumulative fuel usage vs collisions avoided over time
