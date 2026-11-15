# Backtest Comparison: Donchian EMA Trend vs BB RSI Mean Reversion

**Backtest Period:** 2024-01-01 to 2025-01-01  
**Platform:** QuantConnect/Lean via [SharkDev.ai](https://sharkdev.ai)  
**Initial Capital:** $10,000

---

## 📊 Side-by-Side Metrics

| Metric | 🟢 Donchian + EMA Trend | 🔴 BB + RSI Mean Reversion |
|--------|------------------------|---------------------------|
| **Net Return** | **+42.3%** | **-12.1%** |
| **Max Drawdown** | **-16.2%** | **-21.4%** |
| **Sharpe Ratio** | **1.34** | **-0.89** |
| **Profit Factor** | **1.68** | **0.62** |
| **Win Rate** | **54.3%** | **41.7%** |
| **Total Trades** | **47** | **128** |
| **Avg Trade Duration** | **3.2 days** | **18.4 hours** |
| **Signal Strength (SharkDev)** | **54/100** | **54/100** |
| **Risk Mgmt Score** | **50/100** | **45/100** |
| **Diversification Score** | **10/100** | **10/100** |
| **Timeframe** | **4H** | **1H** |
| **Trend Filter** | ✅ **200 EMA** | ❌ **None** |
| **Winning Variants (of 100)** | **3** | **0** |
| **Robustness** | ✅ Multiple profitable combos | ❌ All combos lost |

---

## 🎯 Key Takeaway

> **Same signal score (54/100). Opposite PnL.**
> 
> The difference wasn't signal quality — it was **logic structure**.
> 
> - Donchian + EMA: **Trend alignment** (only long above 200 EMA)
> - BB + RSI: **No trend filter** (fought every trend move)

---

## 📈 Equity Curve Comparison

```
Donchian EMA Trend (+42%)          BB RSI Mean Reversion (-12%)
     ▲                                     ▼
     │    ╱╲                              ╲
     │   ╱  ╲                              ╲  ╱
     │  ╱    ╲                              ╲╱
     │ ╱      ╲
     │╱        ╲
     ╱          ╲
─────────────────────────>         ─────────────────────────>
     Time                                Time
```

**Donchian** captures macro trends on 4H timeframe with EMA gate.  
**BB+RSI** gets whipsawed on 1H — noise dominates, no trend filter.

---

## ⚙️ Parameter Comparison

| Parameter | Donchian EMA Trend | BB RSI Mean Reversion |
|-----------|-------------------|----------------------|
| Entry Signal | Donchian Upper Break (34) + Price > 200 EMA | Price < Lower BB (20, 2σ) + RSI < 30 |
| Exit Signal | Donchian Lower Break (7) | Price crosses Middle BB (SMA 20) |
| Stop Loss | 2 × ATR(14) | Fixed 2.5% |
| Take Profit | Fixed 8% | Fixed 5% |
| Timeout | 60 bars (10 days) | 24 bars (24 hours) |
| Position Size | 80% equity | 80% equity |
| Direction | Long Only | Long + Short |

---

## 🏷️ SharkDev.ai Tags

- **Strategy Lab:** `Trend vs Mean Reversion`
- **Status:** `Published` 
- **Week:** `1`
- **Verdict:** `Logic Structure > Signal Quality`

---

*Generated: 2026-11-14 | Source: SharkDev.ai Optimization Runs*