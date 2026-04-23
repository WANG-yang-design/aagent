import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuthStore } from '../store/authStore'

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [form, setForm] = useState({ username: '', password: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await authApi.login(form)
      login({ id: data.user_id, username: data.username, email: data.email }, data.access_token)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || '登录失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">📈</div>
          <h1 className="text-2xl font-bold text-slate-900">AAgent 量化交易</h1>
          <p className="text-slate-500 text-sm mt-1">登录您的账户</p>
        </div>

        <div className="card shadow-lg">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">用户名 / 邮箱</label>
              <input
                className="input"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                placeholder="请输入用户名或邮箱"
                autoComplete="username"
                required
              />
            </div>
            <div>
              <label className="label">密码</label>
              <input
                type="password"
                className="input"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="请输入密码"
                autoComplete="current-password"
                required
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-100 text-red-600 text-sm rounded-xl px-3 py-2.5">
                {error}
              </div>
            )}

            <button type="submit" className="btn-primary w-full py-3 text-base" disabled={loading}>
              {loading ? '登录中...' : '登录'}
            </button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-4">
            还没有账号？{' '}
            <Link to="/register" className="text-blue-600 font-medium hover:underline">
              立即注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
