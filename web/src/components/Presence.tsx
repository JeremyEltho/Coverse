import type { Peer } from '../lib/types'

/** The row of avatars showing who is in the document, AI included. */
export function Presence({ peers, connected }: { peers: Peer[]; connected: boolean }) {
  return (
    <div className="presence">
      <span className={`presence-status ${connected ? 'is-online' : 'is-offline'}`}>
        {connected ? 'Live' : 'Reconnecting…'}
      </span>
      <div className="presence-avatars">
        {peers.map((peer) => (
          <span
            key={peer.clientId}
            className={`avatar${peer.isAI ? ' is-ai' : ''}`}
            style={{ backgroundColor: peer.color }}
            title={peer.isAI ? `${peer.name} (assistant)` : peer.name}
          >
            {peer.isAI ? '✦' : peer.name.slice(0, 1).toUpperCase()}
          </span>
        ))}
      </div>
    </div>
  )
}
