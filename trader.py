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

	def predict_stock(self):
		# Pull the most recent stock data 
		stock_raw, stock_dat = recent_stock_data(self.stock_ticker)
		stock_predict = self.model.predict(stock_dat)
		stock_predict = unnormalize_data(stock_raw, stock_predict, [[0]])[0]
		return stock_predict[0][0]

	def trading_loop(self):
		price_target = 0.0
		prev_order_action = ''
		prev_order_id = ''
		next_prediction_time = datetime.datetime.now()
		prediction_interval = datetime.timedelta(seconds=PREDICTION_INTERVAL)

		while (1):

			order = {
				"price_type": "MARKET",
				"order_term": "GOOD_FOR_DAY",
				"symbol": self.stock_ticker,
				"order_action": "",
				"limit_price": 0.0,
				"quantity": 0
			}

			curr_price = self.client.get_last_price(self.stock_ticker)
			curr_bid_price = self.client.get_last_bid(self.stock_ticker)
			curr_ask_price = self.client.get_last_ask(self.stock_ticker)

			print("\n---\n%s" % datetime.datetime.now(tz).strftime("%H:%M:%S,  %m/%d/%Y"))
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

			print("CURRENT = $%.3f" % curr_price)

			# Check if previous order was filled
			prev_order_filled = True
			if prev_order_id:
				filled_qty, qty, filled_avg_price = self.client.get_average_fill_price(prev_order_id)
				prev_order_filled = filled_qty == qty

				s = (prev_order_action, filled_qty, qty, filled_avg_price)
				if prev_order_filled:
					print("--> ORDER FILLED: %s %s/%s shares @ avg price $%.3f" % s)
					prev_order_id = ''
				else:
					print("--> ORDER NOT YET FILLED: %s %s/%s shares @ avg price $%.3f" % s)

				if filled_avg_price != 0.0:
					order_type = 1 if prev_order_action == "BUY" else -1
					self.shares += filled_qty * order_type
					self.cash -= filled_qty * filled_avg_price * order_type

			# Make decision based on previous prediction
			if prev_order_action == 'BUY' and curr_ask_price >= price_target:
				print("PRICE ROSE ABOVE TARGET OF $%.3f" % price_target, end=' | ')
				next_prediction_time = datetime.datetime.now()
			elif prev_order_action == 'SELL' and curr_bid_price <= price_target:
				print("PRICE FELL BELOW TARGET OF $%.3f" % price_target, end=' | ')
				next_prediction_time = datetime.datetime.now()
			elif price_target:
				print("PRICE TARGET $%.3f NOT YET MET" % price_target)

			quantity = 0
			if next_prediction_time < datetime.datetime.now():
				# Cancel previous order if not filled
				if not prev_order_filled:
					self.client.cancel_order(prev_order_id)
				# Make a new prediction for the stock
				price_target = self.predict_stock()
				print("NEW PREDICTION = $%.3f" % price_target)
				order['limit_price'] = curr_price
				if price_target > curr_ask_price:
					order["order_action"] = "BUY"
					quantity = int(self.cash // curr_price)
				elif price_target < curr_bid_price:
					order["order_action"] = "SELL"
					quantity = self.shares
				prev_order_action = order["order_action"]
				next_prediction_time = datetime.datetime.now() + prediction_interval

			if quantity > 0 and order["order_action"]:
				try:
					# EXECUTE THE ORDER
					order["quantity"] = quantity
					prev_order_id = self.client.place_order(order).id
				except Exception as e:
					print("\n\n########## PLACE ORDER ERROR ##########\n%s: %s" % (type(e).__name__, e))
					if self.prompt_quit():
						break
					next_prediction_time = datetime.datetime.now()
					continue

				print("--> ORDER PLACED: %s %s shares @ $%.3f" % (order["order_action"], quantity, curr_price))

			self.print_value(curr_price)

			try:
				time.sleep(TRADING_HOURS_SLEEP)
			except KeyboardInterrupt:
				self.trading_summary(curr_price)
				if self.prompt_quit():
					break


	def print_value(self, curr_price):
		value = self.cash + curr_price * self.shares 
		print("SHARES = $%.2f, CASH = $%.2f, VALUE = $%.2f"  % (self.shares * curr_price, self.cash, value))
		return value

	def prompt_quit(self):
		print("Quit trader? (y/n)   ")
		if input("").lower() == 'y':
			#model_file = input("Save model to file:  ")
			#if model_file:
			#	self.model.save(model_file)
			#	print("@@@@@@@@@@@@@@@@@@@@@@  MODEL SAVED  @@@@@@@@@@@@@@@@@@@@@@")
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

	trading_client = TradingClient()
	trader = Trader(STOCK_TICKER, model, trading_client, INIT_CASH)

	ask_continue = input("\n**********\nCONFRIM TRADER START WITH THIS MODEL (y/n): ").lower()
	ask_continue = 'y'
	if ask_continue != 'y':
		exit(0)

	tz = pytz.timezone('US/Eastern')
	sys.stdout = Logger()

	trader.trading_loop()
