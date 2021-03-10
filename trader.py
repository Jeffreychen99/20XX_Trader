import datetime, pytz, holidays
import time
import sys
import yfinance as yf
import json

from etrade.auth import oauth
from etrade.accounts import Accounts
from etrade.market import Market
from etrade.order import Order

from config_20XX import *
if MODEL_TYPE == 'TF':
	from model_tf import *
elif MODEL_TYPE == 'TORCH':
	from model_pytorch import *
from data_util import *

tz = pytz.timezone('US/Eastern')
us_holidays = holidays.US()



class Trader:

	session, base_url = None, None
	accounts, market = None, None

	stock_ticker = ''

	def __init__(self, stock_ticker, model, init_cash=1000.00):
		self.stock_ticker = stock_ticker
		self.model = model

		self.total_trades = 0
		self.init_cash = init_cash
		self.cash = init_cash
		self.shares = 0

	def is_trading_hour(self, now=None):
		if not now:
			now = datetime.datetime.now(tz)
		openTime = datetime.time(hour=9, minute=35, second=0)
		closeTime = datetime.time(hour=15, minute=55, second=0)
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

	def etrade_auth(self):
		self.session, self.base_url = oauth()
		self.market = Market(self.session, self.base_url)
		self.accounts = Accounts(self.session, self.base_url)
		self.accounts.account_list()
		self.orders = Order(self.session, self.accounts.account, self.base_url)

	def predict_stock(self):
		# Pull the most recent stock data 
		stock_raw, stock_dat = recent_stock_data(self.stock_ticker)
		stock_predict = self.model.predict(stock_dat)
		stock_predict = unnormalize_data(stock_raw, stock_predict, [[0]])[0]
		return stock_predict[0][0]

	def place_order(self, order):
		self.orders.place_order(order)
		pass

	def trading_loop(self):
		price_target = 0.0
		prev_trade_type = ''
		next_prediction_time = datetime.datetime.now()

		while (1):

			order = {
				"price_type": "MARKET",
				"order_term": "GOOD_FOR_DAY",
				"symbol": self.stock_ticker,
				"order_action": "",
				"limit_price":"",
				"quantity": "0"
			}

			stock_quote = self.market.quotes(self.stock_ticker)
			if not stock_quote:
				# Error with the API - reauthenticate
				self.etrade_auth()
				continue

			curr_price = stock_quote['lastTrade']

			if not self.is_trading_hour():
				value = self.cash + stock_quote['lastTrade'] * self.shares 
				print("---\n%s" % datetime.datetime.now(tz).strftime("%H:%M:%S,  %m/%d/%Y"))
				print("AFTER HOURS TRADING - NO ACTION")
				print("SHARES = $%.2f, CASH = $%.2f, VALUE = $%.2f\n"  % (self.shares * curr_price, self.cash, value))
				try:
					time.sleep(AFTER_HOURS_SLEEP)
				except KeyboardInterrupt:
					self.trading_summary(curr_price)
					if input("Quit trader? (y/n)").lower() == 'y':
						print("@@@@@@@@@@@@@@@@ TRADER HALTED @@@@@@@@@@@@@@@@")
						break
					else:
						print("Continuing to trade...")
				continue

			print("---\n%s" % datetime.datetime.now(tz).strftime("%H:%M:%S,  %m/%d/%Y"))
			print("CURRENT = $%.2f" % curr_price)

			# Make decision based on previous prediction
			if prev_trade_type == 'BUY' and curr_price >= price_target:
				print("PRICE ROSE ABOVE TARGET OF $%.2f" % price_target, end=' | ')
				next_prediction_time = datetime.datetime.now()
			elif prev_trade_type == 'SELL' and curr_price < price_target:
				print("PRICE FELL BELOW TARGET OF $%.2f" % price_target, end=' | ')
				next_prediction_time = datetime.datetime.now()
			elif price_target:
				print("PRICE TARGET $%.2f NOT YET MET" % price_target)

			quantity = 0
			if next_prediction_time < datetime.datetime.now():
				# Make a new prediction for the stock
				price_target = self.predict_stock(self.stock_ticker, self.model)
				print("NEW PREDICTION = $%.2f" % price_target)
				if price_target > curr_price:
					order["order_action"] = "BUY"
					quantity = int(self.cash // curr_price)
				else:
					order["order_action"] = "SELL"
					quantity = self.shares

				prediction_interval = datetime.timedelta(seconds=PREDICTION_INTERVAL)
				next_prediction_time = datetime.datetime.now() + prediction_interval

			if quantity > 0 and order["order_action"]:
				# EXECUTE THE ORDER
				order["quantity"] = str(quantity)
				self.place_order(order)
				print("--> %s %s shares @ $%.2f" % (order["order_action"], quantity, curr_price))

				order_type = 1 if order["order_action"] == "BUY" else -1
				self.shares += quantity * order_type
				self.cash -= quantity * curr_price * order_type
	 
				prev_trade_type = order["order_action"]

			# Update the value
			value = self.cash + curr_price * self.shares
			print("SHARES = $%.2f, CASH = $%.2f, VALUE = $%.2f"  % (self.shares * curr_price, self.cash, value))

			try:
				time.sleep(TRADING_HOURS_SLEEP)
			except KeyboardInterrupt:
				self.trading_summary(curr_price)
				if input("Quit trader? (y/n)").lower() == 'y':
					print("@@@@@@@@@@@@@@@@ TRADER HALTED @@@@@@@@@@@@@@@@")
					break
				else:
					print("Continuing to trade...")

	def trading_summary(self, curr_stock_price):
		value = self.cash + curr_stock_price * self.shares
		print("\n\n********************* TRADING SUMMARY *********************")
		print("STARTING VALUE:  $%.2f" % self.init_cash)
		print("ENDING VALUE:    $%.2f" % value)
		print("")
		r = (value/self.init_cash - 1) * 100
		print("TOTAL'S RETURN:  %% %.2f" % r)
		print("***********************************************************")



if __name__ == '__main__':
	if len(sys.argv) > 1 and sys.argv[1].isupper():
		STOCK_TICKER = sys.argv[1]
	STOCK_TICKER = STOCK_TICKER.upper()

	stock_raw, stock_dat, stock_labels = model_stock_data(STOCK_TICKER)
	train_x, train_y, test_x, test_y = partition_data(TRAINING_SET_THRESH, stock_dat, stock_labels)
	train_x, train_y, val_x, val_y = partition_data(TRAINING_SET_THRESH, train_x, train_y)
	input_frame_shape = (stock_dat.shape[1], stock_dat.shape[2])

	model = generate_model(input_frame_shape)
	train_model(model, train_x, train_y, val_x, val_y)
	eval_model(STOCK_TICKER, model, test_x, test_y)

	trader = Trader(STOCK_TICKER, model, INIT_CASH)
	trader.etrade_auth()

	ask_continue = input("\n**********\nCONFRIM TRADER START WITH THIS MODEL (y/n): ").lower()
	ask_continue = 'y'
	if ask_continue != 'y':
		exit(0)

	trader.trading_loop()

	'''
	order = {
		"price_type": "MARKET",
		"order_term": "GOOD_FOR_DAY",
		"symbol": "ITI",
		"order_action": "BUY",
		"limit_price":"",
		"quantity": "1"
	}
	trader.place_order(order)
	'''

	
