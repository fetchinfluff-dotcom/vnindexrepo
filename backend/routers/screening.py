"""Screener router - filter stocks by technical criteria"""
from fastapi import APIRouter, Query
import httpx, json
import numpy as np
import pandas as pd
from config import settings
from routers.signals import load_data, compute_features, TICKER_SECTOR

router = APIRouter(tags=["screener"])

@router.get("/screener")
async def screener(
    trend: str = Query("all", description="above_ema20, above_ema50, above_ema200, all"),
    vol_ratio_min: float = Query(0.0, ge=0),
    rsi_min: float = Query(0.0, ge=0, le=100),
    rsi_max: float = Query(100.0, ge=0, le=100),
    candle: str = Query("all", description="bullish, bearish, all"),
    sector: str = Query("all", description="filter by sector"),
    price_min: float = Query(0, ge=0),
    price_max: float = Query(1e9, ge=0),
):
    df = await load_data()
    ticker_data = {}
    for t in sorted(df['ticker'].unique()):
        tdf = df[df['ticker']==t].copy().sort_values('date')
        if len(tdf) >= 200:
            ticker_data[t] = compute_features(tdf)

    last_date = df['date'].max()
    results = []
    for t, tdf in ticker_data.items():
        row = tdf[tdf['date']<=last_date]
        if len(row)==0: continue
        r = row.iloc[-1]
        if pd.isna(r.get('ema200')): continue
        price = float(r['close'])
        if price < price_min or price > price_max: continue
        sec = TICKER_SECTOR.get(t, 'Others')
        if sector != 'all' and sec != sector: continue
        if trend != 'all':
            if 'ema20' in trend and not bool(r['close'] > r['ema20']): continue
            if 'ema50' in trend and not bool(r['close'] > r['ema50']): continue
            if 'ema200' in trend and not bool(r['close'] > r['ema200']): continue
        vr = r['vol_ratio']; rsi = r['rsi14']
        if not np.isnan(vr) and vr < vol_ratio_min: continue
        if not np.isnan(rsi) and (rsi < rsi_min or rsi > rsi_max): continue
        if candle == 'bullish' and not r['bullish']: continue
        if candle == 'bearish' and r['bullish']: continue
        results.append({
            'ticker': t, 'sector': sec, 'price': price,
            'ema20': float(r['ema20']), 'ema50': float(r['ema50']), 'ema200': float(r['ema200']),
            'pct_ema20': (price/float(r['ema20'])-1)*100,
            'pct_ema50': (price/float(r['ema50'])-1)*100,
            'pct_ema200': (price/float(r['ema200'])-1)*100,
            'vol_ratio': None if np.isnan(vr) else float(vr),
            'rsi14': None if np.isnan(rsi) else float(rsi),
            'bullish': bool(r['bullish']),
            'signal': bool(r['close'] > r['ema20'] and r['close'] > r['ema200'] and r['ema50'] > r['ema200']),
        })

    return {'date': str(last_date.date()), 'count': len(results), 'results': results}
