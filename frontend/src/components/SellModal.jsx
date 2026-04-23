import React, { useState } from 'react'
import { X, TrendingUp, TrendingDown } from 'lucide-react'
import { portfolioApi } from '../api/client'

export default function SellModal({ position, onClose, onSuccess }) {
  const [form, setForm] = useState({
    shares: String(position?.shares || ''),
    price: position?.current_price > 0 ? String(position.current_price.toFixed(3)) : '',
    note: '',
    date: new Date().toISOString().split('T')[0],
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }))

  const shares = parseFloat(form.shares) || 0
  const price = parseFloat(form.price) || 0
  const costBasis = shares * (position?.avg_cost || 0)
  const proceeds = shares * price
  const pnl = proceeds - costBasis
  const pnlPct = costBasis > 0 ? (pnl / costBasis) * 100 : 0

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!shares || !price || shares <= 0 || price <= 0) {
      setError('请输入有效的股数和价格')
      return
    }
    if (shares > position.shares) {
      setError(`最多可卖 ${position.shares} 股`)
      return
    }
    setLoading(true)
    try {
      await portfolioApi.sell({
        symbol: position.symbol,
        shares,
        price,
        note: form.note,
        date: form.date,
      })
      onSuccess?.()
      onClose?.()
    } catch (err) {
      setError(err.response?.data?.detail || '卖出失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-end sm:items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <h3 className="font-bold text-slate-900">卖出股票</h3>
            <p className="text-sm text-slate-500">
              {position?.name} · 持仓 {position?.shares} 股 · 均价 ¥{position?.avg_cost?.toFixed(3)}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">卖出股数</label>
              <input
                type="number"
                className="input"
                value={form.shares}
                onChange={set('shares')}
                placeholder="100"
                min="1"
                max={position?.shares}
                required
              />
            </div>
            <div>
              <label className="label">卖出价格 (元)</label>
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
            <label className="label">卖出日期</label>
            <input type="date" className="input" value={form.date} onChange={set('date')} />
          </div>

          <div>
            <label className="label">备注（可选）</label>
            <input className="input" value={form.note} onChange={set('note')} placeholder="如：止盈清仓 / 止损" />
          </div>

          {shares > 0 && price > 0 && (
            <div className={`rounded-xl px-4 py-3 text-sm ${pnl >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
              <div className="flex justify-between mb-1">
                <span className="text-slate-600">卖出金额</span>
                <span className="font-semibold">¥ {proceeds.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-600">预计盈亏</span>
                <span className={`font-bold flex items-center gap-1 ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {pnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  {pnl >= 0 ? '+' : ''}¥{pnl.toFixed(2)} ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                </span>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 text-red-600 text-sm rounded-xl px-3 py-2.5">{error}</div>
          )}

          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose} className="btn-secondary flex-1">取消</button>
            <button type="submit" className="btn-danger flex-1" disabled={loading}>
              {loading ? '卖出中…' : '确认卖出'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
