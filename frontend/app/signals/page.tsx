'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, fmt, fmtPct } from '@/lib/api'
import { TrendingUp, TrendingDown, AlertTriangle, Info, BarChart3 } from 'lucide-react'
import CandlestickChart from '@/components/CandlestickChart'

export default function SignalsPage() {
  const [signalData, setSignalData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [detail, setDetail] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    fetchAPI('/signals/entry', 60_000).then(d => { setSignalData(d); setLoading(false) }).catch(e => { setErr(e.message); setLoading(false) })
  }, [])

  useEffect(() => {
    if (detail) { setDetailLoading(true); fetchAPI(`/signals/entry/${detail}`).then(d => { setDetailData(d); setDetailLoading(false) }) }
  }, [detail])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Tín hiệu giao dịch</h1>
      <p className="text-muted-foreground text-sm">Các mã chứng khoán đủ điều kiện mua theo chiến lược</p>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Entry signals list */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Entry Signals</h2>
            <span className="badge-buy">{signalData?.signals_count || 0} signals</span>
          </div>
          {err ? <p className="text-sell">{err}</p> :
           loading ? <div className="animate-pulse space-y-3">{[...Array(5)].map((_,i) => <div key={i} className="h-10 rounded-lg bg-secondary/20" />)}</div> :
           signalData?.signals?.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-muted-foreground border-b border-border">
                      <th className="text-left py-2">Mã</th>
                      <th className="text-left py-2">Ngành</th>
                      <th className="text-right py-2">Giá</th>
                      <th className="text-right py-2">EMA20</th>
                      <th className="text-right py-2">EMA200</th>
                      <th className="text-right py-2">RSI</th>
                      <th className="text-right py-2">Vol</th>
                      <th className="text-center py-2">Chart</th>
                    </tr>
                  </thead>
                  <tbody>
                    {signalData.signals.map((s: any) => (
                      <tr key={s.ticker} className="border-b border-border/50 hover:bg-secondary/30 cursor-pointer" onClick={() => setDetail(detail === s.ticker ? null : s.ticker)}>
                        <td className="py-2 font-medium text-buy">{s.ticker}</td>
                        <td className="py-2 text-muted-foreground">{s.sector}</td>
                        <td className="py-2 text-right">{fmt(s.price)}</td>
                        <td className="py-2 text-right">{fmt(Math.round(s.ema20))}</td>
                        <td className="py-2 text-right">{fmt(Math.round(s.ema200))}</td>
                        <td className="py-2 text-right">{s.rsi14?.toFixed(0) || '-'}</td>
                        <td className="py-2 text-right">{s.vol_ratio?.toFixed(1) || '-'}x</td>
                        <td className="py-2 text-center">
                          <BarChart3 size={16} className={`inline-block ${detail === s.ticker ? 'text-primary' : 'text-muted-foreground'}`} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-muted-foreground">Không có tín hiệu entry hôm nay</p>}
        </div>

        {/* Signal detail panel */}
        <div className="lg:col-span-3 card">
          {detail ? (
            detailLoading ? <div className="animate-pulse space-y-4"><div className="h-8 bg-secondary/20 rounded w-32" /><div className="h-64 bg-secondary/20 rounded" /><div className="grid grid-cols-5 gap-2">{[...Array(5)].map((_,i) => <div key={i} className="h-16 bg-secondary/20 rounded" />)}</div></div> :
            detailData ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">{detail}</h2>
                  <span className="badge-buy">{detailData.sector}</span>
                </div>

                {/* Candlestick chart */}
                {detailData.recent_bars && (
                  <div className="rounded-lg bg-secondary/20 p-3">
                    <div className="flex items-center gap-2 mb-2 text-xs text-muted-foreground">
                      <BarChart3 size={14} />
                      <span>120 phiên gần nhất</span>
                    </div>
                    <CandlestickChart data={detailData.recent_bars} height={280} />
                  </div>
                )}

                {/* Stats grid */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  <InfoItem label="Giá" value={fmt(detailData.close)} />
                  <InfoItem label="EMA20" value={fmt(Math.round(detailData.ema20))} />
                  <InfoItem label="EMA50" value={fmt(Math.round(detailData.ema50))} />
                  <InfoItem label="EMA200" value={fmt(Math.round(detailData.ema200))} />
                  <InfoItem label="RSI(14)" value={detailData.rsi14?.toFixed(1) || 'N/A'} />
                  <InfoItem label="Vol Ratio" value={detailData.vol_ratio?.toFixed(2) || 'N/A'} />
                  <InfoItem label="ATR(14)" value={detailData.atr14?.toFixed(0) || 'N/A'} />
                  <InfoItem label="Bullish" value={detailData.bullish ? '✅' : '❌'} />
                  <InfoItem label="Signal" value={detailData.signal ? '✅ BUY' : '❌'} />
                </div>

                {/* Distance to EMAs */}
                <div className="grid grid-cols-3 gap-2">
                  <DistanceBadge label="vs EMA20" value={(detailData.close/detailData.ema20-1)*100} />
                  <DistanceBadge label="vs EMA50" value={(detailData.close/detailData.ema50-1)*100} />
                  <DistanceBadge label="vs EMA200" value={(detailData.close/detailData.ema200-1)*100} />
                </div>
              </div>
            ) : <p className="text-sell">Không có dữ liệu</p>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
              <BarChart3 size={48} className="mb-4 opacity-30" />
              <p>Chọn một mã để xem biểu đồ nến</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-2 rounded-lg bg-secondary/30">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  )
}

function DistanceBadge({ label, value }: { label: string; value: number }) {
  const isPositive = value >= 0
  return (
    <div className="p-2 rounded-lg bg-secondary/30 text-center">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-sm font-medium ${isPositive ? 'text-buy' : 'text-sell'}`}>
        {fmtPct(value)}
      </div>
    </div>
  )
}
