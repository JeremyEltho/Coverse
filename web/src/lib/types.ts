export interface Member {
  id: string
  name: string
  color: string
  sprite: string
}

export interface MicRequest {
  id: string
  name: string
  at: number
}

export interface ThreadMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  author: string
  authorName: string
  body: string
  at: number
  done: boolean
  shared: boolean
  reactions: Record<string, string[]>
}

export interface SideMessage {
  id: string
  author: string
  author_name: string
  body: string
  at: number
}

export interface QueueItem {
  id: string
  author: string
  author_name: string
  body: string
  at: number
}

export interface ForkTurn {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export interface Peer {
  clientId: number
  memberId?: string
  name: string
  color: string
  sprite?: string
  isAI?: boolean
  /** Epoch ms of this person's last keystroke in the shared draft. */
  typingAt?: number
}

export interface ModelInfo {
  id: string
  name: string
  context_length: number | null
  prompt_price: number | null
  completion_price: number | null
  free: boolean
}

export interface ModelCatalogue {
  provider: string
  default: string
  models: ModelInfo[]
  error: string | null
}

export type RailTab = 'chat' | 'queue' | 'pins' | 'fork'
