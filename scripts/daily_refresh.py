"""GitHub Actions: daily VN100 refresh + signal computation"""
import os, json, asyncio, time
import pandas as pd
import numpy as np
import httpx
from datetime import datetime, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_MGT_PAT = os.environ.get("SUPABASE_MGT_PAT", "")
SUPABASE_PROJECT_REF = "xgbficilqacfnzrbftoo"
REST_URL = f"{SUPABASE_URL}/rest/v1"

async def refresh_service_key():
    """Fetch the latest service role key from Management API."""
    if not SUPABASE_MGT_PAT:
        print("No SUPABASE_MGT_PAT set; using SUPABASE_SERVICE_ROLE_KEY directly")
        return SUPABASE_KEY
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/api-keys",
                            headers={"Authorization": f"Bearer {SUPABASE_MGT_PAT}"})
            if r.status_code == 200:
                for k in r.json():
                    if k["name"] == "service_role":
                        return k["api_key"]
    except Exception as e:
        print(f"Failed to refresh service key: {e}")
    return SUPABASE_KEY

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

_last_fetch_time = 0.0

def fetch_vnstock(ticker, start_date):
    global _last_fetch_time
    from vnstock.api.quote import Quote
    end = datetime.now()
    for attempt in range(3):
        elapsed = time.time() - _last_fetch_time
        if elapsed < 3.5: time.sleep(3.5 - elapsed)
        try:
            q = Quote(symbol=ticker, source="VCI")
            _last_fetch_time = time.time()
            raw = q.history(symbol=ticker, start=start_date, end=end.strftime("%Y-%m-%d"), interval="1D")
            if raw is None or raw.empty: return pd.DataFrame()
            break
        except Exception as e:
            em = str(e).lower()
            if "rate limit" in em or "giới hạn" in em:
                wait = 30 + 30 * attempt
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
    # VCI history() returns raw (unadjusted) prices; store them as-is
    return df[["ticker","date","open","high","low","close","volume"]]

def compute_features(tdf):
    n = len(tdf)
    close = tdf['close'].values; high = tdf['high'].values
    low = tdf['low'].values; vol = tdf['volume'].values; opn = tdf['open'].values
    e20 = np_ema(close,20); e50 = np_ema(close,50); e100 = np_ema(close,100); e200 = np_ema(close,200)
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
    vv = np.empty(n); vv[:]=np.nan
    for i in range(19,n): vv[i]=np.mean((close[i-19:i+1]*vol[i-19:i+1]))
    body = np.abs(close-opn); rng = np.where(high-low==0,0.001,high-low)
    bc = (close > opn) & (body/rng >= 0.4)
    cp = (close-low)/rng; br = body/rng; ap = at/np.where(close==0,0.001,close)
    tdf['ema20']=e20; tdf['ema50']=e50; tdf['ema100']=e100; tdf['ema200']=e200; tdf['rsi14']=r14
    tdf['atr14']=at; tdf['atr_pct']=ap; tdf['vol_ratio']=vr; tdf['value20']=vv
    tdf['close_position']=cp; tdf['body_ratio']=br; tdf['bullish']=bc
    return tdf

