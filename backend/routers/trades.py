"""Trades router - trade history"""
from fastapi import APIRouter, Query
from typing import Optional
import httpx
from config import settings

router = APIRouter(tags=["trades"])
MGMT = settings.MGMT_HEADERS
sql_url = settings.MANAGEMENT_SQL_URL

@router.get("/trades")
async def get_trades(limit: int = Query(100, ge=1, le=1000), ticker: Optional[str] = None):
    where = f"WHERE ticker='{ticker}'" if ticker else ""
    rows = []
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(sql_url, json={"query": f"SELECT * FROM bt_trades {where} ORDER BY exit_date DESC LIMIT {limit}"}, headers=MGMT)
        if r.status_code in (200, 201) and isinstance(r.json(), list):
            rows = r.json()
    return rows
