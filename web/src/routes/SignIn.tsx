import { useState } from 'react'
import { saveDevSession, signIn, signUp, usingSupabase, type Session } from '../lib/auth'

/**
 * Sign in. With Supabase configured this is real auth; without it, you pick a
 * display name so the product is usable with nothing set up.
 */
export function SignIn({ onSignedIn }: { onSignedIn: (session: Session) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submitDev = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    onSignedIn(saveDevSession(trimmed))
  }

  const submitSupabase = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (creating) await signUp(email, password)
      else await signIn(email, password)
      // The session listener in App picks it up from here.
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="signin">
      <form className="signin-card" onSubmit={usingSupabase ? submitSupabase : submitDev}>
        <h1>Coverse</h1>
        <p className="muted">A collaborative document with an assistant in the room.</p>

        {usingSupabase ? (
          <>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                autoComplete={creating ? 'new-password' : 'current-password'}
                minLength={6}
              />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? 'Working…' : creating ? 'Create account' : 'Sign in'}
            </button>
            <button type="button" className="ghost" onClick={() => setCreating((value) => !value)}>
              {creating ? 'I already have an account' : 'Create an account'}
            </button>
          </>
        ) : (
          <>
            <label>
              Display name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Jeremy"
                required
                autoFocus
              />
            </label>
            <button type="submit">Start writing</button>
            <p className="hint">
              Running without Supabase, so this name is your identity. Open the same
              document in another browser under a different name to see collaboration.
            </p>
          </>
        )}

        {error ? <p className="error-banner">{error}</p> : null}
      </form>
    </div>
  )
}
