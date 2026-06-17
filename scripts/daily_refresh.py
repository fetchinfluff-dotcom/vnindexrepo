"""GitHub Actions: daily VN100 refresh + signal computation"""
import os, json, asyncio
import pandas as pd
import numpy as np
import httpx
from datetime import datetime, timedelta

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
REST_URL = f"{SUPABASE_URL}/rest/v1"
HEADERS = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Accept": "application/json"}

# ---- helpers ----
def np_ema(arr, s):
    n = len(arr); r = np.empty(n); r[:] = np.nan
    m = 2/(s+1); r[0] = arr[0] if n > 0 else 0
    for i in range(1, n): r[i] = (arr[i]-r[i-1])*m + r[i-1]
    return r

SECTORS = {
    'Banking': ['ACB','BID','CTG','EIB','HDB','KLB','LPB','MBB','MSB','NAB','OCB','SHB','SSB','STB','TCB','TPB','VCB','VIB','VPB','ABB'],
    'RealEstate': ['VIC','VHM','NVL','KDH','PDR','DXG','DXS','SZC','DIG','HDG','IDC','KBC','NLG','TDH','VRE','HPX','LDG','AGG','CEO','SCR'],
    'Construction': ['BCM','SJS','NTL','LHG','HQC','QCG','TCH','NHA','HBC','CTD'],
    'Securities': ['SSI','VCI','HCM','VND','ORS','AGR','BSI','MBS','FTS','TVS','VDS','EVS','CTS','SHS','APS'],
    'SteelLogistics': ['HPG','HSG','NKG','POM','TLH','GMD','SMC','VGS','HMC','CSV','HHV'],
    'Retail': ['MWG','FRT','PNJ','DGW','MSN','SBT','FMC','VHC','ANV','TNG'],
    'Tech': ['FPT','CMG','ELC','ITD','CMC','VTI'],
    'FoodBeverage': ['VNM','SAB','BHN','SCD','LCD','GTN'],
    'Energy': ['GAS','PLX','POW','PC1','NT2','REE','GEG','PPC','QTP','DTL'],
    'Chemicals': ['DCM','DGC','BFC','DPM','HT1','LAS','TNH','NTP','AAA'],
    'Others': ['VJC','HVN','PLP','PET','PJT','HAX'],
}
TICKER_SECTOR = {t:s for s,ts in SECTORS.items() for t in ts}

VN100_TICKERS = [
    "VCB","BID","CTG","TCB","VPB","MBB","ACB","HDB","STB","TPB",
    "EIB","MSB","OCB","SHB","VIB","LPB","NAB","SSB","ABB","KLB",
    "VIC","VHM","NVL","KDH","PDR","DXG","DXS","SZC","DIG","HDG",
    "IDC","KBC","NLG","TDH","VRE","HPX","LDG","AGG","CEO","SCR",
    "BCM","SJS","NTL","LHG","HQC","QCG","TCH","NHA","HBC","CTD",
    "SSI","VCI","HCM","VND","ORS","AGR","BSI","MBS","FTS","TVS",
    "VDS","EVS","CTS","SHS","APS",
    "HPG","HSG","NKG","POM","TLH","GMD","SMC","VGS","HMC","CSV","HHV",
    "MWG","FRT","PNJ","DGW","MSN","SBT","FMC","VHC","ANV","TNG",
    "CMG","VNM","BHN","SCD","LCD",
    "GAS","PLX","POW","PC1","NT2","REE","GEG","PPC","QTP","DTL",
    "FPT","ELC","ITD","CMC","VTI",
    "DCM","DGC","BFC","DPM","HT1","LAS","TNH","NTP","AAA",
    "SAB","VJC","HVN","PLP","PET","PJT","GTN","HAX",
]

last_fetch = 0.0

def fetch_vnstock(ticker):
    import time
    global last_fetch
    from vnstock.api.quote import Quote
    end = datetime.now()
    start = end - timedelta(days=750)
    for attempt in range(3):
        elapsed = time.time() - last_fetch
        if elapsed < 4.0: time.sleep(4.0 - elapsed)
        try:
            q = Quote(symbol="VCB", source="VCI")
            raw = q.history(symbol=ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1D")
            last_fetch = time.time()
            if raw is None or raw.empty: return pd.DataFrame()
            break
        except Exception as e:
            last_fetch = time.time()
            if "rate limit" in str(e).lower() or "giới hạn" in str(e).lower():
                wait = 20 + 20 * attempt
                print(f"  rate limited on {ticker}, waiting {wait}s...")
                time.sleep(wait)
            else:
                if attempt == 2: raise
                time.sleep(5 * (attempt + 1))
    df = raw.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    if "time" in df.columns and "date" not in df.columns: df = df.rename(columns={"time": "date"})
    df["ticker"] = ticker
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["date"])
    for c in ["open","high","low","close"]: df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df = df.dropna(subset=["open","high","low","close"])
    df = df.sort_values("date").drop_duplicates("date", keep="last")
    return df[["ticker","date","open","high","low","close","volume"]]

