#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix: Create Supabase tables and rerun data pipeline with proper encoding
"""
import sys
import os
# Force UTF-8 encoding globally
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdin.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
import logging
logging.getLogger().setLevel(logging.ERROR)

# Suppress all banners
os.environ['VNSTOCK_SUPPRESS_NOTICE'] = 'true'
os.environ['VNSTOCK_DISABLE_BANNER'] = '1'

print("=" * 60)
print("STEP 1: Creating Supabase Tables")
print("=" * 60)

from supabase import create_client

supabase_url = "https://xgbficilqacfnzrbftoo.supabase.co"
supabase_key = "<SUPABASE_KEY>"

supabase = create_client(supabase_url, supabase_key)
print("Supabase client created")

# Create tables using the Supabase management API (execute_raw_sql if available)
# Try direct table creation with a simple insert test
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

# Supabase doesn't support raw SQL directly in client
# We need to use the management REST API or insert a test row
# Let's try upserting a test row - if table doesn't exist, we'll create via REST API

# Check if table exists by trying to select
try:
    result = supabase.table('daily_bars').select('*').limit(1).execute()
    print("daily_bars table already exists")
except Exception as e:
    error_msg = str(e)
    if 'relation' in error_msg.lower() or 'PGRST205' in error_msg or 'does not exist' in error_msg:
        print("daily_bars table does not exist. Need to create via Supabase SQL editor.")
        print("Please run the following SQL in Supabase SQL Editor:")
        print()
        for stmt in create_statements:
            print(stmt)
            print()
    else:
        print(f"Error checking table: {error_msg[:100]}")

# Try to check/create signals table
try:
    result = supabase.table('signals').select('*').limit(1).execute()
    print("signals table already exists")
except Exception as e:
    error_msg = str(e)
    if 'relation' in error_msg.lower() or 'PGRST205' in error_msg:
        print("signals table does not exist. Create via SQL.")

print("\n" + "=" * 60)
print("STEP 2: Loading data from CSV and uploading to Supabase")
print("=" * 60)

# Load the previously saved CSV data
csv_path = os.path.join(os.path.dirname(__file__), 'vn100_data_2022_2024.csv')
if os.path.exists(csv_path):
    df = pd.read_csv(csv_path)
    print(f"Loaded CSV: {df.shape}")
    print(f"Tickers: {df['ticker'].nunique()}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    
    # Try to insert in batches
    batch_size = 1000
    total_rows = len(df)
    inserted = 0
    errors = 0
    
    for start in range(0, total_rows, batch_size):
        batch = df.iloc[start:start+batch_size]
        records = batch.to_dict('records')
        
        # Clean records
        for r in records:
            for col in ['open', 'high', 'low', 'close']:
                if col in r and pd.notna(r[col]):
                    r[col] = float(r[col])
                elif col in r:
                    r[col] = None
            if 'volume' in r and pd.notna(r['volume']):
                r['volume'] = int(float(r['volume']))
            elif 'volume' in r:
                r['volume'] = None
        
        try:
            result = supabase.table('daily_bars').upsert(records, on_conflict='ticker,date').execute()
            inserted += len(records)
            if start % 5000 == 0:
                print(f"  Inserted: {inserted}/{total_rows}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  Error at {start}: {str(e)[:150]}")
    
    print(f"\nInsert result: {inserted} rows, {errors} errors")
else:
    print(f"CSV not found at: {csv_path}")
    print("Please run the pipeline script first to generate data")

print("\n" + "=" * 60)
print("STEP 3: Verify data in Supabase")
print("=" * 60)

try:
    result = supabase.table('daily_bars').select('ticker', count='exact').limit(1).execute()
    print(f"Data count: {result.count}")
except Exception as e:
    print(f"Verify error: {str(e)[:100]}")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)

# Now run the actual backtest using saved CSV data
print("\n" + "=" * 60)
print("BONUS: Running quick backtest on saved data")
print("=" * 60)

if os.path.exists(csv_path):
    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['ticker', 'date'])
    
    # For each ticker, compute features and signals
    for ticker in df['ticker'].unique():
        tdf = df[df['ticker'] == ticker].copy()
        if len(tdf) < 250:
            continue
            
        tdf['close'] = tdf['close'].astype(float)
        tdf['high'] = tdf['high'].astype(float)
        tdf['low'] = tdf['low'].astype(float)
        tdf['open'] = tdf['open'].astype(float)
        tdf['volume'] = tdf['volume'].astype(float)
        
        # EMAs
        tdf['ema200'] = tdf['close'].ewm(span=200, adjust=False).mean()
        tdf['ema50'] = tdf['close'].ewm(span=50, adjust=False).mean()
        tdf['ema20'] = tdf['close'].ewm(span=20, adjust=False).mean()
        
        # Volume MA
        tdf['vol_ma20'] = tdf['volume'].rolling(20).mean()
        tdf['vol_ratio'] = tdf['volume'] / tdf['vol_ma20']
        
        # Entry Signal
        tdf['macro_bull'] = (tdf['close'] > tdf['ema200']) & (tdf['ema50'] > tdf['ema200'])
        tdf['pullback'] = (tdf['close'] <= tdf['ema20'] * 1.01) & (tdf['close'] >= tdf['ema20'] * 0.99)
        tdf['volume_surge'] = tdf['vol_ratio'] > 1.2
        tdf['bullish_candle'] = (tdf['close'] > tdf['open']) & ((tdf['close'] - tdf['open']) > (tdf['high'] - tdf['low']) * 0.5)
        
        tdf['entry_signal'] = tdf['macro_bull'] & tdf['pullback'] & tdf['volume_surge'] & tdf['bullish_candle']
        
        # Exit
        tdf['trend_break'] = tdf['close'] < tdf['ema200']
        
        n_signals = tdf['entry_signal'].sum()
        if n_signals > 0:
            print(f"  {ticker}: {n_signals} signals | Macro Bull: {tdf['macro_bull'].mean()*100:.0f}% | Date: {tdf['date'].iloc[0].strftime('%Y-%m-%d')} to {tdf['date'].iloc[-1].strftime('%Y-%m-%d')}")

print("\nDone!")


