#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create Supabase tables and upload data"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'

import warnings
warnings.filterwarnings('ignore')
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
import time
import json

# Connection parameters
conn_params = {
    'host': 'aws-0-ap-southeast-1.pooler.supabase.com',
    'port': 5432,
    'dbname': 'postgres',
    'user': 'postgres.xgbficilqacfnzrbftoo',
    'password': 'F-J!vatv72hA3q@',
    'connect_timeout': 30,
}

print("=" * 60)
print("Connecting to Supabase PostgreSQL...")
print("=" * 60)

conn = psycopg2.connect(**conn_params)
conn.autocommit = True
cur = conn.cursor()
print("Connected successfully!")

# ============================================================
# STEP 1: Create tables
# ============================================================
print("\n" + "=" * 60)
print("Creating tables...")
print("=" * 60)

create_statements = [
    """
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
    """,
    """
    CREATE TABLE IF NOT EXISTS signals (
        id BIGSERIAL PRIMARY KEY,
        ticker TEXT NOT NULL,
        date DATE NOT NULL,
        close DOUBLE PRECISION,
        ema20 DOUBLE PRECISION,
        ema50 DOUBLE PRECISION,
        ema200 DOUBLE PRECISION,
        rsi_14 DOUBLE PRECISION,
        atr14 DOUBLE PRECISION,
        vol_ratio DOUBLE PRECISION,
        signal TEXT,
        signal_type TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(ticker, date, signal_type)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_results (
        id BIGSERIAL PRIMARY KEY,
        run_date TIMESTAMPTZ DEFAULT NOW(),
        config JSONB,
        total_trades INTEGER,
        win_rate DOUBLE PRECISION,
        total_return DOUBLE PRECISION,
        cagr DOUBLE PRECISION,
        sharpe DOUBLE PRECISION,
        max_drawdown DOUBLE PRECISION,
        final_nav DOUBLE PRECISION,
        trades_json JSONB,
        equity_curve_json JSONB
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_state (
        id BIGSERIAL PRIMARY KEY,
        date DATE NOT NULL,
        nav DOUBLE PRECISION,
        cash DOUBLE PRECISION,
        positions JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
]

for i, stmt in enumerate(create_statements):
    try:
        cur.execute(stmt)
        print(f"  Table {i+1}/4 created successfully")
    except Exception as e:
        print(f"  Table {i+1}/4 error: {str(e)[:100]}")

# Verify tables exist
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' ORDER BY table_name
""")
tables = [r[0] for r in cur.fetchall()]
print(f"\nExisting tables: {tables}")

# ============================================================
# STEP 2: Upload CSV data
# ============================================================
print("\n" + "=" * 60)
print("Uploading CSV data to daily_bars...")
print("=" * 60)

csv_path = os.path.join(os.path.dirname(__file__), 'vn100_data_2022_2024.csv')
if not os.path.exists(csv_path):
    print(f"CSV not found at {csv_path}")
