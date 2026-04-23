import React, { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Eye, EyeOff, CheckCircle, AlertCircle } from 'lucide-react'
import { userApi } from '../api/client'
import { useAuthStore } from '../store/authStore'

function Section({ title, children }) {
  return (
    <div className="card mb-4">
      <h3 className="font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">{title}</h3>
      <div className="space-y-4">{children}</div>
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </div>
  )
}

export default function Settings() {
  const { user } = useAuthStore()
  const qc = useQueryClient()
  const [showKey, setShowKey] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [saved, setSaved] = useState(false)
  const [form, setForm] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => userApi.getSettings().then((r) => r.data),
  })

  useEffect(() => {
    if (data && !form) setForm(data)
  }, [data])

  const mutation = useMutation({
    mutationFn: (values) => userApi.updateSettings(values),
    onSuccess: () => {
      qc.invalidateQueries(['settings'])
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const set = (k) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.type === 'number' ? parseFloat(e.target.value) : e.target.value
    setForm((prev) => ({ ...prev, [k]: val }))
  }

  if (isLoading || !form) {
    return <div className="card text-center py-16 text-slate-400">加载中…</div>
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-900 mb-1">账户设置</h1>
        <p className="text-sm text-slate-500">配置您的 AI 接口和通知方式</p>
      </div>

      {/* Account */}
      <Section title="账户信息">
        <Field label="用户名">
          <input className="input bg-slate-50" value={user?.username || ''} readOnly />
        </Field>
        <Field label="邮箱">
          <input className="input bg-slate-50" value={user?.email || ''} readOnly />
        </Field>
      </Section>

      {/* AI Settings */}
      <Section title="大模型 API 配置">
        <Field label="API Key" hint="您的大模型 API 密钥，仅保存在服务端，不会泄露">
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              className="input pr-10"
              value={form.ai_api_key || ''}
              onChange={set('ai_api_key')}
              placeholder="sk-..."
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
            >
              {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </Field>
        <Field label="API Base URL" hint="默认: https://yunwu.ai/v1  支持任何 OpenAI 兼容接口">
          <input
            className="input"
            value={form.ai_base_url || ''}
            onChange={set('ai_base_url')}
            placeholder="https://yunwu.ai/v1"
          />
        </Field>
        <Field label="模型名称">
          <input
            className="input"
            value={form.ai_model || ''}
            onChange={set('ai_model')}
            placeholder="gpt-4o"
          />
        </Field>
        <Field label="最低置信度阈值" hint="AI 置信度低于此值时不触发信号通知（0.0 ~ 1.0）">
          <input
            type="number"
            className="input"
            value={form.notify_min_confidence || 0.6}
            onChange={set('notify_min_confidence')}
            min="0"
            max="1"
            step="0.05"
          />
        </Field>
      </Section>

      {/* Email */}
      <Section title="邮件通知设置">
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="email_enabled"
            className="w-4 h-4 rounded"
            checked={form.email_enabled || false}
            onChange={set('email_enabled')}
          />
          <label htmlFor="email_enabled" className="text-sm font-medium text-slate-700">
            启用邮件通知
          </label>
        </div>

        {form.email_enabled && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="SMTP 服务器">
                <input className="input" value={form.email_smtp_host || ''} onChange={set('email_smtp_host')} placeholder="smtp.qq.com" />
              </Field>
              <Field label="SMTP 端口">
                <input type="number" className="input" value={form.email_smtp_port || 465} onChange={set('email_smtp_port')} />
              </Field>
            </div>
            <Field label="发件人邮箱">
              <input type="email" className="input" value={form.email_sender || ''} onChange={set('email_sender')} placeholder="your@qq.com" />
            </Field>
            <Field label="发件人授权码" hint="QQ 邮箱请使用授权码而非密码">
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  className="input pr-10"
                  value={form.email_sender_pass || ''}
                  onChange={set('email_sender_pass')}
                  placeholder="授权码"
                />
                <button type="button" onClick={() => setShowPass(!showPass)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </Field>
            <Field label="接收邮箱">
              <input type="email" className="input" value={form.email_receiver || ''} onChange={set('email_receiver')} placeholder="receive@email.com" />
            </Field>
          </>
        )}
      </Section>

      {/* Capital */}
      <Section title="资金设置">
        <Field label="初始资金 (元)" hint="用于计算仓位比例和回测">
          <input
            type="number"
            className="input"
            value={form.initial_capital || 100000}
            onChange={set('initial_capital')}
            min="1000"
            step="1000"
          />
        </Field>
      </Section>

      {/* Save button */}
      <div className="flex items-center gap-3">
        <button
          className="btn-primary flex items-center gap-2"
          onClick={() => mutation.mutate(form)}
          disabled={mutation.isPending}
        >
          <Save size={16} />
          {mutation.isPending ? '保存中…' : '保存设置'}
        </button>
        {saved && (
          <div className="flex items-center gap-1.5 text-green-600 text-sm font-medium">
            <CheckCircle size={16} /> 已保存
          </div>
        )}
        {mutation.isError && (
          <div className="flex items-center gap-1.5 text-red-600 text-sm">
            <AlertCircle size={16} /> 保存失败
          </div>
        )}
      </div>
    </div>
  )
}
