/**
 * The ARGUS brand artwork, from the brand asset pack (not redrawn).
 *
 * Each is the brand's transparent PNG used as a CSS mask, so it takes the
 * current text colour and stays right in both the dark and the day theme.
 */

import icon from '../assets/brand/argus-icon.png'
import wordmark from '../assets/brand/argus-wordmark.png'
import { say } from './wording'

/** The chevron icon on its own. Decorative: a name always sits beside it. */
export function ArgusIcon({ className = '' }: { className?: string }) {
  return <span className={`brand-art brand-icon ${className}`} style={{ ['--art' as string]: `url(${icon})` }} aria-hidden />
}

/** The ARGUS wordmark, whose A is the chevron. */
export function ArgusWordmark({ className = '' }: { className?: string }) {
  return (
    <span
      className={`brand-art brand-wordmark ${className}`}
      style={{ ['--art' as string]: `url(${wordmark})` }}
      role="img"
      aria-label={say.shell.brand}
    />
  )
}
