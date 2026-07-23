import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import EncounterDetailPage from './pages/EncounterDetailPage'
import EncounterListPage from './pages/EncounterListPage'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<EncounterListPage />} />
          <Route path="/encounters/:encounterId" element={<EncounterDetailPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
