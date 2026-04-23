import React, { useState } from 'react'
import { X } from 'lucide-react'
import { portfolioApi } from '../api/client'

export default function AddPositionModal({ stock, onClose, onSuccess, showSearch }) {
  const [searchCode, setSearchCode] = useState(stock?.code || '')
  const [searchName, setSearchName] = useState(stock?.name || '')
  const [form, setForm] = useState({
    shares: '',
    price: stock?.price ? String(stock.price.toFixed(3)) : '',
    note: '',
    date: new Date().toISOString().split('T')[0],
  })
  const effectiveCode = stock?.code || searchCode
  const effectiveName = stock?.name || searchName
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }))

  const totalAmount = ((parseFloat(form.shares) || 0) * (parseFloat(form.price) || 0)).toFixed(2)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    const shares = parseFloat(form.shares)
    const price = parseFloat(form.price)
    if (!shares || !price || shares <= 0 || price <= 0) {
      setError('请输入有效的股数和价格')
      return
    }
    setLoading(true)
    try {
      await portfolioApi.buy({
        symbol: effectiveCode,
        name: effectiveName,
        shares,
        price,
        note: form.note,
        date: form.date,
      })
      onSuccess?.()
      onClose?.()
    } catch (err) {
      setError(err.response?.data?.detail || '添加失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-end sm:items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <h3 className="font-bold text-slate-900">加入持仓</h3>
            {effectiveName && <p className="text-sm text-slate-500">{effectiveName} · {effectiveCode}</p>}
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {showSearch && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">股票代码</label>
                <input className="input" value={searchCode} onChange={(e) => setSearchCode(e.target.value.toUpperCase())} placeholder="000001" maxLength={6} required={!stock?.code} />
              </div>
              <div>
                <label className="label">股票名称（可选）</label>
                <input className="input" value={searchName} onChange={(e) => setSearchName(e.target.value)} placeholder="自动获取" />
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">买入股数</label>
              <input
                type="number"
                className="input"
                value={form.shares}
                onChange={set('shares')}
                placeholder="100"
                min="1"
                step="100"
                required
              />
            </div>
            <div>
              <label className="label">买入价格 (元)</label>
              <input
                type="number"
                className="input"
                value={form.price}
                onChange={set('price')}
                placeholder="0.00"
                min="0.001"
                step="0.001"
                required
              />
            </div>
          </div>

          <div>
            <label className="label">买入日期</label>
            <input type="date" className="input" value={form.date} onChange={set('date')} />
          </div>

          <div>
            <label className="label">备注（可选）</label>
            <input className="input" value={form.note} onChange={set('note')} placeholder="如：AI信号 / 自行判断" />
          </div>

          {parseFloat(form.shares) > 0 && parseFloat(form.price) > 0 && (
            <div className="bg-blue-50 rounded-xl px-4 py-3 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-600">总金额</span>
                <span className="font-bold text-blue-600">¥ {Number(totalAmount).toLocaleString()}</span>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 text-red-600 text-sm rounded-xl px-3 py-2.5">{error}</div>
          )}

          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} className="btn-secondary flex-1">取消</button>
            <button type="submit" className="btn-primary flex-1" disabled={loading}>
              {loading ? '添加中…' : '确认买入'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
