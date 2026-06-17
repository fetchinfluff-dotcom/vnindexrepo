"""Portfolio router - manage positions"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import httpx, json
from config import settings

router = APIRouter(tags=["portfolio"])
MGMT = settings.MGMT_HEADERS
sql_url = settings.MANAGEMENT_SQL_URL

class PositionCreate(BaseModel):
    ticker: str
    entry_price: float
    quantity: int
    entry_date: date
    stop_loss: Optional[float] = None
    note: Optional[str] = None

class PositionUpdate(BaseModel):
    entry_price: Optional[float] = None
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    note: Optional[str] = None
    is_active: Optional[bool] = None

async def query_supabase(q: str, params: list = []):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(sql_url, json={"query": q}, headers=MGMT)
    if r.status_code not in (200, 201):
        raise HTTPException(500, detail=f"Query failed: {r.text[:200]}")
    return r.json()

@router.get("/portfolio")
async def get_positions():
    rows = await query_supabase("SELECT * FROM portfolio_positions ORDER BY created_at DESC")
    # Enrich with current prices
    tickers = [r['ticker'] for r in rows]
    prices = {}
    if tickers:
        ticker_list = "','".join(tickers)
        price_rows = await query_supabase(
            f"SELECT ticker, adj_close AS price FROM daily_bars_adjusted WHERE (ticker, date) IN (SELECT ticker, MAX(date) FROM daily_bars_adjusted GROUP BY ticker) AND ticker IN ('{ticker_list}')"
        )
        for pr in price_rows:
            prices[pr['ticker']] = pr['price']
    for r in rows:
        r['current_price'] = prices.get(r['ticker'])
        r['pnl_pct'] = ((r['current_price'] / r['entry_price']) - 1) * 100 if r.get('current_price') else None
    return rows

@router.post("/portfolio/positions")
async def add_position(pos: PositionCreate):
    await query_supabase(
        f"INSERT INTO portfolio_positions (ticker, entry_price, quantity, entry_date, stop_loss, note) VALUES ('{pos.ticker}', {pos.entry_price}, {pos.quantity}, '{pos.entry_date}', {pos.stop_loss or 'NULL'}, '{pos.note or ''}')"
    )
    return {"status": "ok", "ticker": pos.ticker}

@router.put("/portfolio/positions/{position_id}")
async def update_position(position_id: str, pos: PositionUpdate):
    sets = []
    if pos.entry_price is not None: sets.append(f"entry_price={pos.entry_price}")
    if pos.quantity is not None: sets.append(f"quantity={pos.quantity}")
    if pos.stop_loss is not None: sets.append(f"stop_loss={pos.stop_loss}")
    if pos.note is not None: sets.append(f"note='{pos.note}'")
    if pos.is_active is not None: sets.append(f"is_active={str(pos.is_active).lower()}")
    sets.append("updated_at=NOW()")
    if sets:
        await query_supabase(f"UPDATE portfolio_positions SET {','.join(sets)} WHERE id='{position_id}'")
    return {"status": "ok"}

@router.delete("/portfolio/positions/{position_id}")
async def delete_position(position_id: str):
    await query_supabase(f"DELETE FROM portfolio_positions WHERE id='{position_id}'")
    return {"status": "ok"}
