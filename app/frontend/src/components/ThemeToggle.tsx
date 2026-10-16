import type { Theme } from '../types'
import { Icon } from './Icons'

export function ThemeToggle({ theme, onChange }: { theme: Theme; onChange: (theme: Theme) => void }) {
  const next = theme === 'light' ? 'dark' : 'light'
  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={() => onChange(next)}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
    >
      <Icon name={theme === 'light' ? 'moon' : 'sun'} size={16} />
      <span>{theme === 'light' ? 'DARK' : 'LIGHT'}</span>
    </button>
  )
}
