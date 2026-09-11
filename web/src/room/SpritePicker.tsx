import { SPRITES } from '../sprites/catalogue'
import { Sprite } from '../sprites/Sprite'

interface SpritePickerProps {
  value: string
  taken?: string[]
  onChange: (id: string) => void
}

/**
 * Choose who you are before entering the room.
 *
 * Sprites already in use are marked but not blocked: in a room of four, being
 * told your first choice is unavailable is more annoying than occasionally
 * matching someone.
 */
export function SpritePicker({ value, taken = [], onChange }: SpritePickerProps) {
  return (
    <div className="sprite-picker">
      <div className="sprite-grid" role="radiogroup" aria-label="Choose your sprite">
        {SPRITES.map((sprite) => {
          const isTaken = taken.includes(sprite.id)
          return (
            <button
              key={sprite.id}
              type="button"
              role="radio"
              aria-checked={value === sprite.id}
              title={isTaken ? `${sprite.name} (already in the room)` : sprite.name}
              className={`sprite-choice${value === sprite.id ? ' is-chosen' : ''}${
                isTaken ? ' is-taken' : ''
              }`}
              onClick={() => onChange(sprite.id)}
            >
              <Sprite def={sprite} size={34} state={value === sprite.id ? 'idle' : 'still'} />
            </button>
          )
        })}
      </div>
    </div>
  )
}
