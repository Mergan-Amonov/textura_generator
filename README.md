# PBRForge::Core

Lokal PBR texture generator — referens rasm yoki matn orqali 6 ta professional PBR xarita yaratadi.

**Versiya:** v0.4  
**Holat:** Prototip — asosiy pipeline ishlaydi, sifat yaxshilanishi kerak  
**GitHub:** https://github.com/Mergan-Amonov/textura_generator

---

## Nima qiladi

1. Foydalanuvchi chatda texture tavsifi yozadi yoki referens rasm yuklaydi
2. LLaVA (vision AI) material turini aniqlaydi → SDXL prompt yaratadi
3. ComfyUI / SDXL → 4K albedo generatsiya qiladi (img2img yoki txt2img)
4. OpenCV pipeline 6 ta PBR xarita chiqaradi:

| Xarita | Tavsif |
|---|---|
| **Color** | De-lit seamless albedo (baked lighting olib tashlanadi) |
| **NormalGL** | OpenGL format normal map (Sobel + bilateral filter) |
| **Height** | Multi-scale grayscale displacement map |
| **Roughness** | CLAHE + gamma korreksiyali roughness map |
| **Metallic** | HSV-based heuristic metallic mask |
| **AO** | Multi-scale Gaussian diff ambient occlusion |

5. ZIP arxiv sifatida yuklab olish

---

## Talablar

| Komponent | Versiya | Izoh |
|---|---|---|
| Python | 3.10+ | Backend |
| Node.js | 18+ | Frontend |
| ComfyUI | latest | `localhost:8188` da ishlab turishi kerak |
| Ollama | latest | `localhost:11434` da ishlab turishi kerak |
| GPU | 8GB+ VRAM | SDXL uchun (minimum 6GB) |

### Kerakli modellar

**SDXL checkpoint** → `ComfyUI/models/checkpoints/`
```
Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors
```

