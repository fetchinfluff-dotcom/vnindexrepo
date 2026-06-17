#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Full backtest: multi-position, sector-aware, with exit logic"""
import sys, os, json, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ============================================================
# CONFIG
# ============================================================
INITIAL_CAPITAL = 1_000_000_000  # 1 ty VND
MAX_POSITIONS = 10
COMMISSION = 0.0015
SLIPAGE = 0.001
STOP_LOSS_PCT = 0.07
VOL_SURGE_THRESHOLD = 1.2
PULLBACK_LOWER = 0.97
PULLBACK_UPPER = 1.01
CANDLE_BODY_RATIO = 0.4
RSI_UPPER = 70

# ============================================================
# LOAD DATA
# ============================================================
csv_path = os.path.join(os.path.dirname(__file__), 'vn100_data_2022_2024.csv')
df = pd.read_csv(csv_path)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
for c in ['open','high','low','close','volume']:
    df[c] = pd.to_numeric(df[c], errors='coerce')

print(f"Loaded {len(df)} rows, {df['ticker'].nunique()} tickers")
print(f"Period: {df['date'].min().date()} to {df['date'].max().date()}")

# ============================================================
# COMPUTE FEATURES PER TICKER
# ============================================================
def compute_features(tdf):
    n = len(tdf)
    close = tdf['close'].values; high = tdf['high'].values
    low = tdf['low'].values; vol = tdf['volume'].values
    
    def ema(arr, s):
        r = np.empty(n); r[:] = np.nan
        m = 2/(s+1); r[0]=arr[0]
        for i in range(1,n): r[i]=(arr[i]-r[i-1])*m+r[i-1]
        return r
    def rsi(arr, p=14):
        d=np.diff(arr); g=np.where(d>0,d,0); ls=np.where(d<0,-d,0)
        ag=np.empty(n); al=np.empty(n); ag[:]=np.nan; al[:]=np.nan
        ag[p]=np.mean(g[:p]); al[p]=np.mean(ls[:p])
        for i in range(p+1,n):
            ag[i]=(ag[i-1]*(p-1)+g[i-1])/p
            al[i]=(al[i-1]*(p-1)+ls[i-1])/p
        rs=ag/np.where(al==0,0.001,al); return 100-(100/(1+rs))
    
    e20=ema(close,20); e50=ema(close,50); e200=ema(close,200)
    r14=rsi(close)
    tr=np.maximum(high[1:]-low[1:], np.maximum(np.abs(high[1:]-close[:-1]), np.abs(low[1:]-close[:-1])))
    at=np.empty(n); at[:]=np.nan; at[14]=np.mean(tr[:14])
    for i in range(15,n): at[i]=(at[i-1]*13+tr[i-1])/14
    vm=np.empty(n); vm[:]=np.nan
    for i in range(19,n): vm[i]=np.mean(vol[i-19:i+1])
    vr=vol/np.where(vm==0,1,vm)
    body=np.abs(close-tdf['open'].values); cr=high-low; cr=np.where(cr==0,0.001,cr)
    bc=(close>tdf['open'].values)&(body/cr>=CANDLE_BODY_RATIO)
    
    return {'ema20':e20,'ema50':e50,'ema200':e200,'rsi14':r14,'atr14':at,'vol_ratio':vr,'bullish_candle':bc}

ticker_data = {}
for t in df['ticker'].unique():
    tdf = df[df['ticker']==t].copy().sort_values('date')
    if len(tdf)>=250:
        feats = compute_features(tdf)
        for k,v in feats.items(): tdf[k]=v
        ticker_data[t]=tdf

# ============================================================
# BACKTEST ENGINE
# ============================================================
dates = sorted(df['date'].unique())
cash = INITIAL_CAPITAL
portfolio = []  # list of active positions {ticker, entry_date, entry_price, shares, sector}
trades = []
equity_curve = []