def compute_market_regime(vnidx):
    """Compute market regime from VNINDEX dataframe. Returns dict of regime booleans + VNINDEX features."""
    if vnidx is None or len(vnidx) < 100:
        return {'bull': True, 'recovery': False, 'risk': False, 'distribution': False, 'close': 0, 'ema20': 0, 'ema50': 0, 'ema100': 0, 'rsi14': 50, 'return_20': 0, 'return_60': 0}
    c = vnidx['close'].values
    e20 = np_ema(c, 20); e50 = np_ema(c, 50); e100 = np_ema(c, 100)
    delta = np.diff(c); gain = np.where(delta>0,delta,0); loss = np.where(delta<0,-delta,0)
    ag = np.empty(len(c)); al = np.empty(len(c)); ag[:]=np.nan; al[:]=np.nan
    ag[14]=np.mean(gain[:14]); al[14]=np.mean(loss[:14])
    for i in range(15, len(c)):
        ag[i]=(ag[i-1]*13+gain[i-1])/14; al[i]=(al[i-1]*13+loss[i-1])/14
    rs = ag/np.where(al==0,0.001,al); rsi14 = 100-(100/(1+rs))
    last = vnidx.iloc[-1]; n = len(vnidx)
    close_val = float(last['close'])
    # Market Bull
    bull = bool(close_val > e50[-1] and e20[-1] > e50[-1] and e50[-1] >= e100[-1])
    # Market Recovery: close > e20, e20 rising 3 sessions, rsi >= 45
    e20_rising = n >= 3 and e20[-1] > e20[-2] > e20[-3] if n >= 3 else False
    recovery = bool(close_val > e20[-1] and e20_rising and rsi14[-1] >= 45)
    # Market Risk
    risk = bool(close_val < e50[-1] and e20[-1] < e50[-1])
    # Market Distribution
    vol = vnidx['volume'].values
    vm = np.empty(len(vol)); vm[:]=np.nan
    for i in range(19, len(vol)): vm[i]=np.mean(vol[i-19:i+1])
    vr = vol/np.where(vm==0,1,vm)
    down_count = 0
    for i in range(max(0, n-10), n):
        row = vnidx.iloc[i]
        if row['close'] < row['open'] and vr[i] > 1.2:
            down_count += 1
    distribution = bool(down_count >= 3 or close_val < e100[-1])
    # Returns for RS
    ret20 = close_val / vnidx.iloc[-20]['close'] - 1 if n >= 20 else 0
    ret60 = close_val / vnidx.iloc[-60]['close'] - 1 if n >= 60 else 0
    return {'bull': bull, 'recovery': recovery, 'risk': risk, 'distribution': distribution,
            'close': close_val, 'ema20': float(e20[-1]), 'ema50': float(e50[-1]), 'ema100': float(e100[-1]),
            'rsi14': float(rsi14[-1]), 'return_20': float(ret20), 'return_60': float(ret60)}

def compute_rs(stock_return_20, stock_return_60, mkt):
    """Compute relative strength scores given stock returns and market regime dict."""
    rs20 = stock_return_20 - mkt['return_20']
    rs60 = stock_return_60 - mkt['return_60']
    rs_score = 0
    if rs20 > 0: rs_score += 8
    if rs60 > 0: rs_score += 8
    if stock_return_60 >= 0.12: rs_score += 4
    return min(rs_score, 20), rs20, rs60

def compute_reward_risk(tdf):
    """Compute reward/risk ratio from the full dataframe."""
    n = len(tdf)
    if n < 5: return 1.0
    r = tdf.iloc[-1]
    entry = r['close']
    atr14 = r.get('atr14', 0)
    if np.isnan(atr14): atr14 = 0
    e50 = r['ema50']
    low5 = tdf['low'].iloc[-5:].min() if n >= 5 else r['low']
    stop = min(low5, e50 * 0.98, entry - 1.5 * atr14)
    if entry <= stop: return 1.0
    high20 = tdf['high'].iloc[-20:].max() if n >= 20 else r['high']
    target = high20
    rr = (target - entry) / (entry - stop)
    return max(min(rr, 5.0), 0.5)

