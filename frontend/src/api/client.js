import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
})

// 自动附带 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 401 自动登出
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── Auth ──────────────────────────────────────────────────────────────────
export const authApi = {
  register: (data) => api.post('/api/auth/register', data),
  login: (data) => api.post('/api/auth/login', data),
  me: () => api.get('/api/auth/me'),
}

// ── User Settings ─────────────────────────────────────────────────────────
export const userApi = {
  getSettings: () => api.get('/api/user/settings'),
  updateSettings: (data) => api.put('/api/user/settings', data),
}

// ── Stocks ────────────────────────────────────────────────────────────────
export const stocksApi = {
  search: (q) => api.get('/api/stocks/search', { params: { q } }),
  getPrice: (symbol) => api.get(`/api/stocks/${symbol}/price`),
  analyze: (symbol) => api.get(`/api/analyze/${symbol}`),
  analyzeWithContext: (symbol, context) => api.post(`/api/analyze/${symbol}`, context),
  getKline: (symbol, days = 120) => api.get(`/api/kline/${symbol}`, { params: { days } }),
}

// ── Portfolio ─────────────────────────────────────────────────────────────
export const portfolioApi = {
  getPositions: () => api.get('/api/portfolio/positions'),
  buy: (data) => api.post('/api/portfolio/buy', data),
  sell: (data) => api.post('/api/portfolio/sell', data),
  deletePosition: (id) => api.delete(`/api/portfolio/positions/${id}`),
  getTransactions: (limit = 50) => api.get('/api/portfolio/transactions', { params: { limit } }),
}
