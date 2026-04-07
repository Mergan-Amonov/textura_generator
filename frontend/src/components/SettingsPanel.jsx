import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { useStore } from '../store/useStore'

const RESOLUTIONS = [512, 1024, 2048]
const MAX_FILE_MB  = 5

const WELCOME = 'Salom! Qanday tekstura kerak? Masalan: "ko\'k velvet mato", "eman yog\'ochi" yoki "qora charm"\n\nRasm yuklab AI tahlil ham qildirish mumkin 📎'

export default function SettingsPanel() {
  const { status, startJob, reset } = useStore()
  const isGenerating = status === 'queued' || status === 'generating' || status === 'postprocessing'

  const [messages, setMessages]         = useState([{ role: 'assistant', content: WELCOME }])
  const [input, setInput]               = useState('')
  const [sending, setSending]           = useState(false)
  const [sdxlPrompt, setSdxlPrompt]     = useState(null)
  const [resolution, setResolution]     = useState(1024)
  const [seed, setSeed]                 = useState(-1)
  const [showSettings, setShowSettings] = useState(false)
  const [refFile, setRefFile]           = useState(null)
  const [refPreview, setRefPreview]     = useState(null)
  const [analyzing, setAnalyzing]       = useState(false)

  const bottomRef  = useRef(null)
  const inputRef   = useRef(null)
  const fileRef    = useRef(null)

  // Yangi xabar kelganda pastga scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || sending || isGenerating) return

    const newMessages = [...messages, { role: 'user', content: text }]
    setMessages(newMessages)
    setInput('')
    setSending(true)

    try {
      const { data } = await axios.post('/api/chat', {
        messages: newMessages.filter(m => m.role !== 'system'),
      })

      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])

      if (data.prompt) {
        setSdxlPrompt(data.prompt)
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Xato yuz berdi. Ollama ishlayaptimi? `ollama serve`',
      }])
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleGenerate = async () => {
    if (!sdxlPrompt || isGenerating) return
    const fd = new FormData()
    fd.append('prompt', sdxlPrompt)
    fd.append('resolution', resolution)
    fd.append('seed', seed)
    // Referens rasm bo'lsa yuboriladi — backend img2img avtomatik yoqadi
    if (refFile) fd.append('reference_image', refFile)
    try {
      const { data } = await axios.post('/api/generate', fd)
      startJob(data.job_id)
    } catch (err) {
      alert(err.response?.data?.detail || "Xato")
    }
  }

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''

    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Fayl ${MAX_FILE_MB}MB dan katta.` }])
      return
    }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Faqat JPEG, PNG, WEBP ruxsat etiladi.' }])
      return
    }

    setRefFile(file)
    setRefPreview(URL.createObjectURL(file))
    setAnalyzing(true)
    setMessages(prev => [...prev, { role: 'assistant', content: 'Rasm yuklandi. LLaVA tahlil qilmoqda...' }])

    try {
      const fd = new FormData()
      fd.append('image', file)
      const { data } = await axios.post('/api/analyze', fd)
      setSdxlPrompt(data.prompt)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Tahlil tugadi!\n\nMaterial: **${data.category}**\nTavsif: "${data.description}"\n\nPrompt tayyorlandi. Pastda "Generatsiya qilish" tugmasini bosing yoki o'zgartirish kiritishingiz mumkin.`,
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: err.response?.data?.detail || 'Tahlil xatosi. Ollama ishlayaptimi?',
      }])
    } finally {
      setAnalyzing(false)
    }
  }

  const removeImage = () => {
    setRefFile(null)
    setRefPreview(null)
  }

  const handleReset = () => {
    reset()
    setMessages([{ role: 'assistant', content: WELCOME }])
    setSdxlPrompt(null)
    setInput('')
    setRefFile(null)
    setRefPreview(null)
  }

  return (
    <div className="flex flex-col h-full bg-panel">

      {/* Header */}
      <div className="px-5 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h1 className="text-base font-bold text-white tracking-tight">
            PBRForge<span className="text-accent">::</span>Core
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">AI Texture Generator</p>
        </div>
        <button
          onClick={() => setShowSettings(v => !v)}
          title="Sozlamalar"
          className={`p-1.5 rounded-md transition-colors
            ${showSettings ? 'text-accent bg-accent/10' : 'text-gray-400 hover:text-gray-200'}`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>
      </div>

      {/* Sozlamalar panel (yig'iladigan) */}
      {showSettings && (
        <div className="px-5 py-3 border-b border-border bg-surface flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-xs text-gray-400">O'lcham (px)</span>
            <div className="flex gap-1.5">
              {RESOLUTIONS.map(r => (
                <button key={r} type="button" disabled={isGenerating}
                  onClick={() => setResolution(r)}
                  className={`flex-1 py-1.5 rounded-md text-xs font-medium border transition-colors
                    ${resolution === r
                      ? 'bg-accent border-accent text-white'
                      : 'bg-panel border-border text-gray-400 hover:border-gray-500'
                    } disabled:opacity-40 disabled:cursor-not-allowed`}>
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-gray-400">Seed <span className="text-gray-600">(−1 = tasodifiy)</span></span>
            <input type="number" value={seed} min={-1}
              onChange={e => setSeed(Number(e.target.value))}
              disabled={isGenerating}
              className="w-full bg-panel border border-border rounded-md px-3 py-1.5
                         text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-accent
                         disabled:opacity-50" />
          </div>
        </div>
      )}

      {/* Chat xabarlar */}
      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed
              ${msg.role === 'user'
                ? 'bg-accent text-white rounded-br-sm'
                : 'bg-surface border border-border text-gray-200 rounded-bl-sm'
              }`}>
              {/* PROMPT: qismini ko'rsatmaslik — alohida kartada chiqadi */}
              {msg.role === 'assistant'
                ? msg.content.split('PROMPT:')[0].trim()
                : msg.content
              }
            </div>
          </div>
        ))}

        {/* Sending indicator */}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-surface border border-border rounded-xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1 items-center">
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{animationDelay:'0ms'}}/>
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{animationDelay:'150ms'}}/>
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{animationDelay:'300ms'}}/>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Tayyorlangan SDXL prompt kartasi */}
      {sdxlPrompt && !isGenerating && (
        <div className="mx-4 mb-3 p-3 bg-surface border border-accent/40 rounded-xl flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-accent font-semibold uppercase tracking-wide">Tayyor prompt</p>
            {refFile && (
              <span className="text-xs bg-indigo-900/60 text-indigo-300 px-2 py-0.5 rounded-full">
                img2img ✓
              </span>
            )}
          </div>
          <p className="text-xs text-gray-300 leading-relaxed line-clamp-3">{sdxlPrompt}</p>
          <button onClick={handleGenerate}
            className="w-full py-2 bg-accent hover:bg-accent-hover text-white text-sm
                       font-semibold rounded-lg transition-colors">
            Generatsiya qilish
          </button>
        </div>
      )}

      {/* Generating holat */}
      {isGenerating && sdxlPrompt && (
        <div className="mx-4 mb-3 p-3 bg-surface border border-border rounded-xl">
          <p className="text-xs text-gray-400 text-center">Generatsiya qilinmoqda...</p>
        </div>
      )}

      {/* Input qatori */}
      <div className="px-4 pb-4 pt-2 border-t border-border flex flex-col gap-2">

        {/* Rasm preview (yuklangan bo'lsa) */}
        {refPreview && (
          <div className="relative w-full rounded-lg overflow-hidden border border-border">
            <img src={refPreview} alt="Referens" className="w-full h-28 object-cover" />
            <button onClick={removeImage}
              className="absolute top-1.5 right-1.5 bg-black/60 hover:bg-black/80
                         text-white text-xs px-2 py-0.5 rounded transition-colors">
              ✕
            </button>
          </div>
        )}

        <div className="flex gap-2 items-end">
          {/* Rasm yuklash tugmasi */}
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp"
            onChange={handleFileChange} className="hidden" />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={sending || analyzing || isGenerating}
            title="Rasm yuklash (LLaVA tahlil)"
            className="flex-shrink-0 p-2.5 rounded-xl border border-border text-gray-400
                       hover:border-accent hover:text-accent transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed">
            {analyzing ? (
              <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            )}
          </button>

          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={sending || analyzing || isGenerating}
            placeholder="Teksturani tasvirlab bering..."
            rows={2}
            className="flex-1 bg-surface border border-border rounded-xl px-3 py-2.5
                       text-sm text-gray-100 placeholder-gray-500 resize-none
                       focus:outline-none focus:ring-1 focus:ring-accent
                       disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button onClick={sendMessage}
            disabled={!input.trim() || sending || analyzing || isGenerating}
            className="flex-shrink-0 p-2.5 bg-accent hover:bg-accent-hover text-white
                       rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </div>

        {/* Reset */}
        {(status !== 'idle' || messages.length > 1) && (
          <button onClick={handleReset} disabled={isGenerating}
            className="w-full py-1.5 text-xs text-gray-500 hover:text-gray-300
                       border border-border rounded-lg transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed">
            Yangi suhbat
          </button>
        )}
      </div>

    </div>
  )
}
