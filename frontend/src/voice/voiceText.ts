export interface SpeechSegmentResult {
  segments: string[]
  consumedUntil: number
}

export interface SpeechSegmentOptions {
  minChars?: number
  maxChars?: number
  flush?: boolean
}

const DEFAULT_MIN_CHARS = 45
const DEFAULT_MAX_CHARS = 190

function stripFencedCode(text: string) {
  const lines = String(text || '').split('\n')
  const output: string[] = []
  let inCode = false
  let announcedCode = false

  for (const line of lines) {
    if (line.trimStart().startsWith('```')) {
      inCode = !inCode
      if (inCode && !announcedCode) {
        output.push(' Bloco de codigo omitido. ')
        announcedCode = true
      }
      continue
    }
    if (!inCode) output.push(line)
  }

  return output.join('\n')
}

export function prepareTextForSpeech(rawText: string) {
  return stripFencedCode(rawText)
    .replace(/<!-- workspace-plan:[a-f0-9]{32} -->/gi, ' ')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/https?:\/\/\S+/gi, ' link ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/[>*_~|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function maskForSpeech(value: string) {
  return value.replace(/[^\r\n]/g, ' ')
}

/**
 * Sanitizes growing streamed text without changing its length. Keeping source
 * offsets stable prevents completed Markdown links from rewinding the TTS cursor.
 */
export function prepareStreamingTextForSpeech(rawText: string) {
  return String(rawText || '')
    .replace(/```[\s\S]*?(?:```|$)/g, maskForSpeech)
    .replace(/<!-- workspace-plan:[a-f0-9]{32} -->/gi, maskForSpeech)
    .replace(/!\[[^\]]*\]\([^)]*(?:\)|$)/g, maskForSpeech)
    .replace(/https?:\/\/[^\s)]+/gi, maskForSpeech)
    .replace(/^\s{0,3}#{1,6}\s+/gm, maskForSpeech)
    .replace(/^\s*[-*+]\s+/gm, maskForSpeech)
    .replace(/^\s*\d+[.)]\s+/gm, maskForSpeech)
    .replace(/[>*_~|`\[\]()]/g, ' ')
}

function safeHardCut(text: string, start: number, maxEnd: number, minChars: number) {
  const candidate = text.slice(start, maxEnd)
  const lastSpace = candidate.lastIndexOf(' ')
  if (lastSpace >= minChars) return start + lastSpace + 1
  return maxEnd
}

export function extractStableSpeechSegments(
  preparedText: string,
  consumedFrom = 0,
  options: SpeechSegmentOptions = {},
): SpeechSegmentResult {
  const text = String(preparedText || '')
  const minChars = Math.max(12, options.minChars ?? DEFAULT_MIN_CHARS)
  const maxChars = Math.max(minChars + 10, options.maxChars ?? DEFAULT_MAX_CHARS)
  const flush = options.flush === true
  const segments: string[] = []
  let consumedUntil = Math.min(Math.max(0, consumedFrom), text.length)
  let start = consumedUntil

  while (start < text.length && /\s/.test(text[start])) start += 1

  while (start < text.length) {
    let end = -1
    for (let index = start; index < text.length; index += 1) {
      const length = index - start + 1
      const char = text[index]
      const next = text[index + 1]
      const sentenceBoundary = /[.!?;:]/.test(char) && (!next || /\s/.test(next))

      if (sentenceBoundary && length >= minChars) {
        end = index + 1
        break
      }
      if (length >= maxChars) {
        end = safeHardCut(text, start, index + 1, minChars)
        break
      }
    }

    if (end < 0) {
      if (!flush) break
      end = text.length
    }

    const segment = text.slice(start, end).trim()
    if (segment) segments.push(segment)
    consumedUntil = end
    start = end
    while (start < text.length && /\s/.test(text[start])) start += 1
    consumedUntil = start
  }

  return { segments, consumedUntil }
}

export function splitCompletedSpeechText(rawText: string) {
  const prepared = prepareTextForSpeech(rawText)
  return extractStableSpeechSegments(prepared, 0, { flush: true }).segments
}

export function extractStreamingSpeechSegments(
  rawText: string,
  consumedRawFrom = 0,
  options: SpeechSegmentOptions = {},
): SpeechSegmentResult {
  const stablePrepared = prepareStreamingTextForSpeech(rawText)
  const result = extractStableSpeechSegments(stablePrepared, consumedRawFrom, options)
  return {
    consumedUntil: result.consumedUntil,
    segments: result.segments
      .map(segment => segment.replace(/\s+/g, ' ').trim())
      .filter(Boolean),
  }
}
