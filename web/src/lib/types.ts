export interface Member {
  id: string
  name: string
  color: string
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
  isAI?: boolean
}

export type RailTab = 'chat' | 'queue' | 'pins' | 'fork'
