import { useState } from 'react'
import {
  AudioLines,
  ChevronDown,
  ChevronUp,
  Mic,
  MicOff,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Settings2,
  Square,
  Volume2,
} from 'lucide-react'
import type { LiveVoiceController, LiveVoiceState } from '../voice/useLiveVoice'

const STATE_LABELS: Record<LiveVoiceState, string> = {
  idle: 'Live desligado',
  listening: 'Ouvindo',
  endpointing: 'Finalizando sua fala',
  generating: 'Modelo respondendo',
  speaking: 'Falando a resposta',
  paused: 'Fala pausada',
  error: 'Atencao necessaria',
  unsupported: 'Navegador sem suporte',
}

const MOBILE_STATE_LABELS: Record<LiveVoiceState, string> = {
  idle: 'Desligado',
  listening: 'Ouvindo',
  endpointing: 'Enviando',
  generating: 'Respondendo',
  speaking: 'Falando',
  paused: 'Pausado',
  error: 'Atencao',
  unsupported: 'Sem suporte',
}

const STATE_COLORS: Record<LiveVoiceState, string> = {
  idle: 'var(--text-tertiary)',
  listening: '#16a34a',
  endpointing: '#f59e0b',
  generating: 'var(--accent)',
  speaking: '#ea580c',
  paused: '#a16207',
  error: 'var(--danger)',
  unsupported: 'var(--danger)',
}

