"""
PBRForge::Core — Prompt Builder
================================
Vision tahlil natijasidan PBR texture generatsiya uchun
SDXL-optimized prompt yaratadi.

Mebel materiallari uchun maxsus optimallashtirilgan:
  - Mato (velyur, kanop, gazlama, zangori zig-zag...)
  - Charm (natural, sun'iy, vintaj, yangi...)
  - Yog'och (emal, lakli, cho'tka...)
  - Metall (po'lat, bronza, mis...)
  - Boshqa (plastik, tosh, shisha...)
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── PBR suffix — barcha texturalar uchun majburiy ────────────────────────────
PBR_SUFFIX = (
    "seamless tileable texture, pbr albedo map, "
    "flat studio lighting, no shadows, no highlights, "
    "photorealistic material, 4k resolution"
)

# ── Negative prompt — SDXL uchun ─────────────────────────────────────────────
PBR_NEGATIVE = (
    "furniture, sofa, chair, table, room, background, person, "
    "3d render, painting, illustration, cartoon, blurry, "
    "low quality, watermark, signature, text, logo, "
    "strong shadows, harsh lighting, vignette"
)

# ── Material kategoriya aniqlash ──────────────────────────────────────────────
FABRIC_KEYWORDS = [
    "velvet", "fabric", "textile", "cloth", "linen", "cotton", "wool",
    "woven", "knit", "chenille", "boucle", "tweed", "suede", "silk",
    "polyester", "microfiber", "corduroy", "denim", "canvas",
    "velyur", "mato", "gazlama", "jun", "ipak", "kanop",
]

LEATHER_KEYWORDS = [
    "leather", "leatherette", "faux leather", "genuine leather",
    "pebbled", "grain leather", "patent leather", "nubuck",
    "charm", "teri", "sun'iy charm",
]

WOOD_KEYWORDS = [
    "wood", "wooden", "oak", "walnut", "pine", "mahogany", "bamboo",
    "grain", "parquet", "plywood", "veneer",
    "yog'och", "eman", "qayin",
]

METAL_KEYWORDS = [
    "metal", "steel", "iron", "copper", "bronze", "brass", "aluminum",
    "chrome", "brushed", "polished metal", "oxidized",
    "metall", "po'lat", "mis", "bronza",
]


def _detect_material_category(description: str) -> str:
    """Tavsifdan material kategoriyasini aniqlaydi."""
    desc_lower = description.lower()

    for kw in FABRIC_KEYWORDS:
        if kw in desc_lower:
            return "fabric"
    for kw in LEATHER_KEYWORDS:
        if kw in desc_lower:
            return "leather"
    for kw in WOOD_KEYWORDS:
        if kw in desc_lower:
            return "wood"
    for kw in METAL_KEYWORDS:
        if kw in desc_lower:
            return "metal"
    return "general"


def _category_suffix(category: str) -> str:
    """Material kategoriyasiga qarab qo'shimcha PBR hints."""
    suffixes = {
        "fabric": "close-up fabric texture, uniform weave pattern, even surface",
        "leather": "close-up leather surface, natural grain pattern, uniform lighting",
        "wood": "close-up wood grain texture, uniform plank pattern, natural finish",
        "metal": "close-up metal surface, uniform texture, industrial material",
        "general": "close-up material surface, uniform texture",
    }
    return suffixes.get(category, suffixes["general"])


def _clean_description(description: str) -> str:
    """
    Vision tavsifini promptga mos holga keltiradi.
    - Ortiqcha gap/so'zlarni olib tashlaydi
    - Birinchi gapni oladi (eng muhim tavsif)
    """
    # Birinchi gapni ol
    sentences = re.split(r'[.!?]\s+', description.strip())
    first = sentences[0].strip().rstrip('.!?')

    # "This image shows...", "The texture is..." kabi boshlanishlarni tozalash
    first = re.sub(
        r'^(this (image|texture|fabric|material|photo) (shows|depicts|is|appears|features)|'
        r'the (texture|material|fabric|surface|image) (is|shows|appears|features))\s*',
        '', first, flags=re.IGNORECASE
    ).strip()

    # Bosh harf kichiklashtirish (prompt uchun yaxshiroq)
    if first and first[0].isupper():
        first = first[0].lower() + first[1:]

    return first


def build_pbr_prompt(
    vision_description: str,
    user_hint: str = "",
) -> dict:
    """
    Vision tavsifidan to'liq PBR texture prompti yaratadi.

    Args:
        vision_description: LLaVA dan kelgan material tavsifi
        user_hint: Foydalanuvchi qo'shimcha izohi (ixtiyoriy)

    Returns:
        {
            "prompt": str,        — asosiy generatsiya prompti
            "negative": str,      — negative prompt
            "category": str,      — material kategoriyasi
            "use_img2img": bool,  — img2img tavsiya qilinsinmi
        }
    """
    cleaned = _clean_description(vision_description)
    category = _detect_material_category(vision_description)
    cat_suffix = _category_suffix(category)

    parts = [cleaned]
    if user_hint and user_hint.strip():
        parts.append(user_hint.strip())
    parts.append(cat_suffix)
    parts.append(PBR_SUFFIX)

    prompt = ", ".join(p for p in parts if p)

    # img2img: mato va charm uchun tavsiya etiladi (rang/pattern muhim)
    use_img2img = category in ("fabric", "leather")

    logger.info(
        f"Prompt qurildi | category={category} | img2img={use_img2img}\n"
        f"  → {prompt[:120]}..."
    )

    return {
        "prompt": prompt,
        "negative": PBR_NEGATIVE,
        "category": category,
        "use_img2img": use_img2img,
    }


def build_pbr_prompt_from_text(user_text: str) -> dict:
    """
    Foydalanuvchi matnidan (vision tahlilsiz) PBR prompt yaratadi.
    Referens rasm yuklanmagan holatda ishlatiladi.
    """
    category = _detect_material_category(user_text)
    cat_suffix = _category_suffix(category)

    prompt = f"{user_text.strip()}, {cat_suffix}, {PBR_SUFFIX}"

    return {
        "prompt": prompt,
        "negative": PBR_NEGATIVE,
        "category": category,
        "use_img2img": False,
    }
