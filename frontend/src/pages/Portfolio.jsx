import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Trash2, RefreshCw, Plus } from 'lucide-react'
import { portfolioApi } from '../api/client'
import SellModal from '../components/SellModal'
import AddPositionModal from '../components/AddPositionModal'
import StockSearch from '../components/StockSearch'

function PnlTag({ value, pct }) {
  const isPos = value >= 0
  return (
    <div className={`flex items-center gap-1 text-sm font-semibold ${isPos ? 'text-green-600' : 'text-red-600'}`}>
      {isPos ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
      <span>{isPos ? '+' : ''}{value?.toFixed(2)} ({isPos ? '+' : ''}{pct?.toFixed(2)}%)</span>
    </div>
  )
}

function SummaryCard({ label, value, sub, color }) {
  return (
    <div className="card">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color || 'text-slate-900'}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  )
}

export default function Portfolio() {
  const qc = useQueryClient()
  const [sellPosition, setSellPosition] = useState(null)
  const [addStock, setAddStock] = useState(null)
  const [tab, setTab] = useState('positions')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['positions'],
    queryFn: () => portfolioApi.getPositions().then((r) => r.data),
    refetchInterval: 60_000,
  })

  const { data: txns } = useQuery({
    queryKey: ['transactions'],
    queryFn: () => portfolioApi.getTransactions(100).then((r) => r.data),
    enabled: tab === 'history',
  })

  const positions = data?.positions || []
  const summary = data?.summary || {}

  const pnlColor = (v) => (v >= 0 ? 'text-green-600' : 'text-red-600')

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-900 mb-0.5">我的持仓</h1>
          <p className="text-sm text-slate-500">{positions.length} 只股票</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => refetch()} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
            <RefreshCw size={16} className="text-slate-500" />
          </button>
          <button
            onClick={() => setAddStock({ code: '', name: '', price: 0 })}
            className="btn-primary flex items-center gap-1.5 text-sm"
          >
            <Plus size={15} /> 手动添加
          </button>
        </div>
      </div>

      {/* Summary */}
      {positions.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          <SummaryCard
            label="市值"
            value={`¥${(summary.market_value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`}
          />
          <SummaryCard
            label="总成本"
            value={`¥${(summary.total_cost || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`}
          />
          <SummaryCard
            label="浮动盈亏"
            value={`${summary.unrealized_pnl >= 0 ? '+' : ''}¥${(summary.unrealized_pnl || 0).toFixed(2)}`}
            sub={`${(summary.unrealized_pnl_pct || 0).toFixed(2)}%`}
            color={pnlColor(summary.unrealized_pnl)}
          />
          <SummaryCard
            label="已实现盈亏"
            value={`${summary.realized_pnl >= 0 ? '+' : ''}¥${(summary.realized_pnl || 0).toFixed(2)}`}
            color={pnlColor(summary.realized_pnl)}
          />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl mb-4 w-fit">
        {['positions', 'history'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
              tab === t ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
            }`}
          >
            {t === 'positions' ? '持仓' : '交易记录'}
          </button>
        ))}
      </div>

      {tab === 'positions' && (
        <>
          {isLoading && (
            <div className="card text-center py-12 text-slate-400">加载中…</div>
          )}
          {!isLoading && positions.length === 0 && (
            <div className="card text-center py-16">
              <div className="text-5xl mb-4">📊</div>
              <p className="text-slate-700 font-medium mb-1">暂无持仓</p>
              <p className="text-slate-400 text-sm mb-4">在行情页分析股票后可加入持仓</p>
            </div>
          )}

          <div className="space-y-3">
            {positions.map((pos) => (
              <div key={pos.id} className="card">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900">{pos.name}</span>
                      <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">{pos.symbol}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500">
                      <span>{pos.shares} 股</span>
                      <span>均价 ¥{pos.avg_cost?.toFixed(3)}</span>
                      <span>成本 ¥{pos.total_cost?.toFixed(0)}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-lg text-slate-900">
                      {pos.current_price > 0 ? `¥${pos.current_price?.toFixed(3)}` : '--'}
                    </p>
                    {pos.current_price > 0 && (
                      <PnlTag value={pos.unrealized_pnl} pct={pos.unrealized_pnl_pct} />
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-50">
                  <div className="text-xs text-slate-400">
                    市值: {pos.current_price > 0 ? `¥${pos.market_value?.toFixed(0)}` : '获取中…'}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setSellPosition(pos)}
                      className="btn-danger text-xs py-1.5 px-3"
                    >
                      卖出
                    </button>
                    <button
                      onClick={() => portfolioApi.deletePosition(pos.id).then(() => qc.invalidateQueries(['positions']))}
                      className="p-1.5 hover:bg-red-50 text-slate-400 hover:text-red-500 rounded-lg transition-colors"
                      title="删除持仓记录"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'history' && (
        <div className="space-y-2">
          {!txns?.length && (
            <div className="card text-center py-12 text-slate-400">暂无交易记录</div>
          )}
          {txns?.map((t) => (
            <div key={t.id} className="card flex items-center justify-between py-3">
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${t.action === 'BUY' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                  {t.action === 'BUY' ? '买' : '卖'}
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-900">{t.name} <span className="text-slate-400 text-xs">{t.symbol}</span></p>
                  <p className="text-xs text-slate-400">{t.date} · {t.shares}股 @ ¥{t.price}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-slate-900">¥{t.amount?.toFixed(2)}</p>
                {t.action === 'SELL' && (
                  <p className={`text-xs font-medium ${t.realized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {t.realized_pnl >= 0 ? '+' : ''}¥{t.realized_pnl?.toFixed(2)}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      {sellPosition && (
        <SellModal
          position={sellPosition}
          onClose={() => setSellPosition(null)}
          onSuccess={() => {
            qc.invalidateQueries(['positions'])
            qc.invalidateQueries(['transactions'])
            setSellPosition(null)
          }}
        />
      )}

      {addStock !== null && (
        <AddPositionModal
          stock={addStock.code ? addStock : null}
          onClose={() => setAddStock(null)}
          onSuccess={() => {
            qc.invalidateQueries(['positions'])
            setAddStock(null)
          }}
          showSearch={!addStock.code}
        />
      )}
    </div>
  )
}
