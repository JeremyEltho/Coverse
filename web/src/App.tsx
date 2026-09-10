import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { currentSession, supabase, type Session } from './lib/auth'
import { SignIn } from './routes/SignIn'
import { DocumentList } from './routes/DocumentList'
import { DocumentPage } from './routes/DocumentPage'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    void currentSession().then((existing) => {
      setSession(existing)
      setReady(true)
    })

    if (!supabase) return
    const { data } = supabase.auth.onAuthStateChange(() => {
      void currentSession().then(setSession)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  if (!ready) return <div className="boot">Loading…</div>
  if (!session) return <SignIn onSignedIn={setSession} />

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={<DocumentList session={session} onSignOut={() => setSession(null)} />}
        />
        <Route path="/d/:documentId" element={<DocumentPage session={session} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
