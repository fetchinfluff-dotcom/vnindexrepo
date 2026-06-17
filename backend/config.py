"""Backend configuration - load from environment variables only"""
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "VN100 Trading Dashboard"
    SUPABASE_URL: str = "https://xgbficilqacfnzrbftoo.supabase.co"
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_PAT: str = ""
    MANAGEMENT_SQL_URL: str = "https://api.supabase.com/v1/projects/xgbficilqacfnzrbftoo/database/query"
    MGMT_HEADERS: dict = {}
    INITIAL_CAPITAL: float = 1_000_000_000
    ENTRY_FRAC: float = 0.07
    MAX_POSITIONS: int = 7
    SECTOR_CAP: float = 0.20
    STOP_LOSS: float = 0.15
    TRAIL_PCT: float = 0.10
    TIME_STOP_DAYS: int = 30
    DATA_START_DATE: str = "2021-01-01"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pat = self.SUPABASE_PAT or os.getenv("SUPABASE_PAT", "")
        if pat:
            self.MGMT_HEADERS = {
                "Authorization": f"Bearer {pat}",
                "Content-Type": "application/json",
            }

import os
settings = Settings()
