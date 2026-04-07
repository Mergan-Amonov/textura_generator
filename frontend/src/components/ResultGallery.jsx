import { useState } from 'react'
import axios from 'axios'
import { useStore } from '../store/useStore'

const MAP_LABELS = {
  Color:     'Albedo',
  NormalGL:  'Normal GL',
  Height:    'Height',
  Roughness: 'Roughness',
  Metallic:  'Metallic',
  AO:        'AO',
}

const MAP_ORDER = ['Color', 'NormalGL', 'Height', 'Roughness', 'Metallic', 'AO']

// ── Lightbox ───────────────────────────────────────────────────────────────────
function Lightbox({ src, label, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
      onClick={onClose}>
      <div className="relative max-w-3xl max-h-[90vh] p-1 bg-panel rounded-xl shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <img src={src} alt={label} className="rounded-lg max-h-[85vh] object-contain" />
        <p className="text-center text-xs text-gray-400 py-2">{label}</p>
        <button onClick={onClose}
          className="absolute top-2 right-2 w-7 h-7 rounded-full bg-gray-700 hover:bg-gray-600
                     text-gray-300 flex items-center justify-center text-sm transition-colors">
          ×
        </button>
      </div>
    </div>
  )
}

// ── Map thumbnail ──────────────────────────────────────────────────────────────
function MapCard({ mapKey, src, onClick }) {
  return (
    <div className="flex flex-col gap-1 cursor-pointer group" onClick={() => onClick(mapKey, src)}>
      <div className="relative overflow-hidden rounded-lg border border-border
                      group-hover:border-accent transition-colors aspect-square bg-surface">
        <img src={src} alt={mapKey}
          className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105" />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/25 transition-colors
                        flex items-end justify-center pb-2">
          <span className="opacity-0 group-hover:opacity-100 text-white text-xs
                           bg-black/60 px-2 py-0.5 rounded transition-opacity">
            Kattalashtirish
          </span>
        </div>
      </div>
      <p className="text-xs text-gray-400 text-center">{MAP_LABELS[mapKey]}</p>
    </div>
  )
}

// ── Asosiy komponent ───────────────────────────────────────────────────────────
export default function ResultGallery() {
  const { status, progress, previews, jobId, error } = useStore()
  const [lightbox, setLightbox]     = useState(null)
  const [downloading, setDownloading] = useState(false)

  const isGenerating = status === 'queued' || status === 'generating' || status === 'postprocessing'
  const isDone       = status === 'done' && previews
  const isError      = status === 'error'

  const statusLabel = {
    queued:         'Navbatda...',
    generating:     'AI generatsiya qilmoqda...',
    postprocessing: 'PBR xaritalar ishlanmoqda...',
  }[status] || ''

  const statusHint = {
    queued:         'ComfyUI ga ulanilmoqda',
    generating:     'SDXL, ~1-3 daqiqa',
    postprocessing: 'Normal · Roughness · AO · Height',
  }[status] || ''

  const downloadZip = async () => {
    if (!jobId || downloading) return
    setDownloading(true)
    try {
      const res = await axios.get(`/api/download/${jobId}`, { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const a   = document.createElement('a')
      a.href = url; a.download = 'PBR_Material.zip'
      document.body.appendChild(a); a.click()
      document.body.removeChild(a); URL.revokeObjectURL(url)
    } catch {
      alert('ZIP yuklab olishda xato')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-panel">

      {/* Header */}
      <div className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-200">Natijalar</h2>
          <p className="text-xs text-gray-500 mt-0.5">6 PBR xarita · 4K</p>
        </div>
        {isDone && (
          <button onClick={downloadZip} disabled={downloading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent hover:bg-accent-hover
                       text-white text-xs font-medium rounded-lg transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed">
            {downloading ? '...' : (
              <>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                ZIP
              </>
            )}
          </button>
        )}
      </div>

      <div className="flex flex-col flex-1 px-6 py-5 gap-5 overflow-y-auto">

        {/* ── Generatsiya jarayoni ─────────────────────────────── */}
        {isGenerating && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-200">{statusLabel}</p>
              <span className="text-2xl font-bold text-accent">{progress}%</span>
            </div>
            <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-accent rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }} />
            </div>
            <p className="text-xs text-gray-500">{statusHint}</p>

            {/* Skeleton cards */}
            <div className="grid grid-cols-3 gap-3 mt-2">
              {MAP_ORDER.map(key => (
                <div key={key} className="flex flex-col gap-1">
                  <div className="aspect-square bg-gray-800 rounded-lg animate-pulse" />
                  <p className="text-xs text-gray-600 text-center">{MAP_LABELS[key]}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Xato ────────────────────────────────────────────── */}
        {isError && (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <div className="w-12 h-12 rounded-full bg-red-900/30 flex items-center justify-center">
              <span className="text-red-400 text-xl">!</span>
            </div>
            <p className="text-sm font-medium text-red-400">Xato yuz berdi</p>
            <p className="text-xs text-gray-400 max-w-xs break-words">{error}</p>
          </div>
        )}

        {/* ── Natijalar ────────────────────────────────────────── */}
        {isDone && (
          <>
            <div className="grid grid-cols-3 gap-3">
              {MAP_ORDER.map(key =>
                previews[key] ? (
                  <MapCard key={key} mapKey={key} src={previews[key]}
                    onClick={(k, s) => setLightbox({ key: k, src: s })} />
                ) : null
              )}
            </div>

            {/* Xarita nomlari */}
            <div className="border border-border rounded-lg p-3 text-xs text-gray-500 leading-relaxed">
              <span className="text-gray-400 font-medium">Color</span> de-lit albedo ·{' '}
              <span className="text-gray-400 font-medium">NormalGL</span> normal map ·{' '}
              <span className="text-gray-400 font-medium">Height</span> displacement ·{' '}
              <span className="text-gray-400 font-medium">Roughness</span> ·{' '}
              <span className="text-gray-400 font-medium">Metallic</span> ·{' '}
              <span className="text-gray-400 font-medium">AO</span>
            </div>
          </>
        )}

        {/* ── Bo'sh holat ──────────────────────────────────────── */}
        {status === 'idle' && (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center py-12">
            <div className="grid grid-cols-3 gap-2 opacity-10">
              {MAP_ORDER.map(key => (
                <div key={key} className="aspect-square bg-gray-500 rounded-lg" />
              ))}
            </div>
            <p className="text-sm text-gray-500">
              Chap paneldan texture tavsifini kiriting<br />
              va generatsiya tugmasini bosing
            </p>
          </div>
        )}

      </div>

      {lightbox && (
        <Lightbox src={lightbox.src} label={MAP_LABELS[lightbox.key] || lightbox.key}
          onClose={() => setLightbox(null)} />
      )}
    </div>
  )
}
