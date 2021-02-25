import datetime, pytz, holidays
import time
import sys
import yfinance as yf
import json

from model_tf import *
from data_util import *
from auth import oauth
from etrade.accounts import Accounts
from etrade.market import Market
from etrade.order import Order

tz = pytz.timezone('US/Eastern')
us_holidays = holidays.US()


# CONFIG
STOCK_TICKER = 'AMC'
TRADER_MODE = 'dev'


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

	prev_target = 0.0
	prev_trade_type = ''
	next_trade_time = datetime.datetime.now()
	while (1):
		if not is_trading_hour():
			# Update the value
			prev_trade_time = None
			value = cash + stock_quote['lastTrade'] * shares 
			#time.sleep(300)
			#continue
			pass

		order = {
			"price_type": "MARKET",
			"order_term": "GOOD_FOR_DAY",
			"symbol": stock_ticker,
			"order_action": "",
			"limit_price":"",
			"quantity": "0"
		}

		stock_quote = market.quotes(stock_ticker)
		price_target = stock_quote['lastTrade']
		print("---\nCURRENT = $%.2f" % stock_quote['lastTrade'], end=' | ')

		quantity = 0
		new_prediction = False
		if next_trade_time < datetime.datetime.now():
			# Time for a new prediction
			new_prediction = True
			price_target = get_stock_prediction(stock_ticker, model)
			print("NEW PREDICTION = $%.2f" % price_target)
			if price_target > stock_quote['lastTrade']:
				order["order_action"] = "BUY"
				quantity = int(cash // stock_quote['lastTrade'])
			else:
				order["order_action"] = "SELL"
				quantity = shares
		else:
			# Make decision based on previous prediction
			if prev_trade_type == 'BUY' and stock_quote['lastTrade'] >= prev_target:
				print("PRICE MET TARGET OF $%.2f" % prev_target)
				order["order_action"] = "SELL"
				price_target -= 1
			elif prev_trade_type == 'SELL' and stock_quote['lastTrade'] < prev_target:
				print("PRICE FELL BELOW TARGET OF $%.2f" % prev_target)
				order["order_action"] = "BUY"
				price_target += 1
			else:
				print("PRICE TARGET NOT YET MET - NO ACTION TAKEN")

		order["quantity"] = str(quantity)
		if quantity > 0 and order["order_action"]:
			# EXECUTE THE ORDER
			p_tuple = (order["order_action"], quantity, stock_quote['lastTrade'])
			print("--> %s %s shares @ $%.2f" % p_tuple)

			order_type = 1 if order["order_action"] == "BUY" else -1
			shares += quantity * order_type
			cash -= quantity * stock_quote['lastTrade'] * order_type

			prev_trade_type = order["order_action"]
			if new_prediction:
				next_trade_time = datetime.datetime.now() + datetime.timedelta(minutes=10)
			else:
				next_trade_time = datetime.datetime.now()

		# Update the value
		value = cash + stock_quote['lastTrade'] * shares 
		prev_target = price_target
		print("SHARES = %d, CASH = %.2f, VALUE = %.2f\n"  % (shares, cash, value))

		try:
			time.sleep(60)
		except KeyboardInterrupt:
			break

	print("\n\n********************* TRADING SUMMARY *********************")
	print("STARTING VALUE: $", init_cash)
	print("ENDING VALUE:   $", value)
	print("")
	r = (value/init_cash - 1) * 100
	print("TOTAL'S RETURN:   %.2f" % r)
	print("***********************************************************")



if __name__ == '__main__':
	if len(sys.argv) > 1 and sys.argv[1].isupper():
		STOCK_TICKER = sys.argv[1]
	STOCK_TICKER = STOCK_TICKER.upper()

	model, model_data = generate_model(STOCK_TICKER)
	#train_model(model, model_data)
	#eval_model(model, model_data)

	session, base_url = oauth()
	market = Market(session, base_url)
	accounts = Accounts(session, base_url)
	# Select account
	accounts.account_list()

	#ask_continue = input("\n**********\nCONFRIM TRADER START WITH THIS MODEL (Y/N): ").lower()
	ask_continue = 'y'
	if ask_continue != 'y':
		exit(0)

	trading_loop(STOCK_TICKER, model, init_cash=300.0)

	
	orders = Order(session, accounts.account, base_url)
	order = {
		"price_type": "MARKET",
		"order_term": "GOOD_FOR_DAY",
		"symbol": "ITI",
		"order_action": "BUY",
		"limit_price":"",
		"quantity": "1"
	}
	orders.place_order(order)

	
