import { useEffect, useRef } from 'react'
import axios from 'axios'
import { useStore } from './store/useStore'
import SettingsPanel from './components/SettingsPanel'
import ResultGallery from './components/ResultGallery'

const POLL_INTERVAL_MS = 1000

export default function App() {
  const { jobId, status, applyStatus } = useStore()
  const timerRef = useRef(null)

  useEffect(() => {
    const isActive = jobId && status !== 'done' && status !== 'error' && status !== 'idle'

    if (!isActive) {
      clearInterval(timerRef.current)
      return
    }

    timerRef.current = setInterval(async () => {
      try {
        const { data } = await axios.get(`/api/status/${jobId}`)
        applyStatus(data)
      } catch {
        applyStatus({ status: 'error', progress: 0, error: 'Server bilan ulanishda xato' })
      }
    }, POLL_INTERVAL_MS)

    return () => clearInterval(timerRef.current)
  }, [jobId, status])

  return (
    <div className="flex h-screen bg-surface overflow-hidden">
      {/* Chap ustun — Sozlamalar */}
      <aside className="w-80 flex-shrink-0 flex flex-col border-r border-border overflow-y-auto">
        <SettingsPanel />
      </aside>

      {/* O'ng — Natijalar */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <ResultGallery />
      </main>
    </div>
  )
}
