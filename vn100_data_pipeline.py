#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VN100 Full Data Pipeline
- Range: 2021-01-01 -> current date
- Source: vnstock VCI OHLCV + VCI corporate events
- Storage: Supabase daily_bars + corporate_actions + daily_bars_adjusted
"""
from __future__ import annotations

import os
import sys
import time
import json
import warnings
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["VNSTOCK_SUPPRESS_NOTICE"] = "true"
os.environ["VNSTOCK_DISABLE_BANNER"] = "1"
os.environ["PYTHONWARNINGS"] = "ignore"

warnings.filterwarnings("ignore")

import httpx
import numpy as np
import pandas as pd
from supabase import create_client

# ============================================================
# CONFIG
# ============================================================
PROJECT_REF = "xgbficilqacfnzrbftoo"
SUPABASE_URL = f"https://{PROJECT_REF}.supabase.co"
MANAGEMENT_SQL_URL = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"

SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_PAT = os.getenv("SUPABASE_PAT")

# Keep these as fallbacks for local run. In production, prefer env vars.
if not SUPABASE_SERVICE_ROLE_KEY:
    SUPABASE_SERVICE_ROLE_KEY = "<SUPABASE_KEY>"
if not SUPABASE_PAT:
    SUPABASE_PAT = "<SUPABASE_PAT>"

START_DATE = os.getenv("PIPELINE_START_DATE", "2021-01-01")
END_DATE = os.getenv("PIPELINE_END_DATE", date.today().isoformat())
REQUEST_DELAY_SECONDS = float(os.getenv("PIPELINE_REQUEST_DELAY", "3.1"))
BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_SIZE", "500"))
PIPELINE_USE_LOCAL_CSV = os.getenv("PIPELINE_USE_LOCAL_CSV", "0").lower() in {"1", "true", "yes"}
PIPELINE_SKIP_EVENTS = os.getenv("PIPELINE_SKIP_EVENTS", "0").lower() in {"1", "true", "yes"}
LOCAL_CSV_PATH = os.getenv("PIPELINE_LOCAL_CSV", os.path.join(os.path.dirname(__file__), "vn100_data_2021_current.csv"))
LOCAL_ACTIONS_CSV_PATH = os.getenv(
    "PIPELINE_LOCAL_ACTIONS_CSV",
    os.path.join(os.path.dirname(__file__), "corporate_actions_2021_current.csv"),
)

VN100_TICKERS = [
    "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "ACB", "HDB", "STB", "TPB",
    "EIB", "MSB", "OCB", "SHB", "VIB", "LPB", "NAB", "SSB", "ABB", "KLB",
    "VIC", "VHM", "NVL", "KDH", "PDR", "DXG", "DXS", "SZC", "DIG", "HDG",
    "IDC", "KBC", "NLG", "TDH", "VRE", "HPX", "LDG", "AGG", "CEO", "SCR",
    "BCM", "SJS", "NTL", "LHG", "HQC", "QCG", "TCH", "NHA", "HBC", "CTD",
    "SSI", "VCI", "HCM", "VND", "ORS", "AGR", "BSI", "MBS", "FTS", "TVS",
    "VDS", "EVS", "CTS", "SHS", "APS",
    "HPG", "HSG", "NKG", "POM", "TLH", "GMD", "SMC", "VGS", "HMC", "CSV", "HHV",
    "MWG", "FRT", "PNJ", "DGW", "MSN", "SBT", "FMC", "VHC", "ANV", "TNG",
    "CMG", "VNM", "BHN", "SCD", "LCD",
    "GAS", "PLX", "POW", "PC1", "NT2", "REE", "GEG", "PPC", "QTP", "DTL",
    "FPT", "ELC", "ITD", "CMC", "VTI",
    "DCM", "DGC", "BFC", "DPM", "HT1", "LAS", "TNH", "NTP", "AAA",
    "SAB", "VJC", "HVN", "PLP", "PET", "PJT", "GTN", "HAX",
]
VN100_TICKERS = list(dict.fromkeys(VN100_TICKERS))

MGMT_HEADERS = {
    "Authorization": f"Bearer {SUPABASE_PAT}",
    "Content-Type": "application/json",
}

# ============================================================
# UTILS
# ============================================================
def print_sep(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def to_date_col(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    for c in cols:
        if c in df.columns:
            return pd.to_datetime(df[c], errors="coerce")
    return pd.Series(pd.NaT, index=df.index)


def safe_float(x) -> float | None:
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def safe_int(x) -> int | None:
    try:
        if pd.isna(x):
            return None
        return int(float(x))
    except Exception:
        return None


def json_sanitize(obj):
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_sanitize(v) for v in obj]
    if isinstance(obj, tuple):
        return [json_sanitize(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        if np.isnan(obj):
            return None
        return float(obj)
    if isinstance(obj, float):
        if np.isnan(obj):
            return None
        return obj
    if pd.isna(obj) if not isinstance(obj, (str, bytes)) else False:
        return None
    return obj


def normalize_ohlcv(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if "time" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"time": "date"})
    if "date" not in df.columns:
        return pd.DataFrame()

    df["ticker"] = ticker
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["date"])

    keep = ["ticker", "date", "open", "high", "low", "close", "volume"]
    for c in keep:
        if c not in df.columns:
            df[c] = np.nan
    df = df[keep]

    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
    return df


def normalize_events(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    df["ticker"] = ticker

    # Keep dividend/stock-dividend actions only.
    if "category" in df.columns:
        df = df[df["category"].astype(str).str.upper() == "DIVIDEND"].copy()
    if df.empty:
        return pd.DataFrame()

    date_map = {
        "display_date1": "display_date1",
        "display_date2": "display_date2",
        "public_date": "public_date",
        "start_date": "start_date",
        "end_date": "end_date",
        "record_date": "record_date",
        "exright_date": "exright_date",
        "payout_date": "payout_date",
        "issue_date": "issue_date",
        "listing_date": "listing_date",
    }
    for src, dst in date_map.items():
        if src not in df.columns:
            df[dst] = pd.NaT
        else:
            df[dst] = pd.to_datetime(df[src], errors="coerce").dt.strftime("%Y-%m-%d")

    # Adjustment date for backward adjustment.
    df["adjustment_date"] = pd.NaT
    for c in ["exright_date", "record_date", "issue_date", "display_date1", "public_date", "start_date"]:
        if c in df.columns:
            s = pd.to_datetime(df[c], errors="coerce")
            df["adjustment_date"] = df["adjustment_date"].where(df["adjustment_date"].notna(), s)
    df["adjustment_date"] = pd.to_datetime(df["adjustment_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    for c in ["exercise_ratio", "value_per_share"]:
        if c not in df.columns:
            df[c] = np.nan
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "event_id" not in df.columns:
        df["event_id"] = np.nan
    if "event_code" not in df.columns:
        df["event_code"] = np.nan
    if "event_name_vi" not in df.columns:
        df["event_name_vi"] = np.nan
    if "event_name_en" not in df.columns:
        df["event_name_en"] = np.nan
    if "action_type_vi" not in df.columns:
        df["action_type_vi"] = np.nan
    if "action_type_en" not in df.columns:
        df["action_type_en"] = np.nan

    df = df.sort_values(["adjustment_date", "event_code", "event_id"], na_position="last")
    return df


def apply_adjustments(raw: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw
    bars = raw.copy()
    for c in ["open", "high", "low", "close", "volume"]:
        bars[c] = pd.to_numeric(bars[c], errors="coerce")
    bars["date"] = pd.to_datetime(bars["date"], errors="coerce")

    bars["adj_open"] = bars["open"].astype(float)
    bars["adj_high"] = bars["high"].astype(float)
    bars["adj_low"] = bars["low"].astype(float)
    bars["adj_close"] = bars["close"].astype(float)
    bars["adj_volume"] = bars["volume"].astype(float)
    bars["raw_close"] = bars["close"].astype(float)
    bars["raw_volume"] = bars["volume"].astype("int64")
    bars["adjustment_factor"] = 1.0
    bars["is_adjusted"] = False

    if actions is None or actions.empty:
        bars["date"] = bars["date"].dt.strftime("%Y-%m-%d")
        return bars

    acts = actions.copy()
    acts["adjustment_date"] = pd.to_datetime(acts["adjustment_date"], errors="coerce")
    acts = acts.dropna(subset=["adjustment_date"]).sort_values("adjustment_date", ascending=False)

    for _, a in acts.iterrows():
        adj_date = a["adjustment_date"]
        if pd.isna(adj_date):
            continue

        event_code = str(a.get("event_code", "")).upper()
        ratio = safe_float(a.get("exercise_ratio")) or 0.0
        cash_div = safe_float(a.get("value_per_share")) or 0.0
        factor = None

        # Stock dividend / split-like: factor = 1 / (1 + ratio)
        if ratio and ratio > 0:
            factor = 1.0 / (1.0 + ratio)
        # Cash dividend: factor = (ex_close - dividend) / ex_close
        elif cash_div and cash_div > 0:
            same_day = bars.loc[bars["date"] == adj_date, "close"]
            if not same_day.empty:
                ex_close = float(same_day.iloc[0])
            else:
                after = bars.loc[bars["date"] >= adj_date, "close"]
                if after.empty:
                    continue
                ex_close = float(after.iloc[0])
            if ex_close > cash_div:
                factor = (ex_close - cash_div) / ex_close

        if factor is None or factor <= 0:
            continue

        idx = bars.index[bars["date"] < adj_date]
        if len(idx) == 0:
            continue

        bars.loc[idx, ["adj_open", "adj_high", "adj_low", "adj_close"]] *= factor
        # For stock dividends/splits, historical volume should be scaled up; cash dividend leaves volume unchanged.
        if ratio and ratio > 0:
            bars.loc[idx, "adj_volume"] /= factor
        bars.loc[idx, "adjustment_factor"] *= factor
        bars.loc[idx, "is_adjusted"] = True

    bars["date"] = bars["date"].dt.strftime("%Y-%m-%d")
    return bars


# ============================================================
# SUPABASE
# ============================================================
def ensure_tables() -> None:
    create_sql = """
    CREATE TABLE IF NOT EXISTS daily_bars (
        ticker TEXT NOT NULL,
        date DATE NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume BIGINT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (ticker, date)
    );

    CREATE TABLE IF NOT EXISTS corporate_actions (
        id BIGSERIAL PRIMARY KEY,
        ticker TEXT NOT NULL,
        event_id TEXT,
        event_code TEXT,
        category TEXT,
        action_type_vi TEXT,
        action_type_en TEXT,
        event_name_vi TEXT,
        event_name_en TEXT,
        event_title_vi TEXT,
        event_title_en TEXT,
        display_date1 DATE,
        display_date2 DATE,
        public_date DATE,
        start_date DATE,
        end_date DATE,
        record_date DATE,
        exright_date DATE,
        payout_date DATE,
        issue_date DATE,
        listing_date DATE,
        adjustment_date DATE,
        exercise_ratio DOUBLE PRECISION,
        value_per_share DOUBLE PRECISION,
        raw_json JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(ticker, event_id)
    );

    CREATE INDEX IF NOT EXISTS idx_corporate_actions_ticker_date
        ON corporate_actions (ticker, adjustment_date);

    CREATE TABLE IF NOT EXISTS daily_bars_adjusted (
        ticker TEXT NOT NULL,
        date DATE NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume BIGINT,
        adj_open DOUBLE PRECISION,
        adj_high DOUBLE PRECISION,
        adj_low DOUBLE PRECISION,
        adj_close DOUBLE PRECISION,
        adj_volume DOUBLE PRECISION,
        raw_close DOUBLE PRECISION,
        raw_volume BIGINT,
        adjustment_factor DOUBLE PRECISION,
        is_adjusted BOOLEAN,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (ticker, date)
    );

    CREATE INDEX IF NOT EXISTS idx_daily_bars_adjusted_ticker_date
        ON daily_bars_adjusted (ticker, date);
    """
    with httpx.Client(timeout=60) as client:
        r = client.post(MANAGEMENT_SQL_URL, json={"query": create_sql}, headers=MGMT_HEADERS)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"ensure_tables failed: {r.status_code} {r.text[:300]}")


def upsert_table(supabase, table: str, records: list[dict], conflict: str) -> int:
    if not records:
        return 0
    total = 0
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start:start + BATCH_SIZE]
        try:
            supabase.table(table).upsert(batch, on_conflict=conflict).execute()
            total += len(batch)
        except Exception as e:
            print(f"  Upsert error {table} batch {start}: {str(e)[:150]}")
    return total


# ============================================================
# FETCH
# ============================================================
def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    from vnstock.api.quote import Quote
    q = Quote(symbol=ticker, source="VCI")
    raw = q.history(symbol=ticker, start=START_DATE, end=END_DATE, interval="1D")
    return normalize_ohlcv(raw, ticker)


def fetch_events(ticker: str) -> pd.DataFrame:
    from vnstock.common.data import Company
    c = Company(symbol=ticker, source="VCI")
    raw = c.events()
    return normalize_events(raw, ticker)


def records_from_df(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    if df is None or df.empty:
        return []
    rows = []
    for _, r in df[columns].iterrows():
        rec = {}
        for c in columns:
            v = r[c]
            if pd.isna(v):
                rec[c] = None
            elif isinstance(v, (np.integer,)):
                rec[c] = int(v)
            elif isinstance(v, (np.floating,)):
                rec[c] = float(v)
            else:
                rec[c] = v
        rows.append(rec)
    return rows


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    print_sep("VN100 FULL DATA PIPELINE")
    print(f"Range: {START_DATE} -> {END_DATE}")
    print(f"Tickers: {len(VN100_TICKERS)}")
    print(f"Request delay: {REQUEST_DELAY_SECONDS:.1f}s")

    ensure_tables()
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    print("Supabase tables ready")

    all_bars = []
    all_actions = []
    pulled = 0
    failed = 0

    if PIPELINE_USE_LOCAL_CSV and os.path.exists(LOCAL_CSV_PATH):
        print_sep("STEP 1: Load local CSV + pull corporate actions")
        bars_df = pd.read_csv(LOCAL_CSV_PATH)
        all_bars.append(bars_df)
        pulled = bars_df["ticker"].nunique()
        print(f"Loaded local CSV: {len(bars_df)} rows, {pulled} tickers")
    else:
        print_sep("STEP 1: Pull OHLCV + corporate actions")

    if PIPELINE_SKIP_EVENTS:
        print("Skipping corporate events by PIPELINE_SKIP_EVENTS=1")
    else:
        for i, ticker in enumerate(VN100_TICKERS, start=1):
            if PIPELINE_USE_LOCAL_CSV and os.path.exists(LOCAL_CSV_PATH):
                print(f"[{i}/{len(VN100_TICKERS)}] {ticker} actions...", end=" ", flush=True)
            else:
                print(f"[{i}/{len(VN100_TICKERS)}] {ticker}...", end=" ", flush=True)
            try:
                if not PIPELINE_USE_LOCAL_CSV or not os.path.exists(LOCAL_CSV_PATH):
                    bars = fetch_ohlcv(ticker)
                    if bars.empty:
                        print("NO DATA")
                        failed += 1
                    else:
                        all_bars.append(bars)
                        print(f"{len(bars)} bars", end="; ", flush=True)
                        pulled += 1

                actions = fetch_events(ticker)
                if not actions.empty:
                    all_actions.append(actions)
                    print(f"{len(actions)} actions", end="", flush=True)
                else:
                    print("0 actions", end="", flush=True)

            except Exception as e:
                failed += 1
                msg = str(e)
                if "RateLimit" in msg or "Rate limit" in msg:
                    print(f"RATE LIMIT, wait 65s", end="", flush=True)
                    time.sleep(65)
                    try:
                        if not PIPELINE_USE_LOCAL_CSV or not os.path.exists(LOCAL_CSV_PATH):
                            bars = fetch_ohlcv(ticker)
                            if not bars.empty:
                                all_bars.append(bars)
                                pulled += 1
                        actions = fetch_events(ticker)
                        if not actions.empty:
                            all_actions.append(actions)
                        print(" retry OK", end="", flush=True)
                    except Exception as e2:
                        print(f" retry failed: {str(e2)[:80]}", end="", flush=True)
                else:
                    print(f"FAILED: {msg[:80]}", end="", flush=True)

            print()
            time.sleep(REQUEST_DELAY_SECONDS)

    print_sep("STEP 2: Upsert raw bars")
    if all_bars:
        bars_df = pd.concat(all_bars, ignore_index=True)
        bars_df = bars_df.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
        bars_records = records_from_df(bars_df, ["ticker", "date", "open", "high", "low", "close", "volume"])
        upsert_table(supabase, "daily_bars", bars_records, "ticker,date")
        csv_path = os.path.join(os.path.dirname(__file__), "vn100_data_2021_current.csv")
        bars_df.to_csv(csv_path, index=False)
        print(f"Raw bars: {len(bars_df)} rows, {bars_df['ticker'].nunique()} tickers")
        print(f"Saved CSV: {csv_path}")
    else:
        print("No bars to upsert")

    print_sep("STEP 3: Upsert corporate actions")
    # If skip events and local actions CSV exists, load it
    if PIPELINE_SKIP_EVENTS and not all_actions and os.path.exists(LOCAL_ACTIONS_CSV_PATH):
        print(f"Loading corporate actions from local CSV: {LOCAL_ACTIONS_CSV_PATH}")
        actions_df = pd.read_csv(LOCAL_ACTIONS_CSV_PATH)
        all_actions.append(actions_df)
    elif PIPELINE_SKIP_EVENTS:
        print("Skipping corporate events by PIPELINE_SKIP_EVENTS=1 (no local actions CSV found)")

    if all_actions:
        actions_df = pd.concat(all_actions, ignore_index=True)
        actions_df = actions_df.sort_values(["ticker", "adjustment_date", "event_code"])
        # Ensure unique event_id.
        if "event_id" in actions_df.columns:
            actions_df["event_id"] = actions_df["event_id"].fillna("").astype(str)
            mask = actions_df["event_id"].str.strip().eq("")
            if mask.any():
                fallback = (
                    actions_df["ticker"].astype(str) + "-" +
                    actions_df["adjustment_date"].astype(str) + "-" +
                    actions_df["event_code"].astype(str) + "-" +
                    actions_df["event_title_vi"].astype(str)
                )
                actions_df.loc[mask, "event_id"] = fallback[mask]
        else:
            actions_df["event_id"] = (
                actions_df["ticker"].astype(str) + "-" +
                actions_df["adjustment_date"].astype(str) + "-" +
                actions_df["event_code"].astype(str)
            )

        action_cols = [
            "ticker", "event_id", "event_code", "category", "action_type_vi", "action_type_en",
            "event_name_vi", "event_name_en", "event_title_vi", "event_title_en",
            "display_date1", "display_date2", "public_date", "start_date", "end_date",
            "record_date", "exright_date", "payout_date", "issue_date", "listing_date",
            "adjustment_date", "exercise_ratio", "value_per_share", "raw_json",
        ]
        # raw_json column: serialize available columns except raw_json itself.
        if "raw_json" not in actions_df.columns:
            actions_df["raw_json"] = None
        # Deduplicate by ticker+event_id to avoid PostgreSQL ON CONFLICT error
        before = len(actions_df)
        actions_df = actions_df.drop_duplicates(subset=["ticker", "event_id"], keep="first")
        if len(actions_df) < before:
            print(f"  Deduplicated: {before} -> {len(actions_df)} rows")

        action_records = []
        for _, r in actions_df.iterrows():
            rec = {}
            for c in action_cols:
                if c == "raw_json":
                    continue
                v = r.get(c)
                if isinstance(v, (float, np.floating)) and (np.isnan(v) or np.isinf(v)):
                    rec[c] = None
                elif isinstance(v, (np.integer,)):
                    rec[c] = int(v)
                elif pd.isna(v):
                    rec[c] = None
                else:
                    rec[c] = v
            rec["raw_json"] = json.dumps(json_sanitize(r.to_dict()), ensure_ascii=False)
            action_records.append(rec)
        upsert_table(supabase, "corporate_actions", action_records, "ticker,event_id")
        actions_csv = os.path.join(os.path.dirname(__file__), "corporate_actions_2021_current.csv")
        actions_df.to_csv(actions_csv, index=False)
        print(f"Corporate actions: {len(actions_df)} rows, {actions_df['ticker'].nunique()} tickers")
        print(f"Saved CSV: {actions_csv}")
    else:
        print("No corporate actions")

    print_sep("STEP 4: Build adjusted bars and upsert")
    if all_bars:
        # Use local data so adjustment is deterministic.
        bars_df = pd.concat(all_bars, ignore_index=True)
        actions_df = pd.concat(all_actions, ignore_index=True) if all_actions else pd.DataFrame()
        adjusted_frames = []
        for ticker in sorted(bars_df["ticker"].unique()):
            raw = bars_df[bars_df["ticker"] == ticker].copy()
            acts = actions_df[actions_df["ticker"] == ticker].copy() if not actions_df.empty else pd.DataFrame()
            adj = apply_adjustments(raw, acts)
            adjusted_frames.append(adj)

        adj_df = pd.concat(adjusted_frames, ignore_index=True)
        adj_df = adj_df.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last")
        adj_cols = [
            "ticker", "date", "open", "high", "low", "close", "volume",
            "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
            "raw_close", "raw_volume", "adjustment_factor", "is_adjusted",
        ]
        adj_records = records_from_df(adj_df, adj_cols)
        upsert_table(supabase, "daily_bars_adjusted", adj_records, "ticker,date")
        adj_csv = os.path.join(os.path.dirname(__file__), "vn100_data_2021_current_adjusted.csv")
        adj_df.to_csv(adj_csv, index=False)
        print(f"Adjusted bars: {len(adj_df)} rows, {adj_df['ticker'].nunique()} tickers")
        print(f"Saved CSV: {adj_csv}")

    print_sep("DONE")


if __name__ == "__main__":
    main()


