# VN100 Trading Dashboard

Hệ thống giao dịch tự động cho VN100, bao gồm bộ lọc cổ phiếu, tín hiệu giao dịch, quản lý danh mục và theo dõi.

## Kiến trúc

```
GitHub Actions (cron)  →  Python script (daily_refresh.py)
       ↓                        ↓
  VCI/vnstock API        Supabase DB
       ↓                        ↓
  Next.js API routes  ←  Supabase REST API
       ↓
  Vercel (frontend)
```

- **Dữ liệu**: VCI (vietstock) qua thư viện `vnstock`, fallback DNSE
- **Cơ sở dữ liệu**: Supabase PostgreSQL (REST API qua service_role key + apikey)
- **Backend**: Không có backend server riêng — Next.js API routes proxy trực tiếp đến Supabase
- **Cron**: GitHub Actions 15:30 VN, thứ 2 - thứ 6
- **Hosting**: Vercel (frontend + API routes)

## Triển khai

### Quy trình deploy (QUAN TRỌNG)

**Chỉ deploy bằng cách push lên GitHub** — KHÔNG dùng `vercel deploy --prod` từ local.

```bash
git add -A
git commit -m "mô tả thay đổi"
git push origin main
# Vercel auto-deploy từ GitHub integration
```

Lý do: máy local có nhiều GitHub account gây lỗi xác thực khi dùng Vercel CLI trực tiếp.

### Deploy thủ công (nếu auto-deploy không chạy)
1. Vào https://vercel.com/ngtrhieuut-s-projects/vnindex-trading
2. Deployments → tìm commit mới nhất → Promote to Production
3. Hoặc dùng Vercel CLI từ thư mục `frontend/`:
```bash
cd frontend
vercel deploy --prod --force
```

### Cấu hình môi trường Vercel
```
NEXT_PUBLIC_SUPABASE_URL        = https://xgbficilqacfnzrbftoo.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY   = (anon key, đã bị rotate — lấy từ Supabase Management API)
SUPABASE_URL                    = (giống PUBLIC)
SUPABASE_SERVICE_ROLE_KEY       = (service_role key)
GH_PAT                          = (GitHub PAT để trigger workflow từ web)
```

## API Endpoints

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/api/v1/dashboard` | GET | Thông tin dashboard (ngày cập nhật, config) |
| `/api/v1/screener` | GET | Bộ lọc cổ phiếu (trend, rsi, signal, reversal, ...) |
| `/api/v1/signals/entry` | GET | Tín hiệu mua (có filter ticker) |
| `/api/v1/portfolio` | GET | Danh mục đầu tư |
| `/api/v1/watchlist` | GET | Danh sách theo dõi (filter `?list_name=`) |
| `/api/v1/watchlist/lists` | GET | Danh sách các danh mục theo dõi |
| `/api/v1/trades` | GET | Lịch sử giao dịch backtest |
| `/api/v1/alerts/config` | GET/PUT | Cấu hình cảnh báo |
| `/api/v1/sync` | GET | Kích hoạt đồng bộ dữ liệu (trigger GitHub Actions) |
| `/api/v1/portfolio/positions` | POST | Thêm vị thế |
| `/api/v1/watchlist` | POST | Thêm mã theo dõi |
| `/api/v1/portfolio/positions/:id` | DELETE | Xóa vị thế |
| `/api/v1/watchlist/:ticker` | DELETE | Xóa mã theo dõi |

## Database Tables

| Table | Mô tả | Cột chính |
|-------|-------|-----------|
| `daily_bars_adjusted` | Dữ liệu OHLCV điều chỉnh | ticker, date, open, high, low, close, volume |
| `stock_features` | Đặc trưng kỹ thuật hàng ngày | ticker, date, price, ema20, ema50, ema200, rsi14, vol_ratio, bullish, signal |
| `daily_signals` | Tín hiệu giao dịch | ticker, date, action, price |
| `bt_trades` | Kết quả backtest | entry_date, exit_date, ticker, pnl, ... |
| `portfolio_positions` | Vị thế thực | ticker, entry_price, quantity, entry_date, ... |
| `watchlist` | Danh sách theo dõi (multi-list) | ticker, list_name |

## Signal & Chiến lược

### Điều kiện Signal (BUY)
```python
condition = (close > ema20) & (close > ema200) & (ema50 > ema200) & \
            (rsi14 > 50) & (vol_ratio > 0.5) & (bullish == True)
