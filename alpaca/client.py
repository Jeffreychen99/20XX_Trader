import os
import configparser
import alpaca_trade_api as tradeapi

from config_20XX import MODE

# loading configuration file
config = configparser.ConfigParser()
config.read('alpaca/config.ini')
for k in config[MODE]:
    os.environ[k.upper()] = config[MODE][k]

class TradingClient:

    def __init__(self):
        self.api = tradeapi.REST()
        self.account = self.api.get_account()
        self.clock = self.api.get_clock()

    def get_quote(self, symbol):
        barset = self.api.get_barset(symbol.upper(), 'minute', limit=1)
        return barset

    def get_last_price(self, symbol):
        barset = self.api.get_barset(symbol.upper(), 'minute', limit=1)
        return barset[symbol][0].c

    def place_order(self, order):
        self.api.submit_order(
            symbol=order['symbol'].upper(),
            qty=int(order['quantity']),
            side=order['order_action'].lower(),
            type=order['price_type'].lower(),
            time_in_force='gtc'
        )

    def market_is_open(self):
        return self.clock.is_open