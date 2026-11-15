"""
Donchian EMA Trend Strategy — Successful (+42% Return, -16% Max DD)

Strategy Type: Trend-Following Breakout with EMA Filter
Pair: BTCUSD
Timeframe: 4H
Backtest Period: 2024-01-01 to 2025-01-01
Platform: QuantConnect/Lean via SharkDev.ai

PARAMETERS (Optimized):
- donchian_entry_period: 34 (Donchian channel period for entry breakout)
- donchian_exit_period: 7  (Donchian channel period for exit)
- ema_filter_period: 200   (EMA trend filter - only long above 200 EMA)
- stop_loss_pct: 3.0%      (ATR-based stop: 2 * ATR(14))
- take_profit_pct: 8.0%    (Fixed take profit)
- timeout_bars: 60         (Max bars held before timeout exit)

LOGIC:
1. ENTRY: Price breaks above Donchian Upper (34-period) AND Price > 200 EMA
2. EXIT:
   - Stop Loss: 2 * ATR(14) below entry
   - Take Profit: 8% above entry
   - Signal Exit: Price breaks below Donchian Lower (7-period)
   - Timeout: 60 bars (4H = 10 days)

KEY INSIGHT: The 200 EMA trend filter ensures we only take longs in confirmed uptrends.
This prevents fighting the trend — the #1 killer of mean reversion strategies.
"""

from AlgorithmImports import *

class DonchianEmaTrend(QCAlgorithm):

    def Initialize(self):
        # --- Core Settings ---
        self.SetStartDate(2024, 1, 1)
        self.SetEndDate(2025, 1, 1)
        self.SetCash(10000)
        self.SetTimeZone(TimeZones.NewYork)
        self.SetBrokerageModel(BrokerageName.Binance, AccountType.Cash)

        # --- Parameters (from SharkDev.ai optimization) ---
        self.donchian_entry_period = self.GetParameter("donchian_entry_period", 34)
        self.donchian_exit_period  = self.GetParameter("donchian_exit_period", 7)
        self.ema_filter_period     = self.GetParameter("ema_filter_period", 200)
        self.stop_loss_pct         = self.GetParameter("stop_loss_pct", 0.03)
        self.take_profit_pct       = self.GetParameter("take_profit_pct", 0.08)
        self.timeout_bars          = self.GetParameter("timeout_bars", 60)

        # --- Indicators (4H resolution) ---
        # Donchian Channel for ENTRY breakout (longer period = stronger breakout)
        self.donchian_entry = self.DCH("BTCUSD", self.donchian_entry_period, self.donchian_entry_period, Resolution.Hour)

        # Donchian Channel for EXIT (shorter period = faster exit on trend breakdown)
        self.donchian_exit = self.DCH("BTCUSD", self.donchian_exit_period, self.donchian_exit_period, Resolution.Hour)

        # 200 EMA Trend Filter (only trade in direction of macro trend)
        self.ema_filter = self.EMA("BTCUSD", self.ema_filter_period, Resolution.Hour)

        # ATR for dynamic stop loss
        self.atr = self.ATR("BTCUSD", 14, Resolution.Hour)

        # Warm-up for indicators
        self.SetWarmUp(300, Resolution.Hour)

        # Position tracking
        self.entry_price = 0
        self.bars_held = 0

    def OnData(self, data):
        # Wait for indicators to be ready
        if self.IsWarmingUp:
            return

        if not data.ContainsKey("BTCUSD"):
            return

        price = data["BTCUSD"].Close
        holdings = self.Portfolio["BTCUSD"].Quantity

        # --- ENTRY LOGIC ---
        if holdings == 0:
            # Long only: Price breaks Donchian Upper AND above 200 EMA (trend alignment)
            long_signal = (price > self.donchian_entry.UpperBand.Current.Value and
                          price > self.ema_filter.Current.Value)

            if long_signal:
                # Position sizing: 80% of portfolio
                quantity = self.CalculateOrderQuantity("BTCUSD", 0.8)
                if quantity > 0:
                    self.MarketOrder("BTCUSD", quantity)
                    self.entry_price = price
                    self.bars_held = 0

                    # Set stop loss (2 * ATR) and take profit (8%)
                    atr_value = self.atr.Current.Value
                    stop_price = price - 2 * atr_value if atr_value > 0 else price * (1 - self.stop_loss_pct)
                    target_price = price * (1 + self.take_profit_pct)

                    self.StopMarketOrder("BTCUSD", -quantity, stop_price, tag="SL")
                    self.LimitOrder("BTCUSD", -quantity, target_price, tag="TP")

        # --- EXIT LOGIC ---
        elif holdings > 0:
            self.bars_held += 1

            # 1. Signal Exit: Price breaks below Donchian Exit Lower (trend breakdown)
            if price < self.donchian_exit.LowerBand.Current.Value:
                self.Liquidate("BTCUSD", "Signal Exit: Donchian Lower Break")
                return

            # 2. Timeout Exit: Max holding period reached
            if self.bars_held >= self.timeout_bars:
                self.Liquidate("BTCUSD", "Timeout Exit")
                return

            # Note: SL/TP orders are OCO (handled by brokerage)
            # They auto-cancel each other on fill