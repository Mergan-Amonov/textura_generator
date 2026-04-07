"""
PBRForge::Core — Generate Router v0.3
=======================================
REST API endpointlar:
  POST  /api/analyze             — Rasmni LLaVA bilan tahlil qilish + prompt generatsiya
  POST  /api/generate            — Yangi generatsiya boshlash
  GET   /api/status/{job_id}     — Generatsiya holati (polling)
  GET   /api/download/{job_id}   — ZIP arxiv yuklab olish
  GET   /api/comfyui-status      — ComfyUI ulanish holati
  GET   /api/ollama-status       — Ollama ulanish holati
  GET   /api/models              — O'rnatilgan modellar ro'yxati
"""

import asyncio
import logging
import os
import time
import uuid
import zipfile
from functools import partial
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import (
    JOBS_DIR, JOB_TTL_SECONDS,
    NORMAL_STRENGTH, ROUGHNESS_GAMMA, AO_BLUR_SIGMA, SEAMLESS_BLEND_PX,
    DELIT_SIGMA_PCT,
    MAX_REF_IMAGE_BYTES, MAX_REF_DIMENSION,
    JOB_TIMEOUT_SECONDS,
)
from services.comfy_client import is_comfyui_running, get_comfyui_models, generate_albedo
from services.image_processor import process_all_maps, maps_to_previews
from services.vision_service import is_ollama_running, analyze_image_with_llava, enhance_prompt_with_llm, chat_with_llm
from services.prompt_builder import build_pbr_prompt, build_pbr_prompt_from_text

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory job registry ────────────────────────────────────────────────────
_jobs: dict[str, dict] = {}

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ──────────────────────────────────────────────────────────────────────────────
#  Schemalar
# ──────────────────────────────────────────────────────────────────────────────

class JobStatus(BaseModel):
    job_id:   str
    status:   str          # queued | generating | postprocessing | done | error
    progress: int = 0
    error:    Optional[str] = None
    previews: Optional[dict] = None


class AnalyzeResponse(BaseModel):
    success:     bool
    prompt:      str
    negative:    str
    category:    str           # fabric | leather | wood | metal | general
    use_img2img: bool
    description: str           # LLaVA xom tavsifi
    error:       Optional[str] = None


class EnhancePromptRequest(BaseModel):
    user_text: str


class EnhancePromptResponse(BaseModel):
    success:    bool
    prompt:     str
    model_used: Optional[str] = None
    fallback:   bool = False
    error:      Optional[str] = None


class ChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    success:    bool
    reply:      str
    prompt:     Optional[str] = None   # SDXL prompt, agar tayyor bo'lsa
    model_used: Optional[str] = None
    error:      Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
#  Yordamchi
# ──────────────────────────────────────────────────────────────────────────────

def _update_job(job_id: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)


def _cleanup_old_jobs():
    now = time.time()
    to_delete = [
        jid for jid, info in _jobs.items()
        if now - info.get("created_at", now) > JOB_TTL_SECONDS
    ]
    for jid in to_delete:
        zip_path = _jobs[jid].get("zip_path")
        if zip_path and os.path.exists(zip_path):
            os.remove(zip_path)
        del _jobs[jid]


def _downscale_reference(image_bytes: bytes, max_dim: int) -> bytes:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Referens rasm o'qilmadi")

    h, w = img.shape[:2]
    if h <= max_dim and w <= max_dim:
        return image_bytes

    scale = max_dim / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    ok, buf = cv2.imencode(".png", resized)
    if not ok:
        raise RuntimeError("Referens rasm encode qilinmadi")
    return bytes(buf)


def _validate_image(raw: bytes, content_type: str) -> bytes:
    """Rasm validatsiyasi va downscale."""
    content_type = (content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Faqat JPEG, PNG, WEBP formatlar ruxsat etiladi",
        )
    if len(raw) > MAX_REF_IMAGE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Rasm hajmi {MAX_REF_IMAGE_BYTES // 1024 // 1024}MB dan oshmasligi kerak",
        )
    return _downscale_reference(raw, MAX_REF_DIMENSION)


# ──────────────────────────────────────────────────────────────────────────────
#  Fon generatsiya vazifasi
# ──────────────────────────────────────────────────────────────────────────────

