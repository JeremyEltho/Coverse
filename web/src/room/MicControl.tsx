import { Sprite } from '../sprites/Sprite'
import { ASSISTANT_SPRITE } from '../sprites/catalogue'
import type { Member, MicRequest, Peer } from '../lib/types'

interface MicControlProps {
  peers: Peer[]
  members: Member[]
  connected: boolean
  driver: string | null
  driverName: string | null
  isDriver: boolean
  thinking: boolean
  requests: MicRequest[]
  onGrant: (memberId: string) => void
  onRelease: () => void
}

/**
 * Who is in the room, and who is holding the mic.
 *
 * The holder is drawn lifted with the mic beside them, so the core mechanic is
 * legible without reading any text. Presence comes from awareness, identity
 * from the room's member map, so a sprite keeps its name and colour even in the
 * instant after someone's socket drops.
 */
export function MicControl({
  peers,
  members,
  connected,
  driver,
  driverName,
  isDriver,
  thinking,
  requests,
  onGrant,
  onRelease,
}: MicControlProps) {
  const onlineIds = new Set(peers.map((p) => p.memberId).filter(Boolean) as string[])
  const present = members.filter((m) => onlineIds.has(m.id))
  const roster = present.length > 0 ? present : members.slice(0, 1)

  return (
    <div className="mic">
      <div className="mic-presence">
        <span className={`dot ${connected ? 'is-online' : 'is-offline'}`} />

        <div className="roster">
          {roster.map((member) => {
            const holding = member.id === driver
            return (
              <span
                key={member.id}
                className={`roster-slot${holding ? ' is-holding' : ''}`}
                style={{ ['--member' as string]: member.color }}
                title={holding ? `${member.name} has the mic` : member.name}
              >
                <Sprite id={member.sprite} size={30} state={holding ? 'talking' : 'idle'} />
                {holding ? <span className="mic-glyph" aria-hidden="true" /> : null}
              </span>
            )
          })}

          <span className="roster-slot is-ai" title="The assistant">
            <Sprite
              def={ASSISTANT_SPRITE}
              size={30}
              state={thinking ? 'thinking' : 'idle'}
            />
          </span>
        </div>

        <span className="mic-driver">
          {isDriver ? (
            <>
              <strong>You</strong> have the mic
            </>
          ) : (
            <>
              <strong>{driverName ?? 'Nobody'}</strong> has the mic
            </>
          )}
        </span>

        {isDriver ? (
          <button type="button" className="ghost" onClick={onRelease}>
            Drop mic
          </button>
        ) : null}
      </div>

      {isDriver && requests.length > 0 ? (
        <div className="mic-requests">
          {requests.map((request) => (
            <span key={request.id} className="mic-request">
              <Sprite
                id={members.find((m) => m.id === request.id)?.sprite}
                size={18}
                state="typing"
              />
              {request.name} wants the mic
              <button type="button" onClick={() => onGrant(request.id)}>
                Hand over
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}
