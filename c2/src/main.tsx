import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Self-hosted type (law 8: no CDN on the mission path). Four weights of
// Plex Sans to read, one of JetBrains Mono for figures that must line up.
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-sans/700.css'
import '@fontsource/jetbrains-mono/500.css'
import '../../design/tokens.css'
import 'leaflet/dist/leaflet.css'
import './styles.css'
import { App } from './ui/App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
