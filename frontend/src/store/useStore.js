import { create } from 'zustand'

/**
 * PBRForge global state (Zustand)
 *
 * status:       idle | queued | generating | postprocessing | done | error
 * progress:     0..100
 * jobId:        UUID string yoki null
 * previews:     { Color, NormalGL, Roughness, AO ... } base64 data URI lari yoki null
 * error:        xato matni yoki null
 * analyzing:    LLaVA tahlil jarayonida true
 * analyzeError: tahlil xatosi yoki null
 */
export const useStore = create((set) => ({
  status:       'idle',
  progress:     0,
  jobId:        null,
  previews:     null,
  error:        null,
  analyzing:    false,
  analyzeError: null,

  // Generatsiya boshlanganda
  startJob: (jobId) => set({
    jobId,
    status:   'queued',
    progress: 0,
    previews: null,
    error:    null,
  }),

  // Polling natijasini qo'llash
  applyStatus: (data) => set({
    status:   data.status,
    progress: data.progress ?? 0,
    previews: data.previews ?? null,
    error:    data.error   ?? null,
  }),

  // Tahlil boshlanishi
  setAnalyzing: (val) => set({ analyzing: val, analyzeError: null }),

  // Tahlil xatosi
  setAnalyzeError: (msg) => set({ analyzing: false, analyzeError: msg }),

  // Tozalash
  reset: () => set({
    status:       'idle',
    progress:     0,
    jobId:        null,
    previews:     null,
    error:        null,
    analyzing:    false,
    analyzeError: null,
  }),
}))
