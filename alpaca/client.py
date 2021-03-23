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

    def get_quote(self, symbol):
        return self.api.get_last_quote(symbol.upper())

    def get_last_price(self, symbol):
        #return self.get_quote(symbol).bidprice
        return self.api.get_last_trade(symbol).price

    def place_order(self, order):
        return self.api.submit_order(
            symbol=order['symbol'].upper(),
            qty=int(order['quantity']),
            side=order['order_action'].lower(),
            type=order['price_type'].lower(),
            limit_price=float(order['limit_price']) if order['price_type'].lower() == 'limit' else None,
            time_in_force='gtc'
        )

    def list_positions(self):
        return self.api.list_positions()

    def get_order(self, order_id):
        return self.api.get_order(order_id)

    def list_open_orders(self):
        return self.api.list_orders(status='open')

    def cancel_order(self, order_id):
        return self.api.cancel_order(order_id)

    def market_is_open(self):
        return self.api.get_clock().is_open