for d_idx, d in enumerate(dates):
    # --- SCAN FOR ENTRIES ---
    candidates = []
    for t, tdf in ticker_data.items():
        if any(p['ticker']==t for p in portfolio): continue
        if len(portfolio)>=MAX_POSITIONS: break
        row = tdf[tdf['date']==d]
        if len(row)==0: continue
        r = row.iloc[0]
        if pd.isna(r.get('ema200')): continue
        
        entry = (r['close']>r['ema200']) & (r['ema50']>r['ema200'])  # macro_bull
        entry = entry & (r['close']>=r['ema20']*PULLBACK_LOWER) & (r['close']<=r['ema20']*PULLBACK_UPPER)
        entry = entry & (r['vol_ratio']>VOL_SURGE_THRESHOLD if not pd.isna(r['vol_ratio']) else False)
        entry = entry & r['bullish_candle']
        entry = entry & (r['rsi14']<RSI_UPPER if not pd.isna(r['rsi14']) else False)
        
        if entry:
            candidates.append((t, r['close'], r))
    
    # Sort candidates by volume ratio (strongest first)
    candidates.sort(key=lambda x: x[2]['vol_ratio'] if not pd.isna(x[2]['vol_ratio']) else 0, reverse=True)
    
    for t, price, r in candidates:
        if len(portfolio) >= MAX_POSITIONS: break
        pos_value = INITIAL_CAPITAL * 0.10
        shares = int(pos_value / (price * (1+COMMISSION+SLIPAGE)))
        if shares<=0 or price*shares > cash: continue
        cost = price*shares*(1+COMMISSION+SLIPAGE)
        cash -= cost
        portfolio.append({'ticker':t, 'entry_date':d, 'entry_price':price, 'shares':shares, 'cost':cost})
    
    # --- CHECK EXITS ---
    to_remove = []
    for p in portfolio:
        t = p['ticker']
        tdf = ticker_data[t]
        row = tdf[tdf['date']==d]
        if len(row)==0: continue
        r = row.iloc[0]
        curr_price = r['close']
        high_today = r['high']
        low_today = r['low']
        
        exit_reason = None
        # SL hit
        sl = p['entry_price'] * (1-STOP_LOSS_PCT)
        if low_today <= sl:
            exit_reason = 'stop_loss'
            exit_price = sl
        # Trend break
        elif not pd.isna(r.get('ema200')) and curr_price < r['ema200']:
            exit_reason = 'trend_break'
            exit_price = curr_price
        # RSI overbought
        elif not pd.isna(r.get('rsi14')) and r['rsi14'] > 75:
            exit_reason = 'rsi_overbought'
            exit_price = curr_price
        # Volume blow-off
        elif not pd.isna(r.get('vol_ratio')) and r['vol_ratio'] > 3.0 and curr_price < p['entry_price']:
            exit_reason = 'vol_blowoff'
            exit_price = curr_price
        
        if exit_reason:
            proceeds = p['shares']*exit_price*(1-COMMISSION-SLIPAGE)
            pnl = proceeds - p['cost']
            pnl_pct = (exit_price/p['entry_price']-1)*100
            trade = {**p, 'exit_date':d, 'exit_price':exit_price, 'proceeds':proceeds,
                     'pnl':pnl, 'pnl_pct':pnl_pct, 'exit_reason':exit_reason,
                     'days_held':(d-p['entry_date']).days}
            trades.append(trade)
            cash += proceeds
            to_remove.append(p['ticker'])
    
    portfolio = [p for p in portfolio if p['ticker'] not in to_remove]
    
    # Close all on last date
    if d_idx == len(dates)-1:
        for p in portfolio[:]:
            tdf = ticker_data[p['ticker']]
            row = tdf[tdf['date']==d]
            if len(row)>0:
                exit_price = row.iloc[0]['close']
            else:
                exit_price = p['entry_price']
            proceeds = p['shares']*exit_price*(1-COMMISSION-SLIPAGE)
            pnl = proceeds - p['cost']
            trade = {**p, 'exit_date':d, 'exit_price':exit_price, 'proceeds':proceeds,
                     'pnl':pnl, 'pnl_pct':(exit_price/p['entry_price']-1)*100,
                     'exit_reason':'end_of_test', 'days_held':(d-p['entry_date']).days}
            trades.append(trade)
            cash += proceeds
        portfolio = []
    
    # NAV
    pos_value = sum(p['shares']*ticker_data[p['ticker']][ticker_data[p['ticker']]['date']==d].iloc[0]['close']
                    for p in portfolio if len(ticker_data[p['ticker']][ticker_data[p['ticker']]['date']==d])>0)
    nav = cash + pos_value
    equity_curve.append({'date':d, 'nav':nav, 'cash':cash, 'positions':len(portfolio)})

# ============================================================
# METRICS
# ============================================================
eq = pd.DataFrame(equity_curve)
final_nav = eq['nav'].iloc[-1]
total_return = (final_nav/INITIAL_CAPITAL-1)*100

years = (dates[-1]-dates[0]).days/365.25
cagr = ((final_nav/INITIAL_CAPITAL)**(1/years)-1)*100 if years>0 else 0

eq['peak']=eq['nav'].cummax()
eq['dd']=(eq['nav']-eq['peak'])/eq['peak']*100
max_dd=eq['dd'].min()

