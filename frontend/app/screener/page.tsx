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
  const [view, setView] = useState<'current' | 'codex'>('current')
  const [filters, setFilters] = useState<any>({
    trend: 'all', rsi_min: 0, rsi_max: 100,
    candle: 'all', sector: 'all', price_min: 0, price_max: 1000000,
    signal: 'all', reversal: 'all', trend_label: 'all', codex_score: 'all',
  })

  const search = async () => {
    setLoading(true); setErr('')
    try {
      const params = new URLSearchParams()
      Object.entries(filters).forEach(([k,v]) => {
        if (v !== '' && v !== 'all') params.set(k, String(v))
      })
      if (view === 'codex') {
        const cs = filters.codex_score
        if (cs === 'gte_80') params.set('codex_score_min', '80')
        else if (cs === 'gte_65') params.set('codex_score_min', '65')
        else if (cs === 'gte_50') params.set('codex_score_min', '50')
        else if (cs === 'lt_50') params.set('codex_score_max', '49')
      }
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
      if (['change_pct','price','rsi14','vol_ratio','codex_score','codex_rs_score','codex_rr'].includes(sortKey)) {
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

  const revFilter = filters.reversal
  const reversedRows = sorted.filter((r: any) =>
    view === 'codex' ? r.codex_reversal : r.reversal
  )
  const signalRows = sorted.filter((r: any) => r.signal)
  const codexRows = sorted.filter((r: any) => r.codex_signal)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Bộ lọc cổ phiếu</h1>
        <span className="text-sm text-muted-foreground">{data?.count || 0} kết quả</span>
      </div>

      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <button onClick={() => setView('current')} className={`btn btn-sm ${view === 'current' ? 'btn-primary' : ''}`}>Chiến lược hiện tại</button>
          <button onClick={() => setView('codex')} className={`btn btn-sm ${view === 'codex' ? 'btn-primary' : ''}`}>Codex Advise</button>
        </div>
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
          {view === 'codex' && (
            <FilterSelect label="Codex Score" value={filters.codex_score || 'all'} onChange={(v) => setFilters({...filters, codex_score: v})}
              options={[{v:'all',l:'Tất cả'},{v:'gte_80',l:'≥ 80 (mạnh)'},{v:'gte_65',l:'≥ 65 (tốt)'},{v:'gte_50',l:'≥ 50 (theo dõi)'},{v:'lt_50',l:'< 50 (bỏ qua)'}]} />
          )}
          <FilterInput label="RSI Min" value={filters.rsi_min} onChange={(v) => setFilters({...filters, rsi_min: v})} />
          <FilterInput label="RSI Max" value={filters.rsi_max} onChange={(v) => setFilters({...filters, rsi_max: v})} />
          <div className="flex items-end">
            <button onClick={search} disabled={loading} className="btn btn-primary w-full flex items-center justify-center gap-2">
              <Search size={16} /> {loading ? 'Đang lọc...' : 'Lọc'}
            </button>
          </div>
        </div>
      </div>

      {view === 'codex' && (
        <div className="card bg-green-500/5 border border-green-500/20">
          <p className="text-sm font-medium mb-2">📊 Codex Advise:
            <span className="text-buy font-bold"> {sorted.filter((r:any)=>r.codex_score>=80).length} mạnh</span>
            <span className="text-buy"> · {sorted.filter((r:any)=>r.codex_score>=65&&r.codex_score<80).length} tốt</span>
            <span className="text-muted-foreground"> · {sorted.filter((r:any)=>r.codex_score>=50&&r.codex_score<65).length} theo dõi</span>
            <span className="text-sell"> · {sorted.filter((r:any)=>r.codex_score<50).length} bỏ qua</span>
            {codexRows.length > 0 && <span className="text-buy ml-3">· {codexRows.length} mua</span>}
          </p>
          {codexRows.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {codexRows.map((r: any) => (
                <span key={r.ticker} className="text-xs px-2 py-1 rounded bg-buy/10 text-buy">
                  {r.ticker} ({r.codex_score})
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {reversedRows.length > 0 && (
        <div className="card bg-yellow-500/5 border border-yellow-500/20">
          <p className="text-sm font-medium mb-2">⚠ Tín hiệu đảo chiều ({reversedRows.length} mã):</p>
          <div className="flex flex-wrap gap-2">
            {reversedRows.map((r: any) => {
              const rev = view === 'codex' ? r.codex_reversal : r.reversal
              return (
              <span key={r.ticker} className={`text-xs px-2 py-1 rounded ${rev === 'Bullish' ? 'bg-buy/10 text-buy' : 'bg-sell/10 text-sell'}`}>
                {r.ticker} {rev === 'Bullish' ? '🟢' : '🔴'}
              </span>
            )})}
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
                    <Hdr k="rsi14">RSI</Hdr>
                    {view === 'current' ? (
                      <>
                        <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('trend')}>Xu hướng <SortIcon k="trend" /></th>
                        <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('reversal')}>Đảo chiều <SortIcon k="reversal" /></th>
                        <Hdr k="pct_ema20">EMA20</Hdr>
                        <Hdr k="pct_ema50">EMA50</Hdr>
                        <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('signal')}>Signal <SortIcon k="signal" /></th>
                      </>
                      ) : (
                        <>
                          <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('codex_trend')}>C.Xu hướng <SortIcon k="codex_trend" /></th>
                          <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('codex_reversal')}>C.Đảo chiều <SortIcon k="codex_reversal" /></th>
                          <Hdr k="codex_score">Codex</Hdr>
                          <Hdr k="codex_rs_score">RS</Hdr>
                          <Hdr k="codex_rr">R:R</Hdr>
                          <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('codex_eligible')}>Elig <SortIcon k="codex_eligible" /></th>
                          <th className="text-center py-2 cursor-pointer select-none hover:text-foreground" onClick={() => toggleSort('codex_signal')}>C.Advise <SortIcon k="codex_signal" /></th>
                        </>
                      )}
                    <th className="text-center py-2">Chart</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((r: any) => {
                    const sig = view === 'current' ? r.signal : r.codex_signal
                    return (
                    <tr key={r.ticker} className={`border-b border-border/50 hover:bg-secondary/30 ${sig ? 'bg-buy/5' : ''}`}>
                      <td className="py-2"><input type="checkbox" checked={selected.has(r.ticker)} onChange={() => toggleSelect(r.ticker)} className="w-4 h-4" /></td>
                      <td className={`py-2 font-medium ${sig ? 'text-buy' : ''}`}>{r.ticker}</td>
                      <td className="py-2 text-muted-foreground">{r.sector}</td>
                      <td className="py-2 text-right">{fmt(r.price)}</td>
                      <td className={`py-2 text-right ${r.change_pct != null ? (r.change_pct > 0 ? 'text-buy' : 'text-sell') : ''}`}>{r.change_pct != null ? fmtPct(r.change_pct) : '-'}</td>
                      <td className="py-2 text-right">{r.rsi14?.toFixed(0) || '-'}</td>
                      {view === 'current' ? (
                        <>
                          <td className="py-2 text-center">{trendBadge(r.trend)}</td>
                          <td className="py-2 text-center">{r.reversal ? <span className={r.reversal === 'Bullish' ? 'text-buy' : 'text-sell'}>{r.reversal === 'Bullish' ? '🟢' : '🔴'} {r.reversal}</span> : '-'}</td>
                          <td className={`py-2 text-right ${r.pct_ema20 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema20)}</td>
                          <td className={`py-2 text-right ${r.pct_ema50 > 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(r.pct_ema50)}</td>
                          <td className="py-2 text-center">{r.signal ? <span className="badge-buy">BUY</span> : '-'}</td>
                        </>
                      ) : (
                        <>
                          <td className="py-2 text-center">{trendBadge(r.codex_trend)}</td>
                          <td className="py-2 text-center">{r.codex_reversal ? <span className={r.codex_reversal === 'Bullish' ? 'text-buy' : 'text-sell'}>{r.codex_reversal === 'Bullish' ? '🟢' : '🔴'} {r.codex_reversal}</span> : '-'}</td>
                          <td className="py-2 text-right">{codexBadge(r.codex_score)}</td>
                          <td className="py-2 text-right">{r.codex_rs_score || 0}</td>
                          <td className="py-2 text-right">{(r.codex_rr || 1).toFixed(1)}</td>
                          <td className="py-2 text-center">{r.codex_eligible ? <span className="text-buy">✓</span> : '-'}</td>
                          <td className="py-2 text-center">{r.codex_signal ? <span className="badge-buy">BUY</span> : '-'}</td>
                        </>
                      )}
                      <td className="py-2 text-center">
                        <a href={`https://www.tradingview.com/chart/?symbol=HOSE:${r.ticker}`} target="_blank" rel="noopener noreferrer" className="btn btn-sm">Mở</a>
                      </td>
                    </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : <p className="text-muted-foreground">Không có kết quả</p>}
      </div>
    </div>
  )
}

function codexBadge(score: number) {
  if (!score) return <span className="text-muted-foreground">0</span>
  if (score >= 80) return <span className="text-buy font-bold">{score}</span>
  if (score >= 65) return <span className="text-buy">{score}</span>
  if (score >= 50) return <span className="text-muted-foreground">{score}</span>
  return <span className="text-sell">{score}</span>
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
