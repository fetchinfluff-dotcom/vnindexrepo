"""Debug: check why backtest produces 0 trades"""
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

# Same feature code as backtest
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

# Check signals for 1 specific date
test_date = pd.Timestamp('2024-10-09')
print(f"Checking signals for {test_date.date()}")
print(f"Total tickers in data: {len(ticker_data)}")

signals_found = 0
for t, tdf in ticker_data.items():
    row = tdf[tdf['date']==test_date]
    if len(row)==0: continue
    r = row.iloc[0]
    
    try:
        macro = bool(r['close'] > r['ema200'] and r['ema50'] > r['ema200'])
        momentum = bool(r['close'] > r['ema20'])
        vol_ok = bool(not np.isnan(r['vol_ratio']) and r['vol_ratio'] > 1.2)
        bullish = bool(r['bullish'])
        rsi_ok = bool(not np.isnan(r['rsi14']) and r['rsi14'] < 70)
        
        if all([macro, momentum, vol_ok, bullish, rsi_ok]):
            print(f"  SIGNAL: {t} close={r['close']:.0f} ema20={r['ema20']:.0f} ema200={r['ema200']:.0f} vr={r['vol_ratio']:.2f} rsi={r['rsi14']:.1f}")
            signals_found += 1
        
        # Check partial conditions
        partial = macro + momentum + vol_ok + bullish + rsi_ok
        if partial >= 4 and not all([macro, momentum, vol_ok, bullish, rsi_ok]):
            missing = []
            if not macro: missing.append('macro')
            if not momentum: missing.append('mom')
            if not vol_ok: missing.append('vol')
            if not bullish: missing.append('bull')
            if not rsi_ok: missing.append('rsi')
            print(f"  NEAR MISS: {t} {', '.join(missing)} close={r['close']:.0f} ema20={r['ema20']:.0f} ema200={r['ema200']:.0f} vr={r['vol_ratio']:.2f} rsi={r['rsi14']:.1f}")
    except Exception as e:
        print(f"  ERROR {t}: {e}")

print(f"Total signals on {test_date.date()}: {signals_found}")