daily_ret=eq['nav'].pct_change().dropna()
sharpe=np.sqrt(252)*daily_ret.mean()/daily_ret.std() if daily_ret.std()>0 else 0

tr=pd.DataFrame(trades)
if len(tr)>0:
    wins=tr[tr['pnl']>0]; losses=tr[tr['pnl']<=0]
    wr=len(wins)/len(tr)*100
    avg_w=wins['pnl_pct'].mean() if len(wins)>0 else 0
    avg_l=losses['pnl_pct'].mean() if len(losses)>0 else 0
    pf=abs(wins['pnl'].sum()/losses['pnl'].sum()) if len(losses)>0 and losses['pnl'].sum()!=0 else float('inf')
    avg_days=tr['days_held'].mean()

print("\n"+"="*70)
print("BACKTEST TEARSHEET")
print("="*70)
print(f"{'Period':20s}: {dates[0].date()} to {dates[-1].date()} ({years:.1f} years)")
print(f"{'Initial Capital':20s}: {INITIAL_CAPITAL:>15,.0f} VND ({INITIAL_CAPITAL/1e9:.1f} ty)")
print(f"{'Final NAV':20s}: {final_nav:>15,.0f} VND ({final_nav/1e9:.3f} ty)")
print(f"{'Total Return':20s}: {total_return:>+14.2f}%")
print(f"{'CAGR':20s}: {cagr:>+14.2f}%")
print(f"{'Max Drawdown':20s}: {max_dd:>14.2f}%")
print(f"{'Sharpe Ratio':20s}: {sharpe:>14.2f}")
print(f"{'Total Trades':20s}: {len(tr):>14d}")
print(f"{'Win Rate':20s}: {wr:>13.1f}%")
print(f"{'Avg Win':20s}: {avg_w:>+14.2f}%")
print(f"{'Avg Loss':20s}: {avg_l:>+14.2f}%")
print(f"{'Profit Factor':20s}: {pf:>14.2f}")
print(f"{'Avg Days Held':20s}: {avg_days:>14.0f}")

# Monthly returns
eq['month']=eq['date'].dt.to_period('M')
monthly=eq.groupby('month')['nav'].last().pct_change()*100
print(f"\n{'--- MONTHLY RETURNS ---':^50}")
print(f"{'Month':15s} {'Return':>10s} {'Month':15s} {'Return':>10s}")
mons=list(monthly.items())
for i in range(0,len(mons),2):
    m1,r1=mons[i]; m1s=f"{m1}: {r1:+.2f}%" if not pd.isna(r1) else f"{m1}: N/A"
    if i+1<len(mons):
        m2,r2=mons[i+1]; m2s=f"{m2}: {r2:+.2f}%" if not pd.isna(r2) else f"{m2}: N/A"
        print(f"{m1s:25s} {m2s:25s}")
    else:
        print(f"{m1s:25s}")

# Yearly
print(f"\n{'--- YEARLY ---':^30}")
eq['year']=eq['date'].dt.year
yearly=eq.groupby('year')['nav'].last()
for y in yearly.index:
    if y==yearly.index[0]:
        ret=(yearly[y]/INITIAL_CAPITAL-1)*100
    else:
        ret=(yearly[y]/yearly[yearly.index.get_loc(y)-1]-1)*100
    print(f"  {y}: {ret:+.2f}%")

if len(tr)>0:
    print(f"\n--- TOP 5 TRADES ---")
    for _,t in tr.sort_values('pnl',ascending=False).head(5).iterrows():
        print(f"  {t['entry_date'].date()} {t['ticker']:6s} IN:{t['entry_price']:>8.0f} OUT:{t['exit_price']:>8.0f} PNL:{t['pnl_pct']:+6.2f}% [{t['days_held']}d] {t['exit_reason']}")
    
    print(f"\n--- WORST 5 TRADES ---")
    for _,t in tr.sort_values('pnl').head(5).iterrows():
        print(f"  {t['entry_date'].date()} {t['ticker']:6s} IN:{t['entry_price']:>8.0f} OUT:{t['exit_price']:>8.0f} PNL:{t['pnl_pct']:+6.2f}% [{t['days_held']}d] {t['exit_reason']}")
    
    print(f"\n--- EXIT REASONS ---")
    for reason,count in tr['exit_reason'].value_counts().items():
        print(f"  {reason}: {count}")

# Save
eq.to_csv(os.path.join(os.path.dirname(__file__),'backtest_equity.csv'),index=False)
tr.to_csv(os.path.join(os.path.dirname(__file__),'backtest_trades.csv'),index=False)
print(f"\nResults saved to backtest_equity.csv, backtest_trades.csv")
