"""
PBRForge::Core — Post-Processing Service
==========================================
Albedo (Color) rasmdan avtomatik PBR xaritalar generatsiya qiladi:
  - Normal GL map   (Sobel filter asosida)
  - Roughness map   (Grayscale + gamma korreksiya)
  - AO map          (Ambient Occlusion approksimatsiya)

Barcha xaritalar JPG 95% sifatda saqlanadi (AmbientCG/PolyHaven standarti).
"""

import io
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
from scipy.ndimage import gaussian_filter, sobel

from config import NORMAL_STRENGTH, ROUGHNESS_GAMMA, AO_BLUR_RADIUS
from utils.seamless import make_seamless, make_seamless_for_map


# ──────────────────────────────────────────────────────────────────────────────
#  Yordamchi funksiyalar
# ──────────────────────────────────────────────────────────────────────────────

def _to_array(image: Image.Image) -> np.ndarray:
    """PIL Image → float32 numpy [0..1]"""
    return np.array(image, dtype=np.float32) / 255.0


def _to_image(arr: np.ndarray, mode: str = "RGB") -> Image.Image:
    """float32 numpy [0..1] → PIL Image uint8"""
    clipped = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(clipped, mode)


def _to_jpg_bytes(image: Image.Image, quality: int = 95) -> bytes:
    """PIL Image → JPEG bytes"""
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _to_png_bytes(image: Image.Image) -> bytes:
    """PIL Image → PNG bytes"""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
#  Normal GL Map
# ──────────────────────────────────────────────────────────────────────────────

def generate_normal_map(albedo: Image.Image, strength: float = NORMAL_STRENGTH) -> Image.Image:
    """
    Albedo rasmdan Normal GL xaritasini hisoblaydi.

    Algoritm:
      1. Albedo → Grayscale (heightmap sifatida)
      2. Sobel X va Y gradienti
      3. (Gx, Gy, 1/strength) → normalize
      4. [0..1] rangga aylantirish

    Args:
        albedo: Albedo PIL Image (RGB)
        strength: Normal map kuchi (katta = chuqurroq detallar)

    Returns:
        Normal GL PIL Image (RGB): R=X, G=Y, B=Z
    """
    gray = albedo.convert("L")
    h_arr = _to_array(gray).squeeze()  # (H, W) float32 [0..1]

    # Sobel gradienti
    gx = sobel(h_arr, axis=1)   # Gorizontal gradient
    gy = sobel(h_arr, axis=0)   # Vertikal gradient

    # Z komponent (kichik = kuchli normal)
    gz = np.ones_like(gx) / max(strength, 0.1)

    # Normalize (unit vector)
    length = np.sqrt(gx**2 + gy**2 + gz**2) + 1e-8
    nx = gx / length
    ny = gy / length
    nz = gz / length

    # OpenGL format: G o'qi teskari emas (Blender, Unity GL, Godot uchun)
    r_channel = (nx * 0.5 + 0.5)   # X → R
    g_channel = (ny * 0.5 + 0.5)   # Y → G (GL, teskari emas)
    b_channel = (nz * 0.5 + 0.5)   # Z → B

    normal_arr = np.stack([r_channel, g_channel, b_channel], axis=-1)
    return _to_image(normal_arr, "RGB")


# ──────────────────────────────────────────────────────────────────────────────
#  Roughness Map
# ──────────────────────────────────────────────────────────────────────────────

def generate_roughness_map(albedo: Image.Image, gamma: float = ROUGHNESS_GAMMA) -> Image.Image:
    """
    Albedo rasmdan Roughness xaritasini hisoblaydi.

    Algoritm:
      1. Albedo → Grayscale
      2. Teskari: yorqin joy = silliq (past roughness)
      3. Gamma korreksiya bilan kontrast moslash
      4. Normalize [0..255]

    Returns:
        Roughness PIL Image (L): Qora=silliq, Oq=qo'pol
    """
    gray = albedo.convert("L")
    r_arr = _to_array(gray).squeeze()

    # Teskari: yorqin joylar silliqroq (metall, shisha kabi)
    roughness = 1.0 - r_arr

    # Gamma korreksiya — qo'pollik kontrastini moslash
    roughness = np.power(np.clip(roughness, 0, 1), gamma)

    # Kontrast kuchaytirish
    mean = roughness.mean()
    roughness = np.clip((roughness - mean) * 1.3 + mean, 0, 1)

    result = _to_image(roughness[:, :, np.newaxis].repeat(3, axis=-1), "RGB")
    return result.convert("L")


