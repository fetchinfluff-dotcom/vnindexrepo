'use client'
import { useEffect, useState, useMemo } from 'react'
import { fetchAPI, postAPI, fmt, fmtPct } from '@/lib/api'
import { Search, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'

const SECTORS = ['all','Banking','RealEstate','Construction','Securities','SteelLogistics','Retail','Tech','FoodBeverage','Energy','Chemicals','Others']

type SortDir = 'asc' | 'desc'
type SortKey = string

export default function ScreenerPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('ticker')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [watchlistName, setWatchlistName] = useState('default')
  const [filters, setFilters] = useState({
    trend: 'all', rsi_min: 0, rsi_max: 100,
    candle: 'all', sector: 'all', price_min: 0, price_max: 1000000,
    signal: 'all', reversal: 'all', trend_label: 'all',
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

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const sorted = useMemo(() => {
    if (!data?.results) return []
    const arr = [...data.results]
    arr.sort((a: any, b: any) => {
      let av = a[sortKey], bv = b[sortKey]
      if (sortKey === 'change_pct' || sortKey === 'price' || sortKey === 'rsi14' || sortKey === 'vol_ratio') {
        av = Number(av) || 0; bv = Number(bv) || 0
      } else {
        av = String(av || ''); bv = String(bv || '')
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return arr
  }, [data, sortKey, sortDir])

  const toggleSelect = (ticker: string) => {
    const next = new Set(selected)
    if (next.has(ticker)) next.delete(ticker); else next.add(ticker)
    setSelected(next)
  }

  const toggleAll = () => {
    if (selected.size === sorted.length) setSelected(new Set())
    else setSelected(new Set(sorted.map((r: any) => r.ticker)))
  }

  const addToWatchlist = async () => {
    if (!selected.size) return
    try {
      const tickers = Array.from(selected)
      await Promise.all(tickers.map(t => postAPI('/watchlist', { ticker: t, list_name: watchlistName })))
      setSelected(new Set())
      alert(`Đã thêm ${selected.size} mã vào danh mục "${watchlistName}"`)
    } catch (e: any) { alert('Lỗi: ' + e.message) }
  }

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ArrowUpDown size={12} className="inline ml-1 opacity-30" />
    return sortDir === 'asc' ? <ArrowUp size={12} className="inline ml-1" /> : <ArrowDown size={12} className="inline ml-1" />
  }

  function Hdr({ k, children }: { k: SortKey; children: React.ReactNode }) {
    return (
      <th className="text-right py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort(k)}>
        {children} <SortIcon k={k} />
      </th>
    )
  }

  const reversedRows = sorted.filter((r: any) => r.reversal)
  const signalRows = sorted.filter((r: any) => r.signal)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Bộ lọc cổ phiếu</h1>
        <span className="text-sm text-muted-foreground">{data?.count || 0} kết quả</span>
      </div>

      <div className="card">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          <FilterSelect label="Xu hướng EMA" value={filters.trend} onChange={(v) => setFilters({...filters, trend: v})}
            options={[
              {v:'all',l:'Tất cả'},{v:'above_ema20',l:'Trên EMA20'},{v:'above_ema50',l:'Trên EMA50'},{v:'above_ema200',l:'Trên EMA200'}
            ]} />
          <FilterSelect label="Nến" value={filters.candle} onChange={(v) => setFilters({...filters, candle: v})}
            options={[{v:'all',l:'Tất cả'},{v:'bullish',l:'Bullish'},{v:'bearish',l:'Bearish'}]} />
          <FilterSelect label="Ngành" value={filters.sector} onChange={(v) => setFilters({...filters, sector: v})}
            options={SECTORS.map(s => ({v:s, l: s === 'all' ? 'Tất cả' : s}))} />
          <FilterSelect label="Signal" value={filters.signal} onChange={(v) => setFilters({...filters, signal: v})}
            options={[{v:'all',l:'Tất cả'},{v:'has_signal',l:'Có signal'},{v:'no_signal',l:'Không signal'}]} />
          <FilterSelect label="Đảo chiều" value={filters.reversal} onChange={(v) => setFilters({...filters, reversal: v})}
            options={[{v:'all',l:'Tất cả'},{v:'bullish',l:'Bullish'},{v:'bearish',l:'Bearish'}]} />
          <FilterInput label="RSI Min" value={filters.rsi_min} onChange={(v) => setFilters({...filters, rsi_min: v})} />
          <FilterInput label="RSI Max" value={filters.rsi_max} onChange={(v) => setFilters({...filters, rsi_max: v})} />
          <div className="flex items-end">
            <button onClick={search} disabled={loading} className="btn btn-primary w-full flex items-center justify-center gap-2">
              <Search size={16} /> {loading ? 'Đang lọc...' : 'Lọc'}
            </button>
          </div>
        </div>
      </div>

      {reversedRows.length > 0 && (
        <div className="card bg-yellow-500/5 border border-yellow-500/20">
          <p className="text-sm font-medium mb-2">⚠ Cổ phiếu có tín hiệu đảo chiều ({reversedRows.length} mã):</p>
          <div className="flex flex-wrap gap-2">
            {reversedRows.map((r: any) => (
              <span key={r.ticker} className={`text-xs px-2 py-1 rounded ${r.reversal === 'Bullish' ? 'bg-buy/10 text-buy' : 'bg-sell/10 text-sell'}`}>
                {r.ticker} {r.reversal === 'Bullish' ? '🟢' : '🔴'}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        {err ? <p className="text-sell">{err}</p> :
         loading ? <div className="animate-pulse space-y-3">{[...Array(8)].map((_,i) => <div key={i} className="h-10 rounded-lg bg-secondary/30" />)}</div> :
         sorted.length > 0 ? (
          <>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <input type="checkbox" checked={selected.size === sorted.length && sorted.length > 0} onChange={toggleAll} className="w-4 h-4" />
                <span className="text-xs text-muted-foreground">Chọn tất cả ({selected.size} đã chọn)</span>
              </div>
              <div className="flex items-center gap-2">
                <input type="text" value={watchlistName} onChange={e => setWatchlistName(e.target.value)} placeholder="Tên danh mục" className="input-field text-sm w-32" />
                <button onClick={addToWatchlist} disabled={!selected.size} className="btn btn-sm btn-primary">+ Thêm vào danh mục</button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground border-b border-border">
                    <th className="py-2 w-8"><input type="checkbox" checked={selected.size === sorted.length && sorted.length > 0} onChange={toggleAll} className="w-4 h-4" /></th>
                    <th className="text-left py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('ticker')}>Mã <SortIcon k="ticker" /></th>
                    <th className="text-left py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('sector')}>Ngành <SortIcon k="sector" /></th>
                    <Hdr k="price">Giá</Hdr>
                    <Hdr k="change_pct">% Change</Hdr>
                    <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('trend')}>Xu hướng <SortIcon k="trend" /></th>
                    <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('reversal')}>Đảo chiều <SortIcon k="reversal" /></th>
                    <Hdr k="pct_ema20">EMA20</Hdr>
                    <Hdr k="pct_ema50">EMA50</Hdr>
                    <Hdr k="pct_ema200">EMA200</Hdr>
                    <Hdr k="rsi14">RSI</Hdr>
                    <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('signal')}>Signal <SortIcon k="signal" /></th>
                    <th className="text-center py-2">Chart</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((r: any) => (
                    <tr key={r.ticker} className={`border-b border-border/50 hover:bg-secondary/30 ${r.signal ? 'bg-buy/5' : ''}`}>
                      <td className="py-2"><input type="checkbox" checked={selected.has(r.ticker)} onChange={() => toggleSelect(r.ticker)} className="w-4 h-4" /></td>
                      <td className={`py-2 font-medium ${r.signal ? 'text-buy' : ''}`}>{r.ticker}</td>
                      <td className="py-2 text-muted-foreground">{r.sector}</td>
                      <td className="py-2 text-right">{fmt(r.price)}</td>
                      <td className={`py-2 text-right ${r.change_pct != null ? (r.change_pct > 0 ? 'text-buy' : 'text-sell') : ''}`}>{r.change_pct != null ? fmtPct(r.change_pct) : '-'}</td>
                      <td className="py-2 text-center">{trendBadge(r.trend)}</td>
                      <td className="py-2 text-center">{r.reversal ? <span className={r.reversal === 'Bullish' ? 'text-buy' : 'text-sell'}>{r.reversal === 'Bullish' ? '🟢' : '🔴'} {r.reversal}</span> : '-'}</td>
                      <td className={`py-2 text-right ${r.pct_ema20 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema20)}</td>
                      <td className={`py-2 text-right ${r.pct_ema50 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema50)}</td>
                      <td className={`py-2 text-right ${r.pct_ema200 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema200)}</td>
                      <td className="py-2 text-right">{r.rsi14?.toFixed(0) || '-'}</td>
                      <td className="py-2 text-center">{r.signal ? <span className="badge-buy">BUY</span> : '-'}</td>
                      <td className="py-2 text-center">
                        <a href={`https://www.tradingview.com/chart/?symbol=HOSE:${r.ticker}`} target="_blank" rel="noopener noreferrer" className="btn btn-sm">Mở</a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : <p className="text-muted-foreground">Không có kết quả</p>}
      </div>
    </div>
  )
}

function trendBadge(trend: string) {
  const colors: Record<string, string> = {
    'Mạnh': 'text-buy font-bold',
    'Tăng': 'text-buy',
    'Đi ngang': 'text-muted-foreground',
    'Giảm': 'text-sell',
    'Giảm mạnh': 'text-sell font-bold',
  }
  return <span className={colors[trend] || ''}>{trend}</span>
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
