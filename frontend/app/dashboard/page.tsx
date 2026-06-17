'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, fmt } from '@/lib/api'
import { DollarSign, Activity, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'
import Link from 'next/link'

export default function DashboardPage() {
  const [data, setData] = useState<any>(null)
  const [signals, setSignals] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAPI('/dashboard', 60_000).then(d => { setData(d); setLoading(false) }).catch(() => setLoading(false))
    fetchAPI('/signals/entry', 60_000).then(setSignals).catch(() => {})
  }, [])

  if (loading) return <LoadingSkeleton />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <span className="text-sm text-muted-foreground">VN100 · {data?.active_tickers || 0} mã</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard icon={<DollarSign size={20} />} label="Initial Capital" value={`${fmt(data?.initial_capital)} VND`} sub="Số vốn ban đầu" />
        <KPICard icon={<Activity size={20} />} label="Dữ liệu" value={`${fmt(data?.total_bars)} bars`} sub={`${data?.last_data_date || ''}`} />
        <KPICard icon={<TrendingUp size={20} />} label="Cấu hình" value={`${data?.max_positions} positions`} sub={`${(data?.entry_frac*100) || 7}% per entry`} />
        <KPICard icon={<AlertTriangle size={20} />} label="Stop Loss" value={`${(data?.stop_loss*100) || 15}% fixed`} sub={`Trail ${(data?.trail_pct*100) || 10}%`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Signals - lazy load */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Tín hiệu Entry hôm nay</h2>
            <div className="flex items-center gap-2">
              {signals && <span className="badge-buy">{signals.signals_count} signals</span>}
              <Link href="/signals" className="text-xs text-primary hover:underline">Xem tất cả →</Link>
            </div>
          </div>
          {signals ? (
            signals.signals_count > 0 ? (
              <div className="space-y-2">
                {signals.signals.slice(0, 7).map((s: any) => (
                  <div key={s.ticker} className="flex items-center justify-between p-2 rounded-lg bg-secondary/50">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-buy text-sm">{s.ticker}</span>
                      <span className="text-xs text-muted-foreground">{s.sector}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span>{fmt(s.price)}</span>
                      {s.vol_ratio && <span className={s.vol_ratio > 1 ? 'text-buy' : 'text-muted-foreground'}>V: {s.vol_ratio.toFixed(1)}x</span>}
                    </div>
                  </div>
                ))}
                {signals.signals.length > 7 && <p className="text-xs text-muted-foreground">+{signals.signals.length - 7} mã khác</p>}
              </div>
            ) : <p className="text-muted-foreground text-sm">Không có tín hiệu entry hôm nay</p>
          ) : (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => <div key={i} className="h-8 rounded-lg bg-secondary/30 animate-pulse" />)}
            </div>
          )}
        </div>

        {/* Strategy */}
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Chiến lược</h2>
          <div className="space-y-2">
            {[
              { label: 'Entry', cond: 'Close > EMA20 > EMA200 & EMA50 > EMA200' },
              { label: 'Volume', cond: 'Vol > 20-day MA (x1.0)' },
              { label: 'Candle', cond: 'Bullish body ≥ 40% dải giá' },
              { label: 'Stop Loss', cond: '15% cố định hoặc 10% trailing' },
              { label: 'Khác', cond: 'Max 7 vị thế, 20%/ngành' },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-3 text-sm p-1.5 rounded hover:bg-secondary/20">
                <span className="badge-buy min-w-16 text-center">{s.label}</span>
                <span className="text-muted-foreground">{s.cond}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Backtest Summary */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">Backtest (2021-01 → 2026-06)</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {[
            { l: 'CAGR', v: '27.15%', c: 'text-buy' },
            { l: 'Total Return', v: '+270.09%', c: 'text-buy' },
            { l: 'Max DD', v: '-14.20%', c: 'text-sell' },
            { l: 'Sharpe', v: '1.88', c: 'text-buy' },
            { l: 'Win Rate', v: '41.8%', c: 'text-buy' },
            { l: 'Profit Factor', v: '2.04', c: 'text-buy' },
            { l: 'Trades', v: '753', c: '' },
          ].map((s) => (
            <div key={s.l} className="text-center p-3 rounded-lg bg-secondary/30">
              <div className="text-xs text-muted-foreground mb-1">{s.l}</div>
              <div className={`text-lg font-bold ${s.c}`}>{s.v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function KPICard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub: string }) {
  return (
    <div className="card">
      <div className="flex items-center gap-2 text-muted-foreground mb-2">
        {icon}
        <span className="text-sm">{label}</span>
      </div>
      <div className="text-xl font-bold mb-1">{value}</div>
      <div className="text-xs text-muted-foreground">{sub}</div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="rounded-xl border border-border bg-secondary/20 h-24" />)}
      </div>
      <div className="grid grid-cols-2 gap-6">
        <div className="rounded-xl border border-border bg-secondary/20 h-48" />
        <div className="rounded-xl border border-border bg-secondary/20 h-48" />
      </div>
      <div className="rounded-xl border border-border bg-secondary/20 h-32" />
    </div>
  )
}
