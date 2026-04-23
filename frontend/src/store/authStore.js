import { create } from 'zustand'

const stored = localStorage.getItem('user')
const initialUser = stored ? JSON.parse(stored) : null
const initialToken = localStorage.getItem('token') || null

export const useAuthStore = create((set) => ({
  user: initialUser,
  token: initialToken,
  isAuthenticated: !!initialToken,

  login: (user, token) => {
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify(user))
    set({ user, token, isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    set({ user: null, token: null, isAuthenticated: false })
  },

  updateUser: (user) => {
    localStorage.setItem('user', JSON.stringify(user))
    set({ user })
  },
}))
