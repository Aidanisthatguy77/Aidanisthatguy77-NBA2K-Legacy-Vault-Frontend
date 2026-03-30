export function resolveApiBase() {
  const envBase = import.meta.env.VITE_API_BASE_URL
  if (envBase && String(envBase).trim()) return String(envBase).trim()

  if (typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)) {
    return 'http://localhost:8000'
  }

  if (typeof window !== 'undefined') return window.location.origin
  return 'http://localhost:8000'
}

export const API_BASE = resolveApiBase()
export const TOKEN_KEY = 'vault_admin_token'

export type AdminTab =
  | 'Dashboard'
  | 'Content'
  | 'Games'
  | 'Community'
  | 'Creator'
  | 'Health'
  | 'Doctor'
  | 'Comments'
  | 'Clips'
  | 'Proof'
  | 'Mockups'
  | 'Votes'
  | 'Social Feed'
  | 'Deploy'
  | 'Editor'
  | 'System Log'
  | 'Code Export'
  | 'Suggestions'
  | 'Mission Control'

export const TABS: AdminTab[] = [
  'Dashboard',
  'Content',
  'Games',
  'Community',
  'Creator',
  'Health',
  'Doctor',
  'Suggestions',
  'Comments',
  'Clips',
  'Proof',
  'Mockups',
  'Votes',
  'Social Feed',
  'Deploy',
  'Editor',
  'System Log',
  'Code Export',
  'Mission Control',
]
