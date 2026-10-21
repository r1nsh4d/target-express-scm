import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, getToken, setToken } from './api'

export type UserRole =
  | 'SUPER_ADMIN'
  | 'OPS_ADMIN'
  | 'WAREHOUSE_ADMIN'
  | 'ACCOUNTS'
  | 'DRIVER'
  | 'STAKEHOLDER'
  /* Logins that belong to somebody outside Target Express. */
  | 'VENDOR'
  | 'VEHICLE_OWNER'
  /* The man who owns the lorry and drives it himself — most of the hired
     fleet. One login for both halves, because they are both his. */
  | 'OWNER_DRIVER'

export interface User {
  id: string
  full_name: string
  phone: string
  email: string | null
  role: UserRole
  is_active: boolean
  /* Whether this login is shown money at all. A driver on a rented vehicle
     is paid by his vehicle's owner, so there is no figure of ours to show
     him and the tab is left out rather than opened onto a refusal. */
  can_view_earnings?: boolean
}

interface AuthValue {
  user: User | null
  loading: boolean
  login: (phone: string, password: string) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export const ROLE_LABELS: Record<UserRole, string> = {
  SUPER_ADMIN: 'Super admin',
  OPS_ADMIN: 'Operations',
  WAREHOUSE_ADMIN: 'Warehouse admin',
  ACCOUNTS: 'Accounts',
  DRIVER: 'Driver',
  STAKEHOLDER: 'Stakeholder',
  VENDOR: 'Vendor',
  VEHICLE_OWNER: 'Vehicle owner',
  OWNER_DRIVER: 'Owner-driver',
}

/** Where each kind of login starts.
 *
 *  Four different applications share one sign-in page, and sending somebody
 *  to the wrong one is how a vendor concludes the link is broken. `/` is the
 *  public landing page, so the office console starts at `/dashboard`.
 *
 *  An owner-driver lands on the DRIVER app, because at six in the morning he
 *  is a man with a lorry to start, not a man reading last month's figures.
 *  His owner screens are a tab inside it. */
export function homePathForRole(role: UserRole): string {
  if (role === 'DRIVER' || role === 'OWNER_DRIVER') return '/driver'
  if (role === 'VENDOR') return '/vendor'
  if (role === 'VEHICLE_OWNER') return '/owner'
  return '/dashboard'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    api
      .get<User>('/auth/me')
      .then((res) => setUser(res.data))
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (phone: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/auth/login', {
      phone,
      password,
    })
    setToken(res.data.access_token)
    setUser(res.data.user)
    return res.data.user
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