def compute_codex_score(tdf, mkt_regime):
    """Compute Codex Advise score (0-100) and buy signal.
    tdf: stock dataframe with computed features.
    mkt_regime: dict from compute_market_regime().
    """
    n = len(tdf)
    if n < 5: return 0, False
    r = tdf.iloc[-1]
    if pd.isna(r.get('ema100')) or pd.isna(r.get('ema200')): return 0, False

    close = r['close']; e20 = r['ema20']; e50 = r['ema50']; vr = r.get('vol_ratio', 0)
    rsi = r.get('rsi14', 0); br = r.get('body_ratio', 0); cp = r.get('close_position', 0)
    ap = r.get('atr_pct', 0); v20 = r.get('value20', 0)
    mkt = mkt_regime

    # ---- Stock Quality Filters (base_eligible) ----
    liquid = not np.isnan(v20) and v20 >= 30_000_000_000
    tradable_vol = not np.isnan(ap) and ap >= 0.015 and ap <= 0.06
    trend_quality = all([
        close > e50, not np.isnan(r['ema20']) and r['ema20'] > e50,
        r['ema50'] >= r['ema100'], close > r['ema200'],
        n >= 4 and tdf['ema20'].iloc[-1] > tdf['ema20'].iloc[-4],
        n >= 6 and tdf['ema50'].iloc[-1] >= tdf['ema50'].iloc[-6],
    ])
    not_overextended = all([
        close <= e20 * 1.08, close <= e50 * 1.18,
        not np.isnan(rsi) and rsi <= 72,
    ])
    not_distribution = not mkt['distribution']

    # ---- RS Score (max 20) ----
    stock_ret20 = close / tdf.iloc[-20]['close'] - 1 if n >= 20 else 0
    stock_ret60 = close / tdf.iloc[-60]['close'] - 1 if n >= 60 else 0
    rs_score, rs20, rs60 = compute_rs(stock_ret20, stock_ret60, mkt)

    # ---- Trend Score (max 25) ----
    ts = 0
    if close > e50: ts += 8
    if r['ema20'] > e50: ts += 6
    if r['ema50'] > r['ema100']: ts += 5
    if close > r['ema200']: ts += 4
    if n >= 3 and tdf['ema20'].iloc[-1] > tdf['ema20'].iloc[-2] > tdf['ema20'].iloc[-3]: ts += 2

    # ---- Volume Score (max 15) ----
    vs = 0
    if not np.isnan(vr) and vr >= 1.1: vs += 5
    if not np.isnan(vr) and vr >= 1.3: vs += 5
    if not np.isnan(v20) and v20 >= 50_000_000_000: vs += 5

    # ---- Entry Quality Score (max 25) ----
    es = 0
    if close >= e20 * 0.97 and close <= e20 * 1.03: es += 10
    if not np.isnan(cp) and cp >= 0.65: es += 7
    if not np.isnan(br) and br >= 0.35: es += 4
    if not np.isnan(rsi) and rsi >= 45 and rsi <= 68: es += 4

    # ---- Risk Score (max 15) ----
    rk = 0
    if not np.isnan(ap) and ap >= 0.015 and ap <= 0.045: rk += 5
    if close <= e20 * 1.05: rk += 5
    rr = compute_reward_risk(tdf)
    if rr >= 2.0: rk += 5

    total = min(ts + rs_score + vs + es + rk, 100)

    # ---- base_eligible gate ----
    rs_ok = rs20 > 0 and rs60 > 0
    base_eligible = liquid and tradable_vol and trend_quality and rs_ok and not_overextended and not_distribution

    # ---- Section 12: Simplified scanner buy signal ----
    has_signal = all([
        mkt['bull'],
        not np.isnan(v20) and v20 >= 30_000_000_000,
        close > e50,
        r['ema20'] > e50,
        r['ema50'] >= r['ema100'],
        close > r['ema200'],
        n >= 4 and tdf['ema20'].iloc[-1] > tdf['ema20'].iloc[-4],
        rs60 > 0,
        close >= e20 * 0.97, close <= e20 * 1.05,
        not np.isnan(rsi) and rsi >= 45 and rsi <= 70,
        not np.isnan(vr) and vr >= 1.15,
        close > r['open'],
        not np.isnan(br) and br >= 0.35,
        not np.isnan(cp) and cp >= 0.6,
        not np.isnan(ap) and ap >= 0.015 and ap <= 0.055,
    ])
    return total, has_signal, base_eligible, rs_score, rr

