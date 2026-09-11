import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, forgetMember, recallMember, rememberMember, type JoinResult } from '../lib/api'
import { useRoom } from '../hooks/useRoom'
import { Thread } from '../room/Thread'
import { Composer } from '../room/Composer'
import { MicControl } from '../room/MicControl'
import { Rail } from '../room/Rail'
import { SpritePicker } from '../room/SpritePicker'
import { SPRITES } from '../sprites/catalogue'
import { ModelPicker } from '../room/ModelPicker'

export function Room() {
  const { code = '' } = useParams()
  const [member, setMember] = useState<JoinResult | null>(() => recallMember(code))

  if (!member) return <JoinForm code={code} onJoined={setMember} />
  return <RoomInterior code={code} member={member} />
}

function JoinForm({ code, onJoined }: { code: string; onJoined: (m: JoinResult) => void }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)
  // Start on a random creature so the grid never looks like an unanswered form.
  const [sprite, setSprite] = useState(
    () => SPRITES[Math.floor(Math.random() * SPRITES.length)].id,
  )
  const [taken, setTaken] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    api
      .describeRoom(code)
      .then((info) => {
        setNeedsPassword(info.needs_password)
        setTaken(info.sprites ?? [])
      })
      .catch(() => setError('That room does not exist. It may have already ended.'))
  }, [code])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const joined = await api.joinRoom(code, name.trim(), password, sprite)
      rememberMember(code, joined)
      onJoined(joined)
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="landing">
      <form className="landing-card glass glass-strong" onSubmit={submit}>
        <h1>Join {code}</h1>
        <label>
          Your name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="What should the room call you"
            required
            autoFocus
            maxLength={40}
          />
        </label>

        <label>
          Pick your sprite
          <SpritePicker value={sprite} taken={taken} onChange={setSprite} />
        </label>

        {needsPassword ? (
          <label>
            Room password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
        ) : null}

        <button type="submit" disabled={busy || !name.trim()}>
          {busy ? 'Joining…' : 'Join the room'}
        </button>
        <button type="button" className="ghost" onClick={() => navigate('/')}>
          Back
        </button>

        {error ? <p className="error-banner">{error}</p> : null}
      </form>
    </div>
  )
}

function RoomInterior({ code, member }: { code: string; member: JoinResult }) {
  const room = useRoom(code, member)
  const [copied, setCopied] = useState(false)
  const navigate = useNavigate()

  // A room that is gone is not a connection problem, and saying "reconnecting"
  // forever would be a lie. The seat is dropped so the code can be reused if
  // somebody starts a fresh room with it.
  if (room.ended) {
    return (
      <div className="landing">
        <div className="landing-card glass glass-strong">
          <h1>{room.ended === 'room-gone' ? 'This room has ended' : 'You are not in this room'}</h1>
          <p className="muted">
            {room.ended === 'room-gone'
              ? 'Rooms disappear once everyone has left. Nothing was saved, which is the deal.'
              : 'Your seat expired, probably because the room ended and was started again.'}
          </p>
          <button
            type="button"
            onClick={() => {
              forgetMember()
              navigate('/')
            }}
          >
            Start a new room
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              forgetMember()
              location.reload()
            }}
          >
            Try joining {code} again
          </button>
        </div>
      </div>
    )
  }

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(location.href)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked; the code is on screen anyway */
    }
  }

  return (
    <div className="page">
      <header className="app-header glass">
        <div className="app-header-left">
          <span className="brand">Coverse</span>
          <button type="button" className="room-code" onClick={copyLink} title="Copy the link">
            {code}
            <span>{copied ? 'copied' : 'copy link'}</span>
          </button>
        </div>
        <ModelPicker
          current={room.model}
          isDriver={room.isDriver}
          disabled={room.streaming}
          onChoose={room.chooseModel}
        />
      </header>

      <MicControl
        peers={room.peers}
        members={room.members}
        connected={room.connected}
        driver={room.driver}
        driverName={room.driverName}
        isDriver={room.isDriver}
        thinking={room.streaming}
        requests={room.requests}
        onGrant={room.grantMic}
        onRelease={room.releaseMic}
      />

      <div className="room-body">
        <main className="room-main">
          <Thread
            messages={room.messages}
            pins={room.pins}
            memberId={member.member_id}
            members={room.members}
            onPin={room.togglePin}
            onReact={room.toggleReaction}
          />

          <Composer
            text={room.session?.composer ?? null}
            isDriver={room.isDriver}
            streaming={room.streaming}
            driverName={room.driverName}
            onSend={room.send}
            onStop={room.stop}
            onRequestMic={room.requestMic}
            onWithdraw={room.withdrawRequest}
            requestPending={room.myRequestPending}
            onTyping={room.signalTyping}
            typing={room.typing}
          />
        </main>

        <Rail
          sidechat={room.sidechat}
          queue={room.queue}
          messages={room.messages}
          pins={room.pins}
          isDriver={room.isDriver}
          forkTurns={room.forkTurns}
          forkBusy={room.forkBusy}
          roomCode={code}
          onSay={room.sayInSideChat}
          onPromote={room.promote}
          onQueue={room.addToQueue}
          onSendQueued={room.sendQueued}
          onDropQueued={room.dropFromQueue}
          onUnpin={room.togglePin}
          onAskPrivately={room.askPrivately}
          onShareFork={room.shareFork}
        />
      </div>

      {room.error ? <div className="toast">{room.error}</div> : null}
    </div>
  )
}
