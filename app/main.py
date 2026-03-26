# app/main.py

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import router

# ─── Structured Logging ──────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "acm.log"), mode="a"),
    ],
)

# Separate maneuver log for scoring
maneuver_logger = logging.getLogger("acm.maneuvers")
mh = logging.FileHandler(os.path.join(LOG_DIR, "maneuvers.log"), mode="a")
mh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
maneuver_logger.addHandler(mh)

# Separate collision log
collision_logger = logging.getLogger("acm.collisions")
ch = logging.FileHandler(os.path.join(LOG_DIR, "collisions.log"), mode="a")
ch.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
collision_logger.addHandler(ch)

logger = logging.getLogger("acm.main")

# ─── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Autonomous Constellation Manager",
    description="Orbital Debris Avoidance & Constellation Management System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# ─── Serve Frontend Static Files ─────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")

    @app.get("/dashboard")
    async def serve_dashboard():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/")
def root():
    return {"message": "ACM Backend Running"}


@app.on_event("startup")
async def startup_event():
    logger.info("ACM Backend started on port 8000")
    logger.info(f"Frontend served at /dashboard")
    logger.info(f"Logs directory: {LOG_DIR}")
