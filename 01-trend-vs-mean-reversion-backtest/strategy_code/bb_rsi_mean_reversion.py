"""
BB RSI Mean Reversion Strategy — Failed (-12% Return, -21% Max DD)

Strategy Type: Counter-Trend Mean Reversion (Bollinger Bands + RSI)
Pair: ETHUSD
Timeframe: 1H
Backtest Period: 2024-01-01 to 2025-01-01
Platform: QuantConnect/Lean via SharkDev.ai

PARAMETERS (Optimized — ALL VARIANTS LOST):
- bb_period: 20           (Bollinger Bands period)
- bb_std_dev: 2.0         (Standard deviations for bands)
- rsi_period: 14          (RSI period)
- rsi_oversold: 30        (RSI threshold for long entry)
- rsi_overbought: 70      (RSI threshold for short entry)
- stop_loss_pct: 2.5%     (Fixed stop loss)
- take_profit_pct: 5.0%   (Fixed take profit)
- timeout_bars: 24        (Max bars held — 1H = 24 hours)

LOGIC:
1. LONG ENTRY:  Price < Lower Bollinger Band AND RSI < 30
2. SHORT ENTRY: Price > Upper Bollinger Band AND RSI > 70
3. EXIT:
   - Stop Loss: 2.5% fixed from entry
   - Take Profit: 5% fixed from entry
   - Signal Exit: Price crosses middle band (20 SMA)
   - Timeout: 24 bars (1H = 24 hours)

KEY FAILURE MODES (identified via SharkDev.ai optimization):
- ❌ NO TREND FILTER — Shorts every overbought rip in uptrends, longs every oversold dip in downtrends
- ❌ 1H TIMEFRAME — Extreme whipsaw; noise dominates signal
- ❌ RIGID RSI THRESHOLDS — 30/70 too tight for crypto volatility
- ❌ ZERO WINNING VARIANTS — Optimization landscape was entirely red across all parameter combos

EDUCATIONAL VALUE: This strategy demonstrates why mean reversion fails in strongly trending markets
without a trend filter. The same signal score (54) produced opposite PnL because LOGIC STRUCTURE
matters more than raw signal quality.
"""

from AlgorithmImports import *

class BBRsiMeanReversion(QCAlgorithm):

    def Initialize(self):
        # --- Core Settings ---
        self.SetStartDate(2024, 1, 1)
        self.SetEndDate(2025, 1, 1)
        self.SetCash(10000)
        self.SetTimeZone(TimeZones.NewYork)
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)

        # --- Parameters (from SharkDev.ai optimization — ALL LOST) ---
        self.bb_period        = self.GetParameter("bb_period", 20)
        self.bb_std_dev       = self.GetParameter("bb_std_dev", 2.0)
        self.rsi_period       = self.GetParameter("rsi_period", 14)
        self.rsi_oversold     = self.GetParameter("rsi_oversold", 30)
        self.rsi_overbought   = self.GetParameter("rsi_overbought", 70)
        self.stop_loss_pct    = self.GetParameter("stop_loss_pct", 0.025)
        self.take_profit_pct  = self.GetParameter("take_profit_pct", 0.05)
        self.timeout_bars     = self.GetParameter("timeout_bars", 24)

        # --- Indicators (1H resolution) ---
        # Bollinger Bands: Upper, Middle (SMA), Lower
        self.bb = self.BB("ETHUSD", self.bb_period, self.bb_std_dev, Resolution.Hour)

        # RSI for oversold/overbought confirmation
        self.rsi = self.RSI("ETHUSD", self.rsi_period, Resolution.Hour)

        # Middle band (20 SMA) for signal exit
        self.sma_middle = self.SMA("ETHUSD", self.bb_period, Resolution.Hour)

        # Warm-up for indicators
        self.SetWarmUp(100, Resolution.Hour)

        # Position tracking
        self.entry_price = 0
        self.bars_held = 0
        self.position_side = 0  # 1 = long, -1 = short

    def OnData(self, data):
        # Wait for indicators to be ready
        if self.IsWarmingUp:
            return

        if not data.ContainsKey("ETHUSD"):
            return

        price = data["ETHUSD"].Close
        holdings = self.Portfolio["ETHUSD"].Quantity

        # --- ENTRY LOGIC ---
        if holdings == 0:
            # LONG: Price below Lower BB AND RSI oversold
            long_signal = (price < self.bb.LowerBand.Current.Value and
                          self.rsi.Current.Value < self.rsi_oversold)

            # SHORT: Price above Upper BB AND RSI overbought
            short_signal = (price > self.bb.UpperBand.Current.Value and
                           self.rsi.Current.Value > self.rsi_overbought)

            if long_signal:
                quantity = self.CalculateOrderQuantity("ETHUSD", 0.8)
                if quantity > 0:
                    self.MarketOrder("ETHUSD", quantity)
                    self.entry_price = price
                    self.bars_held = 0
                    self.position_side = 1

                    stop_price = price * (1 - self.stop_loss_pct)
                    target_price = price * (1 + self.take_profit_pct)
                    self.StopMarketOrder("ETHUSD", -quantity, stop_price, tag="SL")
                    self.LimitOrder("ETHUSD", -quantity, target_price, tag="TP")

            elif short_signal:
                quantity = self.CalculateOrderQuantity("ETHUSD", -0.8)
                if quantity < 0:
                    self.MarketOrder("ETHUSD", quantity)
                    self.entry_price = price
                    self.bars_held = 0
                    self.position_side = -1

                    stop_price = price * (1 + self.stop_loss_pct)
                    target_price = price * (1 - self.take_profit_pct)
                    self.StopMarketOrder("ETHUSD", -quantity, stop_price, tag="SL")
                    self.LimitOrder("ETHUSD", -quantity, target_price, tag="TP")

        # --- EXIT LOGIC ---
        elif holdings != 0:
            self.bars_held += 1

            if self.position_side == 1:  # LONG position
                # 1. Signal Exit: Price crosses back above middle band
                if price > self.sma_middle.Current.Value:
                    self.Liquidate("ETHUSD", "Signal Exit: Cross Middle Band")
                    return

            else:  # SHORT position
                # 1. Signal Exit: Price crosses back below middle band
                if price < self.sma_middle.Current.Value:
                    self.Liquidate("ETHUSD", "Signal Exit: Cross Middle Band")
                    return

            # 2. Timeout Exit: Max holding period reached
            if self.bars_held >= self.timeout_bars:
                self.Liquidate("ETHUSD", "Timeout Exit")
                return

            # Note: SL/TP orders are OCO (handled by brokerage)
            # They auto-cancel each other on fill

            # Reset position tracking on liquidation
            if holdings == 0:
                self.position_side = 0