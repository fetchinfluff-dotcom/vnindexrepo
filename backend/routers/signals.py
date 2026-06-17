"""Signals router - entry/exit signals + detail"""
from fastapi import APIRouter, Query
import httpx, json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from config import settings

router = APIRouter(tags=["signals"])
MGMT = settings.MGMT_HEADERS

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

def np_ema(arr, s):
    n = len(arr); r = np.empty(n); r[:] = np.nan
    m = 2/(s+1); r[0] = arr[0] if n > 0 else 0
    for i in range(1, n): r[i] = (arr[i]-r[i-1])*m + r[i-1]
    return r

async def load_data():
    sql_url = settings.MANAGEMENT_SQL_URL
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(sql_url, json={
            "query": "SELECT ticker, date, adj_open AS open, adj_high AS high, adj_low AS low, adj_close AS close, adj_volume AS volume FROM daily_bars_adjusted WHERE date >= '2021-01-01' ORDER BY ticker, date"
        }, headers=MGMT)
    rows = r.json()
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    for c in ['open','high','low','close','volume']: df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

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

@router.get("/signals/entry")
async def get_entry_signals():
    df = await load_data()
    ticker_data = {}
    for t in sorted(df['ticker'].unique()):
        tdf = df[df['ticker']==t].copy().sort_values('date')
        if len(tdf) >= 250:
            ticker_data[t] = compute_features(tdf)

    last_date = df['date'].max()
    signals_list = []

    for t, tdf in ticker_data.items():
        prev_row = tdf[tdf['date'] <= last_date]
        if len(prev_row) == 0: continue
        r = prev_row.iloc[-1]
        if pd.isna(r.get('ema200')): continue
        macro_bull = bool(r['close'] > r['ema200']) and bool(r['ema50'] > r['ema200'])
        momentum = bool(r['close'] > r['ema20'])
        vol_ok = not np.isnan(r['vol_ratio']) and r['vol_ratio'] > 1.0
        if macro_bull and momentum and vol_ok and r['bullish']:
            signals_list.append({
                'ticker': t, 'sector': TICKER_SECTOR.get(t, 'Others'),
                'price': float(r['close']), 'ema20': float(r['ema20']),
                'ema50': float(r['ema50']), 'ema200': float(r['ema200']),
                'rsi14': float(r['rsi14']) if not np.isnan(r['rsi14']) else None,
                'vol_ratio': float(r['vol_ratio']) if not np.isnan(r['vol_ratio']) else None,
                'atr14': float(r['atr14']) if not np.isnan(r['atr14']) else None,
                'date': str(last_date.date()),
            })

    return {'date': str(last_date.date()), 'signals_count': len(signals_list), 'signals': signals_list}

@router.get("/signals/entry/{ticker}")
async def get_ticker_signal_detail(ticker: str):
    df = await load_data()
    tdf = df[df['ticker']==ticker].sort_values('date').tail(250).copy()
    if len(tdf) < 50: return {'error': 'Not enough data'}
    tdf = compute_features(tdf)
    last = tdf.iloc[-1]
    return {
        'ticker': ticker, 'sector': TICKER_SECTOR.get(ticker, 'Others'),
        'date': str(last['date'].date()),
        'open': float(last['open']), 'high': float(last['high']),
        'low': float(last['low']), 'close': float(last['close']),
        'volume': int(last['volume']), 'ema20': float(last['ema20']),
        'ema50': float(last['ema50']), 'ema200': float(last['ema200']),
        'rsi14': None if np.isnan(last['rsi14']) else float(last['rsi14']),
        'vol_ratio': None if np.isnan(last['vol_ratio']) else float(last['vol_ratio']),
        'atr14': None if np.isnan(last['atr14']) else float(last['atr14']),
        'bullish': bool(last['bullish']),
        'signal': bool(last['close'] > last['ema20'] and last['close'] > last['ema200'] and last['ema50'] > last['ema200']),
        'recent_bars': [
            {'date': str(r['date'].date()), 'open': float(r['open']), 'high': float(r['high']),
             'low': float(r['low']), 'close': float(r['close']), 'volume': int(r['volume'])}
            for _, r in tdf.tail(120).iterrows()
        ],
    }
