import argparse
import datetime, pytz, holidays
import time
import sys
import yfinance as yf
import json

from config_20XX import *

if MODEL_TYPE == 'TF':
	from model_tf import *
elif MODEL_TYPE == 'TORCH':
	from model_pytorch import *
from data_util import *

if CLIENT_TYPE == 'ETRADE':
	from etrade.client import TradingClient
elif CLIENT_TYPE == 'ALPACA':
	from alpaca.client import TradingClient


class Logger(object):
	def __init__(self):
		self.terminal = sys.stdout

	def write(self, message):
		log_datetime = datetime.datetime.now(tz).strftime("%m-%d-%Y")
		with open ("logs/trader_%s.log" % log_datetime, 'a') as self.log:            
			self.log.write(message)
		self.terminal.write(message)

	def flush(self):
		pass



class Trader:

	def __init__(self, stock_ticker, model, client, init_cash=1000.00):
		self.stock_ticker = stock_ticker
		self.model = model
		self.client = client

		self.init_cash = init_cash
		self.cash = init_cash
		self.shares = 0

		self.price_target = 0.0
		self.prev_order_id = ''
		self.prev_filled_shares = 0
		self.next_prediction_time = datetime.datetime.now()
		self.prediction_interval = datetime.timedelta(seconds=PREDICTION_INTERVAL)

	def get_stock_prediction(self):
		# Pull the most recent stock data 
		stock_raw, stock_dat = recent_stock_data(self.stock_ticker)
		stock_predict = self.model.predict(stock_dat) * CONSERVATIVE_CONST
		stock_predict = unnormalize_data(stock_raw, stock_predict, [[0]])[0]
		return round(stock_predict[0][0], 2)

	def new_order(self):
		order = {
			"price_type": "MARKET",
			"order_term": "GOOD_FOR_DAY",
			"symbol": self.stock_ticker,
			"order_action": "",
			"limit_price": 0.0,
			"quantity": 0
		}
		return order

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

	def update_stock_prediction(self, order, curr_bid_price, curr_ask_price):
		# Make a new prediction for the stock
		self.price_target = self.get_stock_prediction()
		print("NEW PREDICTION = $%.3f" % self.price_target)
		order['limit_price'] = self.price_target
		if self.price_target > curr_ask_price:
			order["order_action"] = "BUY"
			order["quantity"] = int(self.cash // curr_ask_price)
		elif self.price_target < curr_bid_price:
			order["order_action"] = "SELL"
			order["quantity"] = self.shares
		self.next_prediction_time = datetime.datetime.now() + self.prediction_interval
		return order

	def check_previous_order_filled(self):
		order_info = self.client.get_order_info(self.prev_order_id)
		prev_order_filled = order_info['filled_qty'] == order_info['qty']

		s = (order_info['order_action'], order_info['filled_qty'], order_info['qty'], order_info['avg_price'])
		if prev_order_filled:
			print("--> ORDER FILLED: %s %s/%s shares @ avg price $%.2f" % s)
			self.prev_order_id = ''
		else:
			print("--> ORDER NOT YET FILLED: %s %s/%s shares @ avg price $%.2f" % s)

		if order_info['avg_price'] != 0.0:
			new_filled_shares = order_info['filled_qty'] - self.prev_filled_shares
			order_type = 1 if order_info['order_action'] == 'BUY' else -1
			self.shares += new_filled_shares * order_type
			self.cash -= new_filled_shares * order_info['avg_price'] * order_type

		self.prev_filled_shares = 0 if prev_order_filled else order_info['filled_qty']
		return prev_order_filled

	def trading_loop(self):

		while (1):

			print("\n---\n%s" % datetime.datetime.now(tz).strftime("%H:%M:%S,  %m/%d/%Y"))
			order = self.new_order()
			curr_price = self.client.get_last_price()
			curr_bid_price = self.client.get_last_price()
			curr_ask_price = self.client.get_last_price()
			#curr_bid_price = self.client.get_last_bid()
			#curr_ask_price = self.client.get_last_ask()

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
				if self.prompt_quit():
					break
				continue

			# Check if previous order was filled
			prev_order_filled = self.prev_order_id == '' or self.check_previous_order_filled()

			# Make decision based on previous prediction
			self.update_prediction_time(curr_bid_price, curr_ask_price)

			if self.next_prediction_time < datetime.datetime.now():
				# Cancel previous order if not filled
				if not prev_order_filled:
					self.client.cancel_order(self.prev_order_id)
					self.prev_filled_shares = 0
				self.update_stock_prediction(order, curr_bid_price, curr_ask_price)

			if order["quantity"] > 0 and order["order_action"]:
				try:
					# EXECUTE THE ORDER
					self.prev_order_id = self.client.place_order(order).id
					self.prev_filed_shares = 0
				except Exception as e:
					print("\n\n########## PLACE ORDER ERROR ##########\n%s: %s" % (type(e).__name__, e))
					if self.prompt_quit():
						break
					self.next_prediction_time = datetime.datetime.now()
					continue
				print("--> ORDER PLACED: %s %s shares " % (order["order_action"], order["quantity"]), end='')
				if order["order_action"] == "MARKET":
					print("@ market price")
				else:
					print("@ $%.2f" % order["limit_price"])
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



def get_args():
	parser = argparse.ArgumentParser(description='Trade some stonks.')
	parser.add_argument('--t', dest='ticker',
						type=str, required=False,
						help='the ticker of the stock to be traded')
	parser.add_argument('--m', dest='model',
						type=str, required=False,
						help='the path of the file in which the model has been saved')
	return parser.parse_args()


if __name__ == '__main__':
	args = get_args()

	if args.ticker:
		STOCK_TICKER = args.ticker
	STOCK_TICKER = STOCK_TICKER.upper()

	stock_raw, stock_dat, stock_labels = model_stock_data(STOCK_TICKER)
	train_x, train_y, test_x, test_y = partition_data(TRAINING_SET_THRESH, stock_dat, stock_labels)
	train_x, train_y, val_x, val_y = partition_data(TRAINING_SET_THRESH, train_x, train_y)
	input_frame_shape = (stock_dat.shape[1], stock_dat.shape[2])

	if args.model:
		load_model(args.model)
	else:
		model = generate_model(input_frame_shape)
		train_model(model, train_x, train_y, val_x, val_y)
		eval_model(STOCK_TICKER, model, test_x, test_y)

	trading_client = TradingClient(STOCK_TICKER)
	trader = Trader(STOCK_TICKER, model, trading_client, INIT_CASH)

	ask_continue = input("\n**********\nCONFRIM TRADER START WITH THIS MODEL (y/n): ").lower()
	if ask_continue != 'y':
		exit(0)

	tz = pytz.timezone('US/Eastern')
	sys.stdout = Logger()

	trader.trading_loop()
