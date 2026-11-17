from datetime import timedelta, datetime
from dataclasses import dataclass, field
from sharkdev_imports import *

@dataclass
class TimeframeData:

    multiplier: int
    resolution: Resolution

@dataclass
class IndicatorData:

    name: str
    timeframe: TimeframeData
    indicator_class: Indicator

@dataclass
class SymbolData:

    symbol: Symbol
    indicators: dict[str, Indicator] = field(default_factory=dict)
    end_time: datetime = None
    ask_open: float = None
    ask_high: float = None
    ask_low: float = None
    ask_close: float = None
    last_ask_size: float = None
    bid_open: float = None
    bid_high: float = None
    bid_low: float = None
    bid_close: float = None
    last_bid_size: float = None
    mid_open: float = None
    mid_high: float = None
    mid_low: float = None
    mid_close: float = None
    spread: float = None

    entry_ticket: OrderTicket = None
    stop_ticket: OrderTicket = None
    target_ticket: OrderTicket = None
    trailing_ticket: OrderTicket = None

    pending_entry_time: datetime = None
    position_open_time: datetime = None
    last_exit_time: datetime = None

class Strategy(QCAlgorithm):

    def initialize(self):
        self.settings.automatic_indicator_warm_up = True
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_brokerage_model(BrokerageName.BINANCE, AccountType.CASH)

        self.security_type: str = "crypto"

        if not self.live_mode:
            self.set_cash(10000.0)
            self.set_start_date(2024, 1, 1)
            self.set_end_date(2025, 1, 1)

        self._configure_warm_up()

        self.data = {}
        self.order_to_data = {}
        self.primary_symbol = None
        self.pos_sizes = {}

        self._initialize_strategy()
        self._recover_position_state()

    def _recover_position_state(self):
        for data in self.data.values():
            recover_position_state(self, data)

    def _configure_warm_up(self):
        days = resolve_warmup_days(
            12, 30, self.live_mode
        )
        self.set_warm_up(timedelta(days=days), Resolution.HOUR)

    def _map_live_ticker(self, ticker):
        if not self.live_mode or self.security_type != "crypto":
            return ticker
        return derive_live_ticker(ticker)

    def _is_effectively_flat(self, data, holdings):
        return is_effectively_flat(self, data.symbol, holdings)

    def _is_effectively_invested(self, data, holdings):
        return is_effectively_invested(self, data.symbol, holdings)

    def on_brokerage_message(self, message):
        self.log(f"BROKERAGE MESSAGE: {message}")
        self._recover_position_state()

    def on_brokerage_disconnect(self):
        self.log("BROKERAGE DISCONNECT")

    def on_brokerage_reconnect(self):
        self.log("BROKERAGE RECONNECT")
        self._recover_position_state()

    def on_warmup_finished(self):
        try:
            entries = []
            for ticker, data in self.data.items():
                for name, indicator in data.indicators.items():
                    entries.append(
                        (ticker, name, indicator.is_ready, indicator.current.value)
                    )
            ready_count = sum(1 for _, _, ready, _ in entries if ready)
            self.log(
                f"WARMUP FINISHED: live_mode={self.live_mode} "
                f"is_warming_up={self.is_warming_up} "
                f"indicators_ready={ready_count}/{len(entries)}"
            )
            if not entries:
                self.log(
                    "WARMUP INDICATOR: none registered by generated code "
                    "(expected only when the spec declares no indicators)"
                )
            for ticker, name, ready, value in entries:
                self.log(
                    f"WARMUP INDICATOR: {ticker}:{name} ready={ready} value={value}"
                )
        except Exception as exception:
            self.log(f"WARMUP FINISHED: readiness log failed: {exception}")

    def _resolve_consolidator_timedelta(self, timeframe: TimeframeData) -> timedelta:
        if timeframe.resolution == Resolution.DAILY:
            return timedelta(days=timeframe.multiplier)
        return timedelta(hours=timeframe.multiplier)

    def _add_symbol_consolidator(self, symbol: Symbol, symbol_timedelta: timedelta):
        consolidator = QuoteBarConsolidator(symbol_timedelta)
        consolidator.data_consolidated += self._on_consolidated_bar
        self.subscription_manager.add_consolidator(symbol, consolidator, TickType.QUOTE)

    def _add_indicator_consolidator(
        self, symbol: Symbol, indicator: Indicator, indicator_timedelta: timedelta
    ):
        consolidator = TradeBarConsolidator(indicator_timedelta)
        self.register_indicator(
            symbol,
            indicator,
            consolidator,
        )

    def _add_symbol_subscription(
        self,
        ticker: str,
        symbol_timeframe: TimeframeData,
        indicators: list[IndicatorData],
    ):
        resolution = symbol_timeframe.resolution
        market = Market.BINANCE if self.live_mode else Market.DUKASCOPY
        if self.live_mode:
            ticker = self._map_live_ticker(ticker)

        if self.security_type == "crypto":
            security = self.add_crypto(
                ticker,
                resolution,
                fill_forward=False,
                market=market,
            )
        elif self.security_type == "forex":
            security = self.add_forex(
                ticker,
                resolution,
                fill_forward=False,
                market=market,
                leverage=50.0,
            )
            security.set_fee_model(InteractiveBrokersFeeModel())
        elif self.security_type == "equity":
            security = self.add_equity(
                ticker,
                resolution,
                fill_forward=False,
                market=market,
            )
            security.is_tradable = False
        else:
            raise ValueError(
                "Only support forex, crypto and equity, other symbol types will be added soon!"
            )

        data = SymbolData(security.symbol)

        for indicator in indicators:
            time_delta = self._resolve_consolidator_timedelta(indicator.timeframe)
            self._add_indicator_consolidator(
                data.symbol, indicator.indicator_class, time_delta
            )
            data.indicators[indicator.name] = indicator.indicator_class

        symbol_timedelta = self._resolve_consolidator_timedelta(symbol_timeframe)
        self._add_symbol_consolidator(data.symbol, symbol_timedelta)

        self.data[ticker] = data

        if self.primary_symbol is None:
            self.primary_symbol = data.symbol
            self.set_benchmark(data.symbol)

        return data

    def _initialize_strategy(self):

        self.donchian_entry_period = self.get_parameter("donchian_entry_period", 34)
        self.donchian_exit_period = self.get_parameter("donchian_exit_period", 7)
        self.ema_filter_period = self.get_parameter("ema_filter_period", 200)
        self.stop_loss_pct = self.get_parameter("stop_loss_pct", 0.03)
        self.take_profit_pct = self.get_parameter("take_profit_pct", 0.08)
        self.timeout_bars = self.get_parameter("timeout_bars", 60)

        tf = TimeframeData(multiplier=4, resolution=Resolution.HOUR)
        indicators = [
            IndicatorData(
                name="donchian_entry",
                timeframe=tf,
                indicator_class=DonchianChannel(self.donchian_entry_period, self.donchian_entry_period)
            ),
            IndicatorData(
                name="donchian_exit",
                timeframe=tf,
                indicator_class=DonchianChannel(self.donchian_exit_period, self.donchian_exit_period)
            ),
            IndicatorData(
                name="ema",
                timeframe=tf,
                indicator_class=ExponentialMovingAverage(self.ema_filter_period)
            ),
            IndicatorData(
                name="atr",
                timeframe=tf,
                indicator_class=AverageTrueRange(14)
            )
        ]

        data = self._add_symbol_subscription("BTCUSD", tf, indicators)
        self.pos_sizes[data.symbol.value] = 0.8

    def _is_quote_valid(self, bar: QuoteBar) -> bool:
        if bar is None:
            return False
        if bar.ask is None or bar.bid is None:
            return False

        def _is_valid_number(value):
            if value is None:
                return False
            try:
                return value == value
            except Exception:
                return False

        for side_bar in [bar.ask, bar.bid]:
            for field in ["open", "high", "low", "close"]:
                if not _is_valid_number(getattr(side_bar, field, None)):
                    return False

        return True

    def _is_indicators_valid(self, data: SymbolData) -> bool:
        for indicator in data.indicators.values():
            if not indicator.is_ready:
                return False
            if (
                indicator.current.value is None
                or indicator.current.value != indicator.current.value
            ):
                return False
        return True

    def _update_quote(self, data: SymbolData, bar: QuoteBar):

        data.end_time = bar.end_time

        data.ask_open = bar.ask.open
        data.ask_high = bar.ask.high
        data.ask_low = bar.ask.low
        data.ask_close = bar.ask.close
        data.last_ask_size = bar.last_ask_size

        data.bid_open = bar.bid.open
        data.bid_high = bar.bid.high
        data.bid_low = bar.bid.low
        data.bid_close = bar.bid.close
        data.last_bid_size = bar.last_bid_size

        data.mid_open = bar.open
        data.mid_high = bar.high
        data.mid_low = bar.low
        data.mid_close = bar.close
        data.spread = data.ask_close - data.bid_close

    def _update_indicators(self, data: SymbolData):

        d_entry = data.indicators.get("donchian_entry")
        if d_entry is not None and d_entry.is_ready:
            data.prev_donchian_entry_upper = getattr(data, "curr_donchian_entry_upper", None)
            data.prev_donchian_entry_lower = getattr(data, "curr_donchian_entry_lower", None)
            data.curr_donchian_entry_upper = d_entry.upper_band.current.value
            data.curr_donchian_entry_lower = d_entry.lower_band.current.value

        d_exit = data.indicators.get("donchian_exit")
        if d_exit is not None and d_exit.is_ready:
            data.prev_donchian_exit_upper = getattr(data, "curr_donchian_exit_upper", None)
            data.prev_donchian_exit_lower = getattr(data, "curr_donchian_exit_lower", None)
            data.curr_donchian_exit_upper = d_exit.upper_band.current.value
            data.curr_donchian_exit_lower = d_exit.lower_band.current.value

        ema = data.indicators.get("ema")
        if ema is not None and ema.is_ready:
            data.prev_ema = getattr(data, "curr_ema", None)
            data.curr_ema = ema.current.value

        atr = data.indicators.get("atr")
        if atr is not None and atr.is_ready:
            data.prev_atr = getattr(data, "curr_atr", None)
            data.curr_atr = atr.current.value

    def _on_consolidated_bar(self, sender, bar: QuoteBar):
        data = self.data.get(bar.symbol.value, None)

        if data is None or not self._is_quote_valid(bar):
            return

        self._update_quote(data, bar)

        if not self._is_indicators_valid(data):
            return

        self._update_indicators(data)

        if self.is_warming_up:
            return

        self._process_symbol(data)

    def _to_lot_size_multiple(self, symbol: Symbol, raw_quantity: float) -> float:
        return to_lot_size_multiple(self, symbol, raw_quantity)

    def _to_tick_size_multiple(self, symbol: Symbol, price: float) -> float:
        return to_tick_size_multiple(self, symbol, price)

    def _cancel_bracket_orders(self, data: SymbolData):

        self._cancel_ticket(data.stop_ticket, "Cancel stop")
        self._cancel_ticket(data.target_ticket, "Cancel target")
        self._cancel_ticket(data.trailing_ticket, "Cancel trailing")
        self._clear_ticket(data, "stop_ticket")
        self._clear_ticket(data, "target_ticket")
        self._clear_ticket(data, "trailing_ticket")

    def _is_open_order(self, ticket: OrderTicket):
        return ticket is not None and ticket.status not in [
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.INVALID,
        ]

    def _has_pending_entry(self, data: SymbolData):
        return self._is_open_order(data.entry_ticket)

    def _cancel_ticket(self, ticket, tag):
        if self._is_open_order(ticket):
            ticket.cancel(tag)

    def _register_ticket(self, data: SymbolData, key: str, ticket: OrderTicket):
        old_ticket: OrderTicket = getattr(data, key)
        if (
            old_ticket is not None
            and ticket is not None
            and old_ticket.order_id != ticket.order_id
        ):
            self.order_to_data.pop(old_ticket.order_id, None)

        setattr(data, key, ticket)
        if ticket is not None:
            self.order_to_data[ticket.order_id] = data

    def _clear_ticket(self, data: SymbolData, key: str):
        ticket: OrderTicket = getattr(data, key)
        if ticket is not None:
            self.order_to_data.pop(ticket.order_id, None)
        setattr(data, key, None)

    def _get_order(self, order_id: int):
        return self.transactions.get_order_by_id(order_id)

    def _close_position(self, data: SymbolData, reason: str):

        self._cancel_bracket_orders(data)
        self.liquidate(data.symbol, reason)
        data.position_open_time = None
        data.last_exit_time = self.time

    def _calculate_entry_quantity(
        self, data: SymbolData, entry_direction: int
    ) -> float:

        if entry_direction == 0:
            return 0

        ticker = data.symbol.value
        position_size_pct = float(self.pos_sizes[ticker])
        target_pct = entry_direction * position_size_pct

        return self.calculate_order_quantity(data.symbol, target_pct)

    def _submit_order(
        self,
        data: SymbolData,
        order_type: str,
        quantity: float,
        *,
        target_pct: float = None,
        limit_price: float = None,
        stop_price: float = None,
        tag: str = "",
    ):
        symbol = data.symbol

        if order_type == "set_holdings":
            if target_pct is None:
                raise ValueError("set_holdings entry requires target_pct")
            quantity = self.calculate_order_quantity(symbol, target_pct)
            quantity = self._to_lot_size_multiple(symbol, quantity)
            if quantity == 0:
                return None
            return self.market_order(symbol=symbol, quantity=quantity, tag=tag)

        if order_type == "market":
            quantity = self._to_lot_size_multiple(symbol, quantity)
            if quantity == 0:
                return None
            return self.market_order(symbol=symbol, quantity=quantity, tag=tag)

        if order_type == "limit":
            if limit_price is None:
                raise ValueError("limit entry requires limit_price")
            return self.limit_order(
                symbol=symbol,
                quantity=quantity,
                limit_price=limit_price,
                tag=tag,
            )

        if order_type == "stop_limit":
            if stop_price is None or limit_price is None:
                raise ValueError("stop_limit entry requires stop_price and limit_price")
            return self.stop_limit_order(
                symbol=symbol,
                quantity=quantity,
                stop_price=stop_price,
                limit_price=limit_price,
                tag=tag,
            )

        if order_type == "stop_market":
            if stop_price is None:
                raise ValueError("stop_market entry requires stop_price")
            return self.stop_market_order(
                symbol=symbol,
                quantity=quantity,
                stop_price=stop_price,
                tag=tag,
            )

    def _process_symbol(self, data: SymbolData):

        if data.ask_close is None or data.bid_close is None or data.mid_close is None:
            return

        holdings = self.portfolio[data.symbol].quantity
        is_invested = self._is_effectively_invested(data, holdings)
        is_flat = self._is_effectively_flat(data, holdings)

        curr_mid_close = data.mid_close
        prev_donchian_entry_upper = getattr(data, "prev_donchian_entry_upper", None)
        prev_donchian_exit_lower = getattr(data, "prev_donchian_exit_lower", None)
        curr_ema = getattr(data, "curr_ema", None)

        if is_invested:
            if data.position_open_time is None:
                data.position_open_time = self.time
            if not self._is_open_order(data.stop_ticket) and not self._is_open_order(data.target_ticket):
                entry_ref = self.portfolio[data.symbol].average_price or curr_mid_close
                self._place_exit_bracket(data, entry_ref, holdings)

            bars_held = (self.time - data.position_open_time).total_seconds() / (4 * 3600)
            if bars_held >= self.timeout_bars:
                self._close_position(data, "Timeout Exit")
                return

            if prev_donchian_exit_lower is not None and curr_mid_close < prev_donchian_exit_lower:
                self._close_position(data, "Signal Exit: Donchian Lower Break")
                return

        if is_flat:
            if self._has_pending_entry(data):
                return
            if data.last_exit_time is not None and data.last_exit_time == self.time:
                return
            if prev_donchian_entry_upper is None or curr_ema is None:
                return

            long_signal = (curr_mid_close > prev_donchian_entry_upper) and (curr_mid_close > curr_ema)
            if long_signal:
                quantity = self._calculate_entry_quantity(data, 1)
                if quantity > 0:
                    self._submit_order(data, "market", quantity, tag="Entry")

    def _place_exit_bracket(
        self, data: SymbolData, fill_price: float, fill_quantity: float
    ):

        if fill_quantity <= 0:
            return

        qty = -fill_quantity
        atr = getattr(data, "curr_atr", None)
        if atr is not None and atr > 0:
            raw_sl = fill_price - 2.0 * atr
        else:
            raw_sl = fill_price * (1.0 - float(self.stop_loss_pct))

        stop_price = self._to_tick_size_multiple(data.symbol, raw_sl)
        limit_price_sl = self._to_tick_size_multiple(data.symbol, stop_price * (1.0 - 0.005))

        raw_tp = fill_price * (1.0 + float(self.take_profit_pct))
        target_price = self._to_tick_size_multiple(data.symbol, raw_tp)
        limit_price_tp = target_price

        sl_ticket = self._submit_protective_order(
            data,
            "stop_limit",
            qty,
            stop_price=stop_price,
            limit_price=limit_price_sl,
            tag="SL"
        )
        self._register_ticket(data, "stop_ticket", sl_ticket)

        tp_ticket = self._submit_protective_order(
            data,
            "stop_limit",
            qty,
            stop_price=target_price,
            limit_price=limit_price_tp,
            tag="TP"
        )
        self._register_ticket(data, "target_ticket", tp_ticket)

    def _submit_protective_order(
        self,
        data: SymbolData,
        order_type: str,
        quantity: float,
        *,
        stop_price: float = None,
        limit_price: float = None,
        trailing_percent: float = None,
        tag: str = "",
    ):

        symbol = data.symbol

        if order_type == "stop_limit":
            if stop_price is None or limit_price is None:
                raise ValueError(
                    "stop_limit protective order requires stop_price and limit_price"
                )
            return self.stop_limit_order(
                symbol=symbol,
                quantity=quantity,
                stop_price=stop_price,
                limit_price=limit_price,
                tag=tag,
            )

        if order_type == "stop_market":
            if stop_price is None:
                raise ValueError("stop_market protective order requires stop_price")
            return self.stop_market_order(
                symbol=symbol,
                quantity=quantity,
                stop_price=stop_price,
                tag=tag,
            )

        if order_type == "limit":
            if limit_price is None:
                raise ValueError("limit protective order requires limit_price")
            return self.limit_order(
                symbol=symbol,
                quantity=quantity,
                limit_price=limit_price,
                tag=tag,
            )

        if order_type == "trailing_stop":
            if trailing_percent is None:
                raise ValueError(
                    "trailing_stop protective order requires trailing_percent"
                )
            return self.trailing_stop_order(
                symbol=symbol,
                quantity=quantity,
                trailing_amount=trailing_percent,
                trailing_as_percentage=True,
                tag=tag,
            )

    def on_order_event(self, order_event: OrderEvent):
        data = self.order_to_data.get(order_event.order_id)
        if data is None:
            data = self.data.get(order_event.symbol.value)
        if data is None:
            return

        order = self._get_order(order_event.order_id)

        self._handle_order_event(
            data,
            order_event,
            order,
        )

    def _handle_order_event(self, data: SymbolData, order_event: OrderEvent, order):

        if order is None:
            return

        if order_event.status == OrderStatus.SUBMITTED:
            if order.tag == "Entry":
                ticket = self.transactions.get_order_ticket(order_event.order_id)
                self._register_ticket(data, "entry_ticket", ticket)
            return

        if order_event.status == OrderStatus.FILLED:
            if order.tag == "Entry":
                data.position_open_time = self.time
                data.pending_entry_time = None
                fill_price = order_event.fill_price
                fill_qty = order_event.fill_quantity
                self._place_exit_bracket(data, fill_price, fill_qty)
                self._clear_ticket(data, "entry_ticket")
                return

            is_stop = data.stop_ticket is not None and data.stop_ticket.order_id == order_event.order_id
            is_target = data.target_ticket is not None and data.target_ticket.order_id == order_event.order_id
            is_trailing = data.trailing_ticket is not None and data.trailing_ticket.order_id == order_event.order_id

            if is_stop or is_target or is_trailing:
                if is_stop:
                    self._cancel_ticket(data.target_ticket, "Cancel target on SL fill")
                    self._cancel_ticket(data.trailing_ticket, "Cancel trailing on SL fill")
                elif is_target:
                    self._cancel_ticket(data.stop_ticket, "Cancel stop on TP fill")
                    self._cancel_ticket(data.trailing_ticket, "Cancel trailing on TP fill")
                elif is_trailing:
                    self._cancel_ticket(data.stop_ticket, "Cancel stop on Trail fill")
                    self._cancel_ticket(data.target_ticket, "Cancel target on Trail fill")

                self._clear_ticket(data, "stop_ticket")
                self._clear_ticket(data, "target_ticket")
                self._clear_ticket(data, "trailing_ticket")

                holdings = self.portfolio[data.symbol].quantity
                if self._is_effectively_flat(data, holdings):
                    data.position_open_time = None
                    data.last_exit_time = self.time
                return

        if order_event.status in [OrderStatus.CANCELED, OrderStatus.INVALID]:
            if order.tag == "Entry":
                self._clear_ticket(data, "entry_ticket")
                data.pending_entry_time = None
            elif data.stop_ticket is not None and data.stop_ticket.order_id == order_event.order_id:
                self._clear_ticket(data, "stop_ticket")
            elif data.target_ticket is not None and data.target_ticket.order_id == order_event.order_id:
                self._clear_ticket(data, "target_ticket")
            elif data.trailing_ticket is not None and data.trailing_ticket.order_id == order_event.order_id:
                self._clear_ticket(data, "trailing_ticket")