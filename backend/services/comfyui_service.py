"""
PBRForge::Core — ComfyUI Service
==================================
ComfyUI bilan barcha aloqani boshqaradi:
  - REST API orqali workflow yuborish
  - WebSocket orqali progress kuzatish
  - Natija rasmlarni yuklab olish
"""

import asyncio
import json
import uuid
import logging
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
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  ComfyUI ulanishini tekshirish
# ──────────────────────────────────────────────────────────────────────────────

async def is_comfyui_running() -> bool:
    """ComfyUI localhost da ishlab turganligini tekshiradi."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{COMFYUI_URL}/system_stats")
            return r.status_code == 200
    except Exception:
        return False


async def get_comfyui_models() -> list[str]:
    """ComfyUI da o'rnatilgan modellar ro'yxatini qaytaradi."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple")
            data = r.json()
            return data["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
#  Referens rasm yuklash
# ──────────────────────────────────────────────────────────────────────────────

async def upload_image_to_comfyui(
    image_bytes: bytes,
    filename: str = "pbrforge_ref.png",
) -> str:
    """
    Referens rasmni ComfyUI /upload/image orqali yuklaydi.

    Returns:
        ComfyUI tomonidan berilgan fayl nomi (LoadImage nodeda ishlatiladi).
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        files = {"image": (filename, image_bytes, "image/png")}
        r = await client.post(f"{COMFYUI_URL}/upload/image", files=files)
        r.raise_for_status()
        data = r.json()
    uploaded_name = data.get("name", filename)
    logger.info(f"Referens rasm yuklandi: {uploaded_name}")
    return uploaded_name


# ──────────────────────────────────────────────────────────────────────────────
#  ComfyUI Workflow yaratish
# ──────────────────────────────────────────────────────────────────────────────

def build_txt2img_workflow(
    prompt: str,
    resolution: int = 1024,
    seed: int = -1,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    sampler: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    negative: str = DEFAULT_NEGATIVE,
    checkpoint: str = CHECKPOINT_NAME,
) -> dict:
    """
    Text-to-image ComfyUI workflow JSON yaratadi.
    PBR texture generatsiyasi uchun optimallashtirilgan prompt.
    """
    if seed < 0:
        import random
        seed = random.randint(0, 2**32 - 1)

    pbr_suffix = (
        ", seamless tileable texture, pbr material, "
        "flat lighting, no shadows, top-down view, diffuse only"
    )
    full_prompt = prompt + pbr_suffix

    return {
        # 1 — Checkpoint yuklash
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        # 2 — Positive prompt
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["1", 1],
                "text": full_prompt,
            },
        },
        # 3 — Negative prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["1", 1],
                "text": negative,
            },
        },
        # 4 — Bo'sh latent
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": resolution,
                "height": resolution,
                "batch_size": 1,
            },
        },
        # 5 — KSampler
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model":        ["1", 0],
                "positive":     ["2", 0],
                "negative":     ["3", 0],
                "latent_image": ["4", 0],
                "seed":         seed,
                "steps":        steps,
                "cfg":          cfg,
                "sampler_name": sampler,
                "scheduler":    scheduler,
                "denoise":      1.0,
            },
        },
        # 6 — VAE decode
        "6": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["5", 0],
                "vae":     ["1", 2],
            },
        },
        # 7 — Rasm saqlash
        "7": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "PBRForge_albedo",
                "images":          ["6", 0],
            },
        },
    }


def build_img2img_workflow(
    prompt: str,
    image_filename: str,
    resolution: int = 1024,
    denoise: float = 0.65,
    seed: int = -1,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    sampler: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    negative: str = DEFAULT_NEGATIVE,
    checkpoint: str = CHECKPOINT_NAME,
) -> dict:
    """
    Image-to-image workflow — referens rasm asosida generatsiya.
    Rasm avval /upload/image orqali ComfyUI ga yuklanishi kerak.
    image_filename: upload_image_to_comfyui() qaytargan fayl nomi.
    """
    if seed < 0:
        import random
        seed = random.randint(0, 2**32 - 1)

    pbr_suffix = (
        ", seamless tileable texture, pbr material, "
        "flat lighting, no shadows, diffuse only"
    )
    full_prompt = prompt + pbr_suffix

    return {
        # 1 — Checkpoint
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        # 2 — Yuklangan rasmni o'qish (standart LoadImage nodi)
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": image_filename},
        },
        # 3 — Referens rasmni kerakli o'lchamga keltirish
        "3": {
            "class_type": "ImageScale",
            "inputs": {
                "image":          ["2", 0],
                "upscale_method": "lanczos",
                "width":          resolution,
                "height":         resolution,
                "crop":           "center",
            },
        },
        # 4 — VAE encode (rasm → latent)
        "4": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["3", 0],
                "vae":    ["1", 2],
            },
        },
        # 5 — Positive prompt
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": full_prompt},
        },
        # 6 — Negative prompt
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": negative},
        },
        # 7 — KSampler
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model":        ["1", 0],
                "positive":     ["5", 0],
                "negative":     ["6", 0],
                "latent_image": ["4", 0],
                "seed":         seed,
                "steps":        steps,
                "cfg":          cfg,
                "sampler_name": sampler,
                "scheduler":    scheduler,
                "denoise":      denoise,
            },
        },
        # 8 — VAE decode
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["1", 2]},
        },
        # 9 — Saqlash
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "PBRForge_albedo",
                "images":          ["8", 0],
            },
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Workflow yuborish va natija olish
# ──────────────────────────────────────────────────────────────────────────────

async def queue_prompt(workflow: dict) -> tuple[str, str]:
    """
    ComfyUI ga workflow yuboradi.
    Returns: (prompt_id, client_id)
    """
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{COMFYUI_URL}/prompt", json=payload)
        r.raise_for_status()
        data = r.json()

    prompt_id = data["prompt_id"]
    logger.info(f"Workflow yuborildi. prompt_id={prompt_id}, client_id={client_id}")
    return prompt_id, client_id


async def stream_progress(
    prompt_id: str,
    client_id: str,
    on_progress: Optional[Callable[[dict], None]] = None,
    timeout: float = 300.0,
) -> AsyncGenerator[dict, None]:
    """
    ComfyUI WebSocket orqali generatsiya progressini kuzatadi.
    Har yangilashda dict yield qiladi.
    """
    ws_url = f"{COMFYUI_WS}?clientId={client_id}"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    try:
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            while loop.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    continue

                if isinstance(raw, bytes):
                    continue  # Preview frame, skip

                msg = json.loads(raw)
                mtype = msg.get("type", "")

                if mtype == "progress":
                    data = msg.get("data", {})
                    event = {
                        "type":   "progress",
                        "step":   data.get("value", 0),
                        "total":  data.get("max", 1),
                        "status": "generating",
                    }
                    if on_progress:
                        on_progress(event)
                    yield event

                elif mtype == "executing":
                    data = msg.get("data", {})
                    if data.get("node") is None:
                        pid = data.get("prompt_id")
                        # Ba'zi ComfyUI versiyalarida prompt_id bo'lmaydi — ikkalasini qabul qilamiz
                        if pid is None or pid == prompt_id:
                            logger.info(f"Executing done signal olindi (prompt_id={pid})")
                            yield {"type": "done", "status": "done"}
                            return

                elif mtype == "execution_success":
                    # Yangi ComfyUI versiyalarida ishlatiladi
                    data = msg.get("data", {})
                    pid = data.get("prompt_id")
                    if pid is None or pid == prompt_id:
                        logger.info(f"Execution_success signal olindi (prompt_id={pid})")
                        yield {"type": "done", "status": "done"}
                        return

                elif mtype == "execution_error":
                    error = msg.get("data", {}).get("exception_message", "Noma'lum xato")
                    yield {"type": "error", "message": error}
                    return

                else:
                    logger.debug(f"ComfyUI event: {mtype}")

    except ConnectionClosed:
        # ComfyUI ba'zan done signalidan so'ng WebSocket ni yopadi —
        # bu normal holat. get_generated_images history ni tekshiradi.
        logger.warning("WebSocket yopildi — history tekshiriladi")
        yield {"type": "done", "status": "done"}
    except Exception as e:
        logger.error(f"Stream xatosi: {e}")
        yield {"type": "error", "message": str(e)}


async def get_generated_images(prompt_id: str) -> list[bytes]:
    """
    Generatsiya tugagach ComfyUI history dan rasm byte-larini qaytaradi.
    History ba'zan kechikib yoziladi — 3 marta qayta urinadi.
    """
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
            r.raise_for_status()
            history = r.json()

        outputs = history.get(prompt_id, {}).get("outputs", {})
        images_data = []

        for node_output in outputs.values():
            for img_info in node_output.get("images", []):
                filename  = img_info["filename"]
                subfolder = img_info.get("subfolder", "")
                img_type  = img_info.get("type", "output")

                params = {"filename": filename, "subfolder": subfolder, "type": img_type}
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.get(f"{COMFYUI_URL}/view", params=params)
                    r.raise_for_status()
                    images_data.append(r.content)

        if images_data:
            return images_data

        # History hali tayyor emas — bir soniya kutib qayta urinish
        if attempt < 2:
            logger.info(f"History bo'sh (urinish {attempt + 1}/3), 1s kutilmoqda...")
            await asyncio.sleep(1.0)

    return images_data


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
    Albedo (Color) tekstura generatsiya qiladi va PNG bytes qaytaradi.

    reference_bytes: referens rasm raw bytes (ixtiyoriy).
                     Agar berilsa, img2img ishlatiladi.
    """
    if reference_bytes:
        image_filename = await upload_image_to_comfyui(reference_bytes)
        workflow = build_img2img_workflow(
            prompt=prompt,
            image_filename=image_filename,
            resolution=resolution,
            seed=seed,
        )
    else:
        workflow = build_txt2img_workflow(
            prompt=prompt,
            resolution=resolution,
            seed=seed,
        )

    prompt_id, client_id = await queue_prompt(workflow)

    async for event in stream_progress(prompt_id, client_id, on_progress):
        if event["type"] == "error":
            raise RuntimeError(event.get("message", "Generatsiya xatosi"))
        if event["type"] == "done":
            break

    # History API ga yozilishi uchun kichik kutish
    await asyncio.sleep(0.5)

    images = await get_generated_images(prompt_id)
    if not images:
        raise RuntimeError("ComfyUI natija qaytarmadi")

    return images[0]
