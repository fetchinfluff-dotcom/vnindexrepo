import { NextRequest, NextResponse } from 'next/server'

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || ''
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY
const SUPABASE_ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''

const REST_URL = `${SUPABASE_URL}/rest/v1`
const HEADERS: Record<string, string> = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
}
if (SUPABASE_KEY) HEADERS['Authorization'] = `Bearer ${SUPABASE_KEY}`
if (SUPABASE_ANON) HEADERS['apikey'] = SUPABASE_ANON

async function restGet(table: string, params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString()
  const res = await fetch(`${REST_URL}/${table}${qs ? '?' + qs : ''}`, { headers: HEADERS })
  if (!res.ok) throw new Error(`DB ${res.status}: ${await res.text()}`)
  return res.json()
}

async function restCount(table: string, filter: string = '') {
  const h = { ...HEADERS, 'Prefer': 'count=exact' }
  const url = `${REST_URL}/${table}?select=ticker&limit=1${filter ? '&' + filter : ''}`
  const res = await fetch(url, { headers: h })
  if (!res.ok) throw new Error(`DB ${res.status}: ${await res.text()}`)
  const range = res.headers.get('content-range') || ''
  const match = range.match(/\/(\d+)$/)
  return match ? parseInt(match[1], 10) : 0
}

