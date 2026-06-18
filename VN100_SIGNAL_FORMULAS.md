# Công thức Codex Advise — Tín hiệu Mua VN100

Tài liệu này mô tả chiến lược **Codex Advise**, hệ thống chấm điểm đa nhân tố và tín hiệu mua cho VN100.

---

## 1. Market Regime (Chế độ thị trường)

Xác định trạng thái thị trường từ chỉ số VNINDEX:

| Chế độ | Điều kiện | Giao dịch |
|--------|-----------|-----------|
| **Bull** | `close > ema50` AND `ema20 > ema50` AND `ema50 >= ema100` | Cho phép mua |
| **Recovery** | `close > ema20` AND `ema20 tăng 3 phiên` AND `rsi >= 45` | Hạn chế |
| **Risk** | `close < ema50` AND `ema20 < ema50` | Cảnh báo |
| **Distribution** | `>=3 ngày giảm với vol_ratio > 1.2` OR `close < ema100` | Không mua |

Công thức (`daily_refresh.py:compute_market_regime`):
```
bull  = close > e50[-1] AND e20[-1] > e50[-1] AND e50[-1] >= e100[-1]
recovery = close > e20[-1] AND e20[-1] > e20[-2] > e20[-3] AND rsi14[-1] >= 45
risk  = close < e50[-1] AND e20[-1] < e50[-1]
distribution = down_count >= 3 OR close < e100[-1]
  trong đó down_count = số phiên trong 10 ngày gần nhất có close < open AND vol_ratio > 1.2
```

---

## 2. Stock Quality Filters (Bộ lọc Chất lượng) — base_eligible

Tất cả điều kiện phải đúng để cổ phiếu được coi là "đủ điều kiện cơ bản":

```
liquid = value20 >= 30 tỷ
tradable_vol = atr_pct >= 1.5% AND atr_pct <= 6%
trend_quality = close > ema50
             AND ema20 > ema50
             AND ema50 >= ema100
             AND close > ema200
             AND ema20[-1] > ema20[-4]     (tăng 4 phiên)
             AND ema50[-1] >= ema50[-6]    (tăng 6 phiên)
not_overextended = close <= ema20 * 1.08
                 AND close <= ema50 * 1.18
                 AND rsi14 <= 72
not_distribution = NOT mkt_regime['distribution']
rs_ok = rs20 > 0 AND rs60 > 0
```

---

## 3. RS Score (Tương quan thị trường) — max 20 điểm

So sánh return của cổ phiếu với VNINDEX cùng kỳ:

| Điều kiện | Điểm |
|-----------|------|
| `rs20 > 0` | 8 |
| `rs60 > 0` | 8 |
| `return_60 >= 12%` | 4 |

```
rs20 = stock_return_20 - mkt_return_20
rs60 = stock_return_60 - mkt_return_60
```

---

## 4. Trend Score (Xu hướng) — max 25 điểm

| Điều kiện | Điểm |
|-----------|------|
| `close > ema50` | 8 |
| `ema20 > ema50` | 6 |
| `ema50 >= ema100` | 5 |
| `close > ema200` | 4 |
| `ema20[-1] > ema20[-2] > ema20[-3]` (3 phiên tăng liên tiếp) | 2 |

**Codex Trend classification** (API route `getCodexTrend()`):
```
Mạnh:      price > ema50 AND ema20 > ema50 AND ema50 >= ema100 AND price > ema200
Tăng:      price > ema50 AND ema20 > ema50
Giảm mạnh: price < ema50 AND ema20 < ema50 AND ema50 < ema200
Giảm:     price < ema50 AND ema20 < ema50
Đi ngang:  còn lại
```

---

## 5. Volume Score (Khối lượng) — max 15 điểm

| Điều kiện | Điểm |
|-----------|------|
| `vol_ratio >= 1.1` | 5 |
| `vol_ratio >= 1.3` | 5 |
| `value20 >= 50 tỷ` | 5 |

---

## 6. Entry Quality Score (Chất điểm điểm vào) — max 25 điểm

| Điều kiện | Điểm |
|-----------|------|
| `close >= ema20 * 0.97 AND close <= ema20 * 1.03` (±3% quanh EMA20) | 10 |
| `close_position >= 0.65` | 7 |
| `body_ratio >= 0.35` | 4 |
| `rsi14 >= 45 AND rsi14 <= 68` | 4 |

