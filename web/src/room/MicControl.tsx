import type { MicRequest, Peer } from '../lib/types'

interface MicControlProps {
  peers: Peer[]
  connected: boolean
  driverName: string | null
  isDriver: boolean
  requests: MicRequest[]
  onGrant: (memberId: string) => void
  onRelease: () => void
}

/** Who is here, who is driving, and who is asking for the mic. */
export function MicControl({
  peers,
  connected,
  driverName,
  isDriver,
  requests,
  onGrant,
  onRelease,
}: MicControlProps) {
  return (
    <div className="mic glass">
      <div className="mic-presence">
        <span className={`dot ${connected ? 'is-online' : 'is-offline'}`} />
        <div className="avatars">
          {peers.map((peer) => (
            <span
              key={peer.clientId}
              className={`avatar${peer.isAI ? ' is-ai' : ''}`}
              style={{ backgroundColor: peer.color }}
              title={peer.name}
            >
              {peer.isAI ? '✦' : peer.name.slice(0, 1).toUpperCase()}
            </span>
          ))}
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
