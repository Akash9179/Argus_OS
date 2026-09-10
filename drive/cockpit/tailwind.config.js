/** @type {import('tailwindcss').Config} */
// The palette is the shared visual language in design/tokens.css, read
// through CSS variables so a Tailwind utility and a var() can never
// disagree. The rgb triplets exist so opacity modifiers (border-accent/40)
// keep working.
const rgb = (name) => `rgb(var(--${name}-rgb) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: rgb('bg'),
        'surface-1': rgb('card'),
        'surface-2': rgb('card-2'),
        'surface-3': rgb('card-3'),
        'surface-inset': rgb('bg'),
        text: rgb('ink'),
        'text-2': rgb('ink-2'),
        'text-3': rgb('ink-3'),
        accent: rgb('sel'),
        'accent-strong': rgb('sel'),
        critical: rgb('act'),
        warning: rgb('warn'),
        info: rgb('sel'),
        success: rgb('ok'),
      },
      borderColor: {
        line: 'var(--line)',
        'line-strong': 'var(--line-2)',
      },
      backgroundColor: {
        'accent-weak': 'var(--sel-bg)',
        'critical-weak': 'var(--act-bg)',
        'warning-weak': 'var(--warn-bg)',
        'info-weak': 'var(--sel-bg)',
        'success-weak': 'var(--ok-bg)',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        card: '4px',
        control: '4px',
        chip: '3px',
      },
      boxShadow: {
        overlay: '0 16px 48px rgba(0,0,0,0.55)',
      },
      ringColor: {
        accent: 'var(--sel-ring)',
      },
    },
  },
  plugins: [],
}
