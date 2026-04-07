"""
PBRForge::Core — Vision Service (Ollama LLaVA)
===============================================
Referens rasmni LLaVA vision modeli orqali tahlil qiladi.
Mebel teksturasi uchun aniq, PBR-friendly tavsif qaytaradi.

Ollama API: http://localhost:11434/api/generate
Model: llava:7b (yoki llava:7b-v1.6-mistral-q4_0)
"""

import base64
import json
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "llava:7b"
TIMEOUT = 300.0  # 5 daqiqa — birinchi yuklanishda model GPU ga o'tadi

SYSTEM_PROMPT = """You are a texture and material specialist.
Your only job: describe the SURFACE MATERIAL visible in the image as a Stable Diffusion prompt.
Rules:
- NEVER mention furniture, sofa, chair, cushion, room or any objects
- NEVER say "on a sofa" or "upholstery" or "furniture fabric"
- ONLY describe: material type, color, texture, pattern, finish
- Output: one short phrase like "dark navy blue velvet fabric, tight pile, soft sheen"
- No sentences. No objects. Just material properties."""

USER_PROMPT = """What material/texture is this? Describe ONLY:
1. Material type (velvet, leather, linen, wool, wood grain, etc.)
2. Color
3. Surface feel (rough/smooth/matte/shiny/soft)
4. Pattern if any (plain, geometric, woven, etc.)

Short phrase only. No furniture. No objects. Example output: "beige linen fabric, medium weave, matte finish" """


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
        timeout = httpx.Timeout(connect=10.0, read=TIMEOUT, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
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


# ─────────────────────────────────���────────────────────────────��───────────────
#  Mebel qismlari tahlili
# ──────────────────────────────────────────────────────────────────────────────

PARTS_PROMPT = """Look at this furniture image. List each visible part and its material.

Return ONLY a JSON array, nothing else. Example:
[
  {"part": "legs", "material": "oak wood grain", "category": "wood"},
  {"part": "seat cushion", "material": "gray velvet fabric", "category": "fabric"},
  {"part": "backrest", "material": "dark leather", "category": "leather"}
]

Categories must be one of: fabric, leather, wood, metal, plastic, glass, general

Only include parts that are clearly visible. Maximum 6 parts. JSON only, no explanation."""


async def analyze_furniture_parts(image_bytes: bytes) -> dict:
    """
    Mebel rasmini tahlil qilib qismlarini va materiallarini aniqlaydi.

    Returns:
        {
            "parts": [{"part": str, "material": str, "category": str}, ...],
            "success": bool,
            "error": str | None,
        }
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    available = await get_available_vision_models()
    model = VISION_MODEL
    if model not in available:
        llava_models = [m for m in available if "llava" in m.lower()]
        if not llava_models:
            return {"parts": [], "success": False, "error": "LLaVA model topilmadi"}
        model = llava_models[0]

    payload = {
        "model": model,
        "prompt": PARTS_PROMPT,
        "images": [image_b64],
        "stream": False,
        "options": {
            "temperature": 0.1,   # Juda past — aniq JSON kerak
            "num_predict": 400,
        },
    }

    try:
        timeout = httpx.Timeout(connect=10.0, read=TIMEOUT, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()

        response = data.get("response", "").strip()
        logger.info(f"Parts raw response: {response[:200]}")

        # JSON ni response dan ajratib olish
        json_match = re.search(r'\[.*?\]', response, re.DOTALL)
        if not json_match:
            return {"parts": [], "success": False, "error": "JSON topilmadi"}

        parts = json.loads(json_match.group())

        # Validatsiya
        valid_categories = {"fabric", "leather", "wood", "metal", "plastic", "glass", "general"}
        cleaned = []
        for p in parts:
            if isinstance(p, dict) and "part" in p and "material" in p:
                cat = p.get("category", "general").lower()
                if cat not in valid_categories:
                    cat = "general"
                cleaned.append({
                    "part":     str(p["part"]),
                    "material": str(p["material"]),
                    "category": cat,
                })

        logger.info(f"Topilgan qismlar: {len(cleaned)} ta")
        return {"parts": cleaned, "success": True, "error": None}

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse xato: {e} | response: {response[:200]}")
        return {"parts": [], "success": False, "error": "JSON parse xatosi"}
    except httpx.TimeoutException:
        return {"parts": [], "success": False, "error": f"Timeout: {TIMEOUT}s"}
    except Exception as e:
        logger.error(f"Parts xato: {e}", exc_info=True)
        return {"parts": [], "success": False, "error": str(e)}
