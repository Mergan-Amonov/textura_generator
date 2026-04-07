# PBRForge::Core

Mebel 3D modellari uchun lokal PBR texture generator.  
Referens rasm yuklang → LLaVA AI tahlil → SDXL generatsiya → 6 professional PBR xarita.

---

## Nima qiladi

1. Referens rasm (mato, charm, yog'och, metall) yuklaysiz
2. LLaVA vision AI material turini aniqlaydi va SDXL prompt yaratadi
3. ComfyUI / SDXL 4K albedo generatsiya qiladi
4. OpenCV 6 ta PBR xaritani avtomatik chiqaradi:
   - **Color** — de-lit seamless albedo
   - **NormalGL** — OpenGL format normal map
   - **Height** — grayscale displacement map
   - **Roughness** — roughness map
   - **Metallic** — metallic map
   - **AO** — ambient occlusion
5. ZIP arxiv sifatida yuklab olasiz

---

## Talablar

| Komponent | Versiya | Izoh |
|---|---|---|
| Python | 3.10+ | Backend uchun |
| Node.js | 18+ | Frontend uchun |
| ComfyUI | latest | `localhost:8188` da ishlab turishi kerak |
| Ollama | latest | `localhost:11434` da ishlab turishi kerak |
| GPU | 8GB+ VRAM | SDXL uchun tavsiya etiladi |

### Modellar

**SDXL checkpoint** — ComfyUI/models/checkpoints/ ga joylashtiring:
```
Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors
```

**Ollama vision modeli** — terminalda bir marta ishlatiladi:
```bash
ollama pull llava:7b
```

**4K Upscale** (ixtiyoriy, bo'lmasa Lanczos bilan fallback) — ComfyUI/models/upscale_models/ ga:
```
4x_NMKD-Siax_200k.pth
```
yoki
```
RealESRGAN_x4plus.pth
```

---

## O'rnatish va ishga tushirish

### 1. ComfyUI va Ollama ni yoqing

```bash
# ComfyUI
python ComfyUI/main.py

# Ollama (alohida terminalda)
ollama serve
```

### 2. PBRForge ni ishga tushiring

```bash
# Windows
start.bat
```

`start.bat` avtomatik ravishda:
- Python va Node.js paketlarni o'rnatadi (birinchi ishga tushirishda)
- Backend (`localhost:8000`) va Frontend (`localhost:5173`) ni alohida oynalarda yoqadi
- Brauzerda avtomatik ochadi

### Qo'lda ishga tushirish

```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py

# Frontend (alohida terminal)
cd frontend
npm install
npm run dev
```

---

## Sozlamalar

`backend/.env` fayl yaratib o'zgartiring (`.env.example` asosida):

```env
# SDXL model nomi (ComfyUI/models/checkpoints/ dagi fayl nomi)
CHECKPOINT_NAME=Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors

# 4K Upscale modeli (ComfyUI/models/upscale_models/)
UPSCALE_MODEL=4x_NMKD-Siax_200k.pth
OUTPUT_RESOLUTION=4096

# SDXL parametrlari
DEFAULT_STEPS=35
DEFAULT_CFG=7.0
DEFAULT_SAMPLER=dpmpp_2m_sde
DEFAULT_SCHEDULER=karras

# Post-processing
NORMAL_STRENGTH=4.0
ROUGHNESS_GAMMA=1.2
AO_BLUR_SIGMA=4.0
SEAMLESS_BLEND_PX=64
DELIT_SIGMA_PCT=0.10

# Limitlar
MAX_REF_IMAGE_MB=5
MAX_REF_DIMENSION=1024
JOB_TIMEOUT=600
```

---

## API

Swagger UI: `http://localhost:8000/docs`

### `POST /api/analyze`
Referens rasmni LLaVA bilan tahlil qiladi va PBR prompt qaytaradi.

```
Request: multipart/form-data
  image      — rasm fayli (JPEG/PNG/WEBP, max 5MB)
  user_hint  — qo'shimcha izoh (ixtiyoriy)

Response:
  prompt      — tayyor SDXL prompt
  negative    — negative prompt
  category    — fabric | leather | wood | metal | general
  use_img2img — img2img tavsiyasi
  description — LLaVA xom tavsifi
```

### `POST /api/parts`
Mebel rasmini tahlil qilib qismlarini aniqlaydi (oyoq, o'rindiq, suyanchiq...).

```
Request: multipart/form-data
  image — rasm fayli

Response:
  parts — [{ part, material, category }, ...]
```

### `POST /api/generate`
Yangi generatsiya boshlaydi, darhol `job_id` qaytaradi.

```
Request: multipart/form-data
  prompt          — texture tavsifi (majburiy)
  resolution      — 512 | 1024 | 2048 (default: 1024)
  seed            — -1 = tasodifiy (default: -1)
  use_img2img     — referens rasm ishlatilsinmi (default: false)
  reference_image — referens rasm (use_img2img=true bo'lganda)

Response:
  job_id   — kuzatish uchun UUID
  status   — "queued"
  progress — 0
```

### `GET /api/status/{job_id}`
Generatsiya holatini qaytaradi (har 1 soniyada so'rash mumkin).

```
Response:
  status   — queued | generating | postprocessing | done | error
  progress — 0..100
  previews — { Color, NormalGL, Height, Roughness, Metallic, AO } base64 (done bo'lganda)
  error    — xato matni yoki null
```

### `GET /api/download/{job_id}`
Barcha 6 xaritani ZIP arxiv sifatida yuklab beradi.

### `GET /api/comfyui-status`
ComfyUI ulanish holati.

### `GET /api/ollama-status`
Ollama ulanish holati.

---

## Arxitektura

```
Foydalanuvchi (brauzer)
        │
        ▼
React Frontend (localhost:5173)
   SettingsPanel — rasm yuklash, AI tahlil, prompt, sozlamalar
   Preview3D     — @react-three/fiber, 3D ko'rinish
   ResultGallery — 6 xarita preview, ZIP yuklash
        │
        │ REST API
        ▼
FastAPI Backend (localhost:8000)
   POST /api/analyze  → vision_service.py → Ollama LLaVA
   POST /api/parts    → vision_service.py → Ollama LLaVA
   POST /api/generate → BackgroundTask
                            │
                            ▼
                     comfy_client.py
                     POST /prompt → ComfyUI (localhost:8188)
                     WebSocket    → progress kuzatish
                     GET /history → albedo bytes yuklash
                            │
                            ▼
                     image_processor.py (ProcessPoolExecutor)
                     6 PBR xarita generatsiya (OpenCV)
                            │
                            ▼
                     ZIP arxiv → /api/download/{job_id}
```

---

## PBR xarita generatsiya algoritmlari

### Color (De-lit Albedo)
Frequency separation texnikasi: AI generatsiya qilgan rasmda "baked" yoritish gradientini olib tashlaydi.
- Katta sigma Gaussian blur → past chastotali yoritish ayrimi
- Yuqori chastota (material detail) + o'rtacha rang → tozalangan albedo

### Normal GL
OpenGL format normal map (Sobel gradienti asosida).
- Bilateral filter pre-processing (qirralarni saqlagan holda shovqin yo'qotiladi)
- Sobel ksize=5 → Gx, Gy gradientlari
- Vektor normalizatsiya (||v|| = 1)
- Seamless blend → re-normalizatsiya (piksel buzilishini oldini oladi)

### Height
Multi-scale displacement map.
- Coarse (σ=8) × 0.25 — yirik balandlik tuzilmalari
- Medium (σ=2) × 0.45 — o'rtacha bumps
- Fine (raw) × 0.30 — mayda detallar

### Roughness
CLAHE lokal kontrast kuchaytirilgan roughness map.
- Yorug' = silliq (low roughness), qorong'i = g'adir-budir (high roughness)
- Gamma korreksiya (default 1.2)

### Metallic
HSV-based heuristic: `metallic ≈ value^0.8 × (1 - saturation)^2`
- Yuqori yorqinlik + past to'yinganlik → metall belgisi
- Bilateral filter smoothing

### AO (Ambient Occlusion)
Multi-scale Gaussian difference.
- 3 miqyos: σ×0.5, σ, σ×3
- Pastki chegara 0.45 (juda qorong'i AO dan saqlaydi)

### Seamless (barcha xaritalar)
Offset-trick + smoothstep alpha blend.
- Rasm yarmi o'rtaga siljitiladi, S-egri gradient bilan blend qilinadi
- Normal xaritalarda: blend → vektor re-normalizatsiya (||v|| = 1 saqlanishi shart)

---

## Fayl tuzilmasi

```
pbrforge/
├── start.bat                        # Bir tugma bilan ishga tushirish (Windows)
├── TZ.md                            # Texnik spetsifikatsiya
│
├── backend/
│   ├── main.py                      # FastAPI app, ProcessPoolExecutor
│   ├── config.py                    # Barcha sozlamalar (.env orqali)
│   ├── requirements.txt
│   ├── jobs/                        # Generatsiya ZIP arxivlari (vaqtinchalik)
│   ├── routers/
│   │   └── generate.py              # Barcha API endpointlar
│   └── services/
│       ├── vision_service.py        # Ollama LLaVA integratsiya
│       ├── prompt_builder.py        # PBR prompt generatsiya
│       ├── comfy_client.py          # ComfyUI REST + WebSocket
│       └── image_processor.py       # OpenCV 6-map post-processing
│
└── frontend/
    └── src/
        ├── App.jsx
        ├── main.jsx
        ├── store/
        │   └── useStore.js          # Zustand global state
        └── components/
            ├── SettingsPanel.jsx    # Chap panel: rasm yuklash, AI tahlil, sozlamalar
            ├── Preview3D.jsx        # Markaziy: Three.js 3D ko'rinish
            └── ResultGallery.jsx    # O'ng panel: 6 xarita gallery, ZIP yuklash
```

---

## Muammolar va yechimlar

**Ollama ishlamayapti**
```
detail: "Ollama ishga tushirilmagan. Terminal: ollama serve"
```
→ Terminalda `ollama serve` ishga tushiring.

**LLaVA model topilmadi**
```
detail: "LLaVA model o'rnatilmagan. Terminal: ollama pull llava:7b"
```
→ `ollama pull llava:7b` buyrug'ini ishga tushiring (bir marta, ~4GB).

**ComfyUI ishlamayapti**
```
detail: "ComfyUI ishga tushirilmagan."
```
→ `python ComfyUI/main.py` ni ishga tushiring.

**Checkpoint topilmadi (ComfyUI xatosi)**  
→ `config.py` yoki `.env` dagi `CHECKPOINT_NAME` ni ComfyUI/models/checkpoints/ dagi fayl nomi bilan moslashtiring.

**4K sifatsiz (Lanczos)**  
→ `4x_NMKD-Siax_200k.pth` yoki `RealESRGAN_x4plus.pth` ni ComfyUI/models/upscale_models/ ga joylang.

---

## Texnologiyalar

| | |
|---|---|
| **Backend** | FastAPI, Uvicorn, Python 3.10+ |
| **Image processing** | OpenCV 4.9, NumPy 1.26 |
| **HTTP / WS client** | httpx, websockets |
| **Frontend** | React 18, Vite, Tailwind CSS |
| **3D** | @react-three/fiber, @react-three/drei |
| **State** | Zustand |
| **AI generatsiya** | ComfyUI, SDXL (Juggernaut XL) |
| **Vision AI** | Ollama, LLaVA 7B |
