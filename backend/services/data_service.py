"""Data service - daily refresh, signal computation"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import httpx
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import settings

MGMT = settings.MGMT_HEADERS
sql_url = settings.MANAGEMENT_SQL_URL

scheduler = AsyncIOScheduler()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(refresh_data, 'cron', hour=15, minute=30, id='daily_refresh')
        scheduler.add_job(compute_daily_signals, 'cron', hour=16, minute=0, id='daily_signals')
        scheduler.start()

async def refresh_data():
    """Fetch latest VN100 data and upsert into Supabase"""
    from vnstock_api import VnstockAPI
    api = VnstockAPI()
    tickers = get_vn100_tickers()
    for t in tickers:
        try:
            bars = api.fetch_bars(t)
            if not bars.empty:
                await upsert_bars(bars)
        except Exception as e:
            print(f"refresh error {t}: {e}")

async def compute_daily_signals():
    """Compute entry/exit signals and save to daily_signals table"""
    try:
        from routers.signals import load_data, compute_features, TICKER_SECTOR
        df = await load_data()
        ticker_data = {}
        for t in sorted(df['ticker'].unique()):
            tdf = df[df['ticker']==t].copy().sort_values('date')
            if len(tdf) >= 250:
                ticker_data[t] = compute_features(tdf)
        last_date = df['date'].max()
        signals = []
        for t, tdf in ticker_data.items():
            row = tdf[tdf['date']<=last_date]
            if len(row)==0: continue
            r = row.iloc[-1]
            if pd.isna(r.get('ema200')): continue
            mb = bool(r['close'] > r['ema200']) and bool(r['ema50'] > r['ema200'])
            mom = bool(r['close'] > r['ema20'])
            vol = not np.isnan(r['vol_ratio']) and r['vol_ratio'] > 1.0
            if mb and mom and vol and r['bullish']:
                signals.append({
                    'date': str(last_date.date()), 'ticker': t,
                    'signal_type': 'entry', 'reason': 'trend_momentum_volume_candle',
                    'strength': 1.0, 'price': float(r['close']),
                    'details': {'ema20': float(r['ema20']), 'ema50': float(r['ema50']), 'ema200': float(r['ema200']),
                                'rsi14': None if np.isnan(r['rsi14']) else float(r['rsi14']),
                                'vol_ratio': None if np.isnan(r['vol_ratio']) else float(r['vol_ratio'])}
                })
        if signals:
            async with httpx.AsyncClient(timeout=60) as c:
                for s in signals:
                    await c.post(sql_url, json={"query": f"INSERT INTO daily_signals (date, ticker, signal_type, reason, strength, price, details) VALUES ('{s['date']}','{s['ticker']}','{s['signal_type']}','{s['reason']}',{s['strength']},{s['price']},'{str(s['details'])}') ON CONFLICT DO NOTHING"}, headers=MGMT)
        return {'date': str(last_date.date()), 'signals': len(signals)}
    except Exception as e:
        return {'error': str(e)}

def get_vn100_tickers():
    return [
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

async def upsert_bars(bars):
    async with httpx.AsyncClient(timeout=30) as c:
        for _, row in bars.iterrows():
            q = f"INSERT INTO daily_bars_adjusted (ticker, date, adj_open, adj_high, adj_low, adj_close, adj_volume) VALUES ('{row['ticker']}','{row['date']}',{row['open']},{row['high']},{row['low']},{row['close']},{row['volume']}) ON CONFLICT (ticker, date) DO UPDATE SET adj_open={row['open']},adj_high={row['high']},adj_low={row['low']},adj_close={row['close']},adj_volume={row['volume']}"
            await c.post(sql_url, json={"query": q}, headers=MGMT)
