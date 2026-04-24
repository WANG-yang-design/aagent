import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuthStore } from '../store/authStore'

const API_URL = import.meta.env.VITE_API_URL || '(未设置，使用相对路径)'

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [form, setForm] = useState({ username: '', password: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [backendOk, setBackendOk] = useState(null)

  useEffect(() => {
    const base = import.meta.env.VITE_API_URL || ''
    fetch(`${base}/api/health`)
      .then((r) => setBackendOk(r.ok))
      .catch(() => setBackendOk(false))
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await authApi.login(form)
      login({ id: data.user_id, username: data.username, email: data.email }, data.access_token)
      navigate('/')
    } catch (err) {
      if (!err.response) {
        setError(`网络连接失败（${err.message}）——请确认后端隧道仍在运行`)
      } else {
        setError(err.response?.data?.detail || '登录失败，请重试')
      }
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
          {/* Backend status indicator */}
          <div className={`text-xs rounded-lg px-3 py-2 mb-4 font-mono break-all ${
            backendOk === null ? 'bg-slate-100 text-slate-500' :
            backendOk ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'
          }`}>
            {backendOk === null && '正在检测后端连接...'}
            {backendOk === true && `后端已连接 ✓`}
            {backendOk === false && `后端无法连接 ✗ — 请启动隧道`}
            <span className="block text-slate-400 mt-0.5">{API_URL}</span>
          </div>

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
