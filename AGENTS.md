# AGENTS.md — Kronos VN100 Trading System

## Project Overview

**VN100 trading system** — daily data refresh, strategy signals, Vercel-hosted dashboard backed by Supabase (no Python backend).
- **Frontend**: Next.js 14 (React 18) on Vercel, TailwindCSS, Recharts, lucide-react
- **DB**: Supabase (Postgres) — direct REST calls from Next.js API routes (no ORM)
- **Cron**: GitHub Actions (`daily_refresh.yml`) — Python script runs `daily_refresh.py`
- **Strategy**: Current simple strategy (EMA200/50/20 trend + momentum + volume + bullish candle) + **Codex Advise** multi-factor scoring (trend 25 + RS 20 + volume 15 + entry quality 25 + risk 15 = 100)
- **Symbols**: VN100 universe, 1 tỷ VND capital, max DD ≤15%, max positions 7, sector cap 20%

## Setup Commands

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend data refresh
cd scripts && pip install -r ../requirements.txt && python daily_refresh.py

# Type-check
cd frontend && npx tsc --noEmit

# Full build (must succeed before deploy)
cd frontend && npm run build
```

## Critical Context (read before any edit)

### Supabase REST API
- **REQUIRED headers**: `apikey` (anon key) AND `Authorization: Bearer <service_role_key>` — missing either causes "No API key found"
- **`head=true` NOT supported** — use `Prefer: count=exact` + `limit=1` instead
- **`and()` syntax**: inside parens use dot notation (`price.gte.0,close.gt.ema20`) NOT `=` signs
- **Boolean filters**: use `is.true` / `is.false` (NOT `eq.true`)
- **Service key rotated periodically** — `daily_refresh.py` auto-refreshes via Management API + PAT

### Secrets
- **`SUPABASE_MGT_PAT`**: `sbp_xxxx` — used for auto-refresh of service key
- **`GH_PAT`**: `github_pat_xxxx` — used for GH Actions dispatch from `/sync` page
- **Project ref**: `xgbficilqacfnzrbftoo`
- **Supabase URL**: `https://xgbficilqacfnzrbftoo.supabase.co`

### Arch & Deployment
- **Vercel root directory** = `frontend/` (NOT repo root)
- **Deploy**: push to `main` → Vercel auto-deploys (~1-2 min build)
- **No Render / no Python backend** — Next.js API routes replace FastAPI
- **Single-user, no auth**

### Data Model
- `daily_bars_adjusted` — OHLCV + adjusted columns, raw close in `close` column, adj in `adj_close`
- `stock_features` — pre-computed features per ticker (ema20/50/100/200, rsi14, atr14, vol_ratio, codex_score, codex_signal, codex_eligible...), `price` = adjusted close, `real_close` = raw close
- `market_index` — VNINDEX history for regime detection
- `bt_trades` — backtest trades
- Signal = **BUY only** (no sell signal in DB or API)

## Formula References

Any change to strategy logic MUST reference and match the corresponding spec doc:

- **`FILTER_FORMULAS.md`** — current simple strategy: trend/reversal/signal computation. All formulas here are source of truth.
- **`VN100_SIGNAL_FORMULAS.md`** — Codex Advise: scoring, market regime, base_eligible, buy signal (Section 12). All formulas here are source of truth.

### Key Codex formulas at a glance

| Component | Max | Key conditions |
|-----------|-----|----------------|
| Trend score | 25 | close>e50(8) + ema20>e50(6) + ema50>=ema100(5) + close>ema200(4) + 3 rising ema20(2) |
| RS score | 20 | rs20>0(8) + rs60>0(8) + ret60>=12%(4) |
| Volume score | 15 | vol_ratio>=1.1(5) + >=1.3(5) + value20>=50B(5) |
| Entry quality | 25 | close in ±3% ema20(10) + cp>=0.65(7) + br>=0.35(4) + rsi 45-68(4) |
| Risk score | 15 | atr_pct 1.5-4.5%(5) + close <= ema20*1.05(5) + rr>=2.0(5) |

### Market regime
- **Bull**: close>e50 AND e20>e50 AND e50>=e100
- **Recovery**: close>e20 AND e20 rising 3 sessions AND rsi>=45
- **Risk**: close<e50 AND e20<e50
- **Distribution**: >=3 down days with vol>1.2x OR close<e100

### Score classification (Section 9)
- >=80: Mạnh (strong)
- 65-79: Tốt (good)
- 50-64: Theo dõi (watch)
- <50: Bỏ qua (ignore)

## Workflow / Conventions

1. **Spec-first**: Before coding any logic change, read the relevant spec doc (FILTER_FORMULAS.md or VN100_SIGNAL_FORMULAS.md) and verify the formula matches
2. **Implement in Python first** (`scripts/daily_refresh.py`) for DB computation, **then mirror in TypeScript** (API route `frontend/app/api/v1/[...path]/route.ts`) for on-the-fly computation
3. **No comments** in code unless required by spec
4. **Vietnamese UI labels** for all user-facing text
5. **booleans in Supabase**: use `is.true` / `is.false` in REST params
6. **Secrets never in code**: use `.env` for local, GitHub Secrets for CI. Never commit actual secret values.
7. **Build must pass**: always run `npm run build` before pushing

## Deploy Flow (MANDATORY)

After any code change:
1. Run `npm run build` (frontend) to verify
2. Run `npx tsc --noEmit` to type-check
3. `git add -A && git commit -m "<message>"`
4. `git push origin main`
5. Wait for Vercel auto-deploy (~1-2 min)
6. **Do NOT ask for permission** — just commit, push, and deploy automatically unless explicitly told not to

## Code Style
- TypeScript strict mode
- No semicolons in JSX attributes
- Single quotes for strings
- Avoid comments unless explaining non-obvious logic
- Use existing patterns from neighboring files

## Verification Steps (run after any change)

```bash
# 1. Frontend build (catches type + compile errors)
cd frontend && npm run build

# 2. Type-check (catches type errors)
cd frontend && npx tsc --noEmit

# 3. Backend recompute (requires .env in scripts/)
cd scripts && python daily_refresh.py

# 4. Verify reversal / trend logic
cd scripts && python verify_reversal2.py
```

## Codex Reversal (Section 7) — On-the-fly only
- `codex_reversal` is NOT stored in DB — computed in API route via `getCodexReversal()`
- Uses prev-day adjusted data from `prevAdjMap` and prev-day volume from `prevVolMap`
- **Bullish Engulfing Body** (7A): bullish + prev red + open<=prev_close + close>=prev_open + br>=0.45 + cp>=0.65
- **Reclaim Candle** (7B): close>ema20 + low<ema20 + bullish + cp>=0.7 + br>=0.35
- **Volume confirmation**: vol_ratio>=1.2 AND curVol > prevVol
- Both need: volume_ok + rsi 40-65 + close >= ema50*0.97
- Prior pullback/prior downswing conditions NOT implemented (missing historical low/high queries)

## Security
- Never commit actual PAT tokens or API keys to the repo
- Use `.env.example` with placeholder values for reference
- GitHub Push Protection will block commits containing secrets — amend and retry
