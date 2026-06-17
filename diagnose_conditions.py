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

# Pick a few representative tickers
test_tickers = ['ACB', 'FPT', 'HPG', 'MWG', 'VCB', 'GAS', 'VNM', 'SSI']

for t in test_tickers:
    tdf = df[df['ticker']==t].sort_values('date').copy()
    c=tdf['close'].values; h=tdf['high'].values; l=tdf['low'].values
    o=tdf['open'].values; v=tdf['volume'].values
    n=len(tdf)
    if n<250: continue
    
    def e(arr,s):
        r=np.empty(n); r[:]=np.nan; m=2/(s+1); r[0]=arr[0]
        for i in range(1,n): r[i]=(arr[i]-r[i-1])*m+r[i-1]
        return r
    e20=e(c,20); e50=e(c,50); e200=e(c,200)
    delta=np.diff(c); g=np.where(delta>0,delta,0); ls=np.where(delta<0,-delta,0)
    ag=np.empty(n); al=np.empty(n); ag[:]=np.nan; al[:]=np.nan
    ag[14]=np.mean(g[:14]); al[14]=np.mean(ls[:14])
    for i in range(15,n):
        ag[i]=(ag[i-1]*13+g[i-1])/14; al[i]=(al[i-1]*13+ls[i-1])/14
    rs=ag/np.where(al==0,0.001,al); r14=100-(100/(1+rs))
    vm=np.empty(n); vm[:]=np.nan
    for i in range(19,n): vm[i]=np.mean(v[i-19:i+1])
    vr=v/np.where(vm==0,1,vm)
    body=np.abs(c-o); cr=h-l; cr=np.where(cr==0,0.001,cr)
    bc=(c>o)&(body/cr>=0.4)
    
    # Conditions
    mb=(c>e200)&(e50>e200)  # macro_bull
    mom=(c>e20)             # momentum
    vs=vr>1.2               # vol_surge
    rok=r14<70              # rsi_ok
    
    combined=mb&mom&vs&bc&rok
    
    # Count each condition only where ema200 exists
    valid=~np.isnan(e200)
    print(f"\n{t} ({n} rows):")
    print(f"  macro_bull:    {mb.sum()} / {valid.sum()} = {mb.sum()/valid.sum()*100:.0f}%")
    print(f"  momentum:      {mom.sum()} / {valid.sum()} = {mom.sum()/valid.sum()*100:.0f}%")
    print(f"  vol_surge:     {vs.sum()} / {valid.sum()} = {vs.sum()/valid.sum()*100:.0f}%")
    print(f"  bullish:       {bc.sum()} / {valid.sum()} = {bc.sum()/valid.sum()*100:.0f}%")
    print(f"  rsi_ok:        {rok.sum()} / {valid.sum()} = {rok.sum()/valid.sum()*100:.0f}%")
    print(f"  ALL 5:         {combined.sum()} / {valid.sum()}")
    
    # Show dates when combined is true
    if combined.sum() > 0:
        sig_dates = tdf['date'].values[valid][combined[valid]]
        print(f"  Signal dates: {[str(d)[:10] for d in sig_dates]}")
    else:
        # Show most restrictive conditions
        print(f"  mb+mom+vs:     {(mb&mom&vs).sum()}")
        print(f"  mb+mom+bc:     {(mb&mom&bc).sum()}")
        print(f"  mb+mom+rsi:    {(mb&mom&rok).sum()}")
        print(f"  mb+vs+bc:      {(mb&vs&bc).sum()}")
        print(f"  mb+vs+rsi:     {(mb&vs&rok).sum()}")
        print(f"  mb+bc+rsi:     {(mb&bc&rok).sum()}")