# ──────────────────────────────────────────────────────────────────────────────
#  Ambient Occlusion Map
# ──────────────────────────────────────────────────────────────────────────────

def generate_ao_map(albedo: Image.Image, blur_radius: int = AO_BLUR_RADIUS) -> Image.Image:
    """
    Albedo rasmdan Ambient Occlusion xaritasini approksimatsiya qiladi.

    Algoritm:
      1. Grayscale (heightmap)
      2. Gaussian blur (global yorug'lik)
      3. Lokal farq: height - blurred → chuqurlik ma'lumoti
      4. Normalize va teskari

    Returns:
        AO PIL Image (L): Oq=ochiq, Qora=soya
    """
    gray = albedo.convert("L")
    h_arr = _to_array(gray).squeeze()

    # Lokal va global yorug'lik farqi
    blurred = gaussian_filter(h_arr, sigma=blur_radius)
    ao = h_arr - blurred

    # Normalize
    ao_min, ao_max = ao.min(), ao.max()
    if ao_max - ao_min > 1e-8:
        ao = (ao - ao_min) / (ao_max - ao_min)
    else:
        ao = np.ones_like(ao) * 0.8

    # AO: qorong'i joylar soya, yorqin joylar ochiq
    ao = np.clip(0.5 + ao * 0.5, 0, 1)

    result = _to_image(ao[:, :, np.newaxis].repeat(3, axis=-1), "RGB")
    return result.convert("L")


# ──────────────────────────────────────────────────────────────────────────────
#  To'liq PBR xaritalar to'plami
# ──────────────────────────────────────────────────────────────────────────────

class PBRMapSet:
    """Barcha PBR xaritalarini saqlaydi."""
    def __init__(self):
        self.albedo:    Image.Image | None = None
        self.normal:    Image.Image | None = None
        self.roughness: Image.Image | None = None
        self.ao:        Image.Image | None = None


def process_all_maps(
    albedo_bytes: bytes,
    material_name: str = "Material",
    make_seamless_flag: bool = True,
) -> dict[str, bytes]:
    """
    Albedo rasm bytes dan barcha PBR xaritalarni generatsiya qiladi.

    Args:
        albedo_bytes:       ComfyUI dan kelgan albedo rasm (PNG/JPG)
        material_name:      Fayl nomlari uchun material nomi
        make_seamless_flag: Seamless tile algoritmini qo'llash

    Returns:
        {
          "Color":     JPEG bytes,
          "NormalGL":  JPEG bytes,
          "Roughness": JPEG bytes,
          "AO":        JPEG bytes,
        }
    """
    # Albedo yuklash
    albedo = Image.open(io.BytesIO(albedo_bytes)).convert("RGB")

    # Seamless qilish (ixtiyoriy)
    if make_seamless_flag:
        albedo = make_seamless(albedo)

    # Xaritalar generatsiyasi
    normal    = generate_normal_map(albedo)
    roughness = generate_roughness_map(albedo)
    ao        = generate_ao_map(albedo)

    # Seamless qilish (normal va roughness ham)
    if make_seamless_flag:
        normal    = make_seamless(normal)
        roughness = make_seamless_for_map(roughness, mode="L")
        ao        = make_seamless_for_map(ao, mode="L")

    return {
        "Color":     _to_jpg_bytes(albedo),
        "NormalGL":  _to_jpg_bytes(normal),
        "Roughness": _to_jpg_bytes(roughness.convert("RGB")),
        "AO":        _to_jpg_bytes(ao.convert("RGB")),
    }


def maps_to_previews(maps: dict[str, bytes]) -> dict[str, str]:
    """
    Xaritalar → base64 data URI (frontend preview uchun).
    """
    import base64
    previews = {}
    for name, data in maps.items():
        b64 = base64.b64encode(data).decode("utf-8")
        previews[name] = f"data:image/jpeg;base64,{b64}"
    return previews
