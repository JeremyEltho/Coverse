import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

/** Start a room, or join one with a code. */
export function Landing() {
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [locking, setLocking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const room = await api.createRoom(locking ? password : '')
      navigate(`/r/${room.code}`)
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const join = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = code.trim().toUpperCase()
    if (trimmed) navigate(`/r/${trimmed}`)
  }

  return (
    <div className="landing">
      <div className="landing-card">
        <h1>Coverse</h1>
        <p className="muted">
          One assistant, several people. Whoever holds the mic talks to it, everyone
          else watches the reply land, argues in the side chat, and queues up what to
          ask next.
        </p>

        <div className="landing-actions">
          <button type="button" onClick={create} disabled={busy}>
            {busy ? 'Starting…' : 'Start a room'}
          </button>

          <label className="landing-lock">
            <input
              type="checkbox"
              checked={locking}
              onChange={(event) => setLocking(event.target.checked)}
            />
            Require a password
          </label>

          {locking ? (
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Room password"
            />
          ) : null}
        </div>

        <form className="landing-join" onSubmit={join}>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            placeholder="Room code"
            maxLength={6}
            autoCapitalize="characters"
          />
          <button type="submit" className="secondary" disabled={!code.trim()}>
            Join
          </button>
        </form>

        {error ? <p className="error-banner">{error}</p> : null}

        <p className="hint">
          Rooms are not saved anywhere. When the last person leaves, it is gone, so
          export anything you want to keep.
        </p>
      </div>
    </div>
  )
}
