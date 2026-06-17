'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, fmt, fmtPct } from '@/lib/api'
import { Search } from 'lucide-react'

const SECTORS = ['all','Banking','RealEstate','Construction','Securities','SteelLogistics','Retail','Tech','FoodBeverage','Energy','Chemicals','Others']

export default function ScreenerPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [filters, setFilters] = useState({
    trend: 'all', vol_ratio_min: 0, rsi_min: 0, rsi_max: 100,
    candle: 'all', sector: 'all', price_min: 0, price_max: 1000000,
  })

  const search = async () => {
    setLoading(true); setErr('')
    try {
      const params = new URLSearchParams()
      Object.entries(filters).forEach(([k,v]) => params.set(k, String(v)))
      const res = await fetchAPI(`/screener?${params}`)
      setData(res)
    } catch (e: any) { setErr(e.message) }
    setLoading(false)
  }

  useEffect(() => { search() }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Bộ lọc cổ phiếu</h1>
        <span className="text-sm text-muted-foreground">{data?.count || 0} kết quả</span>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <FilterSelect label="Xu hướng" value={filters.trend} onChange={(v) => setFilters({...filters, trend: v})}
            options={[
              {v:'all',l:'Tất cả'},{v:'above_ema20',l:'Trên EMA20'},{v:'above_ema50',l:'Trên EMA50'},{v:'above_ema200',l:'Trên EMA200'}
            ]} />
          <FilterSelect label="Nến" value={filters.candle} onChange={(v) => setFilters({...filters, candle: v})}
            options={[{v:'all',l:'Tất cả'},{v:'bullish',l:'Bullish'},{v:'bearish',l:'Bearish'}]} />
          <FilterSelect label="Ngành" value={filters.sector} onChange={(v) => setFilters({...filters, sector: v})}
            options={SECTORS.map(s => ({v:s, l: s === 'all' ? 'Tất cả' : s}))} />
          <FilterInput label="Vol Min" value={filters.vol_ratio_min} onChange={(v) => setFilters({...filters, vol_ratio_min: v})} />
          <FilterInput label="RSI Min" value={filters.rsi_min} onChange={(v) => setFilters({...filters, rsi_min: v})} />
          <FilterInput label="RSI Max" value={filters.rsi_max} onChange={(v) => setFilters({...filters, rsi_max: v})} />
          <div className="flex items-end">
            <button onClick={search} disabled={loading} className="btn btn-primary w-full flex items-center justify-center gap-2">
              <Search size={16} /> {loading ? 'Đang lọc...' : 'Lọc'}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="card">
        {err ? <p className="text-sell">{err}</p> :
         loading ? <div className="animate-pulse space-y-3">{[...Array(8)].map((_,i) => <div key={i} className="h-10 rounded-lg bg-secondary/30" />)}</div> :
         data?.results?.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground border-b border-border">
                  <th className="text-left py-2">Mã</th>
                  <th className="text-left py-2">Ngành</th>
                  <th className="text-right py-2">Giá</th>
                  <th className="text-right py-2">EMA20</th>
                  <th className="text-right py-2">EMA50</th>
                  <th className="text-right py-2">EMA200</th>
                  <th className="text-right py-2">RSI</th>
                  <th className="text-right py-2">Vol</th>
                  <th className="text-center py-2">Nến</th>
                  <th className="text-center py-2">Signal</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((r: any) => (
                  <tr key={r.ticker} className={`border-b border-border/50 hover:bg-secondary/30 ${r.signal ? 'bg-buy/5' : ''}`}>
                    <td className={`py-2 font-medium ${r.signal ? 'text-buy' : ''}`}>{r.ticker}</td>
                    <td className="py-2 text-muted-foreground">{r.sector}</td>
                    <td className="py-2 text-right">{fmt(r.price)}</td>
                    <td className={`py-2 text-right ${r.pct_ema20 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema20)}</td>
                    <td className={`py-2 text-right ${r.pct_ema50 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema50)}</td>
                    <td className={`py-2 text-right ${r.pct_ema200 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema200)}</td>
                    <td className="py-2 text-right">{r.rsi14?.toFixed(0) || '-'}</td>
                    <td className="py-2 text-right">{r.vol_ratio?.toFixed(1) || '-'}x</td>
                    <td className="py-2 text-center">{r.bullish ? '🟢' : '🔴'}</td>
                    <td className="py-2 text-center">{r.signal ? <span className="badge-buy">BUY</span> : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-muted-foreground">Không có kết quả</p>}
      </div>
    </div>
  )
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: {v:string;l:string}[] }) {
  return (
    <div>
      <label className="text-xs text-muted-foreground mb-1 block">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="input-field w-full">
        {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  )
}

function FilterInput({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <label className="text-xs text-muted-foreground mb-1 block">{label}</label>
      <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} className="input-field w-full" />
    </div>
  )
}
