import type { ComponentType, SVGProps } from 'react'
import Antigravity from '@lobehub/icons/es/Antigravity/components/Color'
import Anthropic from '@lobehub/icons/es/Anthropic/components/Mono'
import Cerebras from '@lobehub/icons/es/Cerebras/components/Color'
import Claude from '@lobehub/icons/es/Claude/components/Color'
import Cloudflare from '@lobehub/icons/es/Cloudflare/components/Color'
import Cohere from '@lobehub/icons/es/Cohere/components/Color'
import DeepSeek from '@lobehub/icons/es/DeepSeek/components/Color'
import Fireworks from '@lobehub/icons/es/Fireworks/components/Color'
import Gemini from '@lobehub/icons/es/Gemini/components/Color'
import Gemma from '@lobehub/icons/es/Gemma/components/Color'
import Grok from '@lobehub/icons/es/Grok/components/Mono'
import Groq from '@lobehub/icons/es/Groq/components/Mono'
import HuggingFace from '@lobehub/icons/es/HuggingFace/components/Color'
import Kimi from '@lobehub/icons/es/Kimi/components/Color'
import Meta from '@lobehub/icons/es/Meta/components/Color'
import Mistral from '@lobehub/icons/es/Mistral/components/Color'
import Ollama from '@lobehub/icons/es/Ollama/components/Mono'
import OpenAI from '@lobehub/icons/es/OpenAI/components/Mono'
import OpenRouter from '@lobehub/icons/es/OpenRouter/components/Color'
import Perplexity from '@lobehub/icons/es/Perplexity/components/Color'
import Qwen from '@lobehub/icons/es/Qwen/components/Color'
import Together from '@lobehub/icons/es/Together/components/Color'
import WorkersAI from '@lobehub/icons/es/WorkersAI/components/Color'
import XAI from '@lobehub/icons/es/XAI/components/Mono'
import AiStudio from '@lobehub/icons/es/AiStudio/components/Mono'
import Aya from '@lobehub/icons/es/Aya/components/Color'
import Codex from '@lobehub/icons/es/Codex/components/Mono'
import IBM from '@lobehub/icons/es/IBM/components/Mono'
import Minimax from '@lobehub/icons/es/Minimax/components/Color'
import Morph from '@lobehub/icons/es/Morph/components/Color'
import Nvidia from '@lobehub/icons/es/Nvidia/components/Color'
import OpenCode from '@lobehub/icons/es/OpenCode/components/Mono'
import Poolside from '@lobehub/icons/es/Poolside/components/Color'
import Stepfun from '@lobehub/icons/es/Stepfun/components/Mono'
import XiaomiMiMo from '@lobehub/icons/es/XiaomiMiMo/components/Mono'
import Zhipu from '@lobehub/icons/es/Zhipu/components/Color'
import { Cpu } from 'lucide-react'

type LobeIcon = ComponentType<SVGProps<SVGSVGElement> & { size?: number | string }>

const MODEL_ICONS: Array<[RegExp, LobeIcon]> = [
  [/\bglm\b|z[.-]?ai|zhipu|智谱/i, Zhipu],
  [/nemotron|\bnvidia\b/i, Nvidia],
  [/minimax/i, Minimax],
  [/\bmimo\b|xiaomi/i, XiaomiMiMo],
  [/stepfun|\bstep[- ]?\d/i, Stepfun],
  [/granite|\bibm\b/i, IBM],
  [/poolside|laguna/i, Poolside],
  [/\baya\b/i, Aya],
  [/command[- ]?[ar]|\bcohere\b|north[- ]mini/i, Cohere],
  [/claude/i, Claude],
  [/gemini/i, Gemini],
  [/gemma|diffusiongemma/i, Gemma],
  [/deepseek/i, DeepSeek],
  [/moonshot|kimi/i, Kimi],
  [/qwen/i, Qwen],
  [/mistral|mixtral/i, Mistral],
  [/llama|\bmeta[- /]/i, Meta],
  [/grok/i, Grok],
  [/gpt[- ]?oss|chatgpt|\bgpt[- ]?\d|\bo\d/i, OpenAI],
  [/codex/i, Codex],
]

const PROVIDER_ICONS: Array<[RegExp, LobeIcon]> = [
  [/opencode/i, OpenCode],
  [/codex/i, Codex],
  [/workers\s*ai/i, WorkersAI], [/cloudflare/i, Cloudflare],
  [/antigravity/i, Antigravity], [/cerebras/i, Cerebras],
  [/nvidia/i, Nvidia], [/morph/i, Morph],
  [/openrouter/i, OpenRouter], [/openai|chatgpt|gpt-|\bo\d/i, OpenAI],
  [/anthropic/i, Anthropic], [/claude/i, Claude],
  [/google\s*ai|ai\s*studio/i, AiStudio], [/google|gemini/i, Gemini], [/gemma/i, Gemma],
  [/z[.-]?ai|zhipu|智谱|\bglm\b/i, Zhipu],
  [/minimax/i, Minimax], [/\bmimo\b|xiaomi/i, XiaomiMiMo], [/stepfun/i, Stepfun],
  [/deepseek/i, DeepSeek], [/moonshot|kimi/i, Kimi],
  [/groq/i, Groq], [/grok/i, Grok], [/\bxai\b|x\.ai/i, XAI],
  [/mistral|mixtral/i, Mistral], [/qwen/i, Qwen],
  [/llama|\bmeta\b/i, Meta], [/ollama/i, Ollama],
  [/cohere|command-r/i, Cohere], [/hugging\s*face|huggingface/i, HuggingFace],
  [/together/i, Together], [/fireworks/i, Fireworks],
  [/perplexity/i, Perplexity], [/poolside/i, Poolside], [/\bibm\b/i, IBM],
]

export function AIProviderIcon({ provider, model, size = 16, className }: {
  provider?: string | null
  model?: string | null
  size?: number
  className?: string
}) {
  const modelIcon = model
    ? MODEL_ICONS.find(([pattern]) => pattern.test(model))?.[1]
    : undefined
  const providerIcon = PROVIDER_ICONS.find(([pattern]) => pattern.test(provider || ''))?.[1]
  const Icon = modelIcon || providerIcon
  if (!Icon) return <Cpu aria-hidden="true" className={className} size={size} />
  return <Icon aria-hidden="true" className={className} height={size} width={size} />
}