def compute_enhanced_features(tdf, ticker, mkt_regime=None):
    """Compute features from a per-ticker dataframe, return the last row dict + signal."""
    tdf = tdf.sort_values('date')
    if len(tdf) < 250: return None
    tdf = compute_features(tdf)
    r = tdf.iloc[-1]
    if pd.isna(r.get('ema200')): return None
    macro_bull = bool(r['close'] > r['ema200']) and bool(r['ema50'] > r['ema200'])
    momentum = bool(r['close'] > r['ema20'])
    vol_ok = not np.isnan(r['vol_ratio']) and r['vol_ratio'] > 1.0
    sig = bool(macro_bull and momentum and vol_ok and bool(r['bullish']))
    codex_result = compute_codex_score(tdf, mkt_regime or compute_market_regime(None))
    codex_score_val = codex_result[0]
    codex_signal_val = codex_result[1]
    codex_base_eligible = codex_result[2] if len(codex_result) >= 3 else False
    codex_rs_score = codex_result[3] if len(codex_result) >= 4 else 0
    codex_rr = codex_result[4] if len(codex_result) >= 5 else 1.0
    real_close_val = float(r['real_close']) if 'real_close' in r and not pd.isna(r['real_close']) else float(r['close'])
    feat = {
        'ticker': ticker, 'sector': TICKER_SECTOR.get(ticker, 'Others'),
        'date': str(tdf['date'].max()), 'price': float(r['close']),
        'open': float(r['open']), 'high': float(r['high']), 'low': float(r['low']), 'close': float(r['close']),
        'volume': int(r['volume']), 'real_close': real_close_val,
        'ema20': float(r['ema20']), 'ema50': float(r['ema50']), 'ema100': float(r['ema100']), 'ema200': float(r['ema200']),
        'rsi14': float(r['rsi14']) if not np.isnan(r['rsi14']) else 0,
        'atr14': float(r['atr14']) if not np.isnan(r['atr14']) else 0,
        'atr_pct': float(r['atr_pct']) if not np.isnan(r['atr_pct']) else 0,
        'vol_ratio': float(r['vol_ratio']) if not np.isnan(r['vol_ratio']) else 0,
        'value20': float(r['value20']) if not np.isnan(r['value20']) else 0,
        'close_position': float(r['close_position']) if not np.isnan(r['close_position']) else 0,
        'body_ratio': float(r['body_ratio']) if not np.isnan(r['body_ratio']) else 0,
        'bullish': bool(r['bullish']), 'signal': bool(sig),
        'codex_score': int(codex_score_val), 'codex_signal': bool(codex_signal_val),
        'codex_rs_score': int(codex_rs_score), 'codex_rr': float(codex_rr),
        'codex_eligible': bool(codex_base_eligible),
        'pct_ema20': float((r['close']/r['ema20']-1)*100),
        'pct_ema50': float((r['close']/r['ema50']-1)*100),
        'pct_ema200': float((r['close']/r['ema200']-1)*100),
    }
    signal = None
    if sig:
        signal = {
            'date': str(tdf['date'].max()), 'ticker': ticker,
            'signal_type': 'entry', 'reason': 'trend_momentum_volume_candle',
            'strength': 1.0, 'price': float(r['close']),
            'details': json.dumps({'regime': 'neutral'}),
        }
    return feat, signal, tdf

def load_adj_factors_from_db(df_bars):
    """Compute per-ticker adjustment factor from existing DB bars.
    factor = adj_close / close for each ticker's latest row.
    """
    factors = {}
    df = df_bars.copy()
    if 'adj_close' not in df.columns or 'close' not in df.columns:
        return factors
    df = df.dropna(subset=['adj_close', 'close'])
    df = df[df['close'] != 0].copy()
    df['adj_factor'] = df['adj_close'] / df['close']
    latest = df.sort_values('date').groupby('ticker').last()
    return latest['adj_factor'].to_dict()

