export type DocumentMode = 'doc' | 'canvas'

export interface DocumentSummary {
  id: string
  title: string
  mode: DocumentMode
  owner_id: string
  created_at: string
  updated_at: string
}

export interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  error?: boolean
}

export type AiAction = 'generate' | 'canvas' | 'ask' | 'rewrite' | 'comment'

export interface Suggestion {
  id: string
  kind: 'rewrite' | 'comment'
  status: 'pending' | 'accepted' | 'rejected'
  original: string
  replacement?: string
  body?: string
  author: string
  created_at: number
  relpos?: { from: string; to: string }
  anchor?: { text: string; offset: number }
}

export interface Peer {
  clientId: number
  name: string
  color: string
  isAI?: boolean
}
