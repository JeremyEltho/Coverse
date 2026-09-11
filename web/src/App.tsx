import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Landing } from './routes/Landing'
import { Room } from './routes/Room'
import { Sheet } from './sprites/Sheet'

export default function App() {
  return (
    <BrowserRouter>
      {/* The light the glass sits on. One instance, behind every route. */}
      <div className="backdrop" aria-hidden="true">
        <span />
      </div>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/r/:code" element={<Room />} />
        <Route path="/sprites" element={<Sheet />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
