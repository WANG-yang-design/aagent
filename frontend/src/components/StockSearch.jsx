import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Search, X, TrendingUp, TrendingDown } from 'lucide-react'
import { stocksApi } from '../api/client'

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function StockSearch({ onSelect, placeholder = '搜索股票名称或代码…' }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debounced = useDebounce(query, 300)
  const ref = useRef(null)

  useEffect(() => {
    if (!debounced) {
      setResults([])
      return
    }
    setLoading(true)
    stocksApi
      .search(debounced)
      .then(({ data }) => {
        setResults(data.results || [])
        setOpen(true)
      })
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [debounced])

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = (stock) => {
    setQuery('')
    setOpen(false)
    setResults([])
    onSelect?.(stock)
  }

  const pnlColor = (pct) =>
    pct > 0 ? 'text-green-600' : pct < 0 ? 'text-red-600' : 'text-slate-500'

  return (
    <div ref={ref} className="relative w-full">
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          className="input pl-9 pr-8"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={placeholder}
        />
        {query && (
          <button
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            onClick={() => { setQuery(''); setResults([]); setOpen(false) }}
          >
            <X size={14} />
          </button>
        )}
      </div>

      {open && (results.length > 0 || loading) && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden">
          {loading && (
            <div className="px-4 py-3 text-sm text-slate-400 text-center">搜索中…</div>
          )}
          {results.map((s) => (
            <button
              key={s.code}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors text-left border-b border-slate-50 last:border-0"
              onClick={() => handleSelect(s)}
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
                  <span className="text-blue-600 font-bold text-xs">{s.code.slice(-2)}</span>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-900">{s.name}</p>
                  <p className="text-xs text-slate-400">{s.code} · {s.market}</p>
                </div>
              </div>
              {s.price > 0 && (
                <div className="text-right">
                  <p className="text-sm font-semibold text-slate-900">¥{s.price.toFixed(2)}</p>
                  <p className={`text-xs flex items-center gap-0.5 justify-end ${pnlColor(s.change_pct)}`}>
                    {s.change_pct > 0 ? <TrendingUp size={10} /> : s.change_pct < 0 ? <TrendingDown size={10} /> : null}
                    {s.change_pct > 0 ? '+' : ''}{s.change_pct?.toFixed(2)}%
                  </p>
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