export function LiveVoiceButton({ controller }: { controller: LiveVoiceController }) {
  const color = STATE_COLORS[controller.state]
  const active = controller.enabled

  return (
    <button
      type="button"
      onClick={active ? controller.stop : controller.start}
      className="relative rounded-lg p-1.5 transition-all hover:bg-black/5 dark:hover:bg-white/10"
      style={{ color }}
      title={active ? 'Desligar modo Live' : 'Ativar modo Live com microfone'}
      aria-label={active ? 'Desligar modo Live' : 'Ativar modo Live'}
    >
      {active ? <Radio size={18} /> : <Mic size={18} />}
      {active && (
        <span
          className="absolute right-0 top-0 h-2 w-2 rounded-full"
          style={{ background: color, boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 20%, transparent)` }}
        />
      )}
    </button>
  )
}

export function LiveVoiceDock({ controller }: { controller: LiveVoiceController }) {
  const [showSettings, setShowSettings] = useState(false)
  if (!controller.enabled) return null

  const currentText = controller.interimTranscript || controller.transcript
  const stateColor = STATE_COLORS[controller.state]
  const isSpeaking = controller.state === 'speaking' || controller.state === 'paused'
  const clonedVoices = controller.voices.filter(voice => voice.is_cloned)
  const customVoices = controller.voices.filter(voice => voice.is_custom && !voice.is_cloned)
  const systemVoices = controller.voices.filter(voice => !voice.is_custom)

  return (
    <div className="border-t px-2 py-2 sm:px-3" style={{ borderColor: 'var(--border)', background: 'var(--bg-primary)' }}>
      <div
        className="mx-auto max-w-4xl overflow-hidden rounded-2xl border shadow-sm"
        style={{ borderColor: stateColor, background: 'var(--bg-secondary)' }}
      >
        <div className="flex flex-wrap items-center gap-2 px-2.5 py-2 sm:flex-nowrap sm:gap-3 sm:px-3 sm:py-2.5">
          <div
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${controller.state === 'listening' ? 'live-voice-pulse' : ''}`}
            style={{ background: `color-mix(in srgb, ${stateColor} 16%, transparent)`, color: stateColor }}
          >
            {controller.state === 'listening' || controller.state === 'endpointing'
              ? <Mic size={18} />
              : controller.state === 'speaking' || controller.state === 'paused'
                ? <Volume2 size={18} />
                : <AudioLines size={18} />}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span className="text-xs font-black uppercase tracking-[0.15em]" style={{ color: stateColor }}>
                <span className="sm:hidden">{MOBILE_STATE_LABELS[controller.state]}</span>
                <span className="hidden sm:inline">{STATE_LABELS[controller.state]}</span>
              </span>
              {controller.queueLength > 0 && (
                <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}>
                  {controller.queueLength} trecho(s)
                </span>
              )}
              <span className="hidden rounded-full px-2 py-0.5 text-[10px] font-bold sm:inline" style={{ background: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}>
                Inworld TTS
              </span>
            </div>
            <p className="truncate text-sm" style={{ color: currentText ? 'var(--text-primary)' : 'var(--text-tertiary)' }}>
              {controller.error || currentText || (controller.state === 'listening' ? 'Fale normalmente. O envio acontece apos o silencio.' : 'Aguardando...')}
            </p>
          </div>

          <div className="ml-11 flex w-[calc(100%-2.75rem)] shrink-0 items-center justify-end gap-1 border-t pt-1.5 sm:ml-0 sm:w-auto sm:border-0 sm:pt-0" style={{ borderColor: 'var(--border)' }}>
            {(controller.state === 'generating' || isSpeaking) && (
              <button
                type="button"
                onClick={controller.interruptAndListen}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-2 text-xs font-bold"
                style={{ background: 'rgba(239,68,68,.12)', color: 'var(--danger)' }}
                title="Interromper resposta e voltar a ouvir"
              >
                <Square size={13} />
                <span className="hidden sm:inline">Interromper</span>
              </button>
            )}
            {isSpeaking && (
              <button
                type="button"
                onClick={controller.toggleSpeechPause}
                className="rounded-lg p-2"
                style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
                title={controller.state === 'paused' ? 'Continuar fala' : 'Pausar fala'}
              >
                {controller.state === 'paused' ? <Play size={15} /> : <Pause size={15} />}
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowSettings(value => !value)}
              className="rounded-lg p-2"
              style={{ color: showSettings ? 'var(--accent)' : 'var(--text-secondary)' }}
              title="Configuracoes de voz"
            >
              <Settings2 size={15} />
            </button>
            <button
              type="button"
              onClick={controller.stop}
              className="rounded-lg p-2"
              style={{ color: 'var(--text-tertiary)' }}
              title="Desligar Live"
            >
              <MicOff size={16} />
            </button>
          </div>
        </div>

        {showSettings && (
          <div className="grid gap-3 border-t px-3 py-3 sm:grid-cols-2 lg:grid-cols-4" style={{ borderColor: 'var(--border)' }}>
            <label className="text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
              Idioma do microfone
              <select
                value={controller.settings.language}
                onChange={event => controller.updateSettings({ language: event.target.value })}
                className="mt-1 w-full rounded-lg border px-2 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="pt-BR">Portugues (Brasil)</option>
                <option value="en-US">English (US)</option>
                <option value="es-ES">Espanol</option>
              </select>
            </label>

            <label className="text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
              <span className="flex items-center justify-between gap-2">
                Voz Inworld
                <button
                  type="button"
                  onClick={() => void controller.reloadVoices()}
                  disabled={controller.voicesLoading}
                  className="rounded p-1 disabled:opacity-50"
                  title="Atualizar vozes clonadas"
                >
                  <RefreshCw size={12} className={controller.voicesLoading ? 'animate-spin' : ''} />
                </button>
              </span>
              <select
                value={controller.settings.voiceId}
                onChange={event => controller.updateSettings({ voiceId: event.target.value })}
                className="mt-1 w-full rounded-lg border px-2 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="">Selecione uma voz</option>
                {clonedVoices.length > 0 && (
                  <optgroup label="Minhas vozes clonadas">
                    {clonedVoices.map(voice => (
                      <option key={voice.voice_id} value={voice.voice_id}>{voice.display_name} ({voice.language})</option>
                    ))}
                  </optgroup>
                )}
                {customVoices.length > 0 && (
                  <optgroup label="Minhas vozes personalizadas">
                    {customVoices.map(voice => (
                      <option key={voice.voice_id} value={voice.voice_id}>{voice.display_name} ({voice.language})</option>
                    ))}
                  </optgroup>
                )}
                {systemVoices.length > 0 && (
                  <optgroup label="Vozes Inworld do sistema">
                    {systemVoices.map(voice => (
                      <option key={voice.voice_id} value={voice.voice_id}>{voice.display_name} ({voice.language})</option>
                    ))}
                  </optgroup>
                )}
              </select>
              <span className="mt-1 block text-[10px] font-normal" style={{ color: 'var(--text-tertiary)' }}>
                {controller.voicesLoading
                  ? 'Carregando vozes...'
                  : `${clonedVoices.length} clone(s) encontrado(s)`}
              </span>
            </label>

            <label className="text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
              Enviar apos silencio
              <select
                value={controller.settings.silenceMs}
                onChange={event => controller.updateSettings({ silenceMs: Number(event.target.value) })}
                className="mt-1 w-full rounded-lg border px-2 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <option value={800}>0,8 segundo</option>
                <option value={1200}>1,2 segundos</option>
                <option value={1800}>1,8 segundos</option>
                <option value={3000}>3 segundos</option>
              </select>
            </label>

            <div className="space-y-2">
              <label className="flex items-center justify-between gap-2 text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
                Velocidade {controller.settings.playbackRate.toFixed(1)}x
                <input
                  type="range"
                  min="0.8"
                  max="1.35"
                  step="0.1"
                  value={controller.settings.playbackRate}
                  onChange={event => controller.updateSettings({ playbackRate: Number(event.target.value) })}
                  className="w-24"
                />
              </label>
              <label className="flex items-center gap-2 text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={controller.settings.autoSpeak}
                  onChange={event => controller.updateSettings({ autoSpeak: event.target.checked })}
                />
                Falar respostas automaticamente
              </label>
              <label className="flex items-center gap-2 text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={controller.settings.includeSystemVoices}
                  onChange={event => controller.updateSettings({ includeSystemVoices: event.target.checked })}
                />
                Mostrar vozes do sistema
              </label>
            </div>

            <label className="text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
              Estilo da entrega
              <select
                value={controller.settings.deliveryMode}
                onChange={event => controller.updateSettings({
                  deliveryMode: event.target.value as 'STABLE' | 'BALANCED' | 'CREATIVE',
                })}
                className="mt-1 w-full rounded-lg border px-2 py-2 text-sm"
                style={{ background: 'var(--bg-primary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="STABLE">Estavel</option>
                <option value="BALANCED">Equilibrado</option>
                <option value="CREATIVE">Expressivo</option>
              </select>
              <span className="mt-1 block text-[10px] font-normal" style={{ color: 'var(--text-tertiary)' }}>
                Chave e audio passam somente pelo backend.
              </span>
            </label>
          </div>
        )}

        <button
          type="button"
          onClick={() => setShowSettings(value => !value)}
          className="flex w-full items-center justify-center border-t py-1 text-[10px] font-bold uppercase tracking-[0.15em]"
          style={{ borderColor: 'var(--border)', color: 'var(--text-tertiary)' }}
        >
          {showSettings ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>
    </div>
  )
}
