# VN100 Trading Dashboard — Specification

## 1. Tổng quan

Hệ thống web dashboard giúp người dùng theo dõi tín hiệu giao dịch VN100, quản lý danh mục, lọc cổ phiếu theo điều kiện kỹ thuật, và nhận cảnh báo qua Telegram/Email.

### Kiến trúc

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Next.js    │────▶│  FastAPI     │────▶│  Supabase    │
│  Frontend   │     │  Backend     │     │  (PostgreSQL)│
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────▼───────┐
                    │  APScheduler │
                    │  (daily job) │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  vnstock     │
                    │  API (VCI)   │
                    └──────────────┘
```

## 2. Chức năng chi tiết

### 2.1 Dashboard chính
- 5 KPI cards: NAV, Cash, Positions, Drawdown, Số tín hiệu hôm nay
- Biểu đồ equity curve (NAV theo thời gian)
- Biểu đồ drawdown
- Danh sách tín hiệu mới nhất (hôm nay)
- Trạng thái hệ thống (lần cuối cập nhật, API health)

### 2.2 Tín hiệu (Signals)
- **Entry signals**: Danh sách mã đủ điều kiện mua kèm lý do
  - Macro trend: close > EMA200, EMA50 > EMA200
  - Momentum: close > EMA20
  - Volume surge: vol_ratio > 1.0
  - Bullish candle pattern
  - Điểm tín hiệu (score)
- **Exit signals**: Danh sách mã cần bán kèm lý do
  - Stop loss
  - Trend break (close < EMA200)
  - Time stop (30 ngày)
- Chi tiết từng tín hiệu: biểu đồ nến 6 tháng, EMA lines, volume, RSI

### 2.3 Bộ lọc cổ phiếu (Screener)
- Filter theo:
  - Xu hướng: trên/dưới EMA20/50/200
  - Khối lượng: vol_ratio > X
  - RSI: khoảng giá trị
  - Nến: bullish/bearish
  - Ngành (sector)
  - Giá: khoảng giá
- Kết quả dạng bảng + highlight mã đạt điều kiện entry

### 2.4 Danh mục (Portfolio)
- Quản lý danh mục đầu tư:
  - Thêm/sửa/xóa vị thế
  - Nhập thủ công: ticker, entry_price, quantity, entry_date
  - Tự động cập nhật giá hiện tại
- Hiển thị:
  - PnL theo mã, theo ngành
  - Phân bổ danh mục (biểu đồ tròn)
  - Drawdown từng vị thế
  - Tổng hợp NAV, Cash, % mỗi ngành

### 2.5 Danh sách theo dõi (Watchlist)
- Thêm/xóa mã cần theo dõi
- Hiển thị trạng thái hiện tại:
  - Giá, % thay đổi
  - Tín hiệu (entry/exit/neutral)
  - Khoảng cách đến stop loss / take profit
- Tự động refresh khi có dữ liệu mới

### 2.6 Cảnh báo (Alerts)
- Cấu hình Telegram bot token + chat ID
- Cấu hình Email SMTP
- Bật/tắt từng loại alert:
  - Daily signal: tín hiệu hàng ngày
  - Position open/close: mở/đóng vị thế
  - Stop loss hit: chạm stop loss
  - Drawdown warning: DD > 10%
  - Drawdown stop: DD > 15%
- Test alert button

### 2.7 Lịch sử giao dịch (Trade History)
- Danh sách tất cả giao dịch đã đóng
- Filter theo: ticker, ngày, lý do exit, thắng/thua
- Thống kê: win rate, avg win/loss, profit factor, Sharpe

### 2.8 Cập nhật dữ liệu & API Endpoints

**Backend endpoints:**

```
GET    /api/v1/health                 # Health check
GET    /api/v1/dashboard              # Dashboard summary data
GET    /api/v1/signals/entry          # Entry signal list
GET    /api/v1/signals/exit           # Exit signal list
GET    /api/v1/signals/{ticker}       # Signal detail for a ticker
GET    /api/v1/screener               # Stock screener with filters
GET    /api/v1/portfolio              # Get/watch portfolio
POST   /api/v1/portfolio/positions    # Add position
PUT    /api/v1/portfolio/positions/{id} # Edit position
DELETE /api/v1/portfolio/positions/{id} # Remove position
GET    /api/v1/watchlist              # Get watchlist
POST   /api/v1/watchlist              # Add to watchlist
DELETE /api/v1/watchlist/{ticker}     # Remove from watchlist
GET    /api/v1/alerts/config          # Get alert config
PUT    /api/v1/alerts/config          # Update alert config
POST   /api/v1/alerts/test            # Send test alert
GET    /api/v1/trades                 # Trade history
POST   /api/v1/data/refresh           # Trigger data refresh
```

### 2.9 Các bảng Supabase bổ sung

```sql
-- Watchlist
CREATE TABLE watchlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT DEFAULT 'default',
  ticker TEXT NOT NULL,
  note TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, ticker)
);

