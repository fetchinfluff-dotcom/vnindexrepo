#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick backtest on saved CSV data with relaxed entry conditions"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'

import warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import traceback

# ============================================================
# 1. Load saved data
# ============================================================
csv_path = os.path.join(os.path.dirname(__file__), 'vn100_data_2022_2024.csv')
if not os.path.exists(csv_path):
    print(f"CSV not found at {csv_path}")
    sys.exit(1)

df = pd.read_csv(csv_path)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
print(f"Loaded {len(df)} rows, {df['ticker'].nunique()} tickers")
print(f"Date: {df['date'].min().date()} to {df['date'].max().date()}")
print(f"Tickers: {sorted(df['ticker'].unique())}")
print()

# ============================================================
# 2. Strategy logic (relaxed entry conditions)
# ============================================================
INITIAL_CAPITAL = 1_000_000_000  # 1 tỷ VND
MAX_POSITIONS = 10
SECTOR_CAP = 0.20  # 20% per sector
COMMISSION = 0.0015  # 0.15%
SLIPAGE = 0.001  # 0.1%

results = []

for ticker in sorted(df['ticker'].unique()):
    tdf = df[df['ticker'] == ticker].copy()
    tdf = tdf.sort_values('date')
    
    # Convert types
    for c in ['open','high','low','close','volume']:
        tdf[c] = pd.to_numeric(tdf[c], errors='coerce')
    
    min_bars = 250
    if len(tdf) < min_bars:
        continue
    
    # ---- Features ----
    close = tdf['close'].values
    high = tdf['high'].values
    low = tdf['low'].values
    vol = tdf['volume'].values
    n = len(close)
    
    # EMAs
    def ema(arr, span):
        result = np.empty(n)
        result[:] = np.nan
        mult = 2 / (span + 1)
        result[0] = arr[0]
        for i in range(1, n):
            result[i] = (arr[i] - result[i-1]) * mult + result[i-1]
        return result
    
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema200 = ema(close, 200)
    
    # RSI 14
    def rsi(arr, period=14):
        delta = np.diff(arr)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = np.empty(n)
        avg_loss = np.empty(n)
        avg_gain[:] = np.nan
        avg_loss[:] = np.nan
        avg_gain[period] = np.mean(gain[:period])
        avg_loss[period] = np.mean(loss[:period])
        for i in range(period+1, n):
            avg_gain[i] = (avg_gain[i-1] * (period-1) + gain[i-1]) / period
            avg_loss[i] = (avg_loss[i-1] * (period-1) + loss[i-1]) / period
        rs = avg_gain / np.where(avg_loss == 0, 0.001, avg_loss)
        rsi_vals = 100 - (100 / (1 + rs))
        return rsi_vals
    
    rsi14 = rsi(close, 14)
    
    # ATR 14
    def atr(h, l, c, period=14):
        tr = np.maximum(h[1:] - l[1:], 
                       np.maximum(np.abs(h[1:] - c[:-1]), 
                                 np.abs(l[1:] - c[:-1])))
        atr_vals = np.empty(n)
        atr_vals[:] = np.nan
        atr_vals[period] = np.mean(tr[:period])
        for i in range(period+1, n):
            atr_vals[i] = (atr_vals[i-1] * (period-1) + tr[i-1]) / period
        return atr_vals
    
    atr14 = atr(high, low, close, 14)
    
    # Volume MA and ratio
    vol_ma20 = np.empty(n)
    vol_ma20[:] = np.nan
    for i in range(19, n):
        vol_ma20[i] = np.mean(vol[i-19:i+1])
    vol_ratio = vol / np.where(vol_ma20 == 0, 1, vol_ma20)
    
    # ---- Entry Signals (relaxed) ----
    # Condition 1: Macro Bull - price > EMA200 AND EMA50 > EMA200
    macro_bull = (close > ema200) & (ema50 > ema200)
    
    # Condition 2: Pullback to EMA20 - close within -3% to +1% of EMA20 (was ±1%)
    pullback = (close >= ema20 * 0.97) & (close <= ema20 * 1.01)
    
    # Condition 3: Volume surge > 1.2x MA20
    vol_surge = vol_ratio > 1.2
    
    # Condition 4: Bullish candle (close > open AND body >= 50% of range)
    body = np.abs(close - tdf['open'].values)
    candle_range = high - low
    candle_range = np.where(candle_range == 0, 0.001, candle_range)
    bullish_candle = (close > tdf['open'].values) & (body / candle_range >= 0.4)
    
    # Condition 5: RSI 14 < 70 (weekly look, approximate with daily)
    rsi_ok = rsi14 < 70
    
    # Combined entry
    entry = macro_bull & pullback & vol_surge & bullish_candle & rsi_ok
    entry = entry & ~np.isnan(ema200) & ~np.isnan(ema20) & ~np.isnan(vol_ratio)
    
    # ---- Exit Signals ----
    # Exit 1: Trend break - close < EMA200
    trend_break = close < ema200
    
    # Exit 2: Stop loss - close < entry_price * 0.93 (7% stop)
    # Exit 3: RSI overbought > 75
    rsi_overbought = rsi14 > 75
    
    # Exit 4: Volume blow-off (vol > 3x MA20 and close < previous close)
    vol_blowoff = (vol_ratio > 3.0) & (close < np.roll(close, 1))
    
    # Store signals
    for i in range(200, n):
        if entry[i] and not np.isnan(atr14[i]):
            results.append({
                'ticker': ticker,
                'date': tdf['date'].iloc[i],
                'type': 'entry',
                'close': close[i],
                'ema20': ema20[i],
                'ema50': ema50[i],
                'ema200': ema200[i],
                'rsi14': rsi14[i],
                'atr14': atr14[i],
                'vol_ratio': vol_ratio[i]
            })