else:
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows, {df['ticker'].nunique()} tickers")
    
    # Insert in batches
    batch_size = 500
    total = len(df)
    inserted = 0
    
    # Clear existing data for clean insert
    cur.execute("TRUNCATE daily_bars")
    
    for start in range(0, total, batch_size):
        batch = df.iloc[start:start+batch_size]
        values = []
        for _, row in batch.iterrows():
            ticker = str(row['ticker']).strip()
            date = str(row['date'])[:10]
            try:
                o = float(row['open']) if pd.notna(row['open']) else 'NULL'
                h = float(row['high']) if pd.notna(row['high']) else 'NULL'
                l = float(row['low']) if pd.notna(row['low']) else 'NULL'
                c = float(row['close']) if pd.notna(row['close']) else 'NULL'
                v = int(float(row['volume'])) if pd.notna(row['volume']) else 'NULL'
                values.append(f"('{ticker}', '{date}', {o}, {h}, {l}, {c}, {v})")
            except:
                continue
        
        if values:
            sql = f"INSERT INTO daily_bars (ticker, date, open, high, low, close, volume) VALUES {','.join(values)} ON CONFLICT (ticker, date) DO NOTHING"
            try:
                cur.execute(sql)
                inserted += len(values)
            except Exception as e:
                print(f"  Error at row {start}: {str(e)[:100]}")
        
        if (start // batch_size) % 5 == 0:
            print(f"  Progress: {min(start+batch_size, total)}/{total}")
    
    print(f"Inserted: {inserted} rows")
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM daily_bars")
    count = cur.fetchone()[0]
    print(f"Verified: {count} rows in daily_bars")

# ============================================================
# STEP 3: Check for vnstock and pull more tickers
# ============================================================
print("\n" + "=" * 60)
print("STEP 3: Pull remaining VN100 tickers from vnstock")
print("=" * 60)

try:
    from vnstock import Quote
    
    # All VN100 tickers (the ones we haven't pulled yet)
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
    
    # Check which tickers we already have
    cur.execute("SELECT DISTINCT ticker FROM daily_bars")
    existing = set(r[0] for r in cur.fetchall())
    print(f"Already have: {len(existing)} tickers")
    
    remaining = [t for t in all_tickers if t not in existing]
    print(f"Remaining: {len(remaining)} tickers")
    
    if remaining:
        q = Quote(source='VCI')
        pulled = 0
        failed = 0
        
        for idx, ticker in enumerate(remaining):
            try:
                print(f"  Pulling {idx+1}/{len(remaining)}: {ticker}...", end=' ')
                raw = q.history(symbol=ticker, start='2022-01-01', end='2024-12-31', interval='1D')
                if raw is not None and len(raw) > 0:
                    raw = raw.copy()
                    raw.columns = [c.lower() for c in raw.columns]
                    raw['ticker'] = ticker
                    
                    # Map columns (vnstock uses 'time' for date)
                    date_col = 'time' if 'time' in raw.columns else 'date'
                    raw = raw.rename(columns={date_col: 'date'})
                    
                    # Insert into DB
                    values = []
                    for _, row in raw.iterrows():
                        d = str(row['date'])[:10]
                        try:
                            o = float(row['open']) if pd.notna(row.get('open', None)) else 'NULL'
                            h = float(row['high']) if pd.notna(row.get('high', None)) else 'NULL'
                            l = float(row['low']) if pd.notna(row.get('low', None)) else 'NULL'
                            c = float(row['close']) if pd.notna(row.get('close', None)) else 'NULL'
                            v = int(float(row['volume'])) if pd.notna(row.get('volume', None)) else 'NULL'
                            values.append(f"('{ticker}', '{d}', {o}, {h}, {l}, {c}, {v})")
                        except:
                            continue
                    
                    if values:
                        # Insert in sub-batches of 200
                        for v_start in range(0, len(values), 200):
                            v_batch = values[v_start:v_start+200]
                            sql = f"INSERT INTO daily_bars (ticker, date, open, high, low, close, volume) VALUES {','.join(v_batch)} ON CONFLICT (ticker, date) DO NOTHING"
                            cur.execute(sql)
                    
                    print(f"{len(values)} rows")
                    pulled += 1
                else:
                    print("no data")
                    failed += 1
            except Exception as e:
                err = str(e)[:80]
                if 'RateLimit' in err:
                    print(f"RATE LIMITED - waiting 60s...")
                    time.sleep(60)
                    # Retry once
                    try:
                        raw = q.history(symbol=ticker, start='2022-01-01', end='2024-12-31', interval='1D')
                        if raw is not None and len(raw) > 0:
                            print(f"  Retry success: {ticker}")
                            pulled += 1
                        else:
                            print(f"  Retry failed: no data")
                            failed += 1
                    except:
                        print(f"  Retry also failed")
                        failed += 1
                else:
                    print(f"FAILED: {err}")
                    failed += 1
            
            # Rate limit: wait 3.5s between requests
            if (idx + 1) % 15 == 0:
                print(f"  Cooling down for 5s...")
                time.sleep(5)
            else:
                time.sleep(3.5)
        
        print(f"\nPull complete: {pulled} success, {failed} failed")
    
    # Final count
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM daily_bars")
    total_rows, total_tickers = cur.fetchone()
    print(f"\nFinal daily_bars: {total_rows} rows, {total_tickers} tickers")
    
except ImportError:
    print("vnstock not available, skipping additional data pull")
except Exception as e:
    print(f"Error pulling data: {str(e)[:200]}")
    import traceback
    traceback.print_exc()

# Cleanup
cur.close()
conn.close()
print("\nDone!")
