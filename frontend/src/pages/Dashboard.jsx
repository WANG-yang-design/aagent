import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  TrendingUp, TrendingDown, Minus, RefreshCw, PlusCircle,
  ChevronDown, ChevronUp, Activity
} from 'lucide-react'
import { stocksApi } from '../api/client'
import StockSearch from '../components/StockSearch'
import AddPositionModal from '../components/AddPositionModal'

const ActionBadge = ({ action }) => {
  if (action === 'BUY') return <span className="badge-buy">买入</span>
  if (action === 'SELL') return <span className="badge-sell">卖出</span>
  return <span className="badge-hold">观望</span>
}

const ConfidenceBar = ({ value }) => (
  <div className="flex items-center gap-2">
    <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${value >= 0.75 ? 'bg-green-500' : value >= 0.55 ? 'bg-blue-500' : 'bg-slate-400'}`}
        style={{ width: `${value * 100}%` }}
      />
    </div>
    <span className="text-xs text-slate-500 w-9">{(value * 100).toFixed(0)}%</span>
  </div>
)

function SignalCard({ signal, onAddPosition }) {
  const [expanded, setExpanded] = useState(false)
  const priceColor = signal.change_pct > 0 ? 'text-green-600' : signal.change_pct < 0 ? 'text-red-600' : 'text-slate-600'

  return (
    <div className="card hover:shadow-md transition-all">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-900">{signal.name}</span>
            <ActionBadge action={signal.action} />
          </div>
          <p className="text-xs text-slate-400 mt-0.5">{signal.symbol}</p>
        </div>
        <div className="text-right">
          <p className="font-bold text-slate-900 text-lg">¥{signal.price?.toFixed(3) || '--'}</p>
          {signal.change_pct != null && (
            <p className={`text-xs font-medium flex items-center gap-0.5 justify-end ${priceColor}`}>
              {signal.change_pct > 0 ? <TrendingUp size={11} /> : signal.change_pct < 0 ? <TrendingDown size={11} /> : <Minus size={11} />}
              {signal.change_pct > 0 ? '+' : ''}{signal.change_pct?.toFixed(2)}%
            </p>
          )}
        </div>
      </div>

      <ConfidenceBar value={signal.confidence || 0} />

      <p className="text-xs text-slate-600 mt-2.5 leading-relaxed line-clamp-2">{signal.reason || '等待分析…'}</p>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-slate-50 grid grid-cols-2 gap-2 text-xs">
          {signal.stop_loss && (
            <div className="bg-red-50 rounded-lg px-2.5 py-1.5">
              <p className="text-slate-500">止损价</p>
              <p className="font-semibold text-red-600">¥{signal.stop_loss}</p>
            </div>
          )}
          {signal.take_profit && (
            <div className="bg-green-50 rounded-lg px-2.5 py-1.5">
              <p className="text-slate-500">止盈价</p>
              <p className="font-semibold text-green-600">¥{signal.take_profit}</p>
            </div>
          )}
          {signal.rsi && (
            <div className="bg-slate-50 rounded-lg px-2.5 py-1.5">
              <p className="text-slate-500">RSI</p>
              <p className="font-semibold">{signal.rsi?.toFixed(1)}</p>
            </div>
          )}
          {signal.sentiment && (
            <div className="bg-slate-50 rounded-lg px-2.5 py-1.5">
              <p className="text-slate-500">情绪</p>
              <p className="font-semibold capitalize">{signal.sentiment}</p>
            </div>
          )}
          {signal.position_advice && (
            <div className="col-span-2 bg-blue-50 rounded-lg px-2.5 py-1.5">
              <p className="text-slate-500">建议</p>
              <p className="font-medium text-blue-800">{signal.position_advice}</p>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between mt-3 pt-2">
        <button
          className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1 transition-colors"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <><ChevronUp size={12} />收起</> : <><ChevronDown size={12} />详情</>}
        </button>
        <button
          className="flex items-center gap-1 text-xs bg-blue-50 text-blue-600 px-3 py-1.5 rounded-lg hover:bg-blue-100 transition-colors font-medium"
          onClick={() => onAddPosition({ code: signal.symbol, name: signal.name, price: signal.price })}
        >
          <PlusCircle size={12} /> 加入持仓
        </button>
      </div>
    </div>
  )
}

function AnalyzeCard({ stock, onAddPosition }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const analyze = async () => {
    setLoading(true)
    try {
      const { data } = await stocksApi.analyze(stock.code)
      setResult(data)
    } catch (e) {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  if (result) {
    return <SignalCard signal={{ ...result, change_pct: stock.change_pct }} onAddPosition={onAddPosition} />
  }

  return (
    <div className="card flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
          <Activity size={18} className="text-blue-500" />
        </div>
        <div>
          <p className="font-semibold text-slate-900">{stock.name}</p>
          <p className="text-xs text-slate-400">{stock.code}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        {stock.price > 0 && (
          <span className="text-sm font-bold">¥{stock.price?.toFixed(3)}</span>
        )}
        <button
          className="btn-primary text-sm py-2"
          onClick={analyze}
          disabled={loading}
        >
          {loading ? '分析中…' : 'AI分析'}
        </button>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const qc = useQueryClient()
  const [selectedStock, setSelectedStock] = useState(null)
  const [addPositionStock, setAddPositionStock] = useState(null)
  const [pendingStocks, setPendingStocks] = useState([])

  const { data: signalsData, isLoading, refetch } = useQuery({
    queryKey: ['signals'],
    queryFn: () => stocksApi.analyze ? null : null,
    enabled: false,
  })

  const handleStockSelect = (stock) => {
    const exists = pendingStocks.find((s) => s.code === stock.code)
    if (!exists) {
      setPendingStocks((prev) => [stock, ...prev])
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-900 mb-1">行情分析</h1>
        <p className="text-sm text-slate-500">搜索股票进行 AI 智能分析</p>
      </div>

      {/* Search */}
      <div className="mb-5">
        <StockSearch onSelect={handleStockSelect} />
      </div>

      {/* Empty state */}
      {pendingStocks.length === 0 && (
        <div className="card text-center py-16">
          <div className="text-5xl mb-4">🔍</div>
          <p className="text-slate-700 font-medium mb-1">搜索股票开始分析</p>
          <p className="text-slate-400 text-sm">支持股票名称或6位代码模糊搜索</p>
        </div>
      )}

      {/* Stock cards */}
      {pendingStocks.length > 0 && (
        <div className="space-y-3">
          {pendingStocks.map((stock) => (
            <AnalyzeCard
              key={stock.code}
              stock={stock}
              onAddPosition={setAddPositionStock}
            />
          ))}
        </div>
      )}

      {/* Add Position Modal */}
      {addPositionStock && (
        <AddPositionModal
          stock={addPositionStock}
          onClose={() => setAddPositionStock(null)}
          onSuccess={() => {
            qc.invalidateQueries(['positions'])
            setAddPositionStock(null)
          }}
        />
      )}
    </div>
  )
}