async def _run_generation(
    job_id: str,
    prompt: str,
    resolution: int,
    seed: int,
    reference_bytes: Optional[bytes],
    material_name: str,
    use_img2img: bool,
):
    try:
        _update_job(job_id, status="generating", progress=5)

        def on_progress(event: dict):
            step  = event.get("step", 0)
            total = max(event.get("total", 1), 1)
            pct   = int(step / total * 75) + 5
            _update_job(job_id, progress=pct)

        # ── ComfyUI generatsiya ───────────────────────────────────────────────
        try:
            albedo_bytes = await asyncio.wait_for(
                generate_albedo(
                    prompt=prompt,
                    resolution=resolution,
                    reference_bytes=reference_bytes if use_img2img else None,
                    seed=seed,
                    on_progress=on_progress,
                ),
                timeout=float(JOB_TIMEOUT_SECONDS),
            )
        except asyncio.TimeoutError:
            logger.error(f"[{job_id}] Timeout: {JOB_TIMEOUT_SECONDS}s oshdi")
            _update_job(
                job_id, status="error",
                error=f"Timeout: {JOB_TIMEOUT_SECONDS} soniya ichida generatsiya tugamadi",
                progress=0,
            )
            return

        _update_job(job_id, status="postprocessing", progress=82)

        # ── ProcessPoolExecutor — OpenCV hisob-kitoblar ───────────────────────
        from main import process_pool
        loop = asyncio.get_running_loop()

        fn = partial(
            process_all_maps,
            material_name=material_name,
            normal_strength=NORMAL_STRENGTH,
            roughness_gamma=ROUGHNESS_GAMMA,
            ao_blur_sigma=AO_BLUR_SIGMA,
            seamless_blend_px=SEAMLESS_BLEND_PX,
            delit_sigma_pct=DELIT_SIGMA_PCT,
        )
        maps = await loop.run_in_executor(process_pool, fn, albedo_bytes)

        _update_job(job_id, progress=93)

        # ── ZIP yaratish ──────────────────────────────────────────────────────
        zip_path = os.path.join(JOBS_DIR, f"{job_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for map_type, data in maps.items():
                zf.writestr(f"{material_name}_{map_type}.jpg", data)

        previews = maps_to_previews(maps)

        _update_job(
            job_id,
            status   = "done",
            progress = 100,
            zip_path = zip_path,
            previews = previews,
        )
        logger.info(f"[{job_id}] Generatsiya tugadi")

    except Exception as e:
        logger.error(f"[{job_id}] Xato: {e}", exc_info=True)
        _update_job(job_id, status="error", error=str(e), progress=0)


# ──────────────────────────────────────────────────────────────────────────────
#  Endpointlar
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/comfyui-status")
async def comfyui_status():
    running = await is_comfyui_running()
    return {"connected": running, "url": "http://127.0.0.1:8188"}


@router.get("/ollama-status")
async def ollama_status():
    running = await is_ollama_running()
    return {"connected": running, "url": "http://127.0.0.1:11434"}


@router.get("/models")
async def list_models():
    models = await get_comfyui_models()
    return {"models": models}


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_image(
    image:     UploadFile = File(...),
    user_hint: str        = Form(""),
):
    """
    Referens rasmni LLaVA bilan tahlil qiladi va PBR prompt qaytaradi.
    Frontend bu promptni foydalanuvchiga ko'rsatadi — u tahrirlashi mumkin.
    """
    if not await is_ollama_running():
        raise HTTPException(
            status_code=503,
            detail="Ollama ishga tushirilmagan. Terminal: ollama serve",
        )

    raw = await image.read()
    image_bytes = _validate_image(raw, image.content_type or "")

    # LLaVA tahlil
    vision_result = await analyze_image_with_llava(image_bytes)

    if not vision_result["success"]:
        raise HTTPException(
            status_code=500,
            detail=vision_result["error"] or "Vision tahlil xatosi",
        )

    # Prompt qurish
    pbr = build_pbr_prompt(
        vision_description=vision_result["description"],
        user_hint=user_hint,
    )

    return AnalyzeResponse(
        success     = True,
        prompt      = pbr["prompt"],
        negative    = pbr["negative"],
        category    = pbr["category"],
        use_img2img = pbr["use_img2img"],
        description = vision_result["description"],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    """
    LLM bilan multi-turn suhbat — texture tavsifidan SDXL prompt yaratadi.
    LLM javobida PROMPT: bo'lsa, u ajratib qaytariladi.
    """
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    result = await chat_with_llm(messages)
    return ChatResponse(
        success    = result["success"],
        reply      = result["reply"],
        prompt     = result.get("prompt"),
        model_used = result.get("model_used"),
        error      = result.get("error"),
    )


@router.post("/enhance-prompt", response_model=EnhancePromptResponse)
async def enhance_prompt_endpoint(body: EnhancePromptRequest):
    """
    Foydalanuvchi qisqa matni → to'liq SDXL PBR texture prompt.
    Ollama text modeli ishlatiladi; model bo'lmasa mahalliy fallback.
    """
    text = body.user_text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Matn bo'sh bo'lmasligi kerak")

    result = await enhance_prompt_with_llm(text)
    return EnhancePromptResponse(
        success    = result["success"],
        prompt     = result["prompt"],
        model_used = result.get("model_used"),
        fallback   = result.get("fallback", False),
        error      = result.get("error"),
    )


@router.post("/generate", response_model=JobStatus)
async def start_generate(
    background_tasks: BackgroundTasks,
    prompt:           str                  = Form(...),
    resolution:       int                  = Form(1024),
    seed:             int                  = Form(-1),
    use_img2img:      bool                 = Form(False),
    reference_image:  Optional[UploadFile] = File(None),
):
    """
    Yangi PBR texture generatsiya boshlaydi.
    Darhol job_id qaytaradi — progress GET /api/status/{job_id} orqali kuzatiladi.
    """
    _cleanup_old_jobs()

    if not await is_comfyui_running():
        raise HTTPException(
            status_code=503,
            detail="ComfyUI ishga tushirilmagan. Iltimos dasturni yoqing.",
        )

    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Texture tavsifini kiriting")

    if resolution not in (512, 1024, 2048):
        resolution = 1024

    # ── Referens rasm validatsiyasi ───────────────────────────────────────────
    reference_bytes: Optional[bytes] = None
    if reference_image and reference_image.filename:
        raw = await reference_image.read()
        reference_bytes = _validate_image(raw, reference_image.content_type or "")

    # Referens rasm bo'lsa — img2img avtomatik yoqiladi
    # (foydalanuvchi toggle qilishiga hojat yo'q)
    if reference_bytes:
        use_img2img = True

    # Material nomi promptdan
    words = prompt.replace(",", "").split()[:3]
    material_name = "_".join(w.capitalize() for w in words) or "Material"

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status":     "queued",
        "progress":   0,
        "error":      None,
        "zip_path":   None,
        "previews":   None,
        "created_at": time.time(),
        "prompt":     prompt,
    }

    background_tasks.add_task(
        _run_generation,
        job_id          = job_id,
        prompt          = prompt,
        resolution      = resolution,
        seed            = seed,
        reference_bytes = reference_bytes,
        material_name   = material_name,
        use_img2img     = use_img2img,
    )

    logger.info(f"[{job_id}] Boshlandi: '{prompt[:60]}' | img2img={use_img2img}")
    return JobStatus(job_id=job_id, status="queued", progress=0)


@router.get("/status/{job_id}", response_model=JobStatus)
async def job_status(job_id: str):
    info = _jobs.get(job_id)
    if not info:
        raise HTTPException(status_code=404, detail="Job topilmadi")

    return JobStatus(
        job_id   = job_id,
        status   = info["status"],
        progress = info["progress"],
        error    = info.get("error"),
        previews = info.get("previews") if info["status"] == "done" else None,
    )


@router.get("/download/{job_id}")
async def download_zip(job_id: str):
    info = _jobs.get(job_id)
    if not info:
        raise HTTPException(status_code=404, detail="Job topilmadi")
    if info["status"] != "done":
        raise HTTPException(status_code=400, detail="Generatsiya hali tugamagan")

    zip_path = info.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="ZIP fayl topilmadi")

    words = info.get("prompt", "material").replace(",", "").split()[:3]
    name  = "_".join(w.capitalize() for w in words) + "_PBR.zip"

    return FileResponse(path=zip_path, media_type="application/zip", filename=name)
