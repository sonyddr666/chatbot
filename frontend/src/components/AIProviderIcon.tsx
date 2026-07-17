import type { ComponentType, SVGProps } from 'react'

type LobeIcon = ComponentType<SVGProps<SVGSVGElement> & { size?: number | string }>
type LobeBrand = {
  Color?: LobeIcon
  Mono?: LobeIcon
}

const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, '')

// IDs usados por APIs nem sempre possuem a mesma ordem/grafia do nome do
// componente LobeHub. O valor aponta apenas para exports do @lobehub/icons.
const BRAND_ALIASES: Record<string, string> = {
  '01ai': 'ZeroOne',
  '302ai': 'Ai302',
  aihubmix: 'AiHubMix',
  amazonbedrock: 'Bedrock',
  antigravity: 'Antigravity',
  azureopenai: 'AzureAI',
  blackforestlabs: 'Bfl',
  cloudflareworkersai: 'WorkersAI',
  codexchatgpt: 'Codex',
  googleai: 'AiStudio',
  googlevertex: 'VertexAI',
  huggingface: 'HuggingFace',
  iflytek: 'IFlyTekCloud',
  lmstudio: 'LmStudio',
  metaai: 'MetaAI',
  moonshotai: 'Moonshot',
  nvidianim: 'Nvidia',
  opencodego: 'OpenCode',
  opencodezen: 'OpenCode',
  siliconflow: 'SiliconCloud',
  togetherai: 'Together',
  workersai: 'WorkersAI',
  xai: 'XAI',
  xiaomimimo: 'XiaomiMiMo',
  zai: 'ZAI',
  zhipuai: 'Zhipu',
}

const MODEL_ALIASES: Array<[RegExp, string]> = [
  [/claude/i, 'Claude'],
  [/gemini/i, 'Gemini'],
  [/gemma/i, 'Gemma'],
  [/deepseek/i, 'DeepSeek'],
  [/moonshot|kimi/i, 'Kimi'],
  [/qwen/i, 'Qwen'],
  [/mistral|mixtral/i, 'Mistral'],
  [/llama/i, 'Meta'],
  [/grok/i, 'Grok'],
  [/gpt|chatgpt|\bo\d|davinci|babbage/i, 'OpenAI'],
  [/codex/i, 'Codex'],
  [/glm/i, 'Zhipu'],
  [/nemotron/i, 'Nvidia'],
  [/minimax/i, 'Minimax'],
  [/mimo/i, 'XiaomiMiMo'],
  [/command[- ]?[ar]/i, 'Cohere'],
  [/jamba/i, 'Ai21'],
  [/nova/i, 'Nova'],
  [/rwkv/i, 'Rwkv'],
  [/falcon/i, 'TII'],
]

// Carrega apenas os SVG React do pacote instalado. Nao usa CDN, Models.dev,
// @lobehub/ui nem outra biblioteca de icones.
const colorModules = import.meta.glob('/node_modules/@lobehub/icons/es/*/components/Color.js', {
  eager: true,
  import: 'default',
}) as Record<string, LobeIcon>
const monoModules = import.meta.glob('/node_modules/@lobehub/icons/es/*/components/Mono.js', {
  eager: true,
  import: 'default',
}) as Record<string, LobeIcon>

const lobeExports: Record<string, LobeBrand> = {}
const brandNameFromPath = (path: string) => path.match(/\/es\/([^/]+)\/components\//)?.[1] || ''
for (const [path, Icon] of Object.entries(colorModules)) {
  const name = brandNameFromPath(path)
  if (name) lobeExports[name] = { ...(lobeExports[name] || {}), Color: Icon }
}
for (const [path, Icon] of Object.entries(monoModules)) {
  const name = brandNameFromPath(path)
  if (name) lobeExports[name] = { ...(lobeExports[name] || {}), Mono: Icon }
}

const lobeBrands = Object.entries(lobeExports)
  .map(([name, Icon]) => ({ name, normalized: normalize(name), Icon }))
  .sort((left, right) => right.normalized.length - left.normalized.length)

function resolveBrand(provider: string): LobeBrand | null {
  const normalizedProvider = normalize(provider)
  const alias = Object.entries(BRAND_ALIASES)
    .sort((left, right) => right[0].length - left[0].length)
    .find(([key]) => normalizedProvider.includes(key))?.[1]
  if (alias) {
    const value = lobeExports[alias]
    if (value) return value
  }

  return lobeBrands.find(({ normalized }) => (
    normalized.length >= 3 && normalizedProvider.includes(normalized)
  ))?.Icon || null
}

function resolveModelBrand(model: string): LobeBrand | null {
  const alias = MODEL_ALIASES.find(([pattern]) => pattern.test(model))?.[1]
  if (alias) {
    const value = lobeExports[alias]
    if (value) return value
  }
  return resolveBrand(model)
}

export function AIProviderIcon({ provider, model, size = 16, className }: {
  provider?: string | null
  model?: string | null
  size?: number
  className?: string
}) {
  const Brand = (model && resolveModelBrand(model)) || resolveBrand(provider || '')
  if (Brand) {
    const Icon = Brand.Color || Brand.Mono
    if (!Icon) return null
    return <Icon aria-hidden="true" className={className} height={size} width={size} />
  }

  // SubModel e o fallback generico oficial do proprio pacote LobeHub.
  const Fallback = lobeExports.SubModel || lobeExports.LobeHub
  const Icon = Fallback.Color || Fallback.Mono!
  return <Icon aria-hidden="true" className={className} height={size} width={size} />
}
