import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Dev-only bearer token stub matching backend/app/auth.py. Replaced by real
// per-user auth in a production deployment -- see SECURITY.md.
const DEV_BEARER_TOKEN = import.meta.env.VITE_API_BEARER_TOKEN ?? 'dev-local-token'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    Authorization: `Bearer ${DEV_BEARER_TOKEN}`,
  },
})