async def main():
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # Refresh service key from Management API (handles key rotation)
    srv_key = await refresh_service_key()
    HEADERS = {"Authorization": f"Bearer {srv_key}", "apikey": SUPABASE_ANON, "Content-Type": "application/json", "Accept": "application/json"}

    # ---- Step 1: Check what data already exists in Supabase ----
    print("Checking existing data in Supabase...")
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.get(f"{REST_URL}/daily_bars_adjusted", headers=HEADERS,
                           params={"select": "ticker,date", "order": "date.desc", "limit": 1})
        latest = resp.json()
        oldest_resp = await c.get(f"{REST_URL}/daily_bars_adjusted", headers=HEADERS,
                                  params={"select": "ticker,date", "order": "date.asc", "limit": 1, "ticker": "eq.VCB"})
    
    latest_date = None
    if isinstance(latest, list) and len(latest) > 0 and 'date' in latest[0]:
        latest_date = latest[0]['date']
    
    if latest_date:
        print(f"Latest data date in DB: {latest_date}")
        if latest_date >= today_str:
            # Path A: up-to-date, recompute features from existing DB data
            print("Data is already up-to-date. Recomputed features from DB data.")
            df = None  # will be set below in load_existing_data
        else:
            # Path B: need to fetch incremental data from VCI
            print(f"Need to fetch data from {latest_date} to {today_str}")
            start_fetch = (datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
            new_bars = []
            for idx, t in enumerate(VN100_TICKERS):
                if idx > 0 and idx % 20 == 0:
                    wait = 65
                    print(f"  rate limit buffer: waiting {wait}s after {idx} tickers...")
                    time.sleep(wait)
                try:
                    bars = fetch_vnstock(t, start_fetch)
                    if not bars.empty: new_bars.append(bars)
                    print(f"{t}: {len(bars)} bars")
                except Exception as e:
                    print(f"{t}: error - {e}")
            if new_bars:
                new_df = pd.concat(new_bars, ignore_index=True)
                print(f"Fetched {len(new_df)} new bars from vnstock")
                # ---- Merge with existing data from Supabase ----
                all_existing = []
                async with httpx.AsyncClient(timeout=120) as c:
                    for offset in range(0, 200000, 1000):
                        resp = await c.get(f"{REST_URL}/daily_bars_adjusted", headers=HEADERS,
                                           params={"select": "ticker,date,open,high,low,close,volume,adj_open,adj_high,adj_low,adj_close,adj_volume",
                                                   "order": "ticker,date", "limit": 1000, "offset": offset})
                        rows = resp.json()
                        if not rows or not isinstance(rows, list) or len(rows) == 0: break
                        all_existing.extend(rows)
                if all_existing:
                    old_df = pd.DataFrame(all_existing)
                    adj_factors = load_adj_factors_from_db(old_df)
                    new_df['adj_open'] = new_df['open'] * new_df['ticker'].map(adj_factors).fillna(1.0)
                    new_df['adj_high'] = new_df['high'] * new_df['ticker'].map(adj_factors).fillna(1.0)
                    new_df['adj_low'] = new_df['low'] * new_df['ticker'].map(adj_factors).fillna(1.0)
                    new_df['adj_close'] = new_df['close'] * new_df['ticker'].map(adj_factors).fillna(1.0)
                    new_df['adj_volume'] = new_df['volume']
                    df = pd.concat([old_df, new_df], ignore_index=True)
                    df = df.drop_duplicates(subset=["ticker","date"], keep="last").sort_values(["ticker","date"]).reset_index(drop=True)
                else:
                    new_df['adj_open'] = new_df['open']
                    new_df['adj_high'] = new_df['high']
                    new_df['adj_low'] = new_df['low']
                    new_df['adj_close'] = new_df['close']
                    new_df['adj_volume'] = new_df['volume']
                    df = new_df
                # Upsert merged bars
                upsert_records = df.to_dict(orient='records')
                async with httpx.AsyncClient(timeout=300) as c:
                    for i in range(0, len(upsert_records), 200):
                        batch = upsert_records[i:i+200]
                        await c.post(f"{REST_URL}/daily_bars_adjusted", json=batch,
                                     headers={**HEADERS, 'Prefer': 'resolution=merge-duplicates'})
                print(f"Upserted {len(upsert_records)} bars to daily_bars_adjusted")
            else:
                print("No new data fetched from VCI.")
                df = None  # will be set below in load_existing_data
    else:
        # Path C: first-time fetch, full history
        print("No existing data found. Fetching full history from vnstock...")
        start_fetch = (now - timedelta(days=750)).strftime("%Y-%m-%d")
        all_bars = []
        for idx, t in enumerate(VN100_TICKERS):
            if idx > 0 and idx % 20 == 0:
                wait = 65
                print(f"  rate limit buffer: waiting {wait}s after {idx} tickers...")
                time.sleep(wait)
            try:
                bars = fetch_vnstock(t, start_fetch)
                if not bars.empty: all_bars.append(bars)
                print(f"{t}: {len(bars)} bars")
            except Exception as e:
                print(f"{t}: error - {e}")
        if not all_bars: return print("No data fetched")
        df = pd.concat(all_bars, ignore_index=True)
        print(f"Total: {len(df)} bars")
        df['adj_open'] = df['open']
        df['adj_high'] = df['high']
        df['adj_low'] = df['low']
        df['adj_close'] = df['close']
        df['adj_volume'] = df['volume']
        upsert_records = df.to_dict(orient='records')
        async with httpx.AsyncClient(timeout=300) as c:
            for i in range(0, len(upsert_records), 200):
                batch = upsert_records[i:i+200]
                await c.post(f"{REST_URL}/daily_bars_adjusted", json=batch,
                             headers={**HEADERS, 'Prefer': 'resolution=merge-duplicates'})
        print(f"Upserted {len(upsert_records)} bars")

    # If df is not set (no fetch needed or no new data), load existing data from DB
    if df is None:
        print("Loading existing data from Supabase for feature computation...")
        all_existing = []
        async with httpx.AsyncClient(timeout=120) as c:
            for offset in range(0, 200000, 1000):
                resp = await c.get(f"{REST_URL}/daily_bars_adjusted", headers=HEADERS,
                                   params={"select": "ticker,date,adj_open,adj_high,adj_low,adj_close,adj_volume,close",
                                           "order": "ticker,date", "limit": 1000, "offset": offset})
                rows = resp.json()
                if not rows or not isinstance(rows, list) or len(rows) == 0: break
                all_existing.extend(rows)
        if not all_existing:
            print("No existing data found in DB")
            return
        df_bars_raw = pd.DataFrame(all_existing)
        df_bars_raw['real_close'] = df_bars_raw['close']
        df = df_bars_raw.drop(columns=['close']).rename(columns={"adj_open":"open","adj_high":"high","adj_low":"low","adj_close":"close","adj_volume":"volume"})

    # Normalize columns for feature computation:
    # open/high/low/close/volume should use adjusted values, real_close = raw close
    if 'adj_close' in df.columns and 'close' in df.columns:
        if df['close'].equals(df['adj_close']):
            # First-time path: close==adj_close (factor=1), real_close not set
            df['real_close'] = df['close']
        else:
            # Path B after merge: raw in close, adj in adj_*
            df['real_close'] = df['close']
            df['close'] = df['adj_close']
            df['open'] = df['adj_open']
            df['high'] = df['adj_high']
            df['low'] = df['adj_low']
            df['volume'] = df['adj_volume']
    elif 'real_close' not in df.columns:
        df['real_close'] = df['close']

    # ---- Step 5a: Load VNINDEX data for market regime & RS computation ----
    vnidx_df = None
    mkt_regime = None
    try:
        all_vnidx = []
        async with httpx.AsyncClient(timeout=60) as c:
            for offset in range(0, 10000, 1000):
                resp = await c.get(f"{REST_URL}/market_index", headers=HEADERS,
                                   params={"select": "date,open,high,low,close,volume",
                                           "ticker": "eq.VNINDEX", "order": "date.asc",
                                           "limit": 1000, "offset": offset})
                rows = resp.json()
                if not rows or len(rows) == 0: break
                all_vnidx.extend(rows)
        if all_vnidx:
            vnidx_df = pd.DataFrame(all_vnidx)
            for c in ["open","high","low","close","volume"]:
                vnidx_df[c] = pd.to_numeric(vnidx_df[c], errors="coerce")
            mkt_regime = compute_market_regime(vnidx_df)
            regime_name = 'bull' if mkt_regime['bull'] else ('recovery' if mkt_regime['recovery'] else ('risk' if mkt_regime['risk'] else 'distribution'))
            print(f"Market regime: {regime_name} (VNINDEX {mkt_regime['close']:.1f}, RSI {mkt_regime['rsi14']:.0f})")
    except Exception as e:
        print(f"Could not load VNINDEX data: {e}")

    # ---- Step 5b: Compute features & signals per ticker ----
    features_list = []
    signals_list = []
    for t in VN100_TICKERS:
        tdf = df[df['ticker']==t].copy().sort_values('date')
        result = compute_enhanced_features(tdf, t, mkt_regime)
        if result is None: continue
        feat, sig, _ = result
        features_list.append(feat)
        if sig: signals_list.append(sig)

    print(f"Features: {len(features_list)}, Signals: {len(signals_list)}")

    # Upsert stock_features
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
