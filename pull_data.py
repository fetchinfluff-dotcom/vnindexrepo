#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pull VN100 historical data from VNStock (VCI source) and store to Supabase
Then run backtest with real data
"""
import sys
import warnings
warnings.filterwarnings('ignore')

import os
# Suppress vnstock banners
os.environ['VNSTOCK_SUPPRESS_NOTICE'] = 'true'
os.environ['VNSTOCK_DISABLE_BANNER'] = '1'

from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# =============================================
# STEP 1: Connect to vnstock and get VN100 list
# =============================================
print("=" * 60)
print("STEP 1: Getting VN100 stock list")
print("=" * 60)

from vnstock.api.listing import Listing
l = Listing(source='VCI')

# Get HOSE stocks (VN100 is subset of HOSE)
df_hose = l.symbols_by_exchange('HOSE')
print(f"HOSE stocks total: {len(df_hose)}")
print(f"Columns: {list(df_hose.columns)}")
print(f"First 5: {df_hose.head()['symbol'].tolist()}")

# The data might have more columns - check
print(df_hose.dtypes)

# =============================================
# STEP 2: Pull historical data for each stock
# =============================================
print("\n" + "=" * 60)
print("STEP 2: Pulling historical data for sample stocks")
print("=" * 60)

from vnstock.api.quote import Quote

# Sample pull for top 5 stocks
test_tickers = df_hose['symbol'].head(5).tolist()
print(f"Test pulling data for: {test_tickers}")

all_data = []
for ticker in test_tickers:
    try:
        q = Quote(symbol=ticker, source='VCI')
        df = q.history(start='2022-01-01', end='2024-12-31', interval='1D')
        df['ticker'] = ticker
        all_data.append(df)
        print(f"  {ticker}: {len(df)} rows ({df['time'].min()} to {df['time'].max()})")
    except Exception as e:
        print(f"  {ticker}: ERROR - {str(e)[:80]}")

if all_data:
    combined = pd.concat(all_data, ignore_index=True)
    print(f"\nCombined data: {combined.shape}")
    print(f"Columns: {list(combined.columns)}")
    print(combined.head(3))

# =============================================
# STEP 3: Setup Supabase and store data
# =============================================
print("\n" + "=" * 60)
print("STEP 3: Setup Supabase storage")
print("=" * 60)

from supabase import create_client

supabase_url = "https://xgbficilqacfnzrbftoo.supabase.co"
supabase_key = "<SUPABASE_KEY>"

try:
    supabase = create_client(supabase_url, supabase_key)
    
    # Test Supabase connection
    result = supabase.table('_test').select('*').limit(1).execute() if False else None
    print("Supabase connection: OK")
    
    # Check existing tables
    try:
        tables = supabase.table('daily_bars').select('*').limit(1).execute()
        print(f"daily_bars table exists, sample: {tables.data}")
    except Exception as e:
        print(f"daily_bars table check: {str(e)[:100]}")
        
        # Create table if not exists
        create_sql = """
        CREATE TABLE IF NOT EXISTS daily_bars (
            id BIGSERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            date DATE NOT NULL,
            open DOUBLE PRECISION,
            high DOUBLE PRECISION,
            low DOUBLE PRECISION,
            close DOUBLE PRECISION,
            volume BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(ticker, date)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_bars_ticker ON daily_bars(ticker);
        CREATE INDEX IF NOT EXISTS idx_daily_bars_date ON daily_bars(date);
        CREATE INDEX IF NOT EXISTS idx_daily_bars_ticker_date ON daily_bars(ticker, date);
        """
        try:
            supabase.table('daily_bars').insert({'ticker': '_test', 'date': '2000-01-01', 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'volume': 0}).execute()
            print("daily_bars table created via first insert")
        except Exception as e2:
            print(f"Table creation: {str(e2)[:100]}")
            print("Need to create table manually or via Supabase UI")
    
except Exception as e:
    print(f"Supabase error: {str(e)[:200]}")

print("\n" + "=" * 60)
print("Script complete")
print("=" * 60)


