import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/tailwind.css'
import App from './App'
import { FrontendErrorBoundary } from './components/FrontendErrorBoundary'

// Aplica preferência antes do React renderizar, evitando flash/tema perdido no refresh.
const savedTheme = localStorage.getItem('theme')
const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
const shouldUseDark = savedTheme ? savedTheme === 'dark' : !!prefersDark
document.documentElement.classList.toggle('dark', shouldUseDark)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FrontendErrorBoundary>
      <App />
    </FrontendErrorBoundary>
  </StrictMode>,
)