Trong đó:
```
close_position = (close - low) / (high - low)
body_ratio     = |close - open| / (high - low)
```

---

## 7. Risk Score (Rủi ro) — max 15 điểm

| Điều kiện | Điểm |
|-----------|------|
| `atr_pct >= 1.5% AND atr_pct <= 4.5%` | 5 |
| `close <= ema20 * 1.05` | 5 |
| `reward_risk >= 2.0` | 5 |

### Reward / Risk (`compute_reward_risk`)
```
stop  = min(low_5_ngay, ema50 * 0.98, entry - 1.5 * atr14)
target = high_20_ngay
rr    = (target - entry) / (entry - stop)
```

---

## 8. Total Score (Tổng điểm)

```
total = min(trend + rs + volume + entry + risk, 100)
```

### Phân loại (Section 9)
| Khoảng | Phân loại |
|--------|-----------|
| >= 80 | Mạnh (Strong) |
| 65-79 | Tốt (Good) |
| 50-64 | Theo dõi (Watch) |
| < 50 | Bỏ qua (Ignore) |

---

## 9. Codex Reversal (Đảo chiều) — On-the-fly, NOT stored in DB

Tính trực tiếp trong API route (`getCodexReversal()`), không lưu trong stock_features.

### Section 7A: Bullish Engulfing Body
```
bullish          = close > open
prev_red         = prev_close < prev_open
open <= prev_close
close >= prev_open
body_ratio >= 0.45
close_position >= 0.65
```

### Section 7B: Reclaim Candle
```
close > ema20
low < ema20
bullish
close_position >= 0.7
body_ratio >= 0.35
```

### Volume Confirmation (cả 7A và 7B)
```
vol_ratio >= 1.2
volume > prev_volume    (cần prevVolMap)
```

### Additional filters (cả 7A và 7B)
```
rsi14 >= 40 AND rsi14 <= 65
close >= ema50 * 0.97
```

NOT implemented (thiếu historical low/high queries):
- Prior pullback: `close > lowest(close, 5)` trong 5 ngày trước
- Prior downswing: `close < highest(close, 20)` trong 20 ngày trước

### Section 8: Bearish Reversal
```
NOT bullish
prev_close > prev_open
open >= prev_close
close <= prev_open
body_ratio >= 0.45
close_position <= 0.35
vol_ratio >= 1.2
close < ema20
```

---

## 10. Buy Signal (Section 12) — Simplified Scanner Signal

Tín hiệu mua = **tất cả** 15 điều kiện sau phải đúng:

| # | Điều kiện | Công thức |
|---|-----------|-----------|
| 1 | Market Bull | `mkt_regime['bull'] == true` |
| 2 | Thanh khoản | `value20 >= 30 tỷ` |
| 3-6 | Trend quality | `close > ema50`, `ema20 > ema50`, `ema50 >= ema100`, `close > ema200` |
| 7 | EMA20 momentum | `ema20[-1] > ema20[-4]` |
| 8 | RS dương | `rs60 > 0` |
| 9 | Gần EMA20 | `close >= ema20 * 0.97 AND close <= ema20 * 1.05` |
| 10 | RSI | `rsi14 >= 45 AND rsi14 <= 70` |
| 11 | Volume | `vol_ratio >= 1.15` |
| 12 | Nến xanh | `close > open` |
| 13 | Thân nến | `body_ratio >= 0.35` |
| 14 | Vị trí nến | `close_position >= 0.6` |
| 15 | Biến động | `atr_pct >= 1.5% AND atr_pct <= 5.5%` |

---

## 11. Current Simple Strategy (for reference)

Từ FILTER_FORMULAS.md — khác biệt so với Codex:

| Yếu tố | Simple | Codex |
|--------|--------|-------|
| Trend | EMA200/50/20 (Mạnh/Tăng/Giảm/Đi ngang) | EMA100-based + score |
| Volume | vol_ratio > 1.0 | vol_ratio >= 1.15 + score |
| Candle | bullish + body >= 40% | body >= 35% + cp >= 0.6 |
| Scoring | Không | 5-component (100) |
| Signal | 4 conditions | 15 conditions |
| Reversal | Engulfing (close > prev_high) | Section 7A/B + volume confirmation |
| Market filter | Không | Bull regime required |
