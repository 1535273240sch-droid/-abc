import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/Layout'
import Dashboard from './pages/Dashboard'
import MarketData from './pages/MarketData'
import Analytics from './pages/Analytics'
import Kline from './pages/Kline'
import Research from './pages/Research'
import Execution from './pages/Execution'
import Risk from './pages/Risk'
import Agents from './pages/Agents'
import Settings from './pages/Settings'

export default function App() {
  return <AppShell><Routes><Route path="/" element={<Navigate to="/dashboard" replace />} /><Route path="/dashboard" element={<Dashboard />} /><Route path="/market" element={<MarketData />} /><Route path="/kline" element={<Kline />} /><Route path="/analytics" element={<Analytics />} /><Route path="/research" element={<Research />} /><Route path="/execution" element={<Execution />} /><Route path="/risk" element={<Risk />} /><Route path="/agents" element={<Agents />} /><Route path="/settings" element={<Settings />} /><Route path="*" element={<Navigate to="/dashboard" replace />} /></Routes></AppShell>
}
