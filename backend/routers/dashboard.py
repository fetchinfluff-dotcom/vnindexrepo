"""Dashboard router - KPI cards, equity curve, summary"""
from fastapi import APIRouter
import httpx, json
import numpy as np
import pandas as pd
from datetime import datetime
from config import settings

router = APIRouter(tags=["dashboard"])
MGMT = settings.MGMT_HEADERS

@router.get("/dashboard")
async def get_dashboard():
    sql_url = settings.MANAGEMENT_SQL_URL
    async with httpx.AsyncClient(timeout=60) as client:
        # NAV from equity curve or compute from portfolio
        r = await client.post(sql_url, json={"query": "SELECT COUNT(*) AS cnt FROM daily_bars_adjusted"}, headers=MGMT)
        rows_ct = r.json()[0]["cnt"] if r.status_code in (200,201) else 0

        r2 = await client.post(sql_url, json={"query": "SELECT COUNT(DISTINCT ticker) AS n FROM daily_bars_adjusted"}, headers=MGMT)
        ticker_ct = r2.json()[0]["n"] if r2.status_code in (200,201) else 0

        r3 = await client.post(sql_url, json={"query": "SELECT MAX(date) AS last FROM daily_bars_adjusted"}, headers=MGMT)
        last_date = r3.json()[0]["last"] if r3.status_code in (200,201) else None

    return {
        "total_bars": rows_ct,
        "active_tickers": ticker_ct,
        "last_data_date": last_date,
        "initial_capital": settings.INITIAL_CAPITAL,
        "max_positions": settings.MAX_POSITIONS,
        "entry_frac": settings.ENTRY_FRAC,
        "stop_loss": settings.STOP_LOSS,
        "trail_pct": settings.TRAIL_PCT,
        "time_stop_days": settings.TIME_STOP_DAYS,
        "dashboard_time": datetime.now().isoformat(),
    }
