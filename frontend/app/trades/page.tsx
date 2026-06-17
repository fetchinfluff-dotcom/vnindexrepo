'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, fmt, fmtPct } from '@/lib/api'
import { TrendingUp, TrendingDown, ChevronDown, ChevronUp } from 'lucide-react'

const EXIT_REASON_LABELS: Record<string, string> = {
  stop_loss: 'Cắt lỗ',
  trailing_stop: 'Trailing',
  time_stop: 'Hết hạn',
  take_profit: 'Chốt lời',
  end_of_test: 'Kết thúc',
}

const EXIT_REASON_COLORS: Record<string, string> = {
  stop_loss: 'badge-sell',
  trailing_stop: 'badge-neutral',
  time_stop: 'badge-neutral',
  take_profit: 'badge-buy',
  end_of_test: 'badge-buy',
}

const LIMIT_OPTIONS = [30, 50, 100]

export default function TradesPage() {
  const [allTrades, setAllTrades] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState('')
  const [limit, setLimit] = useState(50)
  const [showOpenOnly, setShowOpenOnly] = useState(false)
  const [sortKey, setSortKey] = useState('entry_date')
  const [sortDir, setSortDir] = useState('desc')

  useEffect(() => {
    fetchAPI('/trades?limit=500&min_date=2025-01-01', 120_000)
      .then(d => { setAllTrades(Array.isArray(d) ? d : []); setLoading(false) })
      .catch(e => { setErr(e.message); setLoading(false) })
  }, [])

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const sorted = [...allTrades]
    .filter(t => !showOpenOnly || !t.exit_date)
    .filter(t => filter ? t.ticker?.includes(filter.toUpperCase()) : true)
    .sort((a, b) => {
      const aVal = a[sortKey] ?? ''
      const bVal = b[sortKey] ?? ''
      const cmp = String(aVal).localeCompare(String(bVal), 'en', { numeric: true })
      return sortDir === 'asc' ? cmp : -cmp
    })
    .slice(0, limit)

  const filtered = sorted
  const allFiltered = allTrades
  const wins = allFiltered.filter((t:any) => t.pnl > 0)
  const losses = allFiltered.filter((t:any) => t.pnl <= 0)

  function SortHeader({ label, k }: { label: string; k: string }) {
    return (
      <th className="text-left py-2 cursor-pointer hover:text-foreground select-none" onClick={() => toggleSort(k)}>
        <span className="flex items-center gap-1">
          {label}
          {sortKey === k && (sortDir === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />)}
        </span>
      </th>
    )
  }

  if (err) return <div className="card text-sell">{err}</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Lịch sử giao dịch</h1>
        <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Lọc theo mã..." className="input-field w-40" />
      </div>

      {loading ? <LoadingSkeleton /> : <>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <StatsCard label="Tổng GD" value={String(allFiltered.length)} />
          <StatsCard label="Win Rate" value={`${allFiltered.length ? (wins.length/allFiltered.length*100).toFixed(1) : '0'}%`} className="text-buy" />
          <StatsCard label="Lãi TB" value={wins.length ? fmtPct(wins.reduce((s:number,t:any)=>s+t.pnl_pct,0)/wins.length) : '-'} className="text-buy" />
          <StatsCard label="Lỗ TB" value={losses.length ? fmtPct(losses.reduce((s:number,t:any)=>s+t.pnl_pct,0)/losses.length) : '-'} className="text-sell" />
          <StatsCard label="Ngày TB" value={allFiltered.length ? `${(allFiltered.reduce((s:number,t:any)=>s+(t.days_held||0),0)/allFiltered.length).toFixed(0)}d` : '0d'} />
        </div>

        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {LIMIT_OPTIONS.map(l => (
              <button key={l} onClick={() => setLimit(l)} className={`btn btn-sm ${limit === l ? 'btn-primary' : 'btn-outline'}`}>{l}</button>
            ))}
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={showOpenOnly} onChange={e => setShowOpenOnly(e.target.checked)} className="accent-primary" />
              Chỉ lệnh đang mở
            </label>
          </div>
          <span className="text-sm text-muted-foreground">{sorted.length} giao dịch</span>
        </div>

        <div className="card">
          {filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground border-b border-border">
                    <SortHeader label="Vào" k="entry_date" />
                    <SortHeader label="Ra" k="exit_date" />
                    <SortHeader label="Mã" k="ticker" />
                    <SortHeader label="Giá vào" k="entry_price" />
                    <SortHeader label="Giá ra" k="exit_price" />
                    <th className="text-right py-2">PnL</th>
                    <th className="text-center py-2">Lý do</th>
                    <SortHeader label="Ngày" k="days_held" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t: any, i: number) => {
                    const isOpen = !t.exit_date
                    return (
                      <tr key={i} className={`border-b border-border/50 hover:bg-secondary/30 ${isOpen ? 'bg-primary/5' : ''}`}>
                        <td className="py-2 text-xs text-muted-foreground">{t.entry_date}</td>
                        <td className="py-2 text-xs text-muted-foreground">{t.exit_date || <span className="text-buy">Đang mở</span>}</td>
                        <td className="py-2 font-medium">{t.ticker}</td>
                        <td className="py-2 text-right">{fmt(t.entry_price)}</td>
                        <td className="py-2 text-right">{t.exit_price ? fmt(t.exit_price) : '-'}</td>
                        <td className={`py-2 text-right font-medium ${t.pnl >= 0 ? 'text-buy' : 'text-sell'}`}>
                          <span className="flex items-center justify-end gap-1">
                            {t.pnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                            {t.pnl_pct != null ? fmtPct(t.pnl_pct) : '-'}
                          </span>
                        </td>
                        <td className="py-2 text-center">
                          <span className={`badge ${EXIT_REASON_COLORS[t.exit_reason] || 'badge-neutral'}`}>
                            {EXIT_REASON_LABELS[t.exit_reason] || t.exit_reason}
                          </span>
                        </td>
                        <td className="py-2 text-center text-xs text-muted-foreground">{t.days_held || '-'}d</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="text-muted-foreground">Không có giao dịch nào</p>}
        </div>
      </>}
    </div>
  )
}

function StatsCard({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="card">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-xl font-bold ${className || ''}`}>{value}</div>
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
