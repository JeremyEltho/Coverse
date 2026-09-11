import { apiUrl } from './origin'
import type { Member } from './types'

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    let detail = ''
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? ''
    } catch {
      detail = response.statusText
    }
    throw new Error(detail || `request failed (${response.status})`)
  }
  return (await response.json()) as T
}

export interface RoomInfo {
  code: string
  needs_password: boolean
  members: string[]
}

export interface JoinResult extends Member {
  code: string
  member_id: string
  is_driver: boolean
}

export const api = {
  createRoom: (password: string) =>
    request<{ code: string; needs_password: boolean }>('/api/rooms', { password }),

  describeRoom: (code: string) => request<RoomInfo>(`/api/rooms/${code}`),

  joinRoom: (code: string, name: string, password: string) =>
    request<JoinResult>(`/api/rooms/${code}/join`, { name, password }),
}

/** The member identity for a room, kept so a refresh does not lose your seat. */
const KEY = 'coverse.member'

export function rememberMember(code: string, member: JoinResult): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ code, member }))
  } catch {
    /* private browsing; the seat simply will not survive a refresh */
  }
}

export function recallMember(code: string): JoinResult | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { code: string; member: JoinResult }
    return parsed.code === code ? parsed.member : null
  } catch {
    return null
  }
}

export function forgetMember(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
