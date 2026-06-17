#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create Supabase tables via Management API, then upload data"""
import sys, os, time, json, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
warnings.filterwarnings('ignore')

import httpx
import pandas as pd
import numpy as np

PAT = '<SUPABASE_PAT>'
PROJECT_REF = 'xgbficilqacfnzrbftoo'

HEADERS = {
    'Authorization': f'Bearer {PAT}',
    'Content-Type': 'application/json',
}

sql_url = f'https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query'
api_url = f'https://{PROJECT_REF}.supabase.co'

print("=" * 60)
print("STEP 1: Testing Management API connection")
print("=" * 60)

with httpx.Client(timeout=30) as client:
    r = client.post(sql_url, json={"query": "SELECT 1 AS test"}, headers=HEADERS)
    print(f"Status: {r.status_code}")
    if r.status_code in (200, 201):
        print(f"Response: {r.text[:200]}")
        print("Connection OK!")
    else:
        print(f"Error: {r.text[:300]}")
        sys.exit(1)
    
    # ============================================================
    # STEP 2: Create tables
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 2: Creating tables")
    print("=" * 60)
    
    create_statements = [
        "CREATE TABLE IF NOT EXISTS daily_bars (ticker TEXT NOT NULL, date DATE NOT NULL, open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION, volume BIGINT, created_at TIMESTAMPTZ DEFAULT NOW(), PRIMARY KEY (ticker, date));",
        "CREATE TABLE IF NOT EXISTS signals (id BIGSERIAL PRIMARY KEY, ticker TEXT NOT NULL, date DATE NOT NULL, close DOUBLE PRECISION, ema20 DOUBLE PRECISION, ema50 DOUBLE PRECISION, ema200 DOUBLE PRECISION, rsi_14 DOUBLE PRECISION, atr14 DOUBLE PRECISION, vol_ratio DOUBLE PRECISION, signal TEXT, signal_type TEXT, created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(ticker, date, signal_type));",
        "CREATE TABLE IF NOT EXISTS backtest_results (id BIGSERIAL PRIMARY KEY, run_date TIMESTAMPTZ DEFAULT NOW(), config JSONB, total_trades INTEGER, win_rate DOUBLE PRECISION, total_return DOUBLE PRECISION, cagr DOUBLE PRECISION, sharpe DOUBLE PRECISION, max_drawdown DOUBLE PRECISION, final_nav DOUBLE PRECISION, trades_json JSONB, equity_curve_json JSONB);",
        "CREATE TABLE IF NOT EXISTS portfolio_state (id BIGSERIAL PRIMARY KEY, date DATE NOT NULL, nav DOUBLE PRECISION, cash DOUBLE PRECISION, positions JSONB, created_at TIMESTAMPTZ DEFAULT NOW());"
    ]
    
    table_names = ['daily_bars', 'signals', 'backtest_results', 'portfolio_state']
    for i, (name, stmt) in enumerate(zip(table_names, create_statements)):
        r = client.post(sql_url, json={"query": stmt}, headers=HEADERS)
        if r.status_code in (200, 201):
            print(f"  [{i+1}/4] {name}: CREATED")
        else:
            print(f"  [{i+1}/4] {name}: {r.status_code} {r.text[:100]}")
    
    # Verify tables exist
    r = client.post(sql_url, json={"query": "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"}, headers=HEADERS)
    if r.status_code in (200, 201):
        tables = r.json()
        print(f"\n  Existing tables: {[t[0] if isinstance(t, list) else t.get('table_name','?') for t in tables]}")
    
    # ============================================================
    # STEP 3: Upload CSV data via SQL INSERT
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 3: Uploading CSV data")
    print("=" * 60)
    
    csv_path = os.path.join(os.path.dirname(__file__), 'vn100_data_2022_2024.csv')
    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}")
    else:
        df = pd.read_csv(csv_path)
        print(f"Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")
        
        # Clear existing
        client.post(sql_url, json={"query": "TRUNCATE daily_bars"}, headers=HEADERS)
        
        BATCH_SIZE = 200
        total = len(df)
        inserted = 0
        
        for start in range(0, total, BATCH_SIZE):
            batch = df.iloc[start:start+BATCH_SIZE]
            values = []
            for _, row in batch.iterrows():
                try:
                    o = float(row['open']) if pd.notna(row['open']) else 'NULL'
                    h = float(row['high']) if pd.notna(row['high']) else 'NULL'
                    l = float(row['low']) if pd.notna(row['low']) else 'NULL'
                    c = float(row['close']) if pd.notna(row['close']) else 'NULL'
                    v = int(float(row['volume'])) if pd.notna(row['volume']) else 'NULL'
                    d = str(row['date'])[:10]
                    t = str(row['ticker']).strip().replace("'", "''")
                    values.append(f"('{t}','{d}',{o},{h},{l},{c},{v})")
                except:
                    continue
            
            if values:
                sql = f"INSERT INTO daily_bars (ticker,date,open,high,low,close,volume) VALUES {','.join(values)} ON CONFLICT (ticker,date) DO NOTHING"
                r = client.post(sql_url, json={"query": sql}, headers=HEADERS, timeout=60)
                if r.status_code in (200, 201):
                    inserted += len(values)
                elif r.status_code == 503:
                    print(f"  Timeout at {start}, retrying...")
                    time.sleep(2)
                    r = client.post(sql_url, json={"query": sql}, headers=HEADERS, timeout=60)
                    if r.status_code in (200, 201):
                        inserted += len(values)
                else:
                    print(f"  Error at {start}: {r.status_code} {r.text[:150]}")
            
            if (start // BATCH_SIZE) % 5 == 0:
                print(f"  Progress: {min(start+BATCH_SIZE, total)}/{total}")
        
        print(f"Inserted: {inserted} rows")
        
        # Verify
        r = client.post(sql_url, json={"query": "SELECT COUNT(*) FROM daily_bars"}, headers=HEADERS)
        if r.status_code == 200:
            count = r.json()
            print(f"Verified: {count[0][0] if isinstance(count, list) else count} rows")
    
    # ============================================================
    # STEP 4: Pull remaining VN100 tickers
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 4: Pulling remaining VN100 tickers from vnstock")
    print("=" * 60)
    
    try:
        from vnstock import Quote
        
        # Get existing tickers
        r = client.post(sql_url, json={"query": "SELECT DISTINCT ticker FROM daily_bars ORDER BY ticker"}, headers=HEADERS)
        existing = set()
        if r.status_code == 200:
            rows = r.json()
            for row in rows:
                existing.add(row[0] if isinstance(row, list) else row.get('ticker',''))
        
        print(f"Existing: {len(existing)} tickers")
        
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
            q = Quote(source='VCI')
            pulled = 0; failed = 0
            
            for idx, ticker in enumerate(remaining):
                print(f"  {idx+1}/{len(remaining)}: {ticker}...", end=' ')
                sys.stdout.flush()
                
                try:
                    raw = q.history(symbol=ticker, start='2022-01-01', end='2024-12-31', interval='1D')
                    if raw is not None and len(raw) > 0:
                        raw = raw.copy()
                        raw.columns = [c.lower() for c in raw.columns]
                        raw['ticker'] = ticker
                        date_col = 'time' if 'time' in raw.columns else 'date'
                        if date_col != 'date':
                            raw = raw.rename(columns={date_col: 'date'})
                        
                        values = []
                        for _, row in raw.iterrows():
                            try:
                                d = str(row['date'])[:10]
                                o = float(row['open']) if pd.notna(row.get('open',0)) else 'NULL'
                                h = float(row['high']) if pd.notna(row.get('high',0)) else 'NULL'
                                l = float(row['low']) if pd.notna(row.get('low',0)) else 'NULL'
                                c = float(row['close']) if pd.notna(row.get('close',0)) else 'NULL'
                                v = int(float(row['volume'])) if pd.notna(row.get('volume',0)) else 'NULL'
                                t = ticker.replace("'","''")
                                values.append(f"('{t}','{d}',{o},{h},{l},{c},{v})")
                            except:
                                continue
                        
                        if values:
                            for vstart in range(0, len(values), 200):
                                vbatch = values[vstart:vstart+200]
                                sql = f"INSERT INTO daily_bars (ticker,date,open,high,low,close,volume) VALUES {','.join(vbatch)} ON CONFLICT (ticker,date) DO NOTHING"
                                rr = client.post(sql_url, json={"query": sql}, headers=HEADERS, timeout=60)
                                if rr.status_code not in (200, 201):
                                    pass
                        
                        print(f"{len(values)} rows")
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
                                print(f"  Retry OK: {ticker}")
                                pulled += 1
                            else:
                                failed += 1
                        except:
                            failed += 1
                    else:
                        print(f"FAIL: {err}")
                        failed += 1
                
                time.sleep(3.5)
                
                # Every 15 tickers, longer cool down
                if (idx + 1) % 15 == 0:
                    print(f"  --- Cool down 5s ---")
                    time.sleep(5)
        
        print(f"\nDone: {pulled} success, {failed} failed")
        
        # Final count
        r = client.post(sql_url, json={"query": "SELECT COUNT(*), COUNT(DISTINCT ticker) FROM daily_bars"}, headers=HEADERS)
        if r.status_code == 200:
            res = r.json()
            print(f"\nFinal daily_bars: {res}")
    
    except ImportError:
        print("vnstock not available")
    except Exception as e:
        print(f"Error: {str(e)[:200]}")
        import traceback
        traceback.print_exc()

print("\nAll done!")

