"""
PBRForge::Core — FastAPI Backend v0.2
=======================================
Ishga tushirish:
    pip install -r requirements.txt
    python main.py

Yoki:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Frontend (React/Vite) alohida port da ishlaydi: http://localhost:5173
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import API_HOST, API_PORT, COMFYUI_URL

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pbrforge")

# ── ProcessPoolExecutor (og'ir OpenCV hisob-kitoblar uchun) ──────────────────
process_pool = ProcessPoolExecutor(max_workers=2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ProcessPoolExecutor ishga tushdi (max_workers=2)")
    yield
    process_pool.shutdown(wait=False)
    logger.info("ProcessPoolExecutor to'xtatildi")


# ── FastAPI ilova ─────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "PBRForge::Core API",
    description = "PBR Texture Generator — ComfyUI integratsiyali lokal API",
    version     = "0.2.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan,
)

# ── CORS (React frontend localhost:5173 dan so'rov yuboradi) ──────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Routerlar ─────────────────────────────────────────────────────────────────
from routers.generate import router as generate_router
app.include_router(generate_router, prefix="/api", tags=["Generate"])


# ── Health endpointlar ────────────────────────────────────────────────────────
@app.get("/info", tags=["Health"])
async def root():
    return {
        "app":     "PBRForge::Core",
        "version": "0.2.0",
        "status":  "running",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


# ── Global xato ushlash ───────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error(f"Kutilmagan xato: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Server ichki xatosi. Loglarni tekshiring."},
    )


# ── Ishga tushirish ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 55)
    logger.info("  PBRForge::Core Backend v0.2.0")
    logger.info(f"  API:     http://localhost:{API_PORT}")
    logger.info(f"  Docs:    http://localhost:{API_PORT}/docs")
    logger.info(f"  ComfyUI: {COMFYUI_URL}")
    logger.info(f"  Frontend: http://localhost:5173")
    logger.info("=" * 55)

    uvicorn.run(
        "main:app",
        host      = API_HOST,
        port      = API_PORT,
        reload    = True,
        log_level = "info",
    )
