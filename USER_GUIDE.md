# Hướng dẫn sử dụng VN100 Trading Dashboard

## Tổng quan

Dashboard giúp theo dõi tín hiệu giao dịch VN100, lọc cổ phiếu, quản lý danh mục và nhận cảnh báo.

## Các trang

### 1. Dashboard (`/dashboard`)
Trang tổng quan hiển thị:
- **KPI cards**: Số vốn, dữ liệu, cấu hình, stop loss
- **Tín hiệu entry hôm nay**: Danh sách mã đủ điều kiện mua
- **Chiến lược**: Tóm tắt điều kiện entry/exit
- **Kết quả backtest**: CAGR, Return, Max DD, Sharpe, Win Rate, Profit Factor

### 2. Tín hiệu (`/signals`)
- **Entry Signals**: Danh sách mã đủ điều kiện mua kèm chỉ số kỹ thuật
- **Chi tiết từng mã**: Click "Xem" để thấy giá, EMA, RSI, Vol Ratio, ATR, khoảng cách đến các EMA

### 3. Bộ lọc cổ phiếu (`/screener`)
Lọc cổ phiếu theo:
- **Xu hướng**: Trên EMA20/50/200
- **Nến**: Bullish/Bearish
- **Ngành**: 11 ngành
- **Vol Ratio, RSI, Giá**
- Kết quả highlight mã có tín hiệu BUY

### 4. Danh mục (`/portfolio`)
Quản lý vị thế đầu tư:
- **Thêm vị thế**: Nhập mã, giá vào, số lượng, ngày
- **Xóa vị thế**: Click icon thùng rác
- **Theo dõi**: Giá hiện tại, PnL, stop loss

### 5. Theo dõi (`/watchlist`)
Danh sách mã theo dõi:
- **Thêm mã**: Nhập mã CK vào ô tìm kiếm
- **Xem giá realtime**: Giá, O/H/L, khối lượng
- **Xóa**: Click icon thùng rác

### 6. Cảnh báo (`/alerts`)
Cấu hình thông báo:
- **Telegram**: Nhập Bot Token + Chat ID
- **Email**: SMTP host, email, password
- **Loại alert**: Bật/tắt từng loại (tín hiệu, mở vị thế, stop loss, drawdown...)

### 7. Lịch sử (`/trades`)
Xem toàn bộ giao dịch đã thực hiện:
- Filter theo mã chứng khoán
- Thống kê: Win rate, avg win/loss, avg days held
- Chi tiết từng giao dịch: Giá vào/ra, PnL, lý do exit

## Cập nhật dữ liệu

Dữ liệu được cập nhật tự động hàng ngày:
- **15:30 VN**: Fetch dữ liệu OHLCV từ vnstock VCI
- **16:00 VN**: Tính toán tín hiệu và lưu vào database

Có thể trigger refresh thủ công qua API:
```bash
curl -X POST http://localhost:8000/api/v1/data/refresh
```

## Cấu hình Telegram Bot

1. Tạo bot trên Telegram: chat với `@BotFather`, gửi `/newbot`
2. Nhận token (VD: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
3. Tìm chat ID: gửi tin nhắn cho bot, truy cập `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Nhập token và chat ID vào trang Alerts

## Xử lý sự cố

| Vấn đề | Giải pháp |
|--------|-----------|
| Không có dữ liệu | Kiểm tra backend logs: `docker logs vn100-backend` |
| API lỗi 500 | Kiểm tra Supabase connection, PAT key |
| Telegram không gửi | Kiểm tra token, chat ID, bot đã được start |
| Dữ liệu cũ | Trigger refresh thủ công, hoặc đợi schedule 15:30 |
