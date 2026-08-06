import { AppShell } from './shell/AppShell'
import { CockpitScreen } from './cockpit/CockpitScreen'

export default function App() {
  return (
    <AppShell>
      <CockpitScreen />
    </AppShell>
  )
}