```

### Backtest (2021-01 → 2026-06)
- CAGR: 27.15%
- Tổng lợi nhuận: +270.09%
- Max Drawdown: -14.20%
- Sharpe: 1.88
- Win Rate: 41.8%
- Profit Factor: 2.04
- Số giao dịch: 753

### Giải thích Signal
- `signal = true` = tín hiệu **MUA** — giá đóng cửa > EMA20 > EMA200, EMA50 > EMA200, RSI > 50, khối lượng > 0.5x trung bình, nến bullish
- Không có tín hiệu bán tự động — nhà đầu tư tự quyết định chốt lời/cắt lỗ
- Mua ở **giá close** ngày có tín hiệu, hoặc ATC phiên tiếp theo (giá mở cửa phiên sau ±1-2%)

### Các cột trong Bộ lọc
| Cột | Ý nghĩa |
|-----|---------|
| Mã | Mã chứng khoán |
| Ngành | Ngành/lĩnh vực |
| Giá | Giá đóng cửa hiện tại (VND) |
| % Change | % thay đổi so với phiên trước |
| Xu hướng | Phân loại xu hướng (Mạnh/Tăng/Đi ngang/Giảm/Giảm mạnh) |
| Đảo chiều | Tín hiệu đảo chiều (Bullish/Bearish) |
| EMA20/50/200 | % chênh lệch giá so với đường EMA |
| RSI | RSI(14) |
| Signal | Tín hiệu mua (BUY) |
| Chart | Nút mở biểu đồ TradingView |

## Filter Parameters (Screener)

| Filter | Giá trị | Mô tả |
|--------|---------|-------|
| Xu hướng EMA | all / above_ema20 / above_ema50 / above_ema200 | Giá trên đường EMA |
| Nến | all / bullish / bearish | Loại nến |
| Ngành | all / Banking / RealEstate / ... | Lọc theo ngành |
| Signal | all / has_signal / no_signal | Có tín hiệu mua hay không |
| Đảo chiều | all / bullish / bearish | Tín hiệu đảo chiều |
| RSI Min/Max | 0-100 | Khoảng RSI |

## Đồng bộ dữ liệu

### Tự động (cron)
- GitHub Actions chạy 15:30 VN (08:30 UTC) thứ 2 - thứ 6
- Script: `scripts/daily_refresh.py`
- Chỉ fetch dữ liệu mới (incremental) — kiểm tra ngày lớn nhất trong DB trước

### Thủ công
- Vào trang **Đồng bộ** → nhấn "Đồng bộ dữ liệu"
- Trigger GitHub Actions workflow dispatch qua API
- Mất ~1-3 phút

### Fallback data source
- Primary: VCI (qua `vnstock`), rate limit 20 req/min → 3.5s delay mỗi call
- Tự động kiểm tra dữ liệu đã có trong Supabase trước khi fetch

## Lưu ý kỹ thuật

### Supabase REST API
- **Phải gửi cả 2 headers**: `Authorization: Bearer <service_role>` và `apikey: <anon_key>`
- Thiếu `apikey` → API trả về lỗi "No API key found"
- Filter trong `and()` dùng dot notation: `column.op.value` (không dùng `=`)
- Boolean columns dùng `is.true`/`is.false` (không dùng `eq.true`)
- `head=true` không được hỗ trợ — dùng `Prefer: count=exact` để đếm

### VN100 Universe
- 122 cổ phiếu từ chỉ số VN100
- Dữ liệu từ 2020-01-01
- Giá đã điều chỉnh (split, cổ tức)

### Rate Limiting
- VCI free tier: 20 requests/minute
- Script tự động delay 3.5s giữa các request
- Thêm 65s buffer sau mỗi batch 20 ticker

## Phát triển

### Frontend
```bash
cd frontend
npm run dev    # local development
npm run build  # kiểm tra lỗi TypeScript
```

### Local test Supabase
```bash
# Kiểm tra kết nối
$headers = @{
  "Authorization" = "Bearer $SERVICE_KEY"
  "apikey" = "$ANON_KEY"
}
Invoke-RestMethod -Uri "$SUPABASE_URL/rest/v1/daily_bars_adjusted?select=date&order=date.desc&limit=1" -Headers $headers
```
