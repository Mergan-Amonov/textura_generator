"""
PBRForge::Core — Konfiguratsiya v0.3
======================================
Barcha sozlamalar shu fayldan boshqariladi.
.env fayl orqali ham o'rnatish mumkin.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── ComfyUI ulanish sozlamalari ───────────────────────────────────────────────
COMFYUI_HOST = os.getenv("COMFYUI_HOST", "127.0.0.1")
COMFYUI_PORT = os.getenv("COMFYUI_PORT", "8188")
COMFYUI_URL  = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"
COMFYUI_WS   = f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}/ws"

# ── Model sozlamalari ─────────────────────────────────────────────────────────
CHECKPOINT_NAME = os.getenv(
    "CHECKPOINT_NAME",
    "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
)

DEFAULT_NEGATIVE = (
    "blurry, low quality, distorted, artifacts, jpeg artifacts, noise, "
    "watermark, signature, text, logo, 3d render, painting, illustration, "
    "oversaturated, overexposed, underexposed"
)

# ── Generatsiya standart sozlamalari (SDXL uchun optimallashtirilgan) ─────────
DEFAULT_STEPS     = int(os.getenv("DEFAULT_STEPS",    "35"))
DEFAULT_CFG       = float(os.getenv("DEFAULT_CFG",     "7.0"))
DEFAULT_SAMPLER   = os.getenv("DEFAULT_SAMPLER",       "dpmpp_2m_sde")
DEFAULT_SCHEDULER = os.getenv("DEFAULT_SCHEDULER",     "karras")

# ── 4K Upscaling ──────────────────────────────────────────────────────────────
# ESRGAN modeli: ComfyUI/models/upscale_models/ ga joylashtiring
#   Tavsiya: 4x_NMKD-Siax_200k.pth  yoki  RealESRGAN_x4plus.pth
# Agar model bo'lmasa — Lanczos bilan avtomatik fallback qiladi
UPSCALE_MODEL     = os.getenv("UPSCALE_MODEL",     "4x_NMKD-Siax_200k.pth")
OUTPUT_RESOLUTION = int(os.getenv("OUTPUT_RESOLUTION", "4096"))

# ── Fayl saqlash ──────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR  = os.path.join(BASE_DIR, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

JOB_TTL_SECONDS = int(os.getenv("JOB_TTL", "3600"))

# ── API server ─────────────────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ── Post-processing ───────────────────────────────────────────────────────────
NORMAL_STRENGTH   = float(os.getenv("NORMAL_STRENGTH",   "4.0"))
ROUGHNESS_GAMMA   = float(os.getenv("ROUGHNESS_GAMMA",   "1.2"))
AO_BLUR_SIGMA     = float(os.getenv("AO_BLUR_SIGMA",     "4.0"))
SEAMLESS_BLEND_PX = int(os.getenv("SEAMLESS_BLEND_PX",  "64"))
DELIT_SIGMA_PCT   = float(os.getenv("DELIT_SIGMA_PCT",   "0.10"))  # 10% of image width

# ── Xavfsizlik va limitlar ────────────────────────────────────────────────────
MAX_REF_IMAGE_MB    = int(os.getenv("MAX_REF_IMAGE_MB", "5"))
MAX_REF_IMAGE_BYTES = MAX_REF_IMAGE_MB * 1024 * 1024
MAX_REF_DIMENSION   = int(os.getenv("MAX_REF_DIMENSION", "1024"))

# Job uchun vaqt limiti (ComfyUI generatsiya + 4K upscale)
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT", "600"))
