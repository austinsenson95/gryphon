import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/caveat/latin-400.css'
import '@fontsource/caveat/latin-500.css'
import '@fontsource/caveat/latin-600.css'
import '@fontsource/caveat/latin-700.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
