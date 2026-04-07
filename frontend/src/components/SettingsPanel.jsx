import { useState, useRef } from 'react'
import axios from 'axios'
import { useStore } from '../store/useStore'

const RESOLUTIONS = [512, 1024, 2048]
const MAX_FILE_MB = 5

export default function SettingsPanel() {
  const { status, analyzing, analyzeError, startJob, reset, setAnalyzing, setAnalyzeError } = useStore()
  const isGenerating = status === 'queued' || status === 'generating' || status === 'postprocessing'

  const [prompt, setPrompt]         = useState('')
  const [resolution, setResolution] = useState(1024)
  const [seed, setSeed]             = useState(-1)
  const [refFile, setRefFile]       = useState(null)
  const [refPreview, setRefPreview] = useState(null)
  const [fileError, setFileError]   = useState('')
  const [useImg2Img, setUseImg2Img] = useState(false)
  const [category, setCategory]     = useState(null)
  const [visionDesc, setVisionDesc] = useState('')
  const [parts, setParts]           = useState([])      // mebel qismlari
  const [partsLoading, setPartsLoading] = useState(false)
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    setFileError('')
    setVisionDesc('')
    setCategory(null)

    if (!file) {
      setRefFile(null)
      setRefPreview(null)
      setUseImg2Img(false)
      return
    }

    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      setFileError(`Fayl ${MAX_FILE_MB}MB dan katta`)
      setRefFile(null)
      setRefPreview(null)
      e.target.value = ''
      return
    }
    const allowed = ['image/jpeg', 'image/png', 'image/webp']
    if (!allowed.includes(file.type)) {
      setFileError('Faqat JPEG, PNG, WEBP ruxsat etiladi')
      setRefFile(null)
      setRefPreview(null)
      e.target.value = ''
      return
    }

    setRefFile(file)
    setRefPreview(URL.createObjectURL(file))
  }

  const handleAnalyze = async () => {
    if (!refFile || analyzing) return
    setAnalyzing(true)

    try {
      const formData = new FormData()
      formData.append('image', refFile)
      if (prompt.trim()) formData.append('user_hint', prompt.trim())

      const { data } = await axios.post('/api/analyze', formData)

      setPrompt(data.prompt)
      setCategory(data.category)
      setVisionDesc(data.description)
      setUseImg2Img(data.use_img2img)
      setAnalyzing(false)
    } catch (err) {
      const msg = err.response?.data?.detail || 'Tahlil xatosi'
      setAnalyzeError(msg)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!prompt.trim() || isGenerating) return

    const formData = new FormData()
    formData.append('prompt', prompt.trim())
    formData.append('resolution', resolution)
    formData.append('seed', seed)
    formData.append('use_img2img', useImg2Img)
    if (refFile && useImg2Img) formData.append('reference_image', refFile)

    try {
      const { data } = await axios.post('/api/generate', formData)
      startJob(data.job_id)
    } catch (err) {
      const msg = err.response?.data?.detail || 'So\'rov yuborishda xato'
      alert(msg)
    }
  }

  const handleReset = () => {
    reset()
    setPrompt('')
    setRefFile(null)
    setRefPreview(null)
    setFileError('')
    setUseImg2Img(false)
    setCategory(null)
    setVisionDesc('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeFile = () => {
    setRefFile(null)
    setRefPreview(null)
    setFileError('')
    setUseImg2Img(false)
    setCategory(null)
    setVisionDesc('')
    setParts([])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDetectParts = async () => {
    if (!refFile || partsLoading) return
    setPartsLoading(true)
    setParts([])
    try {
      const formData = new FormData()
      formData.append('image', refFile)
      const { data } = await axios.post('/api/parts', formData)
      setParts(data.parts || [])
    } catch (err) {
      console.error('Parts xato:', err)
    } finally {
      setPartsLoading(false)
    }
  }

  const handleSelectPart = async (part) => {
    // Qismni tanlash → o'sha material uchun tahlil va prompt generatsiya
    setAnalyzing(true)
    try {
      const formData = new FormData()
      formData.append('image', refFile)
      formData.append('user_hint', part.material)
      const { data } = await axios.post('/api/analyze', formData)
      setPrompt(data.prompt)
      setCategory(data.category)
      setVisionDesc(`${part.part}: ${part.material}`)
      setAnalyzing(false)
    } catch (err) {
      setAnalyzeError('Tahlil xatosi')
    }
  }

  const categoryLabel = {
    fabric:  { text: 'Mato', color: 'text-blue-400' },
    leather: { text: 'Charm', color: 'text-amber-400' },
    wood:    { text: "Yog'och", color: 'text-orange-400' },
    metal:   { text: 'Metall', color: 'text-slate-300' },
    general: { text: 'Umumiy', color: 'text-gray-400' },
  }

  return (
    <div className="flex flex-col h-full bg-panel">
      {/* Header */}
      <div className="px-5 py-4 border-b border-border">
        <h1 className="text-lg font-bold text-white tracking-tight">
          PBRForge<span className="text-accent">::</span>Core
        </h1>
        <p className="text-xs text-gray-400 mt-0.5">Furniture PBR Texture Generator</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col flex-1 gap-4 px-5 py-5 overflow-y-auto">

        {/* Referens rasm */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
            Referens rasm
          </label>

          {/* Preview yoki upload zone */}
          {refPreview ? (
            <div className="relative w-full rounded-lg overflow-hidden border border-border">
              <img
                src={refPreview}
                alt="Referens"
                className="w-full h-40 object-cover"
              />
              {!isGenerating && (
                <button
                  type="button"
                  onClick={removeFile}
                  className="absolute top-2 right-2 bg-black/60 hover:bg-black/80
                             text-white text-xs px-2 py-1 rounded transition-colors"
                >
                  Olib tashlash
                </button>
              )}
              {category && (
                <div className="absolute bottom-2 left-2 bg-black/70 rounded px-2 py-0.5">
                  <span className={`text-xs font-medium ${categoryLabel[category]?.color}`}>
                    {categoryLabel[category]?.text}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <label className={`flex flex-col items-center justify-center w-full h-28 border-2 border-dashed
              rounded-lg cursor-pointer transition-colors
              ${isGenerating ? 'opacity-50 cursor-not-allowed' : 'border-border hover:border-gray-500 bg-surface'}`}>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                disabled={isGenerating}
                onChange={handleFileChange}
                className="hidden"
              />
              <svg className="w-6 h-6 text-gray-500 mb-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span className="text-xs text-gray-500 text-center">
                Texture rasmini yuklang<br />
                <span className="text-gray-600">JPEG / PNG / WEBP · max {MAX_FILE_MB}MB</span>
              </span>
            </label>
          )}
          {fileError && <p className="text-xs text-red-400">{fileError}</p>}
        </div>

        {/* Tahlil tugmasi */}
        {refFile && (
          <div className="flex flex-col gap-1.5">
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={analyzing || isGenerating}
              className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm
                         font-medium rounded-lg transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {analyzing ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                  </svg>
                  LLaVA tahlil qilmoqda...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                  AI bilan tahlil qilish
                </>
              )}
            </button>
            {analyzeError && (
              <p className="text-xs text-red-400">{analyzeError}</p>
            )}
            {visionDesc && (
              <p className="text-xs text-gray-500 italic leading-relaxed">
                "{visionDesc}"
              </p>
            )}
          </div>
        )}

        {/* Mebel qismlari */}
        {refFile && (
          <div className="flex flex-col gap-1.5">
            <button
              type="button"
              onClick={handleDetectParts}
              disabled={partsLoading || isGenerating}
              className="w-full py-2 bg-violet-700 hover:bg-violet-600 text-white text-sm
                         font-medium rounded-lg transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {partsLoading ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                  </svg>
                  Qismlar aniqlanmoqda...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M4 6h16M4 12h8m-8 6h16" />
                  </svg>
                  Mebel qismlarini aniqlash
                </>
              )}
            </button>

            {parts.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-xs text-gray-500 uppercase tracking-wide font-semibold">
                  Topilgan qismlar — bosib tekstura oling
                </p>
                {parts.map((p, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => handleSelectPart(p)}
                    disabled={analyzing || isGenerating}
                    className="flex items-center justify-between w-full px-3 py-2
                               bg-surface border border-border hover:border-accent
                               rounded-lg text-left transition-colors
                               disabled:opacity-50 disabled:cursor-not-allowed group"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm text-white font-medium capitalize">{p.part}</span>
                      <span className="text-xs text-gray-400">{p.material}</span>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium
                      ${p.category === 'fabric'  ? 'bg-blue-900 text-blue-300' :
                        p.category === 'leather' ? 'bg-amber-900 text-amber-300' :
                        p.category === 'wood'    ? 'bg-orange-900 text-orange-300' :
                        p.category === 'metal'   ? 'bg-slate-700 text-slate-300' :
                                                   'bg-gray-700 text-gray-300'}`}>
                      {p.category}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Img2Img toggle */}
        {refFile && (
          <label className="flex items-center gap-2.5 cursor-pointer select-none">
            <div
              onClick={() => !isGenerating && setUseImg2Img(v => !v)}
              className={`relative w-9 h-5 rounded-full transition-colors cursor-pointer
                ${useImg2Img ? 'bg-accent' : 'bg-gray-600'}
                ${isGenerating ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform
                ${useImg2Img ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </div>
            <span className="text-xs text-gray-300">
              Img2Img ishlatish
              <span className="text-gray-500 ml-1">(faqat tekstura closeup uchun)</span>
            </span>
          </label>
        )}

        {/* Prompt */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
            Texture tavsifi
            {visionDesc && <span className="text-indigo-400 font-normal normal-case ml-1.5">— AI yaratdi</span>}
          </label>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            disabled={isGenerating}
            placeholder="Masalan: dark navy velvet fabric, soft pile texture..."
            rows={4}
            className="w-full bg-surface border border-border rounded-lg px-3 py-2.5
                       text-sm text-gray-100 placeholder-gray-500 resize-none
                       focus:outline-none focus:ring-1 focus:ring-accent
                       disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <p className="text-xs text-gray-600">
            AI tahlildan keyin avtomatik to'ldiriladi. Qo'lda ham yozishingiz mumkin.
          </p>
        </div>

        {/* O'lcham */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
            O'lcham (px)
          </label>
          <div className="flex gap-2">
            {RESOLUTIONS.map(r => (
              <button
                key={r}
                type="button"
                disabled={isGenerating}
                onClick={() => setResolution(r)}
                className={`flex-1 py-1.5 rounded-md text-sm font-medium border transition-colors
                  ${resolution === r
                    ? 'bg-accent border-accent text-white'
                    : 'bg-surface border-border text-gray-300 hover:border-gray-500'
                  } disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        {/* Seed */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
            Seed <span className="text-gray-500 normal-case font-normal">(−1 = tasodifiy)</span>
          </label>
          <input
            type="number"
            value={seed}
            onChange={e => setSeed(Number(e.target.value))}
            disabled={isGenerating}
            min={-1}
            className="w-full bg-surface border border-border rounded-lg px-3 py-2
                       text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-accent
                       disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>

        {/* Tugmalar */}
        <div className="flex flex-col gap-2 mt-auto pt-2">
          <button
            type="submit"
            disabled={!prompt.trim() || isGenerating}
            className="w-full py-2.5 bg-accent hover:bg-accent-hover text-white text-sm font-semibold
                       rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isGenerating ? 'Generatsiya qilinmoqda...' : 'Generatsiya qilish'}
          </button>
          {status !== 'idle' && (
            <button
              type="button"
              onClick={handleReset}
              disabled={isGenerating}
              className="w-full py-2 text-sm text-gray-400 hover:text-gray-200 border border-border
                         rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Tozalash
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
