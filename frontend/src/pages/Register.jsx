import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuthStore } from '../store/authStore'

export default function Register() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [form, setForm] = useState({ username: '', email: '', password: '', confirm: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (form.password !== form.confirm) {
      setError('两次密码不一致')
      return
    }
    setLoading(true)
    try {
      const { data } = await authApi.register({
        username: form.username,
        email: form.email,
        password: form.password,
      })
      login({ id: data.user_id, username: data.username, email: data.email }, data.access_token)
      navigate('/settings')
    } catch (err) {
      setError(err.response?.data?.detail || '注册失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const set = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">📈</div>
          <h1 className="text-2xl font-bold text-slate-900">创建账号</h1>
          <p className="text-slate-500 text-sm mt-1">开始您的量化交易之旅</p>
        </div>

        <div className="card shadow-lg">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">用户名</label>
              <input className="input" value={form.username} onChange={set('username')} placeholder="2-20个字符" minLength={2} required />
            </div>
            <div>
              <label className="label">邮箱</label>
              <input type="email" className="input" value={form.email} onChange={set('email')} placeholder="your@email.com" required />
            </div>
            <div>
              <label className="label">密码</label>
              <input type="password" className="input" value={form.password} onChange={set('password')} placeholder="至少6位" minLength={6} required />
            </div>
            <div>
              <label className="label">确认密码</label>
              <input type="password" className="input" value={form.confirm} onChange={set('confirm')} placeholder="再次输入密码" required />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-100 text-red-600 text-sm rounded-xl px-3 py-2.5">
                {error}
              </div>
            )}

            <button type="submit" className="btn-primary w-full py-3 text-base" disabled={loading}>
              {loading ? '注册中...' : '注册'}
            </button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-4">
            已有账号？{' '}
            <Link to="/login" className="text-blue-600 font-medium hover:underline">
              立即登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
