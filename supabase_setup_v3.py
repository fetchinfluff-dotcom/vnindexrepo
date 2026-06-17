#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Supabase setup: Management API for tables, PostgREST for data"""
import sys, os, time, json, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
warnings.filterwarnings('ignore')

import httpx
import pandas as pd
import numpy as np
from supabase import create_client

PAT = '<SUPABASE_PAT>'
PROJECT_REF = 'xgbficilqacfnzrbftoo'
SUPABASE_URL = f'https://{PROJECT_REF}.supabase.co'
SERVICE_KEY = '<SUPABASE_KEY>'

sql_url = f'https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query'
mgmt_headers = {'Authorization': f'Bearer {PAT}', 'Content-Type': 'application/json'}

print("=" * 60)
print("STEP 1: Create tables via Management API")
print("=" * 60)

with httpx.Client(timeout=30) as mgmt:
    create_statements = [
        "CREATE TABLE IF NOT EXISTS daily_bars (ticker TEXT NOT NULL, date DATE NOT NULL, open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION, volume BIGINT, created_at TIMESTAMPTZ DEFAULT NOW(), PRIMARY KEY (ticker, date));",
        "CREATE TABLE IF NOT EXISTS signals (id BIGSERIAL PRIMARY KEY, ticker TEXT NOT NULL, date DATE NOT NULL, close DOUBLE PRECISION, ema20 DOUBLE PRECISION, ema50 DOUBLE PRECISION, ema200 DOUBLE PRECISION, rsi_14 DOUBLE PRECISION, atr14 DOUBLE PRECISION, vol_ratio DOUBLE PRECISION, signal TEXT, signal_type TEXT, created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(ticker, date, signal_type));",
        "CREATE TABLE IF NOT EXISTS backtest_results (id BIGSERIAL PRIMARY KEY, run_date TIMESTAMPTZ DEFAULT NOW(), config JSONB, total_trades INTEGER, win_rate DOUBLE PRECISION, total_return DOUBLE PRECISION, cagr DOUBLE PRECISION, sharpe DOUBLE PRECISION, max_drawdown DOUBLE PRECISION, final_nav DOUBLE PRECISION, trades_json JSONB, equity_curve_json JSONB);",
        "CREATE TABLE IF NOT EXISTS portfolio_state (id BIGSERIAL PRIMARY KEY, date DATE NOT NULL, nav DOUBLE PRECISION, cash DOUBLE PRECISION, positions JSONB, created_at TIMESTAMPTZ DEFAULT NOW());"
    ]
    for i, stmt in enumerate(create_statements):
        r = mgmt.post(sql_url, json={"query": stmt}, headers=mgmt_headers)
        status = "OK" if r.status_code in (200, 201) else f"FAIL {r.status_code}"
        print(f"  [{i+1}/4] {status}")

# ============================================================
# STEP 2: Upload CSV data via PostgREST
# ============================================================
print("\n" + "=" * 60)
print("STEP 2: Upload CSV data via PostgREST")
print("=" * 60)

csv_path = os.path.join(os.path.dirname(__file__), 'vn100_data_2022_2024.csv')
df = pd.read_csv(csv_path)
print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")

supabase = create_client(SUPABASE_URL, SERVICE_KEY)

# Clear and re-insert
supabase.table('daily_bars').delete().neq('ticker', '').execute()

BATCH_SIZE = 500
total = len(df)
inserted = 0

