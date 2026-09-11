import { SPRITES, ASSISTANT_SPRITE } from './catalogue'
import { Sprite } from './Sprite'

/** Dev-only: every creature at the sizes the app actually uses. */
export function Sheet() {
  const all = [...SPRITES, ASSISTANT_SPRITE]
  return (
    <div style={{ padding: 28, display: 'flex', flexDirection: 'column', gap: 22 }}>
      {[64, 36, 28, 20].map((size) => (
        <div key={size}>
          <p style={{ color: 'rgba(255,255,255,.5)', fontSize: 12, margin: '0 0 8px' }}>
            {size}px
          </p>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            {all.map((s) => (
              <div key={s.id} style={{ textAlign: 'center' }}>
                <Sprite def={s} size={size} state="still" />
                {size === 64 ? (
                  <div style={{ color: 'rgba(255,255,255,.55)', fontSize: 11, marginTop: 4 }}>
                    {s.name}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
