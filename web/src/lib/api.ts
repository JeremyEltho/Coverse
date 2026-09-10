import { apiUrl } from './origin'
import type { DocumentMode, DocumentSummary, Suggestion } from './types'

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: token,
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ''}`)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  listDocuments: (token: string) => request<DocumentSummary[]>('/api/documents', token),

  createDocument: (token: string, title: string, mode: DocumentMode) =>
    request<DocumentSummary>('/api/documents', token, {
      method: 'POST',
      body: JSON.stringify({ title, mode }),
    }),

  getDocument: (token: string, id: string) =>
    request<DocumentSummary>(`/api/documents/${id}`, token),

  updateDocument: (token: string, id: string, changes: { title?: string; mode?: DocumentMode }) =>
    request<DocumentSummary>(`/api/documents/${id}`, token, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),

  deleteDocument: (token: string, id: string) =>
    request<void>(`/api/documents/${id}`, token, { method: 'DELETE' }),

  listSuggestions: (token: string, id: string) =>
    request<Suggestion[]>(`/api/documents/${id}/suggestions`, token),

  dismissSuggestion: (token: string, id: string, suggestionId: string) =>
    request<void>(`/api/documents/${id}/suggestions/${suggestionId}`, token, { method: 'DELETE' }),

  getContent: (token: string, id: string) =>
    request<{ markdown: string; xml: string; connected: number }>(
      `/api/documents/${id}/content`,
      token,
    ),
}