for start in range(0, total, BATCH_SIZE):
    batch = df.iloc[start:start+BATCH_SIZE]
    records = []
    for _, row in batch.iterrows():
        try:
            records.append({
                'ticker': str(row['ticker']).strip(),
                'date': str(row['date'])[:10],
                'open': float(row['open']) if pd.notna(row['open']) else None,
                'high': float(row['high']) if pd.notna(row['high']) else None,
                'low': float(row['low']) if pd.notna(row['low']) else None,
                'close': float(row['close']) if pd.notna(row['close']) else None,
                'volume': int(float(row['volume'])) if pd.notna(row['volume']) else None,
            })
        except:
            continue
    if records:
        try:
            supabase.table('daily_bars').upsert(records, on_conflict='ticker,date').execute()
            inserted += len(records)
        except Exception as e:
            print(f"  Error at {start}: {str(e)[:100]}")
    if (start // BATCH_SIZE) % 4 == 0:
        print(f"  Progress: {min(start+BATCH_SIZE, total)}/{total}")

print(f"Inserted: {inserted} rows")

# Verify
result = supabase.table('daily_bars').select('ticker', count='exact').limit(1).execute()
print(f"Verified: {result.count} rows")

# Get existing tickers
result = supabase.table('daily_bars').select('ticker').execute()
existing = set(r['ticker'] for r in result.data)
print(f"Existing tickers: {len(existing)}")

# ============================================================
# STEP 3: Pull remaining VN100 tickers
# ============================================================
print("\n" + "=" * 60)
print("STEP 3: Pull remaining VN100 tickers from vnstock")
print("=" * 60)

from vnstock import Quote

all_tickers = [
    'ACB','BID','CTG','EIB','HDB','KLB','LPB','MBB','MSB','NAB','OCB','SHB','SSB','STB','TCB','TPB','VCB','VIB','VPB','ABB',
    'VIC','VHM','NVL','KDH','PDR','DXG','DXS','SZC','DIG','HDG','IDC','KBC','NLG','TDH','VRE','HPX','LDG','AGG','CEO','SCR',
    'BCM','SJS','NTL','LHG','HQC','QCG','TCH','NHA','HBC','CTD',
    'SSI','VCI','HCM','VND','ORS','AGR','BSI','MBS','FTS','TVS','VDS','EVS','CTS','SHS','APS',
    'HPG','HSG','NKG','POM','TLH','GMD','SMC','VGS','HMC','CSV','HHV',
    'MWG','FRT','PNJ','DGW','MSN','SBT','FMC','VHC','ANV','TNG',
    'CMG','VNM','BHN','SCD','LCD',
    'GAS','PLX','POW','PC1','NT2','REE','GEG','PPC','QTP','DTL',
    'FPT','ELC','ITD','CMC','VTI',
    'DCM','DGC','BFC','DPM','HT1','LAS','TNH','NTP','AAA',
    'SAB','VJC','HVN','PLP','PET','PJT','GTN','HAX'
]

remaining = [t for t in all_tickers if t not in existing]
print(f"Remaining: {len(remaining)} tickers")

if remaining:
    q = Quote(symbol='ACB', source='VCI')
    pulled = 0; failed = 0
    
    for idx, ticker in enumerate(remaining):
        print(f"  {idx+1}/{len(remaining)}: {ticker}...", end=' ')
        sys.stdout.flush()
        
        try:
            raw = q.history(symbol=ticker, start='2022-01-01', end='2024-12-31', interval='1D')
            if raw is not None and len(raw) > 0:
                raw = raw.copy()
                raw.columns = [c.lower() for c in raw.columns]
                date_col = 'time' if 'time' in raw.columns else 'date'
                if date_col != 'date':
                    raw = raw.rename(columns={date_col: 'date'})
                
                records = []
                for _, row in raw.iterrows():
                    try:
                        records.append({
                            'ticker': ticker,
                            'date': str(row['date'])[:10],
                            'open': float(row['open']) if pd.notna(row.get('open',0)) else None,
                            'high': float(row['high']) if pd.notna(row.get('high',0)) else None,
                            'low': float(row['low']) if pd.notna(row.get('low',0)) else None,
                            'close': float(row['close']) if pd.notna(row.get('close',0)) else None,
                            'volume': int(float(row['volume'])) if pd.notna(row.get('volume',0)) else None,
                        })
                    except:
                        continue
                
                if records:
                    for vstart in range(0, len(records), 200):
                        vbatch = records[vstart:vstart+200]
                        try:
                            supabase.table('daily_bars').upsert(vbatch, on_conflict='ticker,date').execute()
                        except:
                            pass
                
                print(f"{len(records)} rows")
                pulled += 1
            else:
                print("no data")
                failed += 1
        except Exception as e:
            err = str(e)[:80]
            if 'RateLimit' in err:
                print("rate limit, waiting 60s...")
                time.sleep(60)
                try:
                    raw = q.history(symbol=ticker, start='2022-01-01', end='2024-12-31', interval='1D')
                    if raw is not None and len(raw) > 0:
                        print(f"  Retry OK")
                        pulled += 1
                    else:
                        failed += 1
                except:
                    failed += 1
            else:
                print(f"FAIL: {err}")
                failed += 1
        
        time.sleep(3.5)
        if (idx + 1) % 15 == 0:
            print(f"  --- Cool down 5s ---")
            time.sleep(5)
    
    print(f"\nPulled: {pulled} success, {failed} failed")
else:
    print("All tickers already loaded!")

# Final summary
result = supabase.table('daily_bars').select('ticker', count='exact').limit(1).execute()
r2 = supabase.table('daily_bars').select('ticker').execute()
tickers_final = set(r['ticker'] for r in r2.data)
print(f"\n=== FINAL ===")
print(f"daily_bars: count={result.count}, unique tickers={len(tickers_final)}")
print(f"Tickers: {sorted(tickers_final)}")
print("\nDone!")

