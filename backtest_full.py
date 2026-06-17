#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VN100 Backtest v2 - fixed D+1 execution, wider stops, proper risk mgmt"""
import sys, os, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import httpx

# ============================================================
# CONFIG
# ============================================================
INITIAL_CAPITAL = 1_000_000_000
MAX_POSITIONS = 7
SECTOR_CAP = 0.20
COMMISSION = 0.0015
STOP_LOSS = 0.15
TRAIL_PCT = 0.10
TIME_STOP_DAYS = 30
MIN_BARS = 250
ENTRY_FRAC = 0.07

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
TICKER_SECTOR = {}
for sector, tickers in SECTORS.items():
    for t in tickers:
        TICKER_SECTOR[t] = sector

# ============================================================
# LOAD DATA
# ============================================================
def load_data():
    try:
        PAT = '<SUPABASE_PAT>'
        sql_url = 'https://api.supabase.com/v1/projects/xgbficilqacfnzrbftoo/database/query'
        r = httpx.post(sql_url, json={
            "query": "SELECT ticker, date, adj_open AS open, adj_high AS high, adj_low AS low, adj_close AS close, adj_volume AS volume FROM daily_bars_adjusted WHERE date >= '2021-01-01' ORDER BY ticker, date"
        }, headers={'Authorization': f'Bearer {PAT}', 'Content-Type': 'application/json'}, timeout=120)
        if r.status_code not in (200, 201):
            raise Exception(f"Status {r.status_code}")
        rows = r.json()
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        for c in ['open','high','low','close','volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        print(f"Data: {len(df)} rows, {df['ticker'].nunique()} tickers, {df['date'].min().date()} to {df['date'].max().date()}")
        return df
    except Exception as e:
        print(f"Load failed: {e}")
        raise

# ============================================================
# FEATURES
# ============================================================
def compute_features(tdf):
    n = len(tdf)
    close = tdf['close'].values; high = tdf['high'].values
    low = tdf['low'].values; vol = tdf['volume'].values

    def np_ema(arr, s):
        r = np.empty(n); r[:] = np.nan
        m = 2/(s+1); r[0] = arr[0]
        for i in range(1, n): r[i] = (arr[i]-r[i-1])*m + r[i-1]
        return r

    e20 = np_ema(close, 20)
    e50 = np_ema(close, 50)
    e200 = np_ema(close, 200)

    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    ag = np.empty(n); al = np.empty(n); ag[:] = np.nan; al[:] = np.nan
    ag[14] = np.mean(gain[:14]); al[14] = np.mean(loss[:14])
    for i in range(15, n):
        ag[i] = (ag[i-1]*13 + gain[i-1])/14
        al[i] = (al[i-1]*13 + loss[i-1])/14
    rs = ag / np.where(al == 0, 0.001, al)
    r14 = 100 - (100/(1+rs))

    tr = np.maximum(high[1:]-low[1:], np.maximum(np.abs(high[1:]-close[:-1]), np.abs(low[1:]-close[:-1])))
    at = np.empty(n); at[:] = np.nan
    at[14] = np.mean(tr[:14])
    for i in range(15, n):
        at[i] = (at[i-1]*13 + tr[i-1])/14

    vm = np.empty(n); vm[:] = np.nan
    for i in range(19, n):
        vm[i] = np.mean(vol[i-19:i+1])
    vr = vol / np.where(vm == 0, 1, vm)

    body = np.abs(close - tdf['open'].values)
    cr = high - low; cr = np.where(cr == 0, 0.001, cr)
    bc = (close > tdf['open'].values) & (body/cr >= 0.4)

    return e20, e50, e200, r14, at, vr, bc

# ============================================================
# BACKTEST
# ============================================================
def run_backtest(df):
    tickers = sorted(df['ticker'].unique())
    ticker_data = {}
    for t in tickers:
        tdf = df[df['ticker']==t].copy().sort_values('date')
        if len(tdf) >= MIN_BARS:
            e20, e50, e200, r14, at, vr, bc = compute_features(tdf)
            tdf['ema20'] = e20; tdf['ema50'] = e50; tdf['ema200'] = e200
            tdf['rsi14'] = r14; tdf['atr14'] = at
            tdf['vol_ratio'] = vr; tdf['bullish'] = bc
            ticker_data[t] = tdf
    print(f"Tickers with data: {len(ticker_data)}")

    dates = sorted(df['date'].unique())
    cash = INITIAL_CAPITAL
    portfolio = []
    trades = []
    equity_curve = []

    date_to_idx = {d: i for i, d in enumerate(dates)}

    def sector_exposure(portfolio):
        se = {}
        for p in portfolio:
            s = TICKER_SECTOR.get(p['ticker'], 'Others')
            se[s] = se.get(s, 0) + p['cost']
        return se

    for d_idx, d in enumerate(dates):
        if d_idx == 0:
            pv = 0
            for p in portfolio:
                tdf = ticker_data.get(p['ticker'])
                if tdf is None: continue
                row = tdf[tdf['date']==d]
                if len(row) > 0:
                    pv += p['shares'] * row.iloc[0]['close']
            nav = cash + pv
            equity_curve.append({'date': d, 'nav': nav, 'cash': cash, 'positions': len(portfolio)})
            continue

        prev_date = dates[d_idx - 1]
        tickers_in_portfolio = {p['ticker'] for p in portfolio}
        n_pos = len(portfolio)

        # Compute total equity for sector cap
        pv = 0
        for p in portfolio:
            tdf = ticker_data.get(p['ticker'])
            if tdf is None: continue
            row = tdf[tdf['date'] == d]
            if len(row) > 0:
                pv += p['shares'] * row.iloc[0]['close']
        total_equity = cash + pv

        # ENTRY: signal at prev_date close, execute at this date close
        if n_pos < MAX_POSITIONS:
            candidates = []
            for t, tdf in ticker_data.items():
                if t in tickers_in_portfolio:
                    continue
                prev_row = tdf[tdf['date'] == prev_date]
                if len(prev_row) == 0:
                    continue
                r = prev_row.iloc[0]
                if pd.isna(r.get('ema200')):
                    continue

                macro_bull = bool(r['close'] > r['ema200']) & bool(r['ema50'] > r['ema200'])
                momentum = bool(r['close'] > r['ema20'])
                vol_ok = not np.isnan(r['vol_ratio']) and r['vol_ratio'] > 1.0

                if macro_bull and momentum and vol_ok and r['bullish']:
                    sec = TICKER_SECTOR.get(t, 'Others')
                    sec_exp = sector_exposure(portfolio)
                    sec_val = sec_exp.get(sec, 0)
                    if sec_val < total_equity * SECTOR_CAP:
                        exec_row = tdf[tdf['date'] == d]
                        if len(exec_row) == 0:
                            continue
                        exec_price = exec_row.iloc[0]['close']
                        candidates.append((t, exec_price, sec, r.get('atr14', exec_price*0.02)))

            candidates.sort(key=lambda x: x[1], reverse=False)

            for t, price, sec, atr in candidates:
                if len(portfolio) >= MAX_POSITIONS:
                    break
                sec_exp = sector_exposure(portfolio)
                add_val = total_equity * ENTRY_FRAC
                if (sec_exp.get(sec, 0) + add_val) >= total_equity * SECTOR_CAP:
                    continue

                pos_val = cash * ENTRY_FRAC
                shares = int(pos_val / (price * (1 + COMMISSION)))
                if shares <= 0:
                    continue
                cost = price * shares * (1 + COMMISSION)
                if cost > cash:
                    pos_val = cash * 0.5
                    shares = int(pos_val / (price * (1 + COMMISSION)))
                    if shares <= 0:
                        continue
                    cost = price * shares * (1 + COMMISSION)
                cash -= cost
                portfolio.append({
                    'ticker': t, 'entry_date': d, 'entry_price': price,
                    'shares': shares, 'cost': cost, 'sector': sec,
                    'high_since_entry': price, 'atr14': atr
                })
                tickers_in_portfolio.add(t)

        # EXIT
        to_remove = []
        for p in portfolio:
            t = p['ticker']
            tdf = ticker_data[t]
            row = tdf[tdf['date'] == d]
            if len(row) == 0:
                continue
            r = row.iloc[0]
            cp = r['close']; lo = r['low']; hi = r['high']

            p['high_since_entry'] = max(p['high_since_entry'], hi)

            sl_fixed = p['entry_price'] * (1 - STOP_LOSS)
            sl_trail = p['high_since_entry'] * (1 - TRAIL_PCT)
            sl = max(sl_fixed, sl_trail)

            reason = None
            ep = None
            if lo <= sl:
                sl_price = sl
                if sl_price > p['entry_price']:
                    sl_price = hi
                reason = 'stop_loss'
                ep = sl_price
            elif not pd.isna(r.get('ema200')) and cp < r['ema200']:
                reason = 'trend_break'
                ep = cp
            elif (d - p['entry_date']).days >= TIME_STOP_DAYS:
                reason = 'time_stop'
                ep = cp

            if reason:
                proceeds = p['shares'] * ep * (1 - COMMISSION)
                pnl = proceeds - p['cost']
                trades.append({
                    **p, 'exit_date': d, 'exit_price': ep, 'proceeds': proceeds,
                    'pnl': pnl, 'pnl_pct': (ep / p['entry_price'] - 1) * 100,
                    'exit_reason': reason, 'days_held': (d - p['entry_date']).days
                })
                cash += proceeds
                to_remove.append(t)

        portfolio = [p for p in portfolio if p['ticker'] not in to_remove]

        # Close at end
        if d_idx == len(dates) - 1:
            for p in portfolio[:]:
                tdf = ticker_data.get(p['ticker'])
                if tdf is None:
                    continue
                row = tdf[tdf['date'] == d]
                ep = row.iloc[0]['close'] if len(row) > 0 else p['entry_price']
                proceeds = p['shares'] * ep * (1 - COMMISSION)
                pnl = proceeds - p['cost']
                trades.append({
                    **p, 'exit_date': d, 'exit_price': ep, 'proceeds': proceeds,
                    'pnl': pnl, 'pnl_pct': (ep / p['entry_price'] - 1) * 100,
                    'exit_reason': 'end_of_test', 'days_held': (d - p['entry_date']).days
                })
                cash += proceeds
            portfolio = []

        # NAV
        pv = 0
        for p in portfolio:
            tdf = ticker_data.get(p['ticker'])
            if tdf is None:
                continue
            row = tdf[tdf['date'] == d]
            if len(row) > 0:
                pv += p['shares'] * row.iloc[0]['close']
        nav = cash + pv
        equity_curve.append({'date': d, 'nav': nav, 'cash': cash, 'positions': len(portfolio)})

    return pd.DataFrame(equity_curve), pd.DataFrame(trades)

# ============================================================
# METRICS
# ============================================================
def print_tearsheet(eq, tr, dates):
    final_nav = eq['nav'].iloc[-1]
    total_ret = (final_nav / INITIAL_CAPITAL - 1) * 100
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = ((final_nav / INITIAL_CAPITAL) ** (1 / years) - 1) * 100 if years > 0 else 0

    eq['peak'] = eq['nav'].cummax()
    eq['dd'] = (eq['nav'] - eq['peak']) / eq['peak'] * 100
    max_dd = eq['dd'].min()

    dr = eq['nav'].pct_change().dropna()
    sharpe = np.sqrt(252) * dr.mean() / dr.std() if dr.std() > 0 else 0

    print("\n" + "=" * 70)
    print("VN100 BACKTEST v2 TEARSHEET")
    print("=" * 70)
    print(f"{'Period':22s}: {dates[0].date()} to {dates[-1].date()} ({years:.1f}y)")
    print(f"{'Initial Capital':22s}: {INITIAL_CAPITAL:>14,.0f}")
    print(f"{'Final NAV':22s}: {final_nav:>14,.0f}")
    print(f"{'Total Return':22s}: {total_ret:>+13.2f}%")
    print(f"{'CAGR':22s}: {cagr:>+13.2f}%")
    print(f"{'Max Drawdown':22s}: {max_dd:>13.2f}%")
    print(f"{'Sharpe':22s}: {sharpe:>13.2f}")

    if len(tr) > 0:
        wins = tr[tr['pnl'] > 0]; losses = tr[tr['pnl'] <= 0]
        wr = len(wins) / len(tr) * 100
        print(f"{'Total Trades':22s}: {len(tr):>14d}")
        print(f"{'Win Rate':22s}: {wr:>12.1f}%")
        print(f"{'Avg Win':22s}: {wins['pnl_pct'].mean():>+13.2f}%")
        print(f"{'Avg Loss':22s}: {losses['pnl_pct'].mean():>+13.2f}%")
        pf = abs(wins['pnl'].sum() / losses['pnl'].sum()) if len(losses) > 0 and losses['pnl'].sum() != 0 else float('inf')
        print(f"{'Profit Factor':22s}: {pf:>13.2f}")
        print(f"{'Avg Days Held':22s}: {tr['days_held'].mean():>13.0f}")

        eq['month'] = eq['date'].dt.to_period('M')
        monthly = eq.groupby('month')['nav'].last().pct_change() * 100
        print(f"\n{'MONTHLY RETURNS':^50}")
        print(f"{'Month':<18} {'Return':>10} | {'Month':<18} {'Return':>10}")
        mons = list(monthly.items())
        for i in range(0, len(mons), 2):
            m1, r1 = mons[i]
            s1 = f"{m1}: {r1:+.2f}%" if not pd.isna(r1) else f"{m1}: N/A"
            if i + 1 < len(mons):
                m2, r2 = mons[i + 1]
                s2 = f"{m2}: {r2:+.2f}%" if not pd.isna(r2) else f"{m2}: N/A"
                print(f"{s1:<30} {s2:<30}")
            else:
                print(f"{s1:<30}")

        eq['year'] = eq['date'].dt.year
        yearly = eq.groupby('year')['nav'].last()
        print(f"\n--- YEARLY ---")
        for i, (y, nv) in enumerate(yearly.items()):
            prev = INITIAL_CAPITAL if i == 0 else yearly.iloc[i - 1]
            print(f"  {y}: {(nv / prev - 1) * 100:+.2f}%")

        print(f"\n--- TRADES BY SECTOR ---")
        for s, grp in tr.groupby('sector'):
            print(f"  {s}: {len(grp)} trades, WR: {(grp['pnl'] > 0).mean() * 100:.0f}%, Avg: {grp['pnl_pct'].mean():+.2f}%")

        print(f"\n--- EXIT REASONS ---")
        for reason, cnt in tr['exit_reason'].value_counts().items():
            grp = tr[tr['exit_reason'] == reason]
            print(f"  {reason}: {cnt} trades, WR: {(grp['pnl'] > 0).mean() * 100:.0f}%, Avg: {grp['pnl_pct'].mean():+.2f}%")

        print(f"\n--- TOP 5 ---")
        for _, t in tr.sort_values('pnl_pct', ascending=False).head(5).iterrows():
            print(f"  {t['entry_date'].date()} {t['ticker']:6s} IN:{t['entry_price']:>8.0f} OUT:{t['exit_price']:>8.0f} {t['pnl_pct']:+6.2f}% [{t['days_held']}d] {t['exit_reason']}")

        print(f"\n--- BOTTOM 5 ---")
        for _, t in tr.sort_values('pnl_pct').head(5).iterrows():
            print(f"  {t['entry_date'].date()} {t['ticker']:6s} IN:{t['entry_price']:>8.0f} OUT:{t['exit_price']:>8.0f} {t['pnl_pct']:+6.2f}% [{t['days_held']}d] {t['exit_reason']}")

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    df = load_data()
    eq, tr = run_backtest(df)
    dates = sorted(df['date'].unique())
    print_tearsheet(eq, tr, dates)
    eq.to_csv(os.path.join(os.path.dirname(__file__), 'bt_equity_v2.csv'), index=False)
    tr.to_csv(os.path.join(os.path.dirname(__file__), 'bt_trades_v2.csv'), index=False)
    print(f"\nSaved bt_equity_v2.csv, bt_trades_v2.csv")