sig_df = pd.DataFrame(results)
print(f"\n=== SIGNAL SUMMARY ===")
print(f"Total entry signals: {len(sig_df)}")
if len(sig_df) > 0:
    print(f"Date range: {sig_df['date'].min().date()} to {sig_df['date'].max().date()}")
    by_ticker = sig_df['ticker'].value_counts()
    print(f"\nSignals per ticker:")
    for t, c in by_ticker.items():
        print(f"  {t}: {c}")
    
    # ============================================================
    # 3. Quick backtest (single position at a time)
    # ============================================================
    print(f"\n{'='*60}")
    print(f"QUICK BACKTEST (Simple - single position, no sector cap)")
    print(f"{'='*60}")
    
    capital = INITIAL_CAPITAL
    cash = capital
    position = 0  # shares held
    entry_price = 0
    entry_date = None
    trade_log = []
    equity_curve = []
    
    all_dates = sorted(df['date'].unique())
    
    for d in all_dates:
        # Check for entry signals on this date
        day_sigs = sig_df[sig_df['date'] == d]
        
        # If no position, try to enter
        if position == 0 and len(day_sigs) > 0:
            # Take first signal
            sig = day_sigs.iloc[0]
            ticker = sig['ticker']
            price = sig['close']
            
            # Position sizing: 10% of capital per trade
            position_value = capital * 0.10
            shares = int(position_value / (price * (1 + COMMISSION + SLIPAGE)))
            if shares > 0 and price * shares <= cash:
                cost = price * shares * (1 + COMMISSION + SLIPAGE)
                cash -= cost
                position = shares
                entry_price = price
                entry_date = d
                trade_log.append({
                    'entry_date': d,
                    'ticker': ticker,
                    'entry_price': price,
                    'shares': shares,
                    'cost': cost
                })
        
        # If in position, check exit
        if position > 0:
            # Get current price for position ticker
            ticker = trade_log[-1]['ticker']
            current_row = df[(df['ticker'] == ticker) & (df['date'] == d)]
            
            if len(current_row) > 0:
                current_price = current_row['close'].values[0]
                current_high = current_row['high'].values[0]
                current_low = current_row['low'].values[0]
                
                # Calculate signal values for exit check
                ticker_data = df[df['ticker'] == ticker].sort_values('date')
                price_idx = ticker_data[ticker_data['date'] == d].index[0]
                pos_in_ticker = ticker_data.index.get_loc(price_idx)
                
                close_arr = ticker_data['close'].values
                high_arr = ticker_data['high'].values
                low_arr = ticker_data['low'].values
                
                # Get current values
                curr_close = close_arr[pos_in_ticker]
                curr_high = high_arr[pos_in_ticker]
                curr_low = low_arr[pos_in_ticker]
                
                # Check exits
                should_exit = False
                exit_reason = ""
                
                # SL: -7% from entry
                sl_price = entry_price * 0.93
                if curr_low <= sl_price:
                    should_exit = True
                    exit_reason = "stop_loss"
                    exit_price = sl_price
                
                # Trend break
                # Compute EMA200 for this ticker at this point
                sub = ticker_data.iloc[:pos_in_ticker+1]
                if len(sub) >= 200:
                    sub_close = sub['close'].values
                    sub_ema200 = pd.Series(sub_close).ewm(span=200, adjust=False).mean().values[-1]
                    if curr_close < sub_ema200:
                        should_exit = True
                        exit_reason = "trend_break"
                        exit_price = curr_close
                
                # Exit at close
                if should_exit:
                    proceeds = position * exit_price * (1 - COMMISSION - SLIPAGE)
                    cash += proceeds
                    pnl = proceeds - trade_log[-1]['cost']
                    pnl_pct = (exit_price / entry_price - 1) * 100
                    trade_log[-1].update({
                        'exit_date': d,
                        'exit_price': exit_price,
                        'proceeds': proceeds,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'exit_reason': exit_reason,
                        'days_held': (d - entry_date).days
                    })
                    position = 0
                    entry_price = 0
                    entry_date = None
        
        nav = cash + (position * current_row['close'].values[0] if position > 0 and len(current_row) > 0 else 0)
        equity_curve.append({'date': d, 'nav': nav})
    
    # Close any open position at last date
    if position > 0:
        last_row = df[(df['ticker'] == trade_log[-1]['ticker']) & (df['date'] == all_dates[-1])]
        if len(last_row) > 0:
            exit_price = last_row['close'].values[0]
            proceeds = position * exit_price * (1 - COMMISSION - SLIPAGE)
            cash += proceeds
            pnl = proceeds - trade_log[-1]['cost']
            trade_log[-1].update({
                'exit_date': all_dates[-1],
                'exit_price': exit_price,
                'proceeds': proceeds,
                'pnl': pnl,
                'pnl_pct': (exit_price / entry_price - 1) * 100,
                'exit_reason': 'end_of_test',
                'days_held': (all_dates[-1] - entry_date).days
            })
            position = 0
    
    final_nav = cash
    total_return = (final_nav / INITIAL_CAPITAL - 1) * 100
    
    # Metrics
    trade_df = pd.DataFrame(trade_log)
    if len(trade_df) > 0:
        win_trades = trade_df[trade_df['pnl'] > 0]
        loss_trades = trade_df[trade_df['pnl'] <= 0]
        win_rate = len(win_trades) / len(trade_df) * 100 if len(trade_df) > 0 else 0
        avg_win = win_trades['pnl_pct'].mean() if len(win_trades) > 0 else 0
        avg_loss = loss_trades['pnl_pct'].mean() if len(loss_trades) > 0 else 0
        total_pnl = trade_df['pnl'].sum()
        avg_days = trade_df['days_held'].mean()
        
        # Max drawdown
        eq_df = pd.DataFrame(equity_curve)
        eq_df['peak'] = eq_df['nav'].cummax()
        eq_df['dd'] = (eq_df['nav'] - eq_df['peak']) / eq_df['peak'] * 100
        max_dd = eq_df['dd'].min()
        
        # CAGR
        days = (all_dates[-1] - all_dates[0]).days
        years = days / 365.25
        cagr = ((final_nav / INITIAL_CAPITAL) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS (Simple Strategy)")
        print(f"{'='*60}")
        print(f"Period:        {all_dates[0].date()} to {all_dates[-1].date()} ({years:.1f} years)")
        print(f"Initial:       {INITIAL_CAPITAL:,.0f} VND ({INITIAL_CAPITAL/1e9:.1f} tỷ)")
        print(f"Final:         {final_nav:,.0f} VND ({final_nav/1e9:.3f} tỷ)")
        print(f"Total Return:  {total_return:+.2f}%")
        print(f"CAGR:          {cagr:+.2f}%")
        print(f"Max DD:        {max_dd:.2f}%")
        print(f"Total Trades:  {len(trade_df)}")
        print(f"Win Rate:      {win_rate:.1f}%")
        print(f"Avg Win:       {avg_win:+.2f}%")
        print(f"Avg Loss:      {avg_loss:+.2f}%")
        print(f"Avg Days Held: {avg_days:.0f}")
        print(f"Profit Factor: {abs(win_trades['pnl'].sum() / loss_trades['pnl'].sum()) if len(loss_trades) > 0 and loss_trades['pnl'].sum() != 0 else float('inf'):.2f}")
        
        # Show trades
        print(f"\n--- TRADES ---")
        for _, t in trade_df.iterrows():
            print(f"{t['entry_date'].date()} {t['ticker']:6s} IN: {t['entry_price']:>8.0f} OUT: {t['exit_price']:>8.0f} PNL: {t['pnl_pct']:+6.2f}% [{t['days_held']}d] {t['exit_reason']}")
        
        # Monthly returns
        eq_df = pd.DataFrame(equity_curve)
        eq_df['date'] = pd.to_datetime(eq_df['date'])
        eq_df['month'] = eq_df['date'].dt.to_period('M')
        monthly = eq_df.groupby('month')['nav'].last().pct_change() * 100
        print(f"\n--- MONTHLY RETURNS ---")
        for m, r in monthly.items():
            if not pd.isna(r):
                print(f"  {m}: {r:+.2f}%")
        
        # Sharpe (assuming 0% risk-free)
        daily_returns = eq_df['nav'].pct_change().dropna()
        sharpe = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() > 0 else 0
        print(f"\nSharpe Ratio:  {sharpe:.2f}")
    else:
        print("No trades executed.")
else:
    print("No signals generated. Try further relaxing conditions.")
