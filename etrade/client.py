import datetime, pytz, holidays

from etrade.auth import oauth
from etrade.accounts import Accounts
from etrade.market import Market
from etrade.order import Order

tz = pytz.timezone('US/Eastern')
us_holidays = holidays.US()

class TradingClient:

    def __init__(self):
        self.authenticate()

    def authenticate(self):
        self.session, self.base_url = oauth()
        self.market = Market(self.session, self.base_url)
        self.accounts = Accounts(self.session, self.base_url)
        self.accounts.account_list()
        self.orders = Order(self.session, self.accounts.account, self.base_url)

    def place_order(self, order):
        self.orders.place_order(order)

    def get_quote(self, symbol):
        stock_quote = self.market.quotes(symbol)
        if not stock_quote:
            # Error with API - retry authentication
            self.authenticate()
            stock_quote = self.market.quotes(symbol)
        return stock_quote

    def get_last_price(self, symbol):
        stock_quote = self.market.quotes(symbol)
        if not stock_quote:
            # Error with API - retry authentication
            self.authenticate()
            stock_quote = self.market.quotes(symbol)
        return stock_quote['lastTrade']


    def market_is_open(self):
        now = datetime.datetime.now(tz)
        openTime = datetime.time(hour=9, minute=30, second=0)
        closeTime = datetime.time(hour=16, minute=0, second=0)
        # If a holiday
        if now.strftime('%Y-%m-%d') in us_holidays:
            return False
        # If before 0930 or after 1600
        if (now.time() < openTime) or (now.time() > closeTime):
            return False
        # If it's a weekend
        if now.date().weekday() > 4:
            return False

        return True