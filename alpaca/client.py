import os
import asyncio
import threading
import configparser
import alpaca_trade_api as tradeapi

from config_20XX import MODE

# loading configuration file
config = configparser.ConfigParser()
config.read('alpaca/config.ini')
for k in config[MODE]:
    os.environ[k.upper()] = config[MODE][k]

class TradingClient:

    def __init__(self, symbol):
        self.symbol = symbol.upper()
        self.api = tradeapi.REST()
        self.account = self.api.get_account()

        self.curr_price = self.api.get_last_trade(self.symbol).price
        quote = self.get_quote()
        self.ask_price = quote.askprice
        self.bid_price = quote.bidprice

        self.stream = tradeapi.Stream(config[MODE]['APCA_API_KEY_ID'],
                config[MODE]['APCA_API_SECRET_KEY'],
                base_url=config[MODE]['APCA_API_BASE_URL'],
                data_feed='iex')

        async def trade_callback(trade):
            #print(trade)
            self.curr_price = trade.price

        async def quote_callback(quote):
            #print(quote)
            self.bid_price = quote.bid_price
            self.ask_price = quote.ask_price

        self.stream.subscribe_trades(trade_callback, self.symbol)
        self.stream.subscribe_quotes(quote_callback, self.symbol)

        self.stream_event_loop = asyncio.new_event_loop()
        def start_stream():
            asyncio.set_event_loop(self.stream_event_loop)
            try:
                self.stream.run()
            except (RuntimeError, asyncio.exceptions.CancelledError):
                print("Stream successfully halted")

        streamThread = threading.Thread(target=start_stream)
        streamThread.start()

    def halt(self):
        print("Shutting down alpaca client stream...")
        self.stream.unsubscribe_trades()
        self.stream.unsubscribe_quotes()
        for task in asyncio.all_tasks(loop=self.stream_event_loop):
            task.cancel()
        self.stream_event_loop.stop()

    def get_quote(self):
        return self.api.get_last_quote(self.symbol)

    def get_last_price(self):
        return self.curr_price

    def get_last_ask(self):
        return self.ask_price

    def get_last_bid(self):
        return self.bid_price

    def place_order(self, order):
        return self.api.submit_order(
            symbol=order['symbol'].upper(),
            qty=int(order['qty']),
            side=order['action'].lower(),
            type=order['price_type'].lower(),
            limit_price=float(order['limit_price']) if order['price_type'].lower() == 'limit' else None,
            time_in_force='gtc'
        )

    def get_order_info(self, order_id):
        order = self.get_order(order_id)
        p = float(order.filled_avg_price) if order.filled_avg_price else 0.0
        info = {
            'filled_qty': int(order.filled_qty),
            'qty': int(order.qty),
            'avg_price': p,
            'action': order.side.upper()
        }
        return  info

    def get_order(self, order_id):
        return self.api.get_order(order_id)

    def cancel_order(self, order_id):
        return self.api.cancel_order(order_id)

    def market_is_open(self):
        return self.api.get_clock().is_open
