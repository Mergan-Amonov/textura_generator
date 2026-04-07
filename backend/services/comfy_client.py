"""
PBRForge::Core — ComfyUI Client v0.3  (4K Edition)
====================================================
Arxitektura:
  1. AI generatsiya: SD 1.5 Hires Fix → 1024px albedo
  2. 4K upscale: ESRGAN 4x → 4096px (model yo'q bo'lsa Lanczos fallback)
  3. Natija: 4096×4096 albedo → image_processor.py → 6 PBR xarita

Timeout: generate_albedo() ni asyncio.wait_for() bilan o'rash
         chaqiruvchi kod (generate.py) amalga oshiradi.
"""

import asyncio
import json
import uuid
import logging
import random
from typing import Optional, Callable, AsyncGenerator

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from config import (
    COMFYUI_URL, COMFYUI_WS,
    CHECKPOINT_NAME,
    DEFAULT_STEPS, DEFAULT_CFG,
    DEFAULT_SAMPLER, DEFAULT_SCHEDULER,
    DEFAULT_NEGATIVE,
    UPSCALE_MODEL, OUTPUT_RESOLUTION,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  Ulanish tekshirish
# ──────────────────────────────────────────────────────────────────────────────

async def is_comfyui_running() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{COMFYUI_URL}/system_stats")
            return r.status_code == 200
    except Exception:
        return False


async def get_comfyui_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple")
            data = r.json()
            return data["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except Exception:
        return []


async def get_comfyui_upscale_models() -> list[str]:
    """O'rnatilgan ESRGAN/upscale modellar ro'yxati."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{COMFYUI_URL}/object_info/UpscaleModelLoader")
            data = r.json()
            result = data["UpscaleModelLoader"]["input"]["required"]["model_name"][0]
            # list bo'lishi kerak — string kelsa bo'sh qaytaramiz
            if not isinstance(result, list):
                return []
            return result
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
#  Referens rasm yuklash
# ──────────────────────────────────────────────────────────────────────────────

def _prepare_texture_patch(image_bytes: bytes, target: int = 1024) -> bytes:
    """
    Furniture fotosidan tekstura patch ajratib oladi.

    Muammo: foydalanuvchi mebel rasmi yuklaydi, lekin bizga
    material yuzasining closeup patchasi kerak.

    Yechim:
      1. Eng ko'p teksturali (yuqori Laplacian variance) mintaqani topish
      2. Markaziy zone dan square crop
      3. target × target ga resize
    """
    import cv2
    import numpy as np

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Eng teksturali mintaqani topish (sliding window, Laplacian variance)
    step     = max(1, min(h, w) // 12)
    win_size = min(h, w) // 3
    best_var  = -1.0
    best_y, best_x = (h - win_size) // 2, (w - win_size) // 2

    for y in range(0, h - win_size, step):
        for x in range(0, w - win_size, step):
            patch = gray[y:y + win_size, x:x + win_size]
            var   = cv2.Laplacian(patch, cv2.CV_64F).var()
            if var > best_var:
                best_var = var
                best_y, best_x = y, x

    crop = img[best_y:best_y + win_size, best_x:best_x + win_size]
    resized = cv2.resize(crop, (target, target), interpolation=cv2.INTER_LANCZOS4)

    _, buf = cv2.imencode(".png", resized)
    logger.info(f"Texture patch ajratildi: {win_size}×{win_size} → {target}×{target} (var={best_var:.0f})")
    return bytes(buf)


async def upload_image_to_comfyui(
    image_bytes: bytes,
    filename: str = "pbrforge_ref.png",
    prepare_patch: bool = True,
) -> str:
    if prepare_patch:
        image_bytes = _prepare_texture_patch(image_bytes)

    async with httpx.AsyncClient(timeout=30.0) as client:
        files = {"image": (filename, image_bytes, "image/png")}
        r = await client.post(f"{COMFYUI_URL}/upload/image", files=files)
        r.raise_for_status()
        data = r.json()
    uploaded_name = data.get("name", filename)
    logger.info(f"Referens rasm yuklandi: {uploaded_name}")
    return uploaded_name


# ──────────────────────────────────────────────────────────────────────────────
#  Prompt builder
# ──────────────────────────────────────────────────────────────────────────────

def _pbr_prompt(user_prompt: str) -> str:
    """Foydalanuvchi promptini PBR tavsifiga kengaytiradi.
    Material tavsifi boshida turadi — CLIP diqqati unga qaratiladi.
    """
    return (
        user_prompt
        + ", seamless tileable texture, pbr albedo map, "
        "flat evenly lit, no shadows, photorealistic, 4k"
    )


# ──────────────────────────────────────────────────────────────────────────────
#  4K Workflow: upscale nodes (ESRGAN yoki Lanczos)
# ──────────────────────────────────────────────────────────────────────────────

def _append_upscale_nodes(
    workflow: dict,
    image_node: str,        # Dekodlangan rasm chiqadigan node ID
    output_resolution: int, # Maqsadli o'lcham (4096)
    upscale_model: Optional[str],  # ESRGAN model nomi yoki None
    start_id: int,          # Yangi nodelar boshlash ID raqami
) -> str:
    """
    Workflow ga upscale nodelar qo'shadi.
    upscale_model berilsa → ESRGAN 4x → ImageScale to exact output_resolution
    upscale_model yo'q    → ImageScale Lanczos to output_resolution

    Returns: SaveImage node ID
    """
    i = start_id

    if upscale_model:
        # ESRGAN: 4x upscale (1024 → 4096)
        workflow[str(i)] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": upscale_model},
        }
        loader_id = str(i); i += 1

        workflow[str(i)] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": [loader_id, 0],
                "image": [image_node, 0],
            },
        }
        esrgan_id = str(i); i += 1

        # Exact size guarantee (ESRGAN 4x ko'pincha to'liq karrali beradi, lekin...)
        workflow[str(i)] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": [esrgan_id, 0],
                "upscale_method": "lanczos",
                "width": output_resolution,
                "height": output_resolution,
                "crop": "disabled",
            },
        }
        scale_id = str(i); i += 1

        workflow[str(i)] = {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "PBRForge_albedo", "images": [scale_id, 0]},
        }

    else:
        # Lanczos fallback (ESRGAN model o'rnatilmagan)
        logger.warning(
            f"ESRGAN model topilmadi — Lanczos bilan {output_resolution}px ga upscale qilinmoqda. "
            "Sifatli 4K uchun ComfyUI/models/upscale_models/ ga "
            "'4x_NMKD-Siax_200k.pth' yoki 'RealESRGAN_x4plus.pth' joylashtiring."
        )
        workflow[str(i)] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": [image_node, 0],
                "upscale_method": "lanczos",
                "width": output_resolution,
                "height": output_resolution,
                "crop": "disabled",
            },
        }
        scale_id = str(i); i += 1

        workflow[str(i)] = {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "PBRForge_albedo", "images": [scale_id, 0]},
        }

    return str(i)  # SaveImage node ID


# ──────────────────────────────────────────────────────────────────────────────
#  4K Txt2Img Workflow (Hires Fix → ESRGAN 4K)
# ──────────────────────────────────────────────────────────────────────────────

def build_txt2img_4k_workflow(
    prompt: str,
    output_resolution: int = OUTPUT_RESOLUTION,
    seed: int = -1,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    sampler: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    negative: str = DEFAULT_NEGATIVE,
    checkpoint: str = CHECKPOINT_NAME,
    upscale_model: Optional[str] = None,
) -> dict:
    """
    Text → 4K Albedo workflow.

    Bosqichlar:
      1. Base pass: 512×512, denoise=1.0
      2. LatentUpscale: 512 → 1024
      3. Hires pass: 1024×1024, denoise=0.50 (detallar, kompozitsiya o'zgarmaydi)
      4. VAEDecode: 1024px rasm
      5. ESRGAN 4x → 4096px (yoki Lanczos fallback)
    """
    if seed < 0:
        seed = random.randint(0, 2 ** 32 - 1)

    full_prompt = _pbr_prompt(prompt)

    workflow = {
        # ── Model va CLIP ──────────────────────────────────────────────────────
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": full_prompt}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},

        # ── Bosqich 1: Base 1024×1024 generatsiya (SDXL native) ───────────────
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                "latent_image": ["4", 0], "seed": seed, "steps": steps,
                "cfg": cfg, "sampler_name": sampler, "scheduler": scheduler,
                "denoise": 1.0,
            },
        },

        # ── VAE Decode → 1024px rasm ───────────────────────────────────────────
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
    }

    # ── 4K Upscale (ESRGAN yoki Lanczos) ──────────────────────────────────────
    _append_upscale_nodes(workflow, "8", output_resolution, upscale_model, start_id=9)

    return workflow


# ──────────────────────────────────────────────────────────────────────────────
#  4K Img2Img Workflow (referens → img2img → ESRGAN 4K)
# ──────────────────────────────────────────────────────────────────────────────

def build_img2img_4k_workflow(
    prompt: str,
    image_filename: str,
    output_resolution: int = OUTPUT_RESOLUTION,
    denoise: float = 0.82,
    seed: int = -1,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    sampler: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    negative: str = DEFAULT_NEGATIVE,
    checkpoint: str = CHECKPOINT_NAME,
    upscale_model: Optional[str] = None,
) -> dict:
    """
    Referens rasm + matn → 4K Albedo workflow (SDXL).

    Bosqichlar:
      1. Referens rasmni yuklash va 1024×1024 ga scale qilish
      2. VAEEncode → KSampler img2img (denoise=0.65, referens saqlanadi)
      3. VAEDecode → 1024px
      4. ESRGAN 4x → 4096px (yoki Lanczos fallback)
    """
    if seed < 0:
        seed = random.randint(0, 2 ** 32 - 1)

    full_prompt = _pbr_prompt(prompt)

    workflow = {
        # ── Model va CLIP ──────────────────────────────────────────────────────
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": full_prompt}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},

        # ── Referens rasm yuklash va scale ────────────────────────────────────
        "4": {"class_type": "LoadImage", "inputs": {"image": image_filename}},
        "5": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["4", 0], "upscale_method": "lanczos",
                "width": 1024, "height": 1024, "crop": "center",
            },
        },
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}},

        # ── img2img pass ──────────────────────────────────────────────────────
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                "latent_image": ["6", 0], "seed": seed, "steps": steps,
                "cfg": cfg, "sampler_name": sampler, "scheduler": scheduler,
                "denoise": denoise,
            },
        },

        # ── VAE Decode → 1024px rasm ───────────────────────────────────────────
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
    }

    # ── 4K Upscale ────────────────────────────────────────────────────────────
    _append_upscale_nodes(workflow, "8", output_resolution, upscale_model, start_id=9)

    return workflow


# ──────────────────────────────────────────────────────────────────────────────
#  Workflow yuborish va progress kuzatish
# ──────────────────────────────────────────────────────────────────────────────

async def queue_prompt(workflow: dict) -> tuple[str, str]:
    client_id = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        r.raise_for_status()
        data = r.json()

    prompt_id = data["prompt_id"]
    logger.info(f"Workflow yuborildi. prompt_id={prompt_id}")
    return prompt_id, client_id


async def stream_progress(
    prompt_id: str,
    client_id: str,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> AsyncGenerator[dict, None]:
    """
    ComfyUI WebSocket orqali generatsiya progressini kuzatadi.
    AI generatsiya (5..80%) + upscale (80..95%) bosqichlari mavjud.
    """
    ws_url = f"{COMFYUI_WS}?clientId={client_id}"

    try:
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
                except asyncio.TimeoutError:
                    continue

                if isinstance(raw, bytes):
                    continue

                msg   = json.loads(raw)
                mtype = msg.get("type", "")

                if mtype == "progress":
                    data  = msg.get("data", {})
                    event = {
                        "type":  "progress",
                        "step":  data.get("value", 0),
                        "total": max(data.get("max", 1), 1),
                    }
                    if on_progress:
                        on_progress(event)
                    yield event

                elif mtype == "executing":
                    data = msg.get("data", {})
                    if data.get("node") is None:
                        pid = data.get("prompt_id")
                        if pid is None or pid == prompt_id:
                            yield {"type": "done"}
                            return

                elif mtype == "execution_success":
                    pid = msg.get("data", {}).get("prompt_id")
                    if pid is None or pid == prompt_id:
                        yield {"type": "done"}
                        return

                elif mtype == "execution_error":
                    error = msg.get("data", {}).get("exception_message", "Noma'lum xato")
                    yield {"type": "error", "message": error}
                    return

    except ConnectionClosed:
        logger.warning("WebSocket yopildi — history tekshiriladi")
        yield {"type": "done"}


async def get_generated_images(prompt_id: str) -> list[bytes]:
    """History dan natija rasmlarni yuklab oladi (3 urinish)."""
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()

        outputs     = history.get(prompt_id, {}).get("outputs", {})
        images_data = []

        for node_output in outputs.values():
            for img_info in node_output.get("images", []):
                params = {
                    "filename":  img_info["filename"],
                    "subfolder": img_info.get("subfolder", ""),
                    "type":      img_info.get("type", "output"),
                }
                async with httpx.AsyncClient(timeout=120.0) as client:
                    r = await client.get(f"{COMFYUI_URL}/view", params=params)
                    r.raise_for_status()
                    images_data.append(r.content)

        if images_data:
            return images_data

        if attempt < 2:
            logger.info(f"History bo'sh (urinish {attempt + 1}/3), 1.5s kutilmoqda...")
            await asyncio.sleep(1.5)

    return []


# ──────────────────────────────────────────────────────────────────────────────
#  Asosiy generatsiya funksiyasi
# ──────────────────────────────────────────────────────────────────────────────

async def generate_albedo(
    prompt: str,
    resolution: int = 1024,
    reference_bytes: Optional[bytes] = None,
    seed: int = -1,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> bytes:
    """
    4K Albedo generatsiya qiladi.

    reference_bytes berilsa → img2img workflow ishlatiladi.
    Qaytaradigan: OUTPUT_RESOLUTION × OUTPUT_RESOLUTION raw image bytes
    Timeout: chaqiruvchi (generate.py) asyncio.wait_for() bilan boshqaradi.
    """
    # ── Mavjud ESRGAN modelini aniqlash ───────────────────────────────────────
    available_upscale = await get_comfyui_upscale_models()
    upscale_model: Optional[str] = None

    if UPSCALE_MODEL in available_upscale:
        upscale_model = UPSCALE_MODEL
        logger.info(f"ESRGAN: '{upscale_model}' topildi → 4K sifatli upscale")
    elif available_upscale:
        upscale_model = available_upscale[0]
        logger.info(f"ESRGAN: '{upscale_model}' (birinchi mavjud model) ishlatiladi")
    else:
        logger.warning("ESRGAN model topilmadi → Lanczos fallback")

    # ── Workflow tanlash ──────────────────────────────────────────────────────
    if reference_bytes:
        image_filename = await upload_image_to_comfyui(reference_bytes)
        workflow = build_img2img_4k_workflow(
            prompt=prompt,
            image_filename=image_filename,
            output_resolution=OUTPUT_RESOLUTION,
            seed=seed,
            upscale_model=upscale_model,
        )
        logger.info("img2img workflow ishlatilmoqda")
    else:
        workflow = build_txt2img_4k_workflow(
            prompt=prompt,
            output_resolution=OUTPUT_RESOLUTION,
            seed=seed,
            upscale_model=upscale_model,
        )

    # ── ComfyUI ga yuborish va progress kuzatish ──────────────────────────────
    prompt_id, client_id = await queue_prompt(workflow)

    async for event in stream_progress(prompt_id, client_id, on_progress):
        if event["type"] == "error":
            raise RuntimeError(event.get("message", "ComfyUI generatsiya xatosi"))
        if event["type"] == "done":
            break

    await asyncio.sleep(0.5)

    images = await get_generated_images(prompt_id)
    if not images:
        raise RuntimeError("ComfyUI natija qaytarmadi (history bo'sh)")

    logger.info(f"4K albedo yuklandi: {len(images[0]) // 1024}KB")
    return images[0]