def compute_features(tdf):
    n = len(tdf)
    close = tdf['close'].values; high = tdf['high'].values
    low = tdf['low'].values; vol = tdf['volume'].values; opn = tdf['open'].values
    e20 = np_ema(close,20); e50 = np_ema(close,50); e200 = np_ema(close,200)
    delta = np.diff(close); gain = np.where(delta>0,delta,0); loss = np.where(delta<0,-delta,0)
    ag = np.empty(n); al = np.empty(n); ag[:]=np.nan; al[:]=np.nan
    ag[14]=np.mean(gain[:14]); al[14]=np.mean(loss[:14])
    for i in range(15,n):
        ag[i]=(ag[i-1]*13+gain[i-1])/14; al[i]=(al[i-1]*13+loss[i-1])/14
    rs = ag / np.where(al==0,0.001,al); r14 = 100-(100/(1+rs))
    tr = np.maximum(high[1:]-low[1:], np.maximum(np.abs(high[1:]-close[:-1]), np.abs(low[1:]-close[:-1])))
    at = np.empty(n); at[:]=np.nan; at[14]=np.mean(tr[:14])
    for i in range(15,n): at[i]=(at[i-1]*13+tr[i-1])/14
    vm = np.empty(n); vm[:]=np.nan
    for i in range(19,n): vm[i]=np.mean(vol[i-19:i+1])
    vr = vol / np.where(vm==0,1,vm)
    bc = (close > opn) & (np.abs(close-opn)/np.where(high-low==0,0.001,high-low) >= 0.4)
    tdf['ema20']=e20; tdf['ema50']=e50; tdf['ema200']=e200; tdf['rsi14']=r14
    tdf['atr14']=at; tdf['vol_ratio']=vr; tdf['bullish']=bc
    return tdf

async def main():
    all_bars = []
    for t in VN100_TICKERS:
        try:
            bars = fetch_vnstock(t)
            if not bars.empty: all_bars.append(bars)
            print(f"{t}: {len(bars)} bars")
        except Exception as e:
            print(f"{t}: error - {e}")

    if not all_bars: return print("No data fetched")
    df = pd.concat(all_bars, ignore_index=True)
    print(f"Total: {len(df)} bars, dates: {df['date'].min()} to {df['date'].max()}")

    # Upsert daily_bars_adjusted via REST API (batch insert)
    bars_records = df.to_dict(orient='records')
    for b in bars_records:
        b['adj_open'] = b.pop('open')
        b['adj_high'] = b.pop('high')
        b['adj_low'] = b.pop('low')
        b['adj_close'] = b.pop('close')
        b['adj_volume'] = b.pop('volume')

    # Batch upsert using POST with Prefer: resolution=merge-duplicates
    async with httpx.AsyncClient(timeout=300) as c:
        # Upsert in batches of 200
        for i in range(0, len(bars_records), 200):
            batch = bars_records[i:i+200]
            await c.post(f"{REST_URL}/daily_bars_adjusted", json=batch, headers={**HEADERS, 'Prefer': 'resolution=merge-duplicates'})
    print(f"daily_bars_adjusted: {len(bars_records)} rows upserted")

    # Compute features per ticker
    last_date = df['date'].max()
    features_list = []
    signals_list = []
    for t in VN100_TICKERS:
        tdf = df[df['ticker']==t].copy().sort_values('date')
        if len(tdf) < 250: continue
        tdf = compute_features(tdf)
        r = tdf.iloc[-1]
        if pd.isna(r.get('ema200')): continue
        macro_bull = bool(r['close'] > r['ema200']) and bool(r['ema50'] > r['ema200'])
        momentum = bool(r['close'] > r['ema20'])
        vol_ok = not np.isnan(r['vol_ratio']) and r['vol_ratio'] > 1.0
        sig = macro_bull and momentum and vol_ok and r['bullish']
        features_list.append({
            'ticker': t, 'sector': TICKER_SECTOR.get(t, 'Others'),
            'date': str(last_date), 'price': float(r['close']),
            'open': float(r['open']), 'high': float(r['high']), 'low': float(r['low']), 'close': float(r['close']),
            'volume': int(r['volume']),
            'ema20': float(r['ema20']), 'ema50': float(r['ema50']), 'ema200': float(r['ema200']),
            'rsi14': float(r['rsi14']) if not np.isnan(r['rsi14']) else 0,
            'atr14': float(r['atr14']) if not np.isnan(r['atr14']) else 0,
            'vol_ratio': float(r['vol_ratio']) if not np.isnan(r['vol_ratio']) else 0,
            'bullish': bool(r['bullish']), 'signal': sig,
            'pct_ema20': float((r['close']/r['ema20']-1)*100),
            'pct_ema50': float((r['close']/r['ema50']-1)*100),
            'pct_ema200': float((r['close']/r['ema200']-1)*100),
        })
        if sig:
            signals_list.append({
                'date': str(last_date), 'ticker': t,
                'signal_type': 'entry', 'reason': 'trend_momentum_volume_candle',
                'strength': 1.0, 'price': float(r['close']),
                'details': json.dumps({'regime': 'neutral'}),
            })

    print(f"Features: {len(features_list)}, Signals: {len(signals_list)}")

    # Upsert stock_features (upsert by ticker using POST with merge-duplicates)
    async with httpx.AsyncClient(timeout=120) as c:
        for i in range(0, len(features_list), 100):
            batch = features_list[i:i+100]
            await c.post(f"{REST_URL}/stock_features", json=batch, headers={**HEADERS, 'Prefer': 'resolution=merge-duplicates'})

    # Upsert daily_signals
    if signals_list:
        async with httpx.AsyncClient(timeout=60) as c:
            for s in signals_list:
                await c.post(f"{REST_URL}/daily_signals", json=s, headers={**HEADERS, 'Prefer': 'resolution=merge-duplicates'})

    print("Done")

if __name__ == "__main__":
    asyncio.run(main())
