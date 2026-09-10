/**
 * Where the backend lives.
 *
 * In development the Vite dev server proxies /api, /health and /ws to the
 * Python process, so same-origin relative URLs are correct and this module
 * resolves to the empty string. A deployed build has no such proxy -- the
 * static bundle is served by a CDN and the backend is a separate host -- so
 * VITE_BACKEND_ORIGIN supplies the absolute origin at build time.
 *
 * Kept in one place because the websocket URLs cannot simply be relative: the
 * WebSocket constructor requires an absolute ws:// or wss:// URL.
 */

const configured = (import.meta.env.VITE_BACKEND_ORIGIN ?? '').trim().replace(/\/+$/, '')

/** True when the bundle was built against an explicit backend host. */
export const hasBackendOrigin = configured !== ''

/** Absolute URL for an HTTP endpoint, or a relative one when proxied. */
export function apiUrl(path: string): string {
  return `${configured}${path}`
}

/** Absolute ws:// or wss:// URL, derived from the backend origin when set. */
export function wsUrl(path: string): string {
  if (!configured) {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${location.host}${path}`
  }
  return `${configured.replace(/^http/, 'ws')}${path}`
}
