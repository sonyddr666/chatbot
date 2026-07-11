import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type InworldVoice } from '../lib/api'
import { extractStreamingSpeechSegments, splitCompletedSpeechText } from './voiceText'

export type LiveVoiceState =
  | 'idle'
  | 'listening'
  | 'endpointing'
  | 'generating'
  | 'speaking'
  | 'paused'
  | 'error'
  | 'unsupported'

export interface LiveVoiceSettings {
  language: string
  voiceId: string
  silenceMs: number
  playbackRate: number
  autoSpeak: boolean
  includeSystemVoices: boolean
  deliveryMode: 'STABLE' | 'BALANCED' | 'CREATIVE'
}

export interface LiveVoiceController {
  supported: boolean
  enabled: boolean
  state: LiveVoiceState
  error: string
  transcript: string
  interimTranscript: string
  queueLength: number
  voices: InworldVoice[]
  voicesLoading: boolean
  ttsConfigured: boolean
  settings: LiveVoiceSettings
  start: () => void
  stop: () => void
  interruptAndListen: () => void
  stopSpeaking: () => void
  toggleSpeechPause: () => void
  speakText: (text: string) => void
  reloadVoices: () => Promise<void>
  updateSettings: (patch: Partial<LiveVoiceSettings>) => void
}

interface SpeechRecognitionAlternativeLike {
  transcript: string
}

interface SpeechRecognitionResultLike {
  isFinal: boolean
  length: number
  [index: number]: SpeechRecognitionAlternativeLike
}

interface SpeechRecognitionResultListLike {
  length: number
  [index: number]: SpeechRecognitionResultLike
}

interface SpeechRecognitionEventLike extends Event {
  results: SpeechRecognitionResultListLike
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string
  message?: string
}

interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  maxAlternatives: number
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
}

interface UseLiveVoiceOptions {
  userId?: number
  isGenerating: boolean
  assistantMessageId?: string
  assistantText: string
  onSend: (message: string) => void
  onInterruptGeneration: () => void
}

interface SpeechQueueItem {
  id: number
  text: string
  voiceId: string
  language: string
  deliveryMode: LiveVoiceSettings['deliveryMode']
  controller?: AbortController
  request?: Promise<string>
  audioUrl?: string
}

const DEFAULT_SETTINGS: LiveVoiceSettings = {
  language: 'pt-BR',
  voiceId: '',
  silenceMs: 1200,
  playbackRate: 1,
  autoSpeak: true,
  includeSystemVoices: true,
  deliveryMode: 'BALANCED',
}

const TTS_PREFETCH_AHEAD = 2
const MAX_PENDING_TTS_ITEMS = 18
const MAX_TTS_SEGMENTS_PER_RESPONSE = 40
const MAX_TTS_CHARACTERS_PER_RESPONSE = 6000

function settingsKey(userId?: number) {
  return `chatbot_live_voice_${userId || 'anonymous'}`
}

function loadSettings(userId?: number): LiveVoiceSettings {
  try {
    const raw = localStorage.getItem(settingsKey(userId))
    if (!raw) return DEFAULT_SETTINGS
    const stored = JSON.parse(raw) as Partial<LiveVoiceSettings> & { voiceURI?: string; rate?: number }
    const deliveryMode = String(stored.deliveryMode || 'BALANCED').toUpperCase()
    return {
      language: typeof stored.language === 'string' ? stored.language : DEFAULT_SETTINGS.language,
      voiceId: typeof stored.voiceId === 'string' ? stored.voiceId : '',
      silenceMs: Math.min(5000, Math.max(600, Number(stored.silenceMs) || DEFAULT_SETTINGS.silenceMs)),
      playbackRate: Math.min(1.35, Math.max(0.8, Number(stored.playbackRate) || DEFAULT_SETTINGS.playbackRate)),
      autoSpeak: stored.autoSpeak !== false,
      includeSystemVoices: stored.includeSystemVoices !== false,
      deliveryMode: deliveryMode === 'STABLE' || deliveryMode === 'CREATIVE' ? deliveryMode : 'BALANCED',
    }
  } catch {
    return DEFAULT_SETTINGS
  }
}

