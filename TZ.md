# PBRForge::Core — Texnik Spetsifikatsiya (TZ)

**Versiya:** 1.1 (Yangilangan arxitektura va React integratsiyasi bilan)
**Sana:** 2026-04-03
**Holat:** v0.2 — Xatolar tuzatilgan, yangi stek tasdiqlangan

---

## 1. Umumiy Ma'lumot

### 1.1 Loyiha nomi va maqsadi
**PBRForge::Core** — lokal kompyuterda ishlovchi, matn tavsifi yoki referens rasm asosida professional, choksiz (seamless) PBR materiallarni avtomatik generatsiya qiluvchi vosita. Loyiha bitta jarayonda 4 ta xarita (Color, NormalGL, Roughness, AmbientOcclusion) yaratadi va 3D ko'rinishda taqdim etadi.

### 1.2 Asosiy cheklovlar
- **Lokal ishlash:** Internet talab etilmaydi (model yuklangandan so'ng).
- **GPU:** SDv1.5/SDXL uchun majburiy (min 4GB-8GB VRAM).
- **Asosiy AI Dvijok:** ComfyUI (localhost:8188).

---

## 2. Texnik Arxitektura

### 2.1 Yangilangan Umumiy Sxema

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Foydalanuvchi brauzeri                      │
│        React Frontend (http://localhost:5173 - Dev/Build)       │
│                                                                 │
│  [ React Komponentlar: Form, Three.js Canvas, ImageGallery ]    │
└─────────┬───────────────────────────────▲───────────────────────┘
          │ REST API (POST)               │ REST API (GET Polling)
          │ form-data                     │ status & progress
          ▼                               │
┌─────────────────────────────────────────┴───────────────────────┐
│                    FastAPI Backend (localhost:8000)             │
│                                                                 │
│  [API Endpointlar] <───> [In-Memory Job Registry (job_id)]      │
│          │                               │                      │
│          ▼                               ▼                      │
│  [Background Worker]             [ComfyUI Service]              │
│  - ProcessPoolExecutor           - REST so'rovlar (prompt_id)   │
│    (Og'ir hisob-kitoblar)        - WebSocket (localhost:8188/ws)│
└─────────┬────────────────────────────────▲──────────────────────┘
          │ POST /prompt                   │ WS hodisalar
          │ GET  /history, /view           │ (progress, success)
          ▼                                │
┌──────────────────────────────────────────┴──────────────────────┐
│                    ComfyUI (localhost:8188)                     │
│  - SD Checkpoints, VAE, CLIP, Samplers                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Yangilangan Texnologiya Steki

| Qatlam | Texnologiya | Maqsad va Izoh |
|---|---|---|
| **Frontend** | React 18, Vite | Komponentli arxitektura va tezkor build |
| **Styling** | Tailwind CSS | Zamonaviy va moslashuvchan dizayn |
| **3D Preview** | `@react-three/fiber` | React muhitida Three.js bilan ishlash |
| **State** | Zustand | Global holatni boshqarish (progress, status) |
| **Backend** | FastAPI + Uvicorn | Asinxron REST API server |
| **Og'ir jarayonlar** | `ProcessPoolExecutor` | API GIL'ni bloklamaslik uchun |
| **Image Math** | OpenCV (`cv2`), NumPy | Yuqori tezlikdagi matritsa hisoblari |
| **AI Engine** | ComfyUI | Grafiklarga asoslangan Stable Diffusion |

### 2.3 Fayl Tuzilmasi

```text
pbrforge/
├── start.bat                    # Frontend va Backend'ni birga ishga tushirish
├── frontend/                    # Vite + React loyiha
│   ├── src/
│   │   ├── components/          # Uploader, ProgressBar, ThreeViewer, MapGallery
│   │   ├── store/               # Zustand state (useStore.js)
│   │   ├── App.jsx              # Asosiy layout
│   │   └── main.jsx
│   ├── package.json
│   └── tailwind.config.js
└── backend/                     # FastAPI loyiha
    ├── main.py                  # API routerlar
    ├── config.py                # Pydantic orqali .env nazorati
    ├── services/
    │   ├── comfy_client.py      # ComfyUI bilan aloqa (REST + WS proxy)
    │   └── image_processor.py   # OpenCV post-processing
    ├── utils/
    │   └── seamless.py          # Choksiz qilingan xaritalarni qayta ishlash
    └── requirements.txt
```

---

## 3. Funksional Talablar

### F-01: Generatsiya Jarayoni
Matn yoki referens rasm yuborilgach, backend `job_id` yaratadi. Ushbu `job_id` ComfyUI ning qaytargan `prompt_id` si bilan bog'lanadi. Jarayon asinxron tarzda orqa fonda ishlaydi.

### F-02: Referens Rasm Cheklovlari (Xavfsizlik)
- **Maksimal hajm:** 5 MB.
- **Ruxsat etilgan formatlar:** JPEG, PNG, WEBP.
- Backend rasmni ComfyUI ga yuborishdan oldin mutanosibligini saqlagan holda maksimal **1024x1024 o'lchamga downscale** qiladi.

### F-03: Vaqt Limiti (Timeout)
ComfyUI dagi har bir job uchun **300 soniya (5 daqiqa)** qat'iy limit belgilanadi. Agar shu vaqt ichida generatsiya tugamasa, backend ulanishni yopadi va job holatini `Timeout Error` ga o'zgartiradi. Tizim resurslari tozalanadi.

### F-04: Post-Processing va Fizika (Luminance)
ComfyUI dan olingan Albedo rasmida yorug'lik va soyalar aralash bo'ladi. U haqiqiy balandlik xaritasi (heightmap) emas.
- Shuning uchun AI dan olingan rasmning **Luminance (Yorqinlik)** qismi olinib, taxminiy balandlik sifatida ishlatiladi.
- Barcha amallar (`Sobel`, `Gaussian blur`) serverni qotirib qo'ymasligi uchun `ProcessPoolExecutor` ichida, C++ da optimallashtirilgan **OpenCV** yordamida bajariladi.

### F-05: Choksizlantirish (Seamless Tiling)
Offset-trick algoritmi yordamida rasmning o'rtasi chetlariga siljitiladi va alpha-blending bilan aralashtiriladi.
- **Normal xaritalar uchun qat'iy qoida:** Alpha-blending natijasida RGB vektorlari buziladi. Normal xarita choksiz holatga keltirilgandan so'ng, uning har bir pikselidagi (R,G,B) vektorlari qat'iy ravishda **uzunligi 1 ga teng bo'lishi uchun qayta normalizatsiya qilinadi**. Aks holda 3D modelda qora nuqtalar paydo bo'ladi.

---

## 4. API Spetsifikatsiyasi

### `POST /api/generate`
**Request:** `multipart/form-data`
| Maydon | Tur | Majburiy | Izoh |
|---|---|---|---|
| `prompt` | string | Ha | Matnli tavsif |
| `resolution` | int | Yo'q | Default: 1024 |
| `reference_image` | file | Yo'q | Max 5MB |

**Response:** Status qabul qilinadi.
```json
{
  "job_id": "uuid-4-string",
  "status": "queued",
  "message": "ComfyUI prompt_id bilan bog'landi"
}
```

### `GET /api/status/{job_id}`
Frontend faqat shu endpoint orqali holatni tekshiradi (Polling, masalan, har 1 soniyada). Frontend to'g'ridan-to'g'ri ComfyUI ga ulanmaydi.
```json
{
  "job_id": "uuid-4-string",
  "status": "generating | postprocessing | done | error",
  "progress": 45,
  "previews": null
}
```

---

## 5. ComfyUI Integratsiyasi (Handoff)

Backend rasmlarni qabul qilib olish va qayta ishlash uchun quyidagi zanjirni bajaradi:

1. **Yuborish:** `POST /prompt` orqali workflow yuboriladi, javob sifatida `prompt_id` olinadi.
2. **Kuzatish:** Backend `ws://127.0.0.1:8188/ws` orqali ulanadi va faqat shu `prompt_id` ga tegishli progressni tinglaydi.
3. **Yuklab olish (Handoff):** WS dan "success" xabari kelgach, backend `GET /history/{prompt_id}` so'rovini yuborib, ComfyUI saqlagan rasm nomlarini aniqlaydi. So'ngra `GET /view?filename={name}` orqali rasmni RAM (baytlar) ga yuklab oladi.
4. **Qayta ishlash:** Rasm xotiraga olingach, ComfyUI serveridagi fayl o'chirilishi (yoki e'tiborsiz qoldirilishi) mumkin. Barcha OpenCV hisob-kitoblari FastAPI xotirasida, izolyatsiya qilingan jarayonda kechadi.

---

## 6. Matematika va OpenCV Kod Mantiqlari

### Normal xarita yaratish
```python
import cv2
import numpy as np

# 1. Albedoni kulrang (luminance) formatga o'tkazish
gray = cv2.cvtColor(albedo_img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

# 2. OpenCV yordamida Sobel gradientlari
Gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
Gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
Gz = np.full_like(gray, 1.0 / strength)

# 3. Vektorlarni normalizatsiya qilish (Vektor uzunligi = 1)
length = np.sqrt(Gx**2 + Gy**2 + Gz**2)
nx, ny, nz = Gx/length, Gy/length, Gz/length

# 4. OpenGL formatiga o'tkazish (0..255)
normal_map = np.stack(((nx*0.5+0.5), (ny*0.5+0.5), (nz*0.5+0.5)), axis=2) * 255
```

### Ambient Occlusion (AO)
```python
# SciPy o'rniga yuqori tezlikdagi OpenCV qo'llaniladi
blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=4, sigmaY=4)
ao = gray - blurred
ao = cv2.normalize(ao, None, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
ao_map = (0.5 + ao * 0.5) * 255
```

---

## 7. Frontend (React) Arxitekturasi

React interfeysi 3 ta asosiy mantiqiy blokka bo'linadi:

1. **`SettingsPanel` (Chap ustun):**
   - Matnli prompt maydoni.
   - O'lcham va Seed tanlash (`useState`).
   - Rasm yuklash (File API yordamida hajmini frontend'da ham 5MB gacha cheklash).
   - "Generatsiya" tugmasi, Zustand dagi holat `generating` bo'lganda disabled bo'ladi.

2. **`Preview3D` (Markaziy ustun):**
   - `@react-three/fiber` va `@react-three/drei` (OrbitControls uchun).
   - `meshStandardMaterial` ishlatiladi. `TextureLoader` orqali backend'dan kelgan base64 formatdagi xaritalarni Sphere'ga yopishtiradi.
   - Generatsiya jarayonida xaritalar o'rniga faqat Progress Bar (Zustand dan olinadi) ko'rsatiladi.

3. **`ResultGallery` (O'ng ustun):**
   - Tizim `done` holatiga o'tganda 4 ta kichik rasm (thumbnail) paydo bo'ladi.
   - Rasmlarni kattalashtirib ko'rish uchun `LightBox` yoki Modal komponenti.
   - ZIP faylni tortib olish uchun yuklab olish tugmasi (Axios orqali blob data qabul qilinadi).