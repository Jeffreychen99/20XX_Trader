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



session, base_url = None, None
accounts, market = None, None

def is_trading_hour(now=None):
		if not now:
			now = datetime.datetime.now(tz)
		openTime = datetime.time(hour=9, minute=45, second=0)
		closeTime = datetime.time(hour=15, minute=45, second=0)
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

def get_stock_prediction(stock_ticker, model):
	# Pull the most recent stock data 
	stock_raw, stock_dat = recent_stock_data(stock_ticker)
	stock_predict = model.predict(stock_dat)
	stock_predict = unnormalize_data(stock_raw, stock_predict, [[0]])[0]
	return stock_predict[0][0]


def trading_loop(stock_ticker, model, init_cash=300.0):
	cash, shares = init_cash, 0
	value = cash

	total_trades = 0
	buys, sells = [0, 0], [0, 0]

	stock_quote = market.quotes(stock_ticker)
	last_trade_time = None
	last_trade_value = stock_quote['lastTrade']

	orders = Order(session, accounts.account, base_url)

	prev_target = None
	prev_trade_type = ''
	next_prediction_time = datetime.datetime.now()
	while (1):

		order = {
			"price_type": "MARKET",
			"order_term": "GOOD_FOR_DAY",
			"symbol": stock_ticker,
			"order_action": "",
			"limit_price":"",
			"quantity": "0"
		}

		stock_quote = market.quotes(stock_ticker)
		if not stock_quote:
			# Error with the API - retry
			continue
		curr_price = stock_quote['lastTrade']
		price_target = stock_quote['lastTrade']

		if not is_trading_hour():
			print("---\n%s" % datetime.datetime.now(tz).strftime("%H:%M,  %m/%d/%Y"))
			print("AFTER HOURS TRADING - NO ACTION")
			print("SHARES = $%.2f, CASH = $%.2f, VALUE = $%.2f\n"  % (shares * curr_price, cash, value))
			value = cash + stock_quote['lastTrade'] * shares 
			try:
				time.sleep(AFTER_HOURS_SLEEP)
			except KeyboardInterrupt:
				break
			continue

		print("---\n%s" % datetime.datetime.now(tz).strftime("%H:%M,  %m/%d/%Y"))
		print("CURRENT = $%.2f" % curr_price)

		# Make decision based on previous prediction
		if prev_trade_type == 'BUY' and curr_price >= prev_target:
			print("PRICE ROSE ABOVE TARGET OF $%.2f" % prev_target, end=' | ')
			next_prediction_time = datetime.datetime.now()
		elif prev_trade_type == 'SELL' and curr_price < prev_target:
			print("PRICE FELL BELOW TARGET OF $%.2f" % prev_target, end=' | ')
			next_prediction_time = datetime.datetime.now()
		elif prev_target:
			print("PRICE TARGET $%.2f NOT YET MET" % prev_target)

		quantity = 0
		if next_prediction_time < datetime.datetime.now():
			# Make a new prediction for the stock
			price_target = get_stock_prediction(stock_ticker, model)
			print("NEW PREDICTION = $%.2f" % price_target)
			if price_target > curr_price:
				order["order_action"] = "BUY"
				quantity = int(cash // curr_price)
			else:
				order["order_action"] = "SELL"
				quantity = shares

		if quantity > 0 and order["order_action"]:
			# EXECUTE THE ORDER
			order["quantity"] = str(quantity)
			#############################
			##### DO THE ORDER HERE #####
			#############################
			print("--> %s %s shares @ $%.2f" % (order["order_action"], quantity, curr_price))

			order_type = 1 if order["order_action"] == "BUY" else -1
			shares += quantity * order_type
			cash -= quantity * curr_price * order_type
 
			prev_target = price_target
			prev_trade_type = order["order_action"]

			prediction_interval = datetime.timedelta(seconds=PREDICTION_INTERVAL)
			next_prediction_time = datetime.datetime.now() + prediction_interval

		# Update the value
		value = cash + curr_price * shares
		print("SHARES = $%.2f, CASH = $%.2f, VALUE = $%.2f"  % (shares * curr_price, cash, value))

		try:
			time.sleep(TRADING_HOURS_SLEEP)
		except KeyboardInterrupt:
			break

	print("\n\n********************* TRADING SUMMARY *********************")
	print("STARTING VALUE:  $%.2f" % init_cash)
	print("ENDING VALUE:    $%.2f" % value)
	print("")
	r = (value/init_cash - 1) * 100
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

	session, base_url = oauth()
	market = Market(session, base_url)
	accounts = Accounts(session, base_url)

	# Select account
	accounts.account_list()

	ask_continue = input("\n**********\nCONFRIM TRADER START WITH THIS MODEL (y/n): ").lower()
	ask_continue = 'y'
	if ask_continue != 'y':
		exit(0)

	trading_loop(STOCK_TICKER, model, init_cash=INIT_CASH)

	
	orders = Order(session, accounts.account, base_url)
	order = {
		"price_type": "MARKET",
		"order_term": "GOOD_FOR_DAY",
		"symbol": "ITI",
		"order_action": "BUY",
		"limit_price":"",
		"quantity": "1"
	}
	#orders.place_order(order)

	
