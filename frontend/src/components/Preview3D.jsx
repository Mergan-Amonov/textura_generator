import { Suspense, useEffect, useRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment, useTexture } from '@react-three/drei'
import * as THREE from 'three'
import { useStore } from '../store/useStore'

// ── PBR Sphere ────────────────────────────────────────────────────────────────
function PBRSphere({ previews }) {
  const meshRef = useRef()

  // Barcha 4 xaritani bir vaqtda yuklash
  const [colorMap, normalMap, roughnessMap, aoMap] = useTexture([
    previews.Color,
    previews.NormalGL,
    previews.Roughness,
    previews.AO,
  ])

  useEffect(() => {
    // ── Color space to'g'rilash ───────────────────────────────────────────
    // Albedo: sRGB (insonning ko'rish tizimiga mos — ranglar to'g'ri chiqadi)
    colorMap.colorSpace = THREE.SRGBColorSpace

    // Data xaritalar: Linear (matematik hisob — qiymatlar buzilmaydi)
    normalMap.colorSpace    = THREE.LinearSRGBColorSpace
    roughnessMap.colorSpace = THREE.LinearSRGBColorSpace
    aoMap.colorSpace        = THREE.LinearSRGBColorSpace

    // ── Texture wrapping (seamless tile uchun) ────────────────────────────
    ;[colorMap, normalMap, roughnessMap, aoMap].forEach(t => {
      t.wrapS = THREE.RepeatWrapping
      t.wrapT = THREE.RepeatWrapping
      t.needsUpdate = true
    })
  }, [colorMap, normalMap, roughnessMap, aoMap])

  useEffect(() => {
    // ── UV2 — aoMap uchun zarur (Three.js r152 dan oldingi versiyalar) ────
    // Yangi versiyalarda ham qo'shish zararsiz va ishonchli
    if (meshRef.current) {
      const geo = meshRef.current.geometry
      if (!geo.attributes.uv2) {
        geo.setAttribute('uv2', geo.attributes.uv)
      }
    }
  }, [])

  return (
    <mesh ref={meshRef} castShadow receiveShadow>
      <sphereGeometry args={[1.6, 128, 128]} />
      <meshStandardMaterial
        // ── 4 PBR xarita ─────────────────────────────────────────────────
        map={colorMap}

        normalMap={normalMap}
        normalMapType={THREE.TangentSpaceNormalMap}   // OpenGL normal format
        normalScale={new THREE.Vector2(1.0, 1.0)}

        roughnessMap={roughnessMap}
        roughness={1.0}       // roughnessMap ni to'liq ishlatish uchun 1.0

        aoMap={aoMap}
        aoMapIntensity={1.0}

        // ── Metal emas (PBR diffuse) ──────────────────────────────────────
        metalness={0.0}

        // ── Environment map ta'siri ───────────────────────────────────────
        envMapIntensity={1.0}
      />
    </mesh>
  )
}

// ── Progress bar ──────────────────────────────────────────────────────────────
function ProgressView({ progress, status }) {
  const label = {
    queued:         'Navbatda...',
    generating:     'AI generatsiya...',
    postprocessing: 'Post-processing...',
  }[status] || 'Ishlanmoqda...'

  return (
    <div className="flex flex-col items-center justify-center gap-5 w-full max-w-xs px-6">
      <div className="text-center">
        <p className="text-sm font-medium text-gray-200">{label}</p>
        <p className="text-3xl font-bold text-accent mt-1">{progress}%</p>
      </div>
      <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-accent rounded-full transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="text-xs text-gray-500 text-center">
        {status === 'generating'     && 'ComfyUI Hires Fix (2 bosqich)...'}
        {status === 'postprocessing' && 'Normal · Roughness · AO generatsiya...'}
        {status === 'queued'         && 'ComfyUI ga ulanilmoqda...'}
      </p>
    </div>
  )
}

// ── Bo'sh holat ───────────────────────────────────────────────────────────────
function EmptyView() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 text-center px-8">
      <div className="w-20 h-20 rounded-full border-2 border-dashed border-gray-600 flex items-center justify-center">
        <span className="text-3xl opacity-20">◉</span>
      </div>
      <p className="text-sm text-gray-400">
        Texture tavsifini kiriting va generatsiya qilish ni bosing
      </p>
      <p className="text-xs text-gray-600">Color · NormalGL · Roughness · AO</p>
    </div>
  )
}

// ── Xato holati ───────────────────────────────────────────────────────────────
function ErrorView({ error }) {
  return (
    <div className="flex flex-col items-center gap-3 text-center px-8 max-w-sm">
      <div className="w-12 h-12 rounded-full bg-red-900/30 flex items-center justify-center">
        <span className="text-red-400 text-xl">!</span>
      </div>
      <p className="text-sm font-medium text-red-400">Xato yuz berdi</p>
      <p className="text-xs text-gray-400 break-words">{error}</p>
    </div>
  )
}

// ── Asosiy komponent ──────────────────────────────────────────────────────────
export default function Preview3D() {
  const { status, progress, previews, error } = useStore()

  const isLoading = status === 'queued' || status === 'generating' || status === 'postprocessing'
  const isDone    = status === 'done' && previews
  const isError   = status === 'error'

  return (
    <div className="flex-1 flex flex-col bg-surface">
      {/* Header */}
      <div className="px-5 py-3 border-b border-border flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          3D Preview
        </span>
        {isDone && <span className="text-xs text-green-400 ml-auto">Tayyor</span>}
      </div>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center">
        {isError ? (
          <ErrorView error={error} />
        ) : isLoading ? (
          <ProgressView progress={progress} status={status} />
        ) : isDone ? (
          <Canvas
            camera={{ position: [0, 0, 4], fov: 45 }}
            style={{ width: '100%', height: '100%' }}
            gl={{
              toneMapping: THREE.ACESFilmicToneMapping,
              toneMappingExposure: 1.0,
              outputColorSpace: THREE.SRGBColorSpace,
            }}
          >
            {/* ── Yoritish ── */}
            {/* Environment: HDRI-based global illumination + reflections */}
            <Environment preset="warehouse" background={false} />

            {/* Asosiy yo'nalishli nur — highlight uchun */}
            <directionalLight
              position={[4, 6, 4]}
              intensity={1.5}
              color="#fff8f0"
            />
            {/* Qarama-qarshi fill light — qorong'i tomonni yumshatadi */}
            <directionalLight
              position={[-3, -2, -3]}
              intensity={0.3}
              color="#c0d8ff"
            />
            {/* Ambient — eng qorong'i joylar uchun minimal yoritish */}
            <ambientLight intensity={0.15} />

            <Suspense fallback={null}>
              <PBRSphere previews={previews} />
            </Suspense>

            <OrbitControls
              enablePan={false}
              minDistance={2.5}
              maxDistance={8}
              autoRotate
              autoRotateSpeed={0.5}
            />
          </Canvas>
        ) : (
          <EmptyView />
        )}
      </div>
    </div>
  )
}