-- Alert config (single row per user)
CREATE TABLE alert_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT DEFAULT 'default',
  telegram_token TEXT,
  telegram_chat_id TEXT,
  email_host TEXT DEFAULT 'smtp.gmail.com',
  email_user TEXT,
  email_pass TEXT,
  alert_daily_signal BOOLEAN DEFAULT true,
  alert_position_open BOOLEAN DEFAULT true,
  alert_position_close BOOLEAN DEFAULT true,
  alert_stop_loss BOOLEAN DEFAULT true,
  alert_drawdown_warning BOOLEAN DEFAULT true,
  alert_drawdown_stop BOOLEAN DEFAULT true,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Portfolio positions
CREATE TABLE portfolio_positions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT DEFAULT 'default',
  ticker TEXT NOT NULL,
  entry_price DOUBLE PRECISION NOT NULL,
  quantity INTEGER NOT NULL,
  entry_date DATE NOT NULL,
  stop_loss DOUBLE PRECISION,
  note TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily signals log
CREATE TABLE daily_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL,
  ticker TEXT NOT NULL,
  signal_type TEXT NOT NULL,  -- 'entry' or 'exit'
  reason TEXT,
  strength DOUBLE PRECISION,
  price DOUBLE PRECISION,
  details JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 3. Công nghệ

| Layer | Công nghệ |
|-------|-----------|
| Frontend | Next.js 14 (App Router), Tailwind CSS, shadcn/ui, Recharts |
| Backend | FastAPI (Python 3.11+), APScheduler |
| Database | Supabase (PostgreSQL) |
| Auth | Supabase Auth (hoặc simple API key) |
| Data source | vnstock VCI API |
| Deployment | Docker Compose |
| CI/CD | GitHub Actions (optional) |

## 4. UI/UX Design

- Dark theme trading dashboard (modern finance style)
- Layout: Sidebar navigation + main content area
- Responsive: desktop-first, tablet-support
- Color scheme:
  - Buy/Up: #22c55e (green)
  - Sell/Down: #ef4444 (red)
  - Neutral: #6b7280 (gray)
  - Background: #0f172a (slate-900)
  - Card: #1e293b (slate-800)
- Charts: interactive (tooltip, zoom) using Recharts

## 5. Deployment

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    restart: always

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on: [backend]
    restart: always
```

## 6. File Structure

```
Kronos/
├── SPEC.md                    # This file
├── USER_GUIDE.md              # Hướng dẫn sử dụng
├── DEV_GUIDE.md               # Hướng dẫn phát triển
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   ├── signals.py
│   │   ├── screening.py
│   │   ├── portfolio.py
│   │   ├── watchlist.py
│   │   ├── alerts.py
│   │   └── trades.py
│   └── services/
│       ├── __init__.py
│       ├── data_service.py
│       ├── signal_service.py
│       ├── screener_service.py
│       └── alert_service.py
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── Dockerfile
│   └── app/
│       ├── layout.tsx
│       ├── page.tsx
│       ├── dashboard/
│       ├── signals/
│       ├── screener/
│       ├── portfolio/
│       ├── watchlist/
│       ├── alerts/
│       └── trades/
├── deploy/
│   └── docker-compose.yml
└── src/                       # Existing strategy code
```
