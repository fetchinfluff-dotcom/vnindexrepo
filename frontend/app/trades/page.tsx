'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, fmt, fmtPct } from '@/lib/api'
import { TrendingUp, TrendingDown } from 'lucide-react'

export default function TradesPage() {
  const [trades, setTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState('')

  useEffect(() => {
    fetchAPI('/trades?limit=500', 120_000)
      .then(d => { setTrades(Array.isArray(d) ? d : []); setLoading(false) })
      .catch(e => { setErr(e.message); setLoading(false) })
  }, [])

  const filtered = filter ? trades.filter((t: any) => t.ticker?.includes(filter.toUpperCase())) : trades
  const wins = filtered.filter((t:any) => t.pnl > 0)
  const losses = filtered.filter((t:any) => t.pnl <= 0)

  if (err) return <div className="card text-sell">{err}</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Lịch sử giao dịch</h1>
        <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Lọc theo mã..." className="input-field w-40" />
      </div>

      {loading ? <LoadingSkeleton /> : <>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="card"><div className="text-xs text-muted-foreground">Tổng GD</div><div className="text-xl font-bold">{filtered.length}</div></div>
          <div className="card"><div className="text-xs text-muted-foreground">Win Rate</div><div className="text-xl font-bold text-buy">{filtered.length ? (wins.length/filtered.length*100).toFixed(1) : '0'}%</div></div>
          <div className="card"><div className="text-xs text-muted-foreground">Avg Win</div><div className="text-xl font-bold text-buy">{wins.length ? fmtPct(wins.reduce((s:number,t:any)=>s+t.pnl_pct,0)/wins.length) : '-'}</div></div>
          <div className="card"><div className="text-xs text-muted-foreground">Avg Loss</div><div className="text-xl font-bold text-sell">{losses.length ? fmtPct(losses.reduce((s:number,t:any)=>s+t.pnl_pct,0)/losses.length) : '-'}</div></div>
          <div className="card"><div className="text-xs text-muted-foreground">Avg Days</div><div className="text-xl font-bold">{filtered.length ? (filtered.reduce((s:number,t:any)=>s+(t.days_held||0),0)/filtered.length).toFixed(0) : '0'}d</div></div>
        </div>

        <div className="card">
          {filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground border-b border-border">
                    <th className="text-left py-2">Vào</th>
                    <th className="text-left py-2">Mã</th>
                    <th className="text-right py-2">Giá vào</th>
                    <th className="text-right py-2">Giá ra</th>
                    <th className="text-right py-2">PnL</th>
                    <th className="text-center py-2">Lý do</th>
                    <th className="text-center py-2">Ngày</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, 200).map((t: any, i: number) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-secondary/30">
                      <td className="py-2 text-xs text-muted-foreground">{t.entry_date}</td>
                      <td className="py-2 font-medium">{t.ticker}</td>
                      <td className="py-2 text-right">{fmt(t.entry_price)}</td>
                      <td className="py-2 text-right">{fmt(t.exit_price)}</td>
                      <td className={`py-2 text-right font-medium ${t.pnl >= 0 ? 'text-buy' : 'text-sell'}`}>
                        <span className="flex items-center justify-end gap-1">
                          {t.pnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                          {fmtPct(t.pnl_pct)}
                        </span>
                      </td>
                      <td className="py-2 text-center">
                        <span className={`badge ${t.exit_reason === 'stop_loss' ? 'badge-sell' : t.exit_reason === 'time_stop' ? 'badge-neutral' : 'badge-buy'}`}>
                          {t.exit_reason}
                        </span>
                      </td>
                      <td className="py-2 text-center text-xs text-muted-foreground">{t.days_held || '-'}d</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-muted-foreground">Không có giao dịch nào</p>}
        </div>
      </>}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="grid grid-cols-5 gap-4">{[...Array(5)].map((_,i) => <div key={i} className="card h-20" />)}</div>
      <div className="card h-96" />
    </div>
  )
}
