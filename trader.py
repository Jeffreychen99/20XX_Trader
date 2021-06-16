import datetime
import pytz
import holidays
import time
import yfinance as yf
import json

from order import *
from alpaca.client import TradingClient

from config_20XX import *

if MODEL_TYPE == 'TF':
	from model_tf import *
elif MODEL_TYPE == 'TORCH':
	from model_pytorch import *
from data_util import *



class Trader:

	def __init__(self, stock_ticker, model, client, init_cash=1000.00):
		self.stock_ticker = stock_ticker
		self.model = model
		self.client = client

		self.init_cash = init_cash
		self.cash = init_cash
		self.shares = 0

		self.price_target = 0.0
		self.next_prediction_time = datetime.datetime.now()
		self.prediction_interval = datetime.timedelta(seconds=PREDICTION_INTERVAL)

		self.active_orders = []

	def get_stock_prediction(self):
		# Pull the most recent stock data 
		stock_raw, stock_dat = recent_stock_data(self.stock_ticker)
		stock_predict = self.model.predict(stock_dat) * CONSERVATIVE_CONST
		stock_predict = unnormalize_data(stock_raw, stock_predict, [[0]])[0]
		return round(stock_predict[0][0], 2)

	def place_order(self, order):
		order.place(self.client)
		self.active_orders.append(order)

	def update_prediction_time(self, curr_bid_price, curr_ask_price):
		# Make decision based on previous prediction
		if (self.shares == 0 or self.cash >= curr_ask_price) and curr_ask_price <= self.price_target:
			# See if it's a good time to buy
			print("PRICE IS BELOW TARGET OF $%.3f" % self.price_target, end=' | ')
			self.next_prediction_time = datetime.datetime.now()
		elif self.shares > 0 and curr_bid_price >= self.price_target:
			# See if it's a good time to sell
			print("PRICE IS ABOVE TARGET OF $%.3f" % self.price_target, end=' | ')
			self.next_prediction_time = datetime.datetime.now()
		elif self.price_target:
			print("PRICE TARGET $%.3f NOT YET MET" % self.price_target)

	def check_active_order_filled(self, order):
		assert order in self.active_orders
		prev_filled_shares = order.filled_qty

		filled = order.is_filled(self.client)
		# Update shares and cash if order was filled at all
		new_filled_shares = order.filled_qty - prev_filled_shares
		if filled:
			order_type = 1 if order.action == "BUY" else -1
			self.shares += new_filled_shares * order_type
			self.cash -= new_filled_shares * order.avg_price * order_type

			self.active_orders.remove(order)

		return filled

	def check_active_orders_filled(self):
		for order in list(self.active_orders):
			if self.check_active_order_filled(order):
				if order.is_filled(self.client) and order.action == "BUY":
					# Place a limit sell order at 1 cent above avg_price to make a profit
					limit_price = round(order.avg_price + 0.01, 2)
					limit_order = LimitOrder(self.stock_ticker, "SELL", limit_price, order.qty)
					self.place_order(limit_order)
				elif isinstance(order, LimitOrder):
					self.next_prediction_time = datetime.datetime.now()

	def act(self, curr_bid_price, curr_ask_price):
		# Make a new prediction for the stock
		self.price_target = self.get_stock_prediction()
		print("NEW PREDICTION = $%.3f" % self.price_target)
		self.next_prediction_time = datetime.datetime.now() + self.prediction_interval

		if self.price_target < curr_bid_price and self.shares > 0:
			# Cancel all active orders
			for active_order in self.active_orders:
				active_order.cancel(self.client)
				self.check_active_order_filled(active_order)
			self.active_orders = []

			if self.shares > 0:
				# Sell all shares
				self.place_order( MarketOrder(self.stock_ticker, "SELL", self.shares) )
		elif self.price_target > curr_ask_price:
			qty = int(self.cash // curr_ask_price)
			if qty > 0:
				order = MarketOrder(self.stock_ticker, "BUY", qty)
				self.place_order(order)

	def trading_loop(self):

		tz = pytz.timezone('US/Eastern')

		while (1):
			print("\n---\n%s" % datetime.datetime.now(tz).strftime("%H:%M:%S,  %m/%d/%Y"))
			curr_price = self.client.get_last_price()
			curr_bid_price = self.client.get_last_bid()
			curr_ask_price = self.client.get_last_ask()

			if not self.client.market_is_open():
				print("AFTER HOURS TRADING - NO ACTION")
				self.print_value(curr_price)

				try:
					time.sleep(AFTER_HOURS_SLEEP)
					pass
				except KeyboardInterrupt:
					self.trading_summary(curr_price)
					if self.prompt_quit():
						break
				continue

			print("LAST TRADE = $%.2f | BID = $%.2f | ASK = $%.2f" % (curr_price, curr_bid_price, curr_ask_price))

			try:
				self.validate_trader(curr_bid_price, curr_ask_price)
			except:
				print("Trader validation went wrong:\n  Shares: %d\n   Cash: $%.2f" % (self.shares, self.cash))
				if self.prompt_quit():
					break
				continue

			# Check if previous order was filled
			order_filled = self.check_active_orders_filled()
			if order_filled:
				continue

			if not any([order for order in self.active_orders if isinstance(order, MarketOrder)]):
				# See if it's time for a new prediction
				self.update_prediction_time(curr_bid_price, curr_ask_price)

			if self.next_prediction_time < datetime.datetime.now():
				# Act on the information
				self.act(curr_bid_price, curr_ask_price)
			else:
				if self.price_target <= curr_ask_price:
					print("NO ACTION:  PRICE TARGET ≤ ASK")
				elif self.price_target >= curr_bid_price:
					print("NO ACTION:  PRICE TARGET ≥ BID")
					
			self.print_value(curr_price)

			try:
				time.sleep(TRADING_HOURS_SLEEP)
			except KeyboardInterrupt:
				self.trading_summary(curr_price)
				if self.prompt_quit():
					break

	def print_value(self, curr_price):
		equity = self.shares * curr_price
		value = self.cash + equity
		t = (self.shares, equity, self.cash, value)
		print("SHARES = %d, EQUITY = $%.2f, CASH = $%.2f, VALUE = $%.2f"  % t)
		return value

	def validate_trader(self, curr_bid_price, curr_ask_price):
		assert self.shares >= 0
		assert self.cash >= 0

		assert curr_bid_price > 0
		assert curr_ask_price > 0

	def prompt_quit(self):
		print("Quit trader? (y/n)   ")
		if input("").lower() == 'y':
			self.client.halt()
			print("@@@@@@@@@@@@@@@@@@@@@@ TRADER HALTED @@@@@@@@@@@@@@@@@@@@@@")
			return True
		else:
			print("Continuing to trade...\n\n\n")
			return False

	def trading_summary(self, curr_stock_price):
		value = self.cash + curr_stock_price * self.shares
		print("\n\n********************* TRADING SUMMARY *********************")
		print("STARTING VALUE:  $%.2f" % self.init_cash)
		print("ENDING VALUE:    $%.2f" % value)
		print("")
		r = (value/self.init_cash - 1) * 100
		print("TOTAL'S RETURN:  %% %.2f" % r, "   🚀🚀🚀" if r > 0 else "")
		print("***********************************************************")
