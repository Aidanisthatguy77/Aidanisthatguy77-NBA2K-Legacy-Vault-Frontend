import { Route, Routes } from 'react-router-dom'
import HomePage from './HomePage'
import AdminPage from './AdminPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/admin" element={<AdminPage />} />
    </Routes>
  )
}
