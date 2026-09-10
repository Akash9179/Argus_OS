import { CockpitScreen } from './cockpit/CockpitScreen'

/**
 * The cockpit is one screen. The operating system shell around it (top
 * bar, applications, who is signed in) belongs to C2, which hosts this
 * page; this app draws no chrome of its own.
 */
export default function App() {
  return <CockpitScreen />
}