function recognitionConstructor() {
  if (typeof window === 'undefined') return undefined
  return window.SpeechRecognition || window.webkitSpeechRecognition
}

function inworldLanguage(language: string) {
  return language.replace('-', '_').toUpperCase()
}

export function useLiveVoice({
  userId,
  isGenerating,
  assistantMessageId,
  assistantText,
  onSend,
  onInterruptGeneration,
}: UseLiveVoiceOptions): LiveVoiceController {
  const [supported] = useState(() => Boolean(recognitionConstructor()))
  const [enabled, setEnabled] = useState(false)
  const [state, setState] = useState<LiveVoiceState>(() => supported ? 'idle' : 'unsupported')
  const [error, setError] = useState('')
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const [queueLength, setQueueLength] = useState(0)
  const [voices, setVoices] = useState<InworldVoice[]>([])
  const [voicesLoading, setVoicesLoading] = useState(false)
  const [ttsConfigured, setTtsConfigured] = useState(false)
  const [settings, setSettings] = useState<LiveVoiceSettings>(() => loadSettings(userId))

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const endpointTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const enabledRef = useRef(false)
  const isGeneratingRef = useRef(isGenerating)
  const speakingRef = useRef(false)
  const pausedRef = useRef(false)
  const speechPumpRunningRef = useRef(false)
  const finalTranscriptRef = useRef('')
  const interimTranscriptRef = useRef('')
  const onSendRef = useRef(onSend)
  const onInterruptRef = useRef(onInterruptGeneration)
  const settingsRef = useRef(settings)
  const ttsConfiguredRef = useRef(ttsConfigured)
  const speechQueueRef = useRef<SpeechQueueItem[]>([])
  const speechItemIdRef = useRef(0)
  const speechSessionRef = useRef(0)
  const activeAudioRef = useRef<HTMLAudioElement | null>(null)
  const sourceTextRef = useRef('')
  const consumedUntilRef = useRef(0)
  const queuedSegmentKeysRef = useRef(new Set<string>())
  const queuedSegmentCountRef = useRef(0)
  const queuedCharacterCountRef = useRef(0)
  const speechLimitWarnedRef = useRef(false)
  const activeAssistantIdRef = useRef<string | undefined>(undefined)
  const ignoreAssistantIdRef = useRef<string | undefined>(undefined)
  const startListeningRef = useRef<() => void>(() => undefined)
  const pumpSpeechRef = useRef<() => void>(() => undefined)
  const prefetchSpeechRef = useRef<() => void>(() => undefined)

  isGeneratingRef.current = isGenerating
  onSendRef.current = onSend
  onInterruptRef.current = onInterruptGeneration
  settingsRef.current = settings
  ttsConfiguredRef.current = ttsConfigured

  const clearEndpointTimer = useCallback(() => {
    if (endpointTimerRef.current) clearTimeout(endpointTimerRef.current)
    endpointTimerRef.current = null
  }, [])

  const clearRestartTimer = useCallback(() => {
    if (restartTimerRef.current) clearTimeout(restartTimerRef.current)
    restartTimerRef.current = null
  }, [])

  const stopRecognition = useCallback((abort = true) => {
    clearEndpointTimer()
    const recognition = recognitionRef.current
    recognitionRef.current = null
    if (!recognition) return
    recognition.onend = null
    recognition.onresult = null
    recognition.onerror = null
    try {
      if (abort) recognition.abort()
      else recognition.stop()
    } catch {
      // The browser may already have closed this recognition session.
    }
  }, [clearEndpointTimer])

  const restartListeningSoon = useCallback((delay = 160) => {
    clearRestartTimer()
    if (!enabledRef.current || isGeneratingRef.current || speakingRef.current || pausedRef.current) return
    restartTimerRef.current = setTimeout(() => startListeningRef.current(), delay)
  }, [clearRestartTimer])

  const releaseSpeechItem = useCallback((item: SpeechQueueItem) => {
    item.controller?.abort()
    item.controller = undefined
    item.request = undefined
    if (item.audioUrl) URL.revokeObjectURL(item.audioUrl)
    item.audioUrl = undefined
  }, [])

  const finishUtteranceQueue = useCallback(() => {
    speakingRef.current = false
    pausedRef.current = false
    speechPumpRunningRef.current = false
    setQueueLength(0)
    if (!enabledRef.current) {
      setState('idle')
      return
    }
    if (isGeneratingRef.current) {
      setState('generating')
      return
    }
    restartListeningSoon()
  }, [restartListeningSoon])

  const fetchSpeechItem = useCallback((item: SpeechQueueItem) => {
    if (item.audioUrl) return Promise.resolve(item.audioUrl)
    if (item.request) return item.request
    const controller = new AbortController()
    item.controller = controller
    item.request = api.synthesizeInworldSpeech(
      item.text,
      item.voiceId,
      item.language,
      item.deliveryMode,
      controller.signal,
    ).then(blob => {
      item.controller = undefined
      item.audioUrl = URL.createObjectURL(blob)
      return item.audioUrl
    }).finally(() => {
      item.request = undefined
    })
    return item.request
  }, [])

  const prefetchSpeech = useCallback(() => {
    for (const item of speechQueueRef.current.slice(0, TTS_PREFETCH_AHEAD)) {
      void fetchSpeechItem(item).catch(() => undefined)
    }
  }, [fetchSpeechItem])
  prefetchSpeechRef.current = prefetchSpeech

  const pumpSpeech = useCallback(() => {
    if (speakingRef.current || pausedRef.current || speechPumpRunningRef.current) return
    const item = speechQueueRef.current[0]
    setQueueLength(speechQueueRef.current.length)
    if (!item) {
      finishUtteranceQueue()
      return
    }

    const session = speechSessionRef.current
    speechPumpRunningRef.current = true
    prefetchSpeechRef.current()
    void fetchSpeechItem(item).then(audioUrl => {
      if (session !== speechSessionRef.current || speechQueueRef.current[0] !== item) return
      const audio = new Audio(audioUrl)
      audio.preload = 'auto'
      audio.playbackRate = settingsRef.current.playbackRate
      activeAudioRef.current = audio
      speakingRef.current = true
      speechPumpRunningRef.current = false
      setState('speaking')

      const finish = () => {
        if (session !== speechSessionRef.current) return
        activeAudioRef.current = null
        speakingRef.current = false
        const completed = speechQueueRef.current.shift()
        if (completed) releaseSpeechItem(completed)
        setQueueLength(speechQueueRef.current.length)
        prefetchSpeechRef.current()
        pumpSpeechRef.current()
      }
      audio.onended = finish
      audio.onerror = () => {
        setError('O navegador nao conseguiu reproduzir o audio Inworld.')
        finish()
      }
      return audio.play()
    }).catch(fetchError => {
      if (session !== speechSessionRef.current || fetchError?.name === 'AbortError') return
      const audio = activeAudioRef.current
      activeAudioRef.current = null
      if (audio) {
        audio.onended = null
        audio.onerror = null
        audio.pause()
        audio.src = ''
      }
      speakingRef.current = false
      speechPumpRunningRef.current = false
      setError(fetchError instanceof Error ? fetchError.message : 'Falha no TTS Inworld.')
      setState('error')
      const failed = speechQueueRef.current.shift()
      if (failed) releaseSpeechItem(failed)
      setQueueLength(speechQueueRef.current.length)
      if (speechQueueRef.current.length) pumpSpeechRef.current()
    })
  }, [fetchSpeechItem, finishUtteranceQueue, releaseSpeechItem])
  pumpSpeechRef.current = pumpSpeech

  const cancelSpeech = useCallback(() => {
    speechSessionRef.current += 1
    const audio = activeAudioRef.current
    activeAudioRef.current = null
    if (audio) {
      audio.onended = null
      audio.onerror = null
      audio.pause()
      audio.src = ''
    }
    for (const item of speechQueueRef.current) releaseSpeechItem(item)
    speechQueueRef.current = []
    speakingRef.current = false
    pausedRef.current = false
    speechPumpRunningRef.current = false
    setQueueLength(0)
  }, [releaseSpeechItem])

  const enqueueSpeech = useCallback((segments: string[]) => {
    const currentSettings = settingsRef.current
    if (!ttsConfiguredRef.current || !currentSettings.voiceId) {
      setError('Selecione uma voz Inworld antes de ativar a fala.')
      return
    }
    const items: SpeechQueueItem[] = []
    let reachedLimit = false
    for (const rawText of segments) {
      const text = rawText.replace(/\s+/g, ' ').trim()
      if (!text) continue
      const key = text.toLocaleLowerCase(currentSettings.language)
      if (queuedSegmentKeysRef.current.has(key)) continue
      if (
        speechQueueRef.current.length + items.length >= MAX_PENDING_TTS_ITEMS
        || queuedSegmentCountRef.current >= MAX_TTS_SEGMENTS_PER_RESPONSE
        || queuedCharacterCountRef.current + text.length > MAX_TTS_CHARACTERS_PER_RESPONSE
      ) {
        reachedLimit = true
        break
      }
      queuedSegmentKeysRef.current.add(key)
      queuedSegmentCountRef.current += 1
      queuedCharacterCountRef.current += text.length
      items.push({
        id: ++speechItemIdRef.current,
        text,
        voiceId: currentSettings.voiceId,
        language: currentSettings.language,
        deliveryMode: currentSettings.deliveryMode,
      })
    }
    if (reachedLimit && !speechLimitWarnedRef.current) {
      speechLimitWarnedRef.current = true
      setError('Leitura automatica limitada para impedir fila infinita e cobrancas repetidas.')
    }
    if (!items.length) return
    speechQueueRef.current.push(...items)
    setQueueLength(speechQueueRef.current.length)
    prefetchSpeechRef.current()
    pumpSpeechRef.current()
  }, [])

  const submitTranscript = useCallback(() => {
    clearEndpointTimer()
    const text = `${finalTranscriptRef.current} ${interimTranscriptRef.current}`.replace(/\s+/g, ' ').trim()
    if (!text || isGeneratingRef.current) return
    stopRecognition(false)
    finalTranscriptRef.current = ''
    interimTranscriptRef.current = ''
    setTranscript(text)
    setInterimTranscript('')
    setState('generating')
    onSendRef.current(text)
  }, [clearEndpointTimer, stopRecognition])

  const scheduleEndpoint = useCallback(() => {
    clearEndpointTimer()
    if (!finalTranscriptRef.current.trim() && !interimTranscriptRef.current.trim()) return
    setState('endpointing')
    endpointTimerRef.current = setTimeout(submitTranscript, settingsRef.current.silenceMs)
  }, [clearEndpointTimer, submitTranscript])

  const startListening = useCallback(() => {
    if (!supported || !enabledRef.current || isGeneratingRef.current || speakingRef.current) return
    clearRestartTimer()
    stopRecognition()
    const Recognition = recognitionConstructor()
    if (!Recognition) {
      setState('unsupported')
      setError('STT nao esta disponivel neste navegador. Use Chrome ou Edge atualizados.')
      return
    }

    const recognition = new Recognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1
    recognition.lang = settingsRef.current.language
    recognitionRef.current = recognition

    recognition.onresult = event => {
      let finalText = ''
      let interimText = ''
      for (let index = 0; index < event.results.length; index += 1) {
        const result = event.results[index]
        const piece = result[0]?.transcript?.trim() || ''
        if (!piece) continue
        if (result.isFinal) finalText += `${piece} `
        else interimText += `${piece} `
      }
      finalTranscriptRef.current = finalText.trim()
      interimTranscriptRef.current = interimText.trim()
      setTranscript(finalTranscriptRef.current)
      setInterimTranscript(interimTranscriptRef.current)
      scheduleEndpoint()
    }

    recognition.onerror = event => {
      if (event.error === 'aborted' || event.error === 'no-speech') return
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        enabledRef.current = false
        setEnabled(false)
        setState('error')
        setError('Permissao do microfone negada. Libere o microfone no navegador e tente novamente.')
        return
      }
      setError(event.message || `Erro de reconhecimento: ${event.error}`)
      setState('error')
    }

    recognition.onend = () => {
      if (recognitionRef.current === recognition) recognitionRef.current = null
      if (enabledRef.current && !isGeneratingRef.current && !speakingRef.current) restartListeningSoon(250)
    }

    try {
      recognition.start()
      setError('')
      setState('listening')
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : 'Nao foi possivel iniciar o microfone.')
      setState('error')
    }
  }, [clearRestartTimer, restartListeningSoon, scheduleEndpoint, stopRecognition, supported])
  startListeningRef.current = startListening

  const reloadVoices = useCallback(async () => {
    if (!userId) return
    setVoicesLoading(true)
    try {
      const status = await api.inworldTtsStatus()
      setTtsConfigured(status.configured)
      if (!status.configured) {
        setVoices([])
        setError('Configure INWORLD_API_KEY no backend/Coolify para usar o TTS.')
        return
      }
      const result = await api.listInworldVoices(
        inworldLanguage(settingsRef.current.language),
        settingsRef.current.includeSystemVoices,
      )
      setVoices(result.voices)
      setError('')
      setSettings(current => {
        if (result.voices.some(voice => voice.voice_id === current.voiceId)) return current
        const preferred = result.voices.find(voice => voice.voice_id === result.default_voice)
          || result.voices.find(voice => voice.is_cloned)
          || result.voices[0]
        return { ...current, voiceId: preferred?.voice_id || '' }
      })
    } catch (voiceError) {
      setTtsConfigured(false)
      setVoices([])
      setError(voiceError instanceof Error ? voiceError.message : 'Falha ao carregar vozes Inworld.')
    } finally {
      setVoicesLoading(false)
    }
  }, [userId])

  const start = useCallback(() => {
    if (!supported) {
      setState('unsupported')
      setError('Live requer Chrome ou Edge com reconhecimento de voz.')
      return
    }
    if (!ttsConfiguredRef.current || !settingsRef.current.voiceId) {
      setState('error')
      setError('Aguarde as vozes Inworld ou configure INWORLD_API_KEY no backend.')
      void reloadVoices()
      return
    }
    enabledRef.current = true
    setEnabled(true)
    setError('')
    setTranscript('')
    setInterimTranscript('')
    finalTranscriptRef.current = ''
    interimTranscriptRef.current = ''
    startListeningRef.current()
  }, [reloadVoices, supported])

  const stop = useCallback(() => {
    enabledRef.current = false
    setEnabled(false)
    clearRestartTimer()
    clearEndpointTimer()
    stopRecognition()
    cancelSpeech()
    finalTranscriptRef.current = ''
    interimTranscriptRef.current = ''
    setTranscript('')
    setInterimTranscript('')
    setState(supported ? 'idle' : 'unsupported')
  }, [cancelSpeech, clearEndpointTimer, clearRestartTimer, stopRecognition, supported])

  const interruptAndListen = useCallback(() => {
    if (!enabledRef.current) return
    ignoreAssistantIdRef.current = activeAssistantIdRef.current
    cancelSpeech()
    if (isGeneratingRef.current) onInterruptRef.current()
    isGeneratingRef.current = false
    finalTranscriptRef.current = ''
    interimTranscriptRef.current = ''
    setTranscript('')
    setInterimTranscript('')
    restartListeningSoon(200)
  }, [cancelSpeech, restartListeningSoon])

  const stopSpeaking = useCallback(() => {
    cancelSpeech()
    if (enabledRef.current && !isGeneratingRef.current) restartListeningSoon()
    else if (!enabledRef.current) setState('idle')
  }, [cancelSpeech, restartListeningSoon])

  const toggleSpeechPause = useCallback(() => {
    const audio = activeAudioRef.current
    if (!audio) return
    if (pausedRef.current) {
      void audio.play()
      pausedRef.current = false
      speakingRef.current = true
      setState('speaking')
    } else {
      audio.pause()
      pausedRef.current = true
      speakingRef.current = false
      setState('paused')
    }
  }, [])

  const speakText = useCallback((text: string) => {
    if (!ttsConfiguredRef.current || !settingsRef.current.voiceId) {
      setError('Selecione uma voz clonada Inworld antes de ouvir a resposta.')
      setState('error')
      void reloadVoices()
      return
    }
    stopRecognition()
    cancelSpeech()
    queuedSegmentKeysRef.current.clear()
    queuedSegmentCountRef.current = 0
    queuedCharacterCountRef.current = 0
    speechLimitWarnedRef.current = false
    enqueueSpeech(splitCompletedSpeechText(text))
  }, [cancelSpeech, enqueueSpeech, reloadVoices, stopRecognition])

  const updateSettings = useCallback((patch: Partial<LiveVoiceSettings>) => {
    setSettings(current => ({
      ...current,
      ...patch,
      silenceMs: patch.silenceMs === undefined ? current.silenceMs : Math.min(5000, Math.max(600, patch.silenceMs)),
      playbackRate: patch.playbackRate === undefined
        ? current.playbackRate
        : Math.min(1.35, Math.max(0.8, patch.playbackRate)),
    }))
  }, [])

  useEffect(() => {
    const next = loadSettings(userId)
    setSettings(next)
    if (!userId && enabledRef.current) stop()
  }, [stop, userId])

  useEffect(() => {
    localStorage.setItem(settingsKey(userId), JSON.stringify(settings))
  }, [settings, userId])

  useEffect(() => {
    if (userId) void reloadVoices()
  }, [reloadVoices, settings.includeSystemVoices, settings.language, userId])

  useEffect(() => {
    if (isGenerating) {
      stopRecognition()
      if (enabledRef.current && !speakingRef.current) setState('generating')
    }
  }, [isGenerating, stopRecognition])

  useEffect(() => {
    if (!assistantMessageId) return
    const changedMessage = assistantMessageId !== activeAssistantIdRef.current
    if (changedMessage) {
      activeAssistantIdRef.current = assistantMessageId
      sourceTextRef.current = ''
      consumedUntilRef.current = 0
      queuedSegmentKeysRef.current.clear()
      queuedSegmentCountRef.current = 0
      queuedCharacterCountRef.current = 0
      speechLimitWarnedRef.current = false
      if (ignoreAssistantIdRef.current !== assistantMessageId) cancelSpeech()
    }

    if (!enabledRef.current || !settings.autoSpeak || ignoreAssistantIdRef.current === assistantMessageId) {
      if (!isGenerating && enabledRef.current && !speakingRef.current) restartListeningSoon()
      return
    }

    if (sourceTextRef.current && !assistantText.startsWith(sourceTextRef.current)) {
      cancelSpeech()
      sourceTextRef.current = assistantText
      consumedUntilRef.current = assistantText.length
      setError('Leitura interrompida porque a resposta foi reescrita durante o streaming.')
      return
    }
    sourceTextRef.current = assistantText
    const result = extractStreamingSpeechSegments(assistantText, consumedUntilRef.current, {
      minChars: 24,
      maxChars: 150,
      flush: !isGenerating,
    })
    consumedUntilRef.current = result.consumedUntil
    enqueueSpeech(result.segments)

    if (!isGenerating && result.segments.length === 0
      && !speakingRef.current && speechQueueRef.current.length === 0) {
      restartListeningSoon()
    }
  }, [assistantMessageId, assistantText, cancelSpeech, enqueueSpeech, isGenerating, restartListeningSoon, settings.autoSpeak])

  useEffect(() => {
    return () => {
      enabledRef.current = false
      clearRestartTimer()
      clearEndpointTimer()
      stopRecognition()
      cancelSpeech()
    }
  }, [cancelSpeech, clearEndpointTimer, clearRestartTimer, stopRecognition])

  return {
    supported,
    enabled,
    state,
    error,
    transcript,
    interimTranscript,
    queueLength,
    voices,
    voicesLoading,
    ttsConfigured,
    settings,
    start,
    stop,
    interruptAndListen,
    stopSpeaking,
    toggleSpeechPause,
    speakText,
    reloadVoices,
    updateSettings,
  }
}
