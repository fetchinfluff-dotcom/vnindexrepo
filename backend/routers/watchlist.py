"""Watchlist router"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import httpx
from config import settings

router = APIRouter(tags=["watchlist"])
MGMT = settings.MGMT_HEADERS
sql_url = settings.MANAGEMENT_SQL_URL

class WatchItem(BaseModel):
    ticker: str
    note: Optional[str] = None

async def query(q: str):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(sql_url, json={"query": q}, headers=MGMT)
    return r.json() if r.status_code in (200,201) else []

@router.get("/watchlist")
async def get_watchlist():
    rows = await query("SELECT * FROM watchlist ORDER BY created_at DESC")
    tickers = [r['ticker'] for r in rows]
    prices = {}
    if tickers:
        tl = "','".join(tickers)
        pr = await query(
            f"SELECT ticker, adj_close AS price, adj_open AS open, adj_high AS high, adj_low AS low, adj_volume AS volume FROM daily_bars_adjusted WHERE (ticker, date) IN (SELECT ticker, MAX(date) FROM daily_bars_adjusted GROUP BY ticker) AND ticker IN ('{tl}')"
        )
        for p in pr:
            prices[p['ticker']] = p
    for r in rows:
        info = prices.get(r['ticker'], {})
        r['current_price'] = info.get('price')
        r['open'] = info.get('open'); r['high'] = info.get('high')
        r['low'] = info.get('low'); r['volume'] = info.get('volume')
    return rows

@router.post("/watchlist")
async def add_watch(item: WatchItem):
    await query(f"INSERT INTO watchlist (ticker, note) VALUES ('{item.ticker}', '{item.note or ''}') ON CONFLICT (user_id, ticker) DO NOTHING")
    return {"status": "ok"}

@router.delete("/watchlist/{ticker}")
async def remove_watch(ticker: str):
    await query(f"DELETE FROM watchlist WHERE ticker='{ticker}'")
    return {"status": "ok"}
