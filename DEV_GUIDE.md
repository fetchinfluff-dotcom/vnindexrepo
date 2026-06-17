# Hướng dẫn phát triển VN100 Trading Dashboard

## Kiến trúc

```
frontend/ (Next.js 14 + Tailwind CSS)
  └── app/
      ├── dashboard/    # Trang tổng quan
      ├── signals/      # Tín hiệu entry/exit
      ├── screener/     # Bộ lọc cổ phiếu
      ├── portfolio/    # Quản lý danh mục
      ├── watchlist/    # Danh sách theo dõi
      ├── alerts/       # Cấu hình cảnh báo
      └── trades/       # Lịch sử giao dịch

backend/ (FastAPI + APScheduler)
  ├── routers/          # API endpoints
  ├── services/         # Business logic
  └── main.py           # App entry point
```

## Cài đặt môi trường phát triển

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/dashboard` | Dashboard summary |
| GET | `/api/v1/signals/entry` | Entry signals list |
| GET | `/api/v1/signals/entry/{ticker}` | Signal detail + chart data |
| GET | `/api/v1/screener?trend=&sector=&vol_ratio_min=&rsi_min=&rsi_max=&candle=&price_min=&price_max=` | Stock screener |
| GET | `/api/v1/portfolio` | Portfolio positions |
| POST | `/api/v1/portfolio/positions` | Add position |
| PUT | `/api/v1/portfolio/positions/{id}` | Update position |
| DELETE | `/api/v1/portfolio/positions/{id}` | Delete position |
| GET | `/api/v1/watchlist` | Watchlist items |
| POST | `/api/v1/watchlist` | Add to watchlist |
| DELETE | `/api/v1/watchlist/{ticker}` | Remove from watchlist |
| GET | `/api/v1/alerts/config` | Alert configuration |
| PUT | `/api/v1/alerts/config` | Update alert config |
| POST | `/api/v1/alerts/test` | Send test alert |
| GET | `/api/v1/trades` | Trade history |

## Database (Supabase)

### Bảng chính
- `daily_bars_adjusted` - Dữ liệu OHLCV adjusted
- `portfolio_positions` - Vị thế người dùng
- `watchlist` - Danh sách theo dõi
- `alert_config` - Cấu hình cảnh báo
- `daily_signals` - Tín hiệu hàng ngày

### Management API
Sử dụng PAT key để query Supabase qua Management API:
```python
r = httpx.post(
    "https://api.supabase.com/v1/projects/{ref}/database/query",
    json={"query": "SELECT * FROM daily_bars_adjusted LIMIT 1"},
    headers={"Authorization": f"Bearer {PAT}"}
)
```

## Chiến lược giao dịch

### Entry Conditions
1. **Macro Bull**: `close > EMA200 AND EMA50 > EMA200`
2. **Momentum**: `close > EMA20`
3. **Volume**: `vol_ratio > 1.0` (volume > 20-day MA)
4. **Candle**: Bullish (body >= 40% of range)

### Exit Conditions
1. **Stop Loss**: 15% fixed OR 10% trailing from highest close
2. **Trend Break**: `close < EMA200`
3. **Time Stop**: 30 days

### Risk Management
- Max 7 positions
- 7% equity per entry
- 20% sector cap
- Position size based on current equity

## Deployment

### Docker
```bash
docker-compose -f deploy/docker-compose.yml up -d
```

### Thêm/Sửa page
1. Tạo thư mục trong `frontend/app/`
2. Tạo `page.tsx` với component mặc định
3. Thêm vào `NAV_ITEMS` trong `Components/Sidebar.tsx`

### Thêm API endpoint
1. Tạo file trong `backend/routers/`
2. Thêm router vào `main.py`

## Coding Conventions
- TypeScript cho frontend, Python cho backend
- Sử dụng `fetchAPI`/`postAPI` từ `lib/api.ts` cho API calls
- Format số VND với `fmt()`, % với `fmtPct()`
- CSS: Tailwind utility classes, tránh custom CSS
- Màu sắc: buy=#22c55e, sell=#ef4444, neutral=#6b7280
