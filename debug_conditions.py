"""Pinpoint: why does backtest see 0 candidates on 2024-10-09?"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import httpx, pandas as pd, numpy as np

PAT = '<SUPABASE_PAT>'
sql_url = 'https://api.supabase.com/v1/projects/xgbficilqacfnzrbftoo/database/query'
r = httpx.post(sql_url, json={"query": "SELECT ticker, date, close, open, high, low, volume FROM daily_bars ORDER BY ticker, date"},
               headers={'Authorization': f'Bearer {PAT}', 'Content-Type': 'application/json'}, timeout=120)
rows = r.json()
df = pd.DataFrame(rows)
df['date'] = pd.to_datetime(df['date'])
for c in ['close','open','high','low','volume']: df[c]=pd.to_numeric(df[c],errors='coerce')

# EXACT same feature code as backtest_full.py
tickers = sorted(df['ticker'].unique())

def np_ema(arr, s):
    n=len(arr); r=np.empty(n); r[:]=np.nan
    m=2/(s+1); r[0]=arr[0]
    for i in range(1,n): r[i]=(arr[i]-r[i-1])*m+r[i-1]
    return r

ticker_data = {}
for t in tickers:
    tdf = df[df['ticker']==t].sort_values('date')
    if len(tdf) < 250: continue
    c=tdf['close'].values; h=tdf['high'].values; l=tdf['low'].values
    o=tdf['open'].values; v=tdf['volume'].values; n=len(tdf)
    
    tdf['ema20']=np_ema(c,20); tdf['ema50']=np_ema(c,50); tdf['ema200']=np_ema(c,200)
    
    delta=np.diff(c); g=np.where(delta>0,delta,0); ls=np.where(delta<0,-delta,0)
    ag=np.empty(n); al=np.empty(n); ag[:]=np.nan; al[:]=np.nan
    ag[14]=np.mean(g[:14]); al[14]=np.mean(ls[:14])
    for i in range(15,n):
        ag[i]=(ag[i-1]*13+g[i-1])/14; al[i]=(al[i-1]*13+ls[i-1])/14
    rs=ag/np.where(al==0,0.001,al); tdf['rsi14']=100-(100/(1+rs))
    
    tr=np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    at=np.empty(n); at[:]=np.nan; at[14]=np.mean(tr[:14])
    for i in range(15,n): at[i]=(at[i-1]*13+tr[i-1])/14
    tdf['atr14']=at
    
    vm=np.empty(n); vm[:]=np.nan
    for i in range(19,n): vm[i]=np.mean(v[i-19:i+1])
    tdf['vol_ratio']=v/np.where(vm==0,1,vm)
    
    body=np.abs(c-o); cr=h-l; cr=np.where(cr==0,0.001,cr)
    tdf['bullish']=(c>o)&(body/cr>=0.4)
    
    ticker_data[t]=tdf

# Check 2024-10-09 with EXACT same condition as backtest
test_date = pd.Timestamp('2024-10-09')
d = test_date
VOL_SURGE = 1.2
R_UPPER = 70

print(f"Testing {d.date()}")
print(f"ticker_data count: {len(ticker_data)}")
print()

for t, tdf in list(ticker_data.items())[:30]:  # First 30
    row = tdf[tdf['date']==d]
    if len(row)==0: 
        print(f"  {t}: no row for date")
        continue
    r = row.iloc[0]
    
    if pd.isna(r.get('ema200')):
        print(f"  {t}: ema200 is NaN")
        continue
    
    # EXACT condition from backtest
    macro_bull = bool(r['close'] > r['ema200']) & bool(r['ema50'] > r['ema200'])
    momentum = bool(r['close'] > r['ema20'])
    vol_ok = not np.isnan(r['vol_ratio']) and r['vol_ratio'] > VOL_SURGE
    rsi_ok = not np.isnan(r['rsi14']) and r['rsi14'] < R_UPPER
    
    conditions = {
        'macro': bool(r['close'] > r['ema200']) & bool(r['ema50'] > r['ema200']),
        'mom': bool(r['close'] > r['ema20']),
        'vol': bool(not np.isnan(r['vol_ratio']) and r['vol_ratio'] > VOL_SURGE),
        'bull': bool(r['bullish']),
        'rsi': bool(not np.isnan(r['rsi14']) and r['rsi14'] < R_UPPER),
    }
    all_ok = macro_bull and momentum and vol_ok and r['bullish'] and rsi_ok
    
    if all_ok:
        print(f"  ✓ {t}: ALL CONDITIONS MET close={r['close']}")
    else:
        failed = [k for k,v in conditions.items() if not v]
        print(f"  ✗ {t}: missing {', '.join(failed)} close={r['close']:.0f} e20={r.get('ema20',0):.0f} e50={r.get('ema50',0):.0f} e200={r.get('ema200',0):.0f} vr={r.get('vol_ratio',0):.2f} rsi={r.get('rsi14',0):.1f} bull={r.get('bullish',False)}")

