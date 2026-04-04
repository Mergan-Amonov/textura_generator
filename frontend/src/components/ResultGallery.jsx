import { useState } from 'react'
import axios from 'axios'
import { useStore } from '../store/useStore'

const MAP_LABELS = {
  Color:     'Albedo (De-lit)',
  NormalGL:  'Normal GL',
  Height:    'Height / Displacement',
  Roughness: 'Roughness',
  Metallic:  'Metallic',
  AO:        'Ambient Occlusion',
}

const MAP_ORDER = ['Color', 'NormalGL', 'Height', 'Roughness', 'Metallic', 'AO']

// ── Lightbox Modal ─────────────────────────────────────────────────────────
function Lightbox({ src, label, onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative max-w-2xl max-h-[90vh] p-1 bg-panel rounded-xl shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <img
          src={src}
          alt={label}
          className="rounded-lg max-h-[80vh] object-contain"
        />
        <p className="text-center text-xs text-gray-400 py-2">{label}</p>
        <button
          onClick={onClose}
          className="absolute top-2 right-2 w-7 h-7 rounded-full bg-gray-700 hover:bg-gray-600
                     text-gray-300 text-sm flex items-center justify-center transition-colors"
        >
          ×
        </button>
      </div>
    </div>
  )
}

// ── Thumbnail karta ────────────────────────────────────────────────────────
function MapCard({ mapKey, src, onClick }) {
  return (
    <div
      className="flex flex-col gap-1.5 cursor-pointer group"
      onClick={() => onClick(mapKey, src)}
    >
      <div className="relative overflow-hidden rounded-lg border border-border
                      group-hover:border-accent transition-colors aspect-square bg-surface">
        <img
          src={src}
          alt={mapKey}
          className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
        />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors
                        flex items-center justify-center">
          <span className="opacity-0 group-hover:opacity-100 text-white text-xs
                           bg-black/50 px-2 py-1 rounded transition-opacity">
            Kattalashtirish
          </span>
        </div>
      </div>
      <p className="text-xs text-gray-400 text-center truncate">{MAP_LABELS[mapKey]}</p>
    </div>
  )
}

// ── Asosiy komponent ───────────────────────────────────────────────────────
export default function ResultGallery() {
  const { status, previews, jobId } = useStore()
  const [lightbox, setLightbox] = useState(null)   // { key, src } | null
  const [downloading, setDownloading] = useState(false)

  const isDone = status === 'done' && previews

  const openLightbox = (key, src) => setLightbox({ key, src })
  const closeLightbox = () => setLightbox(null)

  const downloadZip = async () => {
    if (!jobId || downloading) return
    setDownloading(true)
    try {
      const res = await axios.get(`/api/download/${jobId}`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a   = document.createElement('a')
      a.href     = url
      a.download = 'PBR_Material.zip'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      alert('ZIP yuklab olishda xato')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-panel">
      {/* Header */}
      <div className="px-5 py-4 border-b border-border">
        <h2 className="text-sm font-semibold text-gray-200">Natijalar</h2>
        <p className="text-xs text-gray-500 mt-0.5">4 PBR xarita</p>
      </div>

      <div className="flex flex-col flex-1 px-4 py-4 gap-4">
        {isDone ? (
          <>
            {/* 2x2 thumbnail grid */}
            <div className="grid grid-cols-2 gap-3">
              {MAP_ORDER.map(key =>
                previews[key] ? (
                  <MapCard
                    key={key}
                    mapKey={key}
                    src={previews[key]}
                    onClick={openLightbox}
                  />
                ) : null
              )}
            </div>

            {/* ZIP yuklab olish */}
            <button
              onClick={downloadZip}
              disabled={downloading}
              className="w-full py-2.5 bg-accent hover:bg-accent-hover text-white text-sm
                         font-semibold rounded-lg transition-colors mt-auto
                         disabled:opacity-50 disabled:cursor-not-allowed flex items-center
                         justify-center gap-2"
            >
              {downloading ? (
                <>
                  <span className="animate-spin text-base">↻</span>
                  Yuklanmoqda...
                </>
              ) : (
                'ZIP yuklab olish'
              )}
            </button>

            {/* Xarita nomlari haqida izoh */}
            <div className="border border-border rounded-lg p-3">
              <p className="text-xs text-gray-500 leading-relaxed">
                <strong className="text-gray-400">Color</strong> — Albedo de-lit (4K)<br />
                <strong className="text-gray-400">NormalGL</strong> — Normal OpenGL<br />
                <strong className="text-gray-400">Height</strong> — Displacement<br />
                <strong className="text-gray-400">Roughness</strong> — Roughness<br />
                <strong className="text-gray-400">Metallic</strong> — Metallic mask<br />
                <strong className="text-gray-400">AO</strong> — Ambient Occlusion
              </p>
            </div>
          </>
        ) : (
          // Bo'sh holat
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
            <div className="grid grid-cols-2 gap-2 opacity-20">
              {MAP_ORDER.map(key => (
                <div key={key} className="aspect-square bg-gray-700 rounded-lg" />
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Generatsiyadan so'ng<br />xaritalar bu yerda ko'rinadi
            </p>
          </div>
        )}
      </div>

      {/* Lightbox */}
      {lightbox && (
        <Lightbox
          src={lightbox.src}
          label={MAP_LABELS[lightbox.key] || lightbox.key}
          onClose={closeLightbox}
        />
      )}
    </div>
  )
}