async function restPost(table: string, body: any) {
  const res = await fetch(`${REST_URL}/${table}`, { method: 'POST', headers: HEADERS, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`DB ${res.status}: ${await res.text()}`)
  return res.json()
}

async function restDelete(table: string, query: string) {
  const res = await fetch(`${REST_URL}/${table}?${query}`, { method: 'DELETE', headers: { ...HEADERS, Prefer: 'return=minimal' } })
  if (!res.ok) throw new Error(`DB ${res.status}: ${await res.text()}`)
  return true
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  try {
    const path = params.path.join('/')
    const url = new URL(request.url)

    if (path === 'dashboard') {
      const dateRes = await restGet('daily_bars_adjusted', { select: 'date', order: 'date.desc', limit: '1' })
      return NextResponse.json({
        last_data_date: dateRes?.[0]?.date || null,
        initial_capital: 1_000_000_000,
        max_positions: 7,
        entry_frac: 0.07,
        stop_loss: 0.15,
        trail_pct: 0.10,
        time_stop_days: 30,
      })
    }

    if (path === 'signals/entry') {
      const tickerParam = url.searchParams.get('ticker')
      if (tickerParam) {
        const [feat, bars] = await Promise.all([
          restGet('stock_features', { ticker: `eq.${tickerParam}`, limit: '1' }),
          restGet('daily_bars_adjusted', {
            select: 'ticker,date,open,high,low,close,volume',
            ticker: `eq.${tickerParam}`, order: 'date.desc', limit: '120',
          }),
        ])
        if (!feat?.length) return NextResponse.json({ error: 'No data' })
        const f = feat[0]
        const recentBars = (bars || []).reverse().map((b: any) => ({
          date: b.date, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
        }))
        return NextResponse.json({
          ticker: tickerParam, sector: f.sector || 'Others',
          date: f.date, open: f.open, high: f.high, low: f.low, close: f.close,
          volume: f.volume, ema20: f.ema20, ema50: f.ema50, ema200: f.ema200,
          rsi14: f.rsi14, vol_ratio: f.vol_ratio, atr14: f.atr14,
          bullish: f.bullish, signal: f.signal,
          recent_bars: recentBars,
        })
      }
      const rows = await restGet('stock_features', { signal: 'eq.true', order: 'ticker.asc' })
      return NextResponse.json({
        date: new Date().toISOString().split('T')[0],
        signals_count: rows.length,
        signals: rows.map((r: any) => ({
          ticker: r.ticker, sector: r.sector || 'Others',
          price: r.price, ema20: r.ema20, ema50: r.ema50, ema200: r.ema200,
          rsi14: r.rsi14, vol_ratio: r.vol_ratio, atr14: r.atr14, date: r.date,
        })),
      })
    }

    if (path === 'screener') {
      const trend = url.searchParams.get('trend') || 'all'
      const rsiMin = Number(url.searchParams.get('rsi_min')) || 0
      const rsiMax = Number(url.searchParams.get('rsi_max')) || 100
      const candle = url.searchParams.get('candle') || 'all'
      const sector = url.searchParams.get('sector') || 'all'
      const priceMin = Number(url.searchParams.get('price_min')) || 0
      const priceMax = Number(url.searchParams.get('price_max')) || 1_000_000
      const signalFilter = url.searchParams.get('signal') || 'all'
      const reversalFilter = url.searchParams.get('reversal') || 'all'
      const trendLabel = url.searchParams.get('trend_label') || 'all'

      const filters: string[] = [
        `price.gte.${priceMin}`, `price.lte.${priceMax}`,
        `rsi14.gte.${rsiMin}`, `rsi14.lte.${rsiMax}`,
      ]
      if (trend === 'above_ema20') filters.push('close.gt.ema20')
      if (trend === 'above_ema50') filters.push('close.gt.ema50')
      if (trend === 'above_ema200') filters.push('close.gt.ema200')
      if (candle === 'bullish') filters.push('bullish.is.true')
      if (candle === 'bearish') filters.push('bullish.is.false')
      if (sector !== 'all') filters.push(`sector.eq.${sector}`)
      if (signalFilter === 'has_signal') filters.push('signal.is.true')
      if (signalFilter === 'no_signal') filters.push('signal.is.false')

      const rows = await restGet('stock_features', { select: '*', and: `(${filters.join(',')})`, order: 'ticker.asc' })

      // Fetch raw + adjusted prices from daily_bars_adjusted for correct display
      // stock_features.price = adj_close (VCI-adjusted), but we show real market price
      const today = rows[0]?.date
      let realPriceMap = new Map<string, { close: number; open: number; high: number; low: number }>()
      let prevAdjMap = new Map<string, { close: number; open: number; high: number; low: number }>()
      let prevRealMap = new Map<string, { close: number }>()
      if (today) {
        const [latestBars, prevBarsRaw] = await Promise.all([
          restGet('daily_bars_adjusted', { select: 'ticker,close,open,high,low', date: `eq.${today}` }),
          restGet('daily_bars_adjusted', { select: 'ticker,close,open,high,low,adj_close,adj_open,adj_high,adj_low', date: `lt.${today}`, order: 'date.desc,ticker.asc' }),
        ])
        for (const b of latestBars) {
          realPriceMap.set(b.ticker, { close: b.close, open: b.open, high: b.high, low: b.low })
        }
        for (const b of prevBarsRaw) {
          if (!prevAdjMap.has(b.ticker)) {
            prevAdjMap.set(b.ticker, { close: b.adj_close, open: b.adj_open, high: b.adj_high, low: b.adj_low })
          }
          if (!prevRealMap.has(b.ticker)) {
            prevRealMap.set(b.ticker, { close: b.close })
          }
        }
      }

      const getTrend = (row: any): string => {
        const { price, ema20, ema50, ema200 } = row
        if (price > ema20 && ema20 > ema50 && ema50 > ema200) return 'Mạnh'
        if (price > ema20 && ema20 > ema50) return 'Tăng'
        if (price < ema20 && ema20 < ema50 && ema50 < ema200) return 'Giảm mạnh'
        if (price < ema20 && ema20 < ema50) return 'Giảm'
        return 'Đi ngang'
      }

      const getReversal = (row: any): string => {
        const prev = prevAdjMap.get(row.ticker)
        if (!prev) return ''
        if (!row.bullish && prev.close > prev.open && row.close < prev.low) return 'Bearish'
        if (row.bullish && prev.close < prev.open && row.close > prev.high) return 'Bullish'
        return ''
      }

      return NextResponse.json({
        count: rows.length,
        results: rows.map((r: any) => {
          const real = realPriceMap.get(r.ticker)
          const prevReal = prevRealMap.get(r.ticker)
          const realClose = real?.close ?? r.price
          const realChangePct = prevReal ? ((realClose - prevReal.close) / prevReal.close * 100) : null
          return {
            ticker: r.ticker, sector: r.sector || 'Others',
            price: realClose,
            open: real?.open, high: real?.high, low: real?.low,
            ema20: r.ema20, ema50: r.ema50, ema200: r.ema200,
            pct_ema20: r.pct_ema20, pct_ema50: r.pct_ema50, pct_ema200: r.pct_ema200,
            rsi14: r.rsi14, vol_ratio: r.vol_ratio, bullish: r.bullish, signal: r.signal,
            change_pct: realChangePct != null ? Math.round(realChangePct * 100) / 100 : null,
            reversal: getReversal(r),
            trend: getTrend(r),
          }
        }),
      })
    }

    if (path === 'portfolio') {
      const rows = await restGet('portfolio_positions', { order: 'entry_date.desc' })
      return NextResponse.json(rows)
    }

    if (path === 'watchlist') {
      const listName = url.searchParams.get('list_name') || ''
      const params: Record<string, string> = { order: 'ticker.asc' }
      if (listName) params['list_name'] = `eq.${listName}`
      const rows = await restGet('watchlist', params)
      return NextResponse.json(rows)
    }
    if (path === 'watchlist/lists') {
      const rows = await restGet('watchlist', { select: 'list_name', order: 'list_name.asc' })
      const names = Array.from(new Set(rows.map((r: any) => r.list_name || 'default'))) as string[]
      const counts: Record<string, number> = {}
      for (const r of rows) {
        const k = r.list_name || 'default'
        counts[k] = (counts[k] || 0) + 1
      }
      return NextResponse.json(names.map((n: string) => ({ name: n, count: counts[n] || 0 })))
    }

    if (path === 'trades') {
      const limit = Number(url.searchParams.get('limit')) || 500
      const params: Record<string, string> = { order: 'entry_date.desc', limit: String(limit) }
      const minDate = url.searchParams.get('min_date')
      if (minDate) params['entry_date'] = `gte.${minDate}`
      const rows = await restGet('bt_trades', params)
      return NextResponse.json(rows)
    }

    if (path === 'alerts/config') {
      const rows = await restGet('alert_config', { limit: '1' })
      return NextResponse.json(rows?.[0] || {})
    }

    if (path === 'sync') {
      const ghPat = process.env.GH_PAT || ''
      if (!ghPat) return NextResponse.json({ error: 'Sync not configured' }, { status: 500 })
      const res = await fetch('https://api.github.com/repos/fetchinfluff-dotcom/vnindexrepo/actions/workflows/daily_refresh.yml/dispatches', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${ghPat}`, 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json', 'User-Agent': 'vnindex' },
        body: JSON.stringify({ ref: 'main' }),
      })
      if (!res.ok) return NextResponse.json({ error: 'GitHub API error' }, { status: 500 })
      return NextResponse.json({ status: 'triggered', message: 'Đã kích hoạt đồng bộ dữ liệu. Quá trình này mất ~1-3 phút.' })
    }

    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  try {
    const path = params.path.join('/')
    const body = await request.json()

    if (path === 'portfolio/positions') {
      await restPost('portfolio_positions', body)
      return NextResponse.json({ status: 'ok' })
    }
    if (path === 'watchlist') {
      await restPost('watchlist', body)
      return NextResponse.json({ status: 'ok' })
    }
    if (path === 'alerts/test') {
      return NextResponse.json({ status: 'ok', message: 'Test alert sent (mock)' })
    }
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}

export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  try {
    const path = params.path.join('/')
    const body = await request.json()

    if (path === 'alerts/config') {
      const rows = await restGet('alert_config', { limit: '1' })
      if (rows.length) {
        await fetch(`${REST_URL}/alert_config?id=eq.${rows[0].id}`, { method: 'PATCH', headers: HEADERS, body: JSON.stringify(body) })
      } else {
        await restPost('alert_config', body)
      }
      return NextResponse.json({ status: 'ok' })
    }
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  try {
    const path = params.path.join('/')

    if (path.startsWith('portfolio/positions/')) {
      const id = path.split('/').pop()
      await restDelete('portfolio_positions', `id=eq.${id}`)
      return NextResponse.json({ status: 'ok' })
    }
    if (path.startsWith('watchlist/')) {
      const ticker = path.split('/').pop()
      await restDelete('watchlist', `ticker=eq.${ticker}`)
      return NextResponse.json({ status: 'ok' })
    }
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
