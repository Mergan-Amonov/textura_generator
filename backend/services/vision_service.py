"""
PBRForge::Core — Vision Service (Ollama LLaVA)
===============================================
Referens rasmni LLaVA vision modeli orqali tahlil qiladi.
Mebel teksturasi uchun aniq, PBR-friendly tavsif qaytaradi.

Ollama API: http://localhost:11434/api/generate
Model: llava:7b (yoki llava:7b-v1.6-mistral-q4_0)
"""

import base64
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "llava:7b"
TIMEOUT = 60.0

SYSTEM_PROMPT = """You are a material and texture expert for 3D furniture models.
Analyze the image and describe the texture/material in detail for PBR texture generation.
Focus on: material type, color, surface finish, pattern, weave/grain, reflectivity.
Be specific and concise. Do NOT describe furniture shape or objects — only the surface material.
Output: one detailed sentence suitable for a Stable Diffusion prompt."""

USER_PROMPT = """Describe this texture/material for PBR texture generation.
Focus on: fabric type OR leather type OR wood grain OR other material,
exact color, surface texture (rough/smooth/shiny/matte),
pattern (plain/geometric/floral/woven), pile height if fabric.
One sentence only, no furniture description."""


async def is_ollama_running() -> bool:
    """Ollama server ishga tushganligini tekshiradi."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def get_available_vision_models() -> list[str]:
    """O'rnatilgan vision modellar ro'yxati."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


async def analyze_image_with_llava(image_bytes: bytes) -> dict:
    """
    Rasmni LLaVA bilan tahlil qiladi.

    Returns:
        {
            "description": str,   — material tavsifi
            "model_used": str,    — ishlatilgan model nomi
            "success": bool,
            "error": str | None,
        }
    """
    # Rasmni base64 ga o'girish
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Model tanlash (llava:7b mavjud bo'lmasa boshqasini topish)
    model = VISION_MODEL
    available = await get_available_vision_models()

    if model not in available:
        # llava o'z nomida turishi mumkin (llava:latest, llava:7b-v1.6...)
        llava_models = [m for m in available if "llava" in m.lower()]
        if llava_models:
            model = llava_models[0]
            logger.info(f"Vision model: '{model}' ishlatilmoqda")
        else:
            logger.error(f"Hech qanday llava model topilmadi. Mavjud: {available}")
            return {
                "description": "",
                "model_used": None,
                "success": False,
                "error": "LLaVA model o'rnatilmagan. Terminal: ollama pull llava:7b",
            }

    payload = {
        "model": model,
        "prompt": f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}",
        "images": [image_b64],
        "stream": False,
        "options": {
            "temperature": 0.3,   # Past temperatura — aniq, konsistent tavsif
            "num_predict": 150,   # Maksimal token (1 ta gap yetarli)
        },
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()

        description = data.get("response", "").strip()

        if not description:
            return {
                "description": "",
                "model_used": model,
                "success": False,
                "error": "Model bo'sh javob qaytardi",
            }

        logger.info(f"Vision tahlil: '{description[:100]}...'")
        return {
            "description": description,
            "model_used": model,
            "success": True,
            "error": None,
        }

    except httpx.TimeoutException:
        return {
            "description": "",
            "model_used": model,
            "success": False,
            "error": f"Timeout: {TIMEOUT}s ichida javob kelmadi. Model yuklanayaptimi?",
        }
    except Exception as e:
        logger.error(f"Vision xato: {e}", exc_info=True)
        return {
            "description": "",
            "model_used": model,
            "success": False,
            "error": str(e),
        }