**LLaVA vision modeli** (bir marta o'rnatiladi, ~4GB):
```bash
ollama pull llava:7b
```

**LLM chat modeli** (ixtiyoriy, chat UI uchun, ~2GB):
```bash
ollama pull llama3.2
```
> Yo'q bo'lsa chat ishlaydi, lekin LLM o'rniga mahalliy `build_pbr_prompt_from_text` ishlatiladi.

**4K Upscale modeli** (ixtiyoriy) → `ComfyUI/models/upscale_models/`
```
4x_NMKD-Siax_200k.pth
```
yoki `RealESRGAN_x4plus.pth`. Yo'q bo'lsa Lanczos bilan fallback qiladi.

---

## Ishga tushirish

### 1. ComfyUI va Ollama ni yoqing

```bash
# ComfyUI (alohida terminal)
python ComfyUI/main.py

# Ollama (alohida terminal)
ollama serve
```

### 2. PBRForge

```bash
# Windows — bir tugma (avtomatik paket o'rnatadi)
start.bat

# Yoki qo'lda:
cd backend && pip install -r requirements.txt && python main.py
cd frontend && npm install && npm run dev
```

**Manzillar:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- ComfyUI: http://localhost:8188

---

## Ishlatish

### Variant 1 — Matn orqali
1. Chat ga yozing: `"ko'k velvet mato"` yoki `"dark oak wood"`
2. LLM prompt yaratadi → **Tayyor prompt** kartasi chiqadi
3. **Generatsiya qilish** tugmasini bosing

### Variant 2 — Referens rasm orqali (tavsiya etiladi)
1. Chat inputi yonidagi 📎 tugmasini bosing
2. Material/mebel rasmi yuklang (JPEG/PNG/WEBP, max 5MB)
3. LLaVA avtomatik tahlil qiladi → prompt to'ldiriladi
4. Prompt kartasida `img2img ✓` belgisi ko'rinadi
5. **Generatsiya qilish** — referens rang/material saqlanadi

### Sozlamalar (⚙️ tugmasi)
- **O'lcham**: 512 / 1024 / 2048 px (ESRGAN bilan 4K ga upscale qilinadi)
- **Seed**: -1 = tasodifiy, aniq son = takrorlanuvchi natija

---

## Arxitektura

```
Foydalanuvchi (brauzer localhost:5173)
        │
        ├── Chat: "ko'k velvet" → POST /api/chat → Ollama llama3.2
        │                                              → SDXL prompt + "PROMPT:" marker
        │
        ├── Rasm: 📎 yuklash → POST /api/analyze → Ollama LLaVA
        │                                              → material tavsifi + prompt
        │
        └── Generate → POST /api/generate (multipart)
                              │
                    ┌─────────▼─────────┐
                    │  FastAPI Backend   │
                    │  localhost:8000    │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   comfy_client.py  │
                    │                   │
                    │  Referens rasm:   │
                    │  _prepare_texture │
                    │  _patch() →       │
                    │  Laplacian window │
                    │  → best patch     │
                    │                   │
                    │  img2img (0.82)   │
                    │  yoki txt2img     │
                    │                   │
                    │  ComfyUI REST+WS  │
                    │  localhost:8188   │
                    │  SDXL → ESRGAN 4K │
                    └─────────┬─────────┘
                              │ albedo bytes (4096×4096)
                    ┌─────────▼─────────┐
                    │ image_processor.py │
                    │ ProcessPoolExecutor│
                    │                   │
                    │ FFT Seamless      │
                    │ (Moisan 2011)     │
                    │ De-lit albedo     │
                    │ 6 PBR xarita      │
                    └─────────┬─────────┘
                              │
                    ZIP → GET /api/download/{job_id}
```

---

## API endpointlar

Swagger UI: `http://localhost:8000/docs`

### `POST /api/chat`
Multi-turn LLM suhbat — texture tavsifidan SDXL prompt yaratadi.
```json
Request:  { "messages": [{"role": "user", "content": "ko'k velvet"}] }
Response: { "success": true, "reply": "...", "prompt": "SDXL prompt yoki null" }
```
> `prompt` faqat LLM javobida `PROMPT:` markeri bo'lsa qaytadi.

### `POST /api/analyze`
Referens rasmni LLaVA bilan tahlil qiladi.
```
Request: multipart — image (file), user_hint (string, ixtiyoriy)
Response: { prompt, negative, category, description }
  category: fabric | leather | wood | metal | general
```

### `POST /api/enhance-prompt`
Qisqa matnni SDXL prompt ga aylantiradi (Ollama text model yoki mahalliy fallback).
```json
Request:  { "user_text": "ko'k charm" }
Response: { "prompt": "...", "fallback": false, "model_used": "llama3.2" }
```

### `POST /api/generate`
Generatsiya boshlaydi, darhol `job_id` qaytaradi.
```
Request: multipart
  prompt          — SDXL prompt (majburiy)
  resolution      — 512 | 1024 | 2048 (default: 1024)
  seed            — -1 = tasodifiy
  reference_image — fayl (bo'lsa img2img avtomatik yoqiladi)

Response: { job_id, status: "queued", progress: 0 }
```

### `GET /api/status/{job_id}`
Progress polling (har 1 soniyada).
```json
{
  "status": "queued | generating | postprocessing | done | error",
  "progress": 0..100,
  "previews": { "Color": "data:image/jpeg;base64,...", ... },
  "error": null
}
```

### `GET /api/download/{job_id}`
6 xaritani ZIP sifatida yuklaydi.

### `GET /api/comfyui-status` / `GET /api/ollama-status`
Xizmat ulanish holati.

---

## Texnik detallar

### img2img pipeline (referens rasm bilan)
1. **Texture patch ajratish** (`_prepare_texture_patch`):
   - Sliding window bilan Laplacian variance hisoblanadi
   - Eng yuqori variance → eng teksturali mintaqa
   - O'sha mintaqadan square crop → 1024×1024 resize
2. ComfyUI ga yuklash → img2img denoise=**0.82**
   - 0.65 → rasm deyarli o'zgarmaydi (mebel ko'rinishi qoladi)
   - 0.82 → rang/material saqlanadi, shakl yo'qoladi
   - 1.0 → txt2img bilan bir xil (referens e'tiborsiz)

### FFT Seamless — Moisan (2011) Periodic Decomposition
Eski usul (offset trick) seam ni markazga ko'chiradi — ko'rinadigan "xoch" artefakt qoladi.

Yangi usul: `f = p + s` dekompozitsiyasi
- `p` — periodic komponent (FFT orqali): chekkalarda matematik nolga teng farq
- `s` — smooth komponent: vignette, gradient — olib tashlanadi
- Natija: haqiqiy seamless, hech qanday artefakt yo'q

```python
# Har bir kanal uchun:
v = boundary_discontinuity(u)          # chegaraviy farqlar
denom = 2*(cos(wx) + cos(wy) - 2)     # eigenvalue matritsasi
s = ifft2(fft2(v) / denom)            # smooth komponent
p = u - s                              # periodic = original - smooth
```

Normal xaritalar uchun: FFT seamless + vektor re-normalizatsiya (`||v|| = 1`).

### De-lit Albedo (Frequency Separation)
AI generatsiya qilgan rasmda "baked" yoritish bor. Uni olib tashlash:
```
low_freq  = GaussianBlur(albedo, sigma = width × 10%)   # global yoritish
high_freq = albedo - low_freq                            # material detail
output    = mean_color + high_freq                       # tekis asos + detail
```

### SDXL sozlamalari
```
Steps:     35
CFG:       7.0
Sampler:   dpmpp_2m_sde
Scheduler: karras
Base:      1024×1024 (SDXL native)
Output:    4096×4096 (ESRGAN 4x yoki Lanczos fallback)
```

---

## Fayl tuzilmasi

```
pbrforge/
├── start.bat                    # Windows — bir tugma ishga tushirish
├── TZ.md                        # Dastlabki texnik spetsifikatsiya (v1.1)
│
├── backend/
│   ├── main.py                  # FastAPI app, ProcessPoolExecutor (max_workers=2)
│   ├── config.py                # Barcha sozlamalar (.env orqali override)
│   ├── requirements.txt
│   ├── jobs/                    # Vaqtinchalik ZIP arxivlar (TTL: 1 soat)
│   ├── routers/
│   │   └── generate.py          # Barcha REST endpointlar
│   └── services/
│       ├── vision_service.py    # Ollama: LLaVA tahlil + LLM chat + enhance
│       ├── prompt_builder.py    # PBR prompt generatsiya (material kategoriyalar)
│       ├── comfy_client.py      # ComfyUI REST+WebSocket, img2img/txt2img workflow
│       └── image_processor.py  # OpenCV: FFT seamless + 6 PBR xarita
│
└── frontend/
    └── src/
        ├── App.jsx              # 2-ustun layout, polling logic
        ├── store/
        │   └── useStore.js      # Zustand: status, progress, previews, analyzing
        └── components/
            ├── SettingsPanel.jsx  # Chat UI, rasm yuklash, generatsiya
            ├── Preview3D.jsx      # Three.js sphere (qoldirilgan, ishlatilmaydi)
            └── ResultGallery.jsx  # 6 xarita 3×2 grid, progress bar, ZIP
```

---

## Konfiguratsiya (.env)

```env
# ComfyUI
COMFYUI_HOST=127.0.0.1
COMFYUI_PORT=8188

# SDXL modeli
CHECKPOINT_NAME=Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors

# 4K Upscale
UPSCALE_MODEL=4x_NMKD-Siax_200k.pth
OUTPUT_RESOLUTION=4096

# Generatsiya
DEFAULT_STEPS=35
DEFAULT_CFG=7.0
DEFAULT_SAMPLER=dpmpp_2m_sde
DEFAULT_SCHEDULER=karras

# Post-processing
NORMAL_STRENGTH=4.0       # Normal map keskinligi
ROUGHNESS_GAMMA=1.2       # Roughness gamma korreksiya
AO_BLUR_SIGMA=4.0         # AO blur kuchi
SEAMLESS_BLEND_PX=64      # FFT uchun ishlatilmaydi (eski offset trick uchun)
DELIT_SIGMA_PCT=0.10      # De-lit sigma (rasm kengligi × 10%)

# Limitlar
MAX_REF_IMAGE_MB=5
MAX_REF_DIMENSION=1024    # Referens rasm maksimal o'lchami
JOB_TIMEOUT=600           # 10 daqiqa
JOB_TTL=3600              # Job saqlash muddati (1 soat)

# API server
API_HOST=0.0.0.0
API_PORT=8000
```

---

## Muammolar va yechimlar

**Ollama ishlamayapti**
```
"Ollama ishga tushirilmagan. Terminal: ollama serve"
```
→ `ollama serve` buyrug'ini ishga tushiring.

**LLaVA model yo'q**
```
"LLaVA model o'rnatilmagan. Terminal: ollama pull llava:7b"
```
→ `ollama pull llava:7b` (~4GB, bir marta).

**Chat ishlaydi lekin LLM yo'q**
```
{ "fallback": true }
```
→ `ollama pull llama3.2` o'rnating. Hozircha mahalliy prompt builder ishlatiladi.

**ComfyUI ishlamayapti**
→ `python ComfyUI/main.py` ni ishga tushiring.

**Checkpoint topilmadi**
→ `.env` dagi `CHECKPOINT_NAME` ni ComfyUI/models/checkpoints/ dagi fayl nomi bilan moslashtiring.

**4K sifatsiz (Lanczos fallback)**
→ `4x_NMKD-Siax_200k.pth` ni ComfyUI/models/upscale_models/ ga joylang.

**img2img ishlaydi lekin natija o'xshamaydi**
→ `comfy_client.py` da `denoise` qiymatini kamaytiring (0.82 → 0.70).
   Kichik denoise = referensga yaqinroq, lekin mebel shakli qolishi mumkin.

**ProcessPoolExecutor xatosi**
→ `backend/jobs/` papkasi mavjudligini tekshiring. Yo'q bo'lsa yarating.

---

## Versiya tarixi

| Versiya | O'zgarishlar |
|---|---|
| v0.1 | Dastlabki TZ, SD 1.5 + basic post-processing |
| v0.2 | FastAPI backend, ProcessPoolExecutor, CORS, polling |
| v0.3 | SDXL ga o'tish, LLaVA vision, prompt_builder, mebel qismlari aniqlash |
| v0.4 | Chat UI (LLM multi-turn), FFT seamless (Moisan), img2img auto, texture patch extraction, 2-ustun layout |

---

## Texnologiyalar

| Qatlam | Texnologiya |
|---|---|
| Backend | FastAPI, Uvicorn, Python 3.10+ |
| Image processing | OpenCV 4.9, NumPy 1.26 |
| HTTP / WebSocket | httpx, websockets |
| Frontend | React 18, Vite, Tailwind CSS |
| State management | Zustand |
| AI generatsiya | ComfyUI, SDXL (Juggernaut XL v9) |
| Vision AI | Ollama, LLaVA 7B |
| LLM chat | Ollama, llama3.2 (yoki boshqa text model) |
| 4K Upscale | ESRGAN (4x_NMKD-Siax_200k) |

---

## Kelajakda yaxshilash mumkin bo'lgan joylar

- **Texture sifati**: SDXL texture LoRA qo'shish (masalan, `textures-and-patterns-sdxl`)
- **ControlNet**: Strukturani saqlab rang/material o'zgartirish
- **Batch generatsiya**: Bir vaqtda bir nechta texture
- **Preset materiallar**: Velvet, charm, yog'och — bir bosishda tayyor prompt
- **Negative prompt UI**: Foydalanuvchi o'zi boshqarsin
- **History**: Avvalgi generatsiyalarni saqlash va ko'rish
- **Export formats**: PNG, EXR, sRGB/Linear konversiya
- **Linux/Mac**: `start.bat` o'rniga cross-platform skript
