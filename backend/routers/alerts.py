"""Alerts router - configure and test alerts"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import httpx
from config import settings

router = APIRouter(tags=["alerts"])
MGMT = settings.MGMT_HEADERS
sql_url = settings.MANAGEMENT_SQL_URL

class AlertConfigUpdate(BaseModel):
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    email_host: Optional[str] = None
    email_user: Optional[str] = None
    email_pass: Optional[str] = None
    alert_daily_signal: Optional[bool] = None
    alert_position_open: Optional[bool] = None
    alert_position_close: Optional[bool] = None
    alert_stop_loss: Optional[bool] = None
    alert_drawdown_warning: Optional[bool] = None
    alert_drawdown_stop: Optional[bool] = None

async def query(q: str):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(sql_url, json={"query": q}, headers=MGMT)
    return r.json() if r.status_code in (200,201) else []

@router.get("/alerts/config")
async def get_alert_config():
    rows = await query("SELECT * FROM alert_config LIMIT 1")
    if rows:
        r = rows[0]
        r.pop('email_pass', None)
        return r
    return {
        "telegram_token": "", "telegram_chat_id": "",
        "email_host": "smtp.gmail.com", "email_user": "",
        "alert_daily_signal": True, "alert_position_open": True,
        "alert_position_close": True, "alert_stop_loss": True,
        "alert_drawdown_warning": True, "alert_drawdown_stop": True,
    }

@router.put("/alerts/config")
async def update_alert_config(cfg: AlertConfigUpdate):
    sets = []
    for k, v in cfg.model_dump(exclude_none=True).items():
        if isinstance(v, bool): sets.append(f"{k}={str(v).lower()}")
        elif v is not None: sets.append(f"{k}='{v}'")
    if sets:
        # Upsert: check if row exists
        rows = await query("SELECT id FROM alert_config LIMIT 1")
        if rows:
            await query(f"UPDATE alert_config SET {','.join(sets)}, updated_at=NOW() WHERE id='{rows[0]['id']}'")
        else:
            cols = [s.split('=')[0] for s in sets]
            vals = ['='.join(s.split('=')[1:]) for s in sets]
            await query(f"INSERT INTO alert_config ({','.join(cols)}) VALUES ({','.join(vals)})")
    return {"status": "ok"}

@router.post("/alerts/test")
async def send_test_alert():
    return {"status": "ok", "message": "Test alert sent (mock)"}
