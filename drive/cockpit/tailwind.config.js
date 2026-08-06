/** @type {import('tailwindcss').Config} */
// Tokens mirror DESIGN.md §2–§4. Keep in sync with that brand doc.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0B0C0E',
        'surface-1': '#121417',
        'surface-2': '#16181C',
        'surface-3': '#1C1F24',
        'surface-inset': '#0E0F12',
        text: '#F5F7FA',
        'text-2': '#A4ABB4',
        'text-3': '#6B727B',
        accent: '#2E8FFF',
        'accent-strong': '#1E73E6',
        critical: '#FF4D4D',
        warning: '#F5A623',
        info: '#3B9EFF',
        success: '#22C55E',
      },
      borderColor: {
        line: 'rgba(255,255,255,0.07)',
        'line-strong': 'rgba(255,255,255,0.12)',
      },
      backgroundColor: {
        'accent-weak': 'rgba(46,143,255,0.14)',
        'critical-weak': 'rgba(255,77,77,0.12)',
        'warning-weak': 'rgba(245,166,35,0.14)',
        'info-weak': 'rgba(59,158,255,0.14)',
        'success-weak': 'rgba(34,197,94,0.14)',
      },
      fontFamily: {
        sans: ['Geist', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        card: '16px',
        control: '10px',
        chip: '6px',
      },
      boxShadow: {
        overlay: '0 16px 48px rgba(0,0,0,0.55)',
      },
      ringColor: {
        accent: 'rgba(46,143,255,0.45)',
      },
    },
  },
  plugins: [],
}
