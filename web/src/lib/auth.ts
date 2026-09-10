/**
 * Auth, with a keyless development path.
 *
 * With Supabase configured this wraps the real client. Without it, the user
 * picks a display name that is sent as an opaque token, which the backend
 * accepts in dev mode. That keeps the whole product runnable with no accounts.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null

export const usingSupabase = supabase !== null

export interface Session {
  token: string
  userId: string
  name: string
}

const DEV_KEY = 'coverse.devUser'

export function loadDevSession(): Session | null {
  try {
    const raw = localStorage.getItem(DEV_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { name: string }
    if (!parsed?.name) return null
    return { token: parsed.name, userId: parsed.name, name: parsed.name }
  } catch {
    return null
  }
}

export function saveDevSession(name: string): Session {
  const session = { token: name, userId: name, name }
  try {
    localStorage.setItem(DEV_KEY, JSON.stringify({ name }))
  } catch {
    // Private browsing; the session just will not persist.
  }
  return session
}

export function clearDevSession(): void {
  try {
    localStorage.removeItem(DEV_KEY)
  } catch {
    /* ignore */
  }
}

export async function currentSession(): Promise<Session | null> {
  if (!supabase) return loadDevSession()

  const { data } = await supabase.auth.getSession()
  const session = data.session
  if (!session) return null
  return {
    token: session.access_token,
    userId: session.user.id,
    name:
      (session.user.user_metadata?.full_name as string) ||
      session.user.email?.split('@')[0] ||
      'You',
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  if (!supabase) throw new Error('Supabase is not configured')
  const { error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) throw error
}

export async function signUp(email: string, password: string): Promise<void> {
  if (!supabase) throw new Error('Supabase is not configured')
  const { error } = await supabase.auth.signUp({ email, password })
  if (error) throw error
}

export async function signOut(): Promise<void> {
  if (supabase) await supabase.auth.signOut()
  else clearDevSession()
}
