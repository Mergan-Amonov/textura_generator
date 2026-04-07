"""
PBRForge::Core — Image Processor v0.3  (6-Map PBR Engine)
===========================================================
Albedo dan 6 ta industry-standard PBR xaritasini chiqaradi:

  Color     — De-lit albedo (baked lighting olib tashlanadi)
  NormalGL  — OpenGL format normal map (Sobel, bilateral pre-filter)
  Height    — Grayscale displacement/height map (multi-scale)
  Roughness — Roughness map (CLAHE + gamma korreksiya)
  Metallic  — Metallic map (HSV-based heuristic)
  AO        — Ambient Occlusion (multi-scale Gaussian diff)

ProcessPoolExecutor da ishlatilish uchun mo'ljallangan:
  - process_all_maps() — top-level picklable funksiya
  - Barcha parametrlar argument sifatida uzatiladi (config import yo'q)
"""

from __future__ import annotations
import base64


# ──────────────────────────────────────────────────────────────────────────────
#  Seamless helpers
# ──────────────────────────────────────────────────────────────────────────────

def _smoothstep_gradient(size: int, blend: int):
    import numpy as np
    g = np.ones(size, dtype=np.float32)
    b = min(blend, size // 2)
    t = np.linspace(0.0, 1.0, b, endpoint=False)
    ramp = t * t * (3.0 - 2.0 * t)   # smoothstep: S-egri, linear emas
    g[:b] = ramp
    g[size - b:] = ramp[::-1]
    return g


def _make_seamless(img_bgr, blend_px: int):
    """Offset trick + smoothstep alpha blend (BGR uint8)."""
    import numpy as np
    h, w = img_bgr.shape[:2]
    shifted = np.roll(np.roll(img_bgr, h // 2, axis=0), w // 2, axis=1)
    mask = np.outer(_smoothstep_gradient(h, blend_px), _smoothstep_gradient(w, blend_px))
    mask = mask[:, :, np.newaxis].astype(np.float32)
    blended = img_bgr.astype(np.float32) * mask + shifted.astype(np.float32) * (1.0 - mask)
    return blended.clip(0, 255).astype(np.uint8)


def _make_seamless_normal(normal_bgr, blend_px: int):
    """Seamless + vektor re-normalizatsiya (||v|| = 1 saqlanadi)."""
    import numpy as np
    blended = _make_seamless(normal_bgr, blend_px)
    n  = blended.astype(np.float32) / 255.0 * 2.0 - 1.0
    nx = n[:, :, 2]   # R = X
    ny = n[:, :, 1]   # G = Y
    nz = n[:, :, 0]   # B = Z
    length = (nx ** 2 + ny ** 2 + nz ** 2) ** 0.5 + 1e-8
    nx, ny, nz = nx / length, ny / length, nz / length
    out = np.stack([nz * 0.5 + 0.5, ny * 0.5 + 0.5, nx * 0.5 + 0.5], axis=-1)
    return (np.clip(out, 0.0, 1.0) * 255).astype(np.uint8)


def _make_seamless_gray(img_gray, blend_px: int):
    import cv2
    bgr    = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    result = _make_seamless(bgr, blend_px)
    return cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)


# ──────────────────────────────────────────────────────────────────────────────
#  PBR xarita generatorlari
# ──────────────────────────────────────────────────────────────────────────────

def _delit_albedo(albedo_bgr, sigma_pct: float = 0.10):
    """
    Frequency separation de-lighting.
    AI tomonidan "baked" bo'lgan past chastotali yoritish gradientini olib tashlaydi.
    Sirt rangi va mayda detallari saqlanadi.

    sigma = image_width * sigma_pct  (odatda 10% — yirik yoritish uchun yetarli)
    """
    import cv2
    import numpy as np

    h, w  = albedo_bgr.shape[:2]
    sigma = max(w, h) * sigma_pct

    float_img = albedo_bgr.astype(np.float32)

    # Katta sigma → faqat global yoritish qoladi
    low_freq = cv2.GaussianBlur(float_img, (0, 0), sigmaX=sigma, sigmaY=sigma)

    # Yuqori chastota (material detail)
    high_freq = float_img - low_freq

    # O'rtacha rang (material identiteti)
    mean_color = low_freq.mean(axis=(0, 1))

    # Qayta birlashtirish: tekis asos + detail
    delit = mean_color + high_freq
    return np.clip(delit, 0, 255).astype(np.uint8)


def _generate_normal_gl(gray_f32, normal_strength: float = 4.0, blend_px: int = 64):
    """
    OpenGL format Normal map (Sobel, bilateral pre-filter).

    bilateral filter → shovqin + mayda artefaktlarni yo'qotadi,
    muhim qirralar (cracks, bumps) saqlanadi.
    Sobel ksize=5: detal va silliqlik balansi.
    """
    import cv2
    import numpy as np

    gray_u8 = (gray_f32 * 255).astype(np.uint8)

    # Edge-aware pre-filter: Gaussian dan ancha yaxshi (qirralarni saqlaydi)
    bilateral = cv2.bilateralFilter(gray_u8, d=7, sigmaColor=20, sigmaSpace=20)
    filtered  = bilateral.astype(np.float32) / 255.0

    # Sobel gradienty
    Gx = cv2.Sobel(filtered, cv2.CV_32F, 1, 0, ksize=5)
    Gy = cv2.Sobel(filtered, cv2.CV_32F, 0, 1, ksize=5)
    Gz = np.full_like(filtered, 1.0 / max(normal_strength, 0.1))

    length = (Gx ** 2 + Gy ** 2 + Gz ** 2) ** 0.5 + 1e-8
    nx, ny, nz = Gx / length, Gy / length, Gz / length

    # OpenGL format: R=X, G=Y, B=Z  →  BGR saqlash: [Z, Y, X]
    normal_bgr = np.stack([nz * 0.5 + 0.5, ny * 0.5 + 0.5, nx * 0.5 + 0.5], axis=-1)
    normal_bgr = (np.clip(normal_bgr, 0.0, 1.0) * 255).astype(np.uint8)

    return _make_seamless_normal(normal_bgr, blend_px)


def _generate_height(gray_f32, blend_px: int = 64):
    """
    Grayscale Height / Displacement map.

    Multi-scale yondashuv:
      coarse (sigma=8) → yirik balandlik tuzilmalari (qoyalar, g'isht yo'llari)
      medium (sigma=2) → o'rtacha bumps (tosh yuzasi, yog'och donalari)
      fine   (raw)     → mayda detal (Sobel gradienti magnitudasi)

    Natija: 0=past, 1=baland  (grayscale PNG uchun ideal)
    """
    import cv2
    import numpy as np

    coarse = cv2.GaussianBlur(gray_f32, (0, 0), sigmaX=8.0, sigmaY=8.0)
    medium = cv2.GaussianBlur(gray_f32, (0, 0), sigmaX=2.0, sigmaY=2.0)
    fine   = gray_f32

    # Weighted blend: coarse shakl, medium+fine detal
    height = coarse * 0.25 + medium * 0.45 + fine * 0.30

    # Normalize [0, 1]
    h_min, h_max = height.min(), height.max()
    if h_max - h_min > 1e-6:
        height = (height - h_min) / (h_max - h_min)

    height_u8 = (height * 255).astype(np.uint8)
    return _make_seamless_gray(height_u8, blend_px)


def _generate_roughness(gray_f32, roughness_gamma: float = 1.2, blend_px: int = 64):
    """
    Roughness map (CLAHE lokal kontrast + gamma korreksiya).

    Yorug' = silliq (low roughness), qorong'i = g'adir-budir (high roughness).
    CLAHE: har bir maydonchada mustaqil kontrast → tafsilotlar aniq ajraladi.
    """
    import cv2
    import numpy as np

    gray_u8  = (gray_f32 * 255).astype(np.uint8)
    clahe    = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray_u8).astype(np.float32) / 255.0

    roughness = 1.0 - enhanced
    roughness = np.power(np.clip(roughness, 0.0, 1.0), roughness_gamma)

    # Full range normalizatsiya
    r_min, r_max = roughness.min(), roughness.max()
    if r_max - r_min > 1e-6:
        roughness = (roughness - r_min) / (r_max - r_min)

    roughness_u8 = (roughness * 255).astype(np.uint8)
    return _make_seamless_gray(roughness_u8, blend_px)


def _generate_metallic(albedo_bgr, blend_px: int = 64):
    """
    Metallic map (HSV-based heuristic).

    Metall belgilari:
      - Yuqori yorqinlik (value)
      - Past rang to'yinganligi (saturation)
      - Bir-tekis rang (past dispersion)

    Formulasi: metallic ≈ value^0.8 × (1 - saturation)^2
    Keyin kuchaytiriladi va smoothed.

    Eslatma: Bu taxminiy heuristic. To'liq aniq metallic uchun
    maxsus AI model yoki manual masking kerak.
    """
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(albedo_bgr, cv2.COLOR_BGR2HSV)
    s   = hsv[:, :, 1].astype(np.float32) / 255.0   # saturation
    v   = hsv[:, :, 2].astype(np.float32) / 255.0   # value/brightness

    # Metal: yorqin va desaturated
    metallic = (v ** 0.8) * ((1.0 - s) ** 2)
    metallic = np.clip(metallic * 1.3, 0.0, 1.0)

    # Edge-aware smooth (metallar gradual transition beradi)
    metallic_u8 = (metallic * 255).astype(np.uint8)
    metallic_u8 = cv2.bilateralFilter(metallic_u8, d=9, sigmaColor=25, sigmaSpace=25)

    return _make_seamless_gray(metallic_u8, blend_px)


def _generate_ao(gray_f32, ao_blur_sigma: float = 4.0, blend_px: int = 64):
    """
    Ambient Occlusion (multi-scale Gaussian diff).

    Uch miqyosda soya tahlili:
      mayda (sigma*0.5)  → yaqin mikro-soyalar
      o'rta (sigma)      → o'rtacha chuqurliklar
      keng  (sigma*3)    → yirik botiqlar

    Pastki chegara 0.45 — juda qorong'i AO dan saqlaydi.
    """
    import cv2
    import numpy as np

    b1 = cv2.GaussianBlur(gray_f32, (0, 0), sigmaX=ao_blur_sigma * 0.5)
    b2 = cv2.GaussianBlur(gray_f32, (0, 0), sigmaX=ao_blur_sigma)
    b3 = cv2.GaussianBlur(gray_f32, (0, 0), sigmaX=ao_blur_sigma * 3.0)

    ao = (gray_f32 - b1) * 0.4 + (gray_f32 - b2) * 0.4 + (gray_f32 - b3) * 0.2
    ao = cv2.normalize(ao, None, alpha=0.0, beta=1.0, norm_type=cv2.NORM_MINMAX)
    ao = np.clip(0.45 + ao * 0.55, 0.0, 1.0)

    ao_u8 = (ao * 255).astype(np.uint8)
    return _make_seamless_gray(ao_u8, blend_px)


# ──────────────────────────────────────────────────────────────────────────────
#  Asosiy funksiya — ProcessPoolExecutor uchun top-level (picklable)
# ──────────────────────────────────────────────────────────────────────────────

def process_all_maps(
    albedo_bytes: bytes,
    material_name: str    = "Material",
    normal_strength: float = 4.0,
    roughness_gamma: float = 1.2,
    ao_blur_sigma: float   = 4.0,
    seamless_blend_px: int = 512,
    delit_sigma_pct: float = 0.10,
) -> dict[str, bytes]:
    """
    4K Albedo bytes dan 6 PBR xarita generatsiya qiladi.

    ProcessPoolExecutor ichida alohida jarayonda ishlaydi.

    Returns:
        {
          "Color":     JPEG bytes  — de-lit seamless albedo
          "NormalGL":  JPEG bytes  — OpenGL normal map (seamless + re-normalized)
          "Height":    JPEG bytes  — grayscale displacement map
          "Roughness": JPEG bytes  — roughness map
          "Metallic":  JPEG bytes  — metallic map (heuristic)
          "AO":        JPEG bytes  — ambient occlusion map
        }
    """
    import cv2
    import numpy as np

    # ── 1. Dekodlash ──────────────────────────────────────────────────────────
    arr       = np.frombuffer(albedo_bytes, dtype=np.uint8)
    albedo_raw = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if albedo_raw is None:
        raise ValueError("Albedo rasm dekodlanmadi (noto'g'ri format yoki buzilgan bytes)")

    # ── 2. Albedo seamless ────────────────────────────────────────────────────
    albedo_seamless = _make_seamless(albedo_raw, seamless_blend_px)

    # ── 3. De-lit albedo (baked lighting olib tashlash) ───────────────────────
    albedo_delit = _delit_albedo(albedo_seamless, sigma_pct=delit_sigma_pct)

    # ── 4. Luminance — barcha xaritalar uchun asos ───────────────────────────
    gray_f32 = cv2.cvtColor(albedo_delit, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

    # ── 5. Barcha xaritalarni generatsiya qilish ─────────────────────────────
    normal_bgr   = _generate_normal_gl(gray_f32, normal_strength, seamless_blend_px)
    height_u8    = _generate_height(gray_f32, seamless_blend_px)
    roughness_u8 = _generate_roughness(gray_f32, roughness_gamma, seamless_blend_px)
    metallic_u8  = _generate_metallic(albedo_delit, seamless_blend_px)
    ao_u8        = _generate_ao(gray_f32, ao_blur_sigma, seamless_blend_px)

    # ── 6. JPEG encoding (95% sifat) ─────────────────────────────────────────
    params = [cv2.IMWRITE_JPEG_QUALITY, 95]

    def to_jpg(img: np.ndarray) -> bytes:
        ok, buf = cv2.imencode(".jpg", img, params)
        if not ok:
            raise RuntimeError("JPEG encoding xatosi")
        return bytes(buf)

    def gray_to_jpg(g: np.ndarray) -> bytes:
        return to_jpg(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))

    return {
        "Color":     to_jpg(albedo_delit),
        "NormalGL":  to_jpg(normal_bgr),
        "Height":    gray_to_jpg(height_u8),
        "Roughness": gray_to_jpg(roughness_u8),
        "Metallic":  gray_to_jpg(metallic_u8),
        "AO":        gray_to_jpg(ao_u8),
    }


def maps_to_previews(maps: dict[str, bytes]) -> dict[str, str]:
    """Xaritalar → base64 data URI (frontend preview uchun)."""
    return {
        name: f"data:image/jpeg;base64,{base64.b64encode(data).decode()}"
        for name, data in maps.items()
    }


def analyze_reference_image(image_bytes: bytes) -> dict:
    """
    Referens rasmni tahlil qiladi.
    Qaytaradi: hue, saturation, detail, roughness, contrast, prompt_hints
    """
    import cv2
    import numpy as np

    arr     = np.frombuffer(image_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        return {"prompt_hints": ""}

    img_hsv   = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h_channel = img_hsv[:, :, 0].astype(np.float32)
    s_channel = img_hsv[:, :, 1].astype(np.float32)
    v_channel = img_hsv[:, :, 2].astype(np.float32)

    saturated_mask = s_channel > 30
    mean_sat = s_channel.mean()

    if saturated_mask.sum() > 100:
        mean_h = h_channel[saturated_mask].mean()
        if mean_h < 35 or mean_h > 160:
            hue = "warm"
        elif 75 < mean_h < 150:
            hue = "cool"
        else:
            hue = "neutral"
    else:
        hue = "neutral"

    saturation = "high" if mean_sat > 80 else ("medium" if mean_sat > 35 else "low")

    gray    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    detail  = "high" if lap_var > 800 else ("medium" if lap_var > 200 else "low")

    gx       = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy       = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    grad_mag = ((gx ** 2 + gy ** 2) ** 0.5).mean()
    roughness = "rough" if grad_mag > 25 else ("medium" if grad_mag > 10 else "smooth")

    contrast = "high" if gray.std() > 55 else "low"

    hints = []
    if roughness == "rough":
        hints.append("rough uneven surface with micro-details and pores")
    elif roughness == "smooth":
        hints.append("smooth polished surface with fine texture")
    else:
        hints.append("medium roughness surface texture")

    if detail == "high":
        hints.append("highly detailed with visible cracks, bumps, and irregularities")
    elif detail == "low":
        hints.append("uniform surface with subtle texture variation")

    if saturation == "low":
        hints.append("desaturated neutral tones, aged worn look")
    elif saturation == "high":
        hints.append("vivid saturated color with strong pigmentation")

    if hue == "warm":
        hints.append("warm earth tones")
    elif hue == "cool":
        hints.append("cool stone or metal tones")

    if contrast == "high":
        hints.append("strong value contrast between raised and recessed areas")

    return {
        "hue":          hue,
        "saturation":   saturation,
        "detail":       detail,
        "roughness":    roughness,
        "contrast":     contrast,
        "prompt_hints": ", ".join(hints),
    }
