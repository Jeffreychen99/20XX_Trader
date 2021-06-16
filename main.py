import argparse
import datetime
import pytz
import sys

from order import *
from trader import *
from alpaca.client import TradingClient

from config_20XX import *

if MODEL_TYPE == 'TF':
	from model_tf import *
elif MODEL_TYPE == 'TORCH':
	from model_pytorch import *
from data_util import *



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