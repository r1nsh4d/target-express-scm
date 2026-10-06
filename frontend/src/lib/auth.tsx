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

export interface User {
  id: string
  full_name: string
  phone: string
  email: string | null
  role: UserRole
  is_active: boolean
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
}

/** Drivers land on the driver portal; everyone else on the operations board.
 *  `/` is the public landing page, so the console starts at `/dashboard`. */
export function homePathForRole(role: UserRole): string {
  return role === 'DRIVER' ? '/driver' : '/dashboard'
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
