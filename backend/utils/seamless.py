"""
PBRForge::Core — Seamless Tile Utility (OpenCV)
=================================================
Generatsiya qilingan rasmni seamless (tikuvsiz) qilish algoritmi.

Algoritm:
  1. Rasmni o'rtasiga siljitish (offset trick)
  2. Chekkalarni alpha blending bilan yumshatish
  3. Normal xaritalar uchun: blending keyin vektor re-normalizatsiya

Eslatma: Bu modul ProcessPoolExecutor da ham ishlatiladi,
shuning uchun barcha funksiyalar o'z-o'zini ta'minlaydi.
"""

import cv2
import numpy as np


def _linear_gradient(size: int, blend: int) -> np.ndarray:
    """Chekkalarida 0, markazida 1 bo'lgan gradient massiv."""
    grad = np.ones(size, dtype=np.float32)
    b = min(blend, size // 2)
    ramp = np.linspace(0.0, 1.0, b, endpoint=False)
    grad[:b] = ramp
    grad[size - b:] = ramp[::-1]
    return grad


def make_seamless_cv(img_bgr: np.ndarray, blend_px: int = 64) -> np.ndarray:
    """
    BGR rasmni seamless tileable qiladi (OpenCV).

    Args:
        img_bgr:  Kiruvchi BGR uint8 numpy array
        blend_px: Chekkalar blending kengligi (pixel)

    Returns:
        Seamless BGR uint8 numpy array, xuddi shu o'lchamda
    """
    h, w = img_bgr.shape[:2]
    half_h, half_w = h // 2, w // 2

    # Offset trick: rasm markazga siljitiladi
    shifted = np.roll(np.roll(img_bgr, half_h, axis=0), half_w, axis=1)

    # Gradient mask: markazda 1 (asl rasm), chekkalarda 0 (shifted)
    grad_x = _linear_gradient(w, blend_px)
    grad_y = _linear_gradient(h, blend_px)
    mask = np.outer(grad_y, grad_x)[:, :, np.newaxis].astype(np.float32)

    # Alpha blending
    src = img_bgr.astype(np.float32)
    blended = src * mask + shifted.astype(np.float32) * (1.0 - mask)
    return np.clip(blended, 0, 255).astype(np.uint8)


def make_seamless_normal_cv(normal_bgr: np.ndarray, blend_px: int = 64) -> np.ndarray:
    """
    Normal xarita uchun seamless + vektorlarni re-normalizatsiya.

    Muammo: Alpha blending natijasida RGB vektorlar buziladi (uzunligi 1 bo'lmaydi).
    Yechim: Blendingdan so'ng har bir piksel vektorini ||v|| = 1 ga qayta normalizatsiya.

    Args:
        normal_bgr: Normal GL xaritasi BGR uint8 (R=X, G=Y, B=Z OpenGL formatda)
        blend_px:   Chekkalar blending kengligi

    Returns:
        Seamless va re-normalizatsiya qilingan BGR uint8 normal xarita
    """
    blended = make_seamless_cv(normal_bgr, blend_px)

    # BGR uint8 → XYZ float [-1, 1]
    n = blended.astype(np.float32) / 255.0 * 2.0 - 1.0
    # BGR tartibida: B=Z, G=Y, R=X
    nx = n[:, :, 2]   # R kanal
    ny = n[:, :, 1]   # G kanal
    nz = n[:, :, 0]   # B kanal

    # Vektor uzunligi = 1 ga normalizatsiya
    length = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2) + 1e-8
    nx = nx / length
    ny = ny / length
    nz = nz / length

    # XYZ → BGR uint8
    result = np.stack([
        nz * 0.5 + 0.5,   # B
        ny * 0.5 + 0.5,   # G
        nx * 0.5 + 0.5,   # R
    ], axis=-1)
    return (np.clip(result, 0.0, 1.0) * 255).astype(np.uint8)


def make_seamless_gray_cv(img_gray: np.ndarray, blend_px: int = 64) -> np.ndarray:
    """
    Grayscale xarita (Roughness, AO) uchun seamless.

    Args:
        img_gray: Grayscale uint8 numpy array (H, W)
        blend_px: Chekkalar blending kengligi

    Returns:
        Seamless grayscale uint8 numpy array
    """
    # Grayscale → BGR → seamless → Grayscale
    bgr = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    result = make_seamless_cv(bgr, blend_px)
    return cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
