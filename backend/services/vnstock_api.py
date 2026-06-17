"""Thin wrapper around vnstock for data fetching"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class VnstockAPI:
    def __init__(self):
        self._quote = None
        self._company = None

    def _lazy_init(self):
        if self._quote is None:
            from vnstock.api.quote import Quote
            self._quote = Quote(symbol="VCB", source="VCI")

    def fetch_index_bars(self, symbol: str = "VNINDEX", days: int = 730) -> pd.DataFrame:
        self._lazy_init()
        end = datetime.now()
        start = end - timedelta(days=days)
        raw = self._quote.history(symbol=symbol, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1D")
        if raw is None or raw.empty:
            return pd.DataFrame()
        df = raw.copy()
        df.columns = [str(c).lower().strip() for c in df.columns]
        if "time" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"time": "date"})
        df["symbol"] = symbol
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["date"])
        for c in ["open","high","low","close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
        df = df.dropna(subset=["open","high","low","close"])
        df = df.sort_values("date").drop_duplicates("date", keep="last")
        return df[["symbol","date","open","high","low","close","volume"]]

    def fetch_bars(self, ticker: str, days: int = 10) -> pd.DataFrame:
        self._lazy_init()
        end = datetime.now()
        start = end - timedelta(days=days * 2)
        raw = self._quote.history(symbol=ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1D")
        if raw is None or raw.empty:
            return pd.DataFrame()
        df = raw.copy()
        df.columns = [str(c).lower().strip() for c in df.columns]
        if "time" in df.columns and "date" not in df.columns:
            df = df.rename(columns={"time": "date"})
        df["ticker"] = ticker
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["date"])
        for c in ["open","high","low","close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
        df = df.dropna(subset=["open","high","low","close"])
        df = df.sort_values("date").drop_duplicates("date", keep="last")
        return df[["ticker","date","open","high","low","close","volume"]]
