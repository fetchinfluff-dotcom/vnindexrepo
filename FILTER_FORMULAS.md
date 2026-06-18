# Công thức Bộ lọc Cổ phiếu

## 1. Chỉ báo Xu hướng (Trend)

Phân loại dựa trên vị trí giá so với các đường EMA và thứ tự sắp xếp của EMA:

| Trend | Điều kiện |
|-------|-----------|
| **Mạnh** (Strong uptrend) | `price > ema20 > ema50 > ema200` |
| **Tăng** (Uptrend) | `price > ema20 > ema50` |
| **Giảm mạnh** (Strong downtrend) | `price < ema20 < ema50 < ema200` |
| **Giảm** (Downtrend) | `price < ema20 < ema50` |
| **Đi ngang** (Sideways) | Không thuộc các trường hợp trên |

> ⚠️ **Lưu ý:** "Mạnh" yêu cầu cả 3 EMA xếp theo thứ tự tăng dần (straight bull stack). "Tăng" chỉ cần price > ema20 > ema50, không cần kiểm tra ema200.

---

## 2. Chỉ báo Đảo chiều (Reversal)

Phát hiện mô hình nến nhấn chìm (Engulfing pattern), được tính **trực tiếp trên frontend** (không lưu trong DB):

| Loại | Điều kiện |
|------|-----------|
| **Bullish Engulfing** | Nến hôm nay xanh (bullish) **VÀ** hôm trước đỏ (close < open) **VÀ** close hôm nay > high hôm trước |
| **Bearish Engulfing** | Nến hôm nay không phải xanh **VÀ** hôm trước xanh (close > open) **VÀ** close hôm nay < low hôm trước |

> ℹ️ **Giải thích:** Điều kiện "close > prev_high" (bullish) tương đương nến xanh hôm nay nhấn chìm hoàn toàn nến đỏ hôm trước. Tương tự cho bearish với "close < prev_low".

---

## 3. Tín hiệu Mua (Signal)

Tín hiệu mua = **tất cả** 4 điều kiện sau phải đúng đồng thời:

| # | Điều kiện | Công thức | Ý nghĩa |
|---|-----------|-----------|---------|
| 1 | **Macro Bull** | `close > ema200` **VÀ** `ema50 > ema200` | Xu hướng dài hạn tăng |
| 2 | **Momentum** | `close > ema20` | Đà tăng ngắn hạn |
| 3 | **Khối lượng** | `vol_ratio > 1.0` | Khối lượng trên trung bình 20 phiên |
| 4 | **Nến xanh** | `close > open` **VÀ** `body / range >= 0.4` | Nến tăng với thân ≥ 40% biên độ |

**Công thức đầy đủ:**
```
signal = (close > ema200 AND ema50 > ema200)       -- Macro Bull
     AND (close > ema20)                            -- Momentum
     AND (vol_ratio > 1.0)                          -- Volume Surge
     AND (close > open AND body/range >= 0.4)       -- Bullish Candle
```

> ℹ️ Trong đó `vol_ratio = volume / SMA(volume, 20)` và `body = |close - open|`, `range = high - low`.

---

## 4. Công thức nền tảng (Features)

Các chỉ báo được tính toán trong `scripts/daily_refresh.py` (và lưu vào bảng `stock_features`):

### EMA (Exponential Moving Average)
```
EMA[i] = (price[i] - EMA[i-1]) * (2 / (span + 1)) + EMA[i-1]
```
- Hệ số nhân: `α = 2 / (span + 1)`
- Span: 20, 50, 200

### RSI 14 (Relative Strength Index)
```
RSI = 100 - (100 / (1 + RS))
RS  = AvgGain(14) / AvgLoss(14)
```
- **Phiên đầu tiên (i=14):** `AvgGain = mean(gain[0:14])`, `AvgLoss = mean(loss[0:14])`
- **Các phiên sau (i>=15):**
  - `AvgGain[i] = (AvgGain[i-1] * 13 + gain[i-1]) / 14` (Wilder smoothing)
  - `AvgLoss[i] = (AvgLoss[i-1] * 13 + loss[i-1]) / 14`
- Trong đó: `gain = max(close[i] - close[i-1], 0)`, `loss = max(-(close[i] - close[i-1]), 0)`

### ATR 14 (Average True Range)
```
TrueRange = max(high - low, |high - prev_close|, |low - prev_close|)
ATR[14]   = mean(TR[0:14])
ATR[i]    = (ATR[i-1] * 13 + TR[i-1]) / 14   (với i >= 15)
```

### Vol Ratio (Tỷ lệ khối lượng)
```
vol_ratio = volume / SMA(volume, 20)
```
- `SMA(volume, 20) = mean(volume[i-19 : i+1])` — trung bình 20 phiên gần nhất
- Giá trị > 1.0 = khối lượng trên trung bình

### Bullish Candle (Nến tăng)
```
bullish = (close > open) AND (|close - open| / max(high - low, 0.001) >= 0.4)
```
- Yêu cầu thân nến chiếm ít nhất 40% tổng biên độ giá.

---

## 5. Backtest Signal

Phiên bản backtest (dùng trong `quick_backtest.py`, `full_backtest.py`) có thêm điều kiện **Pullback** và **RSI**:

| Điều kiện | Công thức | Khác biệt so với Signal hiện tại |
|-----------|-----------|----------------------------------|
| Macro Bull | `close > ema200 AND ema50 > ema200` | Giống |
| Pullback | `close >= ema20 * 0.97` **VÀ** `close <= ema20 * 1.01` | **Thêm** — giá dao động quanh EMA20 (±1%) |
| Volume | `vol_ratio > 1.2` | **Khác** — ngưỡng 1.2 thay vì 1.0 |
| Bullish Candle | `close > open` **VÀ** `body/range >= 0.4` | Giống |
| RSI | `rsi14 < 70` | **Thêm** — tránh mua khi quá mua |

> ⚠️ **Signal hiện tại** (dùng trong screener) là phiên bản đơn giản hóa: bỏ pullback và RSI filter, hạ volume threshold từ 1.2 xuống 1.0.
