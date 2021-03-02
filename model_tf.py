import os
import sys
import numpy as np
import tensorflow as tf
kb = tf.keras.backend
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import matplotlib.pyplot as plt

from config_20XX import *

import warnings
warnings.filterwarnings('ignore')

from data_util import *

np.random.seed(150)



# Custom loss function to reward correct sign
def elliptic_paraboloid_loss(x, y):
    # Compute a rotated elliptic parabaloid.
    r = np.pi / 4
    x_rot = (x * np.cos(r)) + (y * np.sin(r))
    y_rot = (x * -np.sin(r)) + (y * np.cos(r))
    z = ((x_rot**2) / C_DIFF_SIGN) + ((y_rot**2) / C_SAME_SIGN)
    return z


# Create the model
def generate_model(input_shape):
	# Model definition
	l1 = tf.keras.regularizers.l1
	l2 = tf.keras.regularizers.l2
	model = tf.keras.models.Sequential([
	    # Shape [batch, time, features] => [batch, time, lstm_units]
	    tf.keras.layers.LSTM(4, input_shape=input_shape, return_sequences=True, activation='relu'),
	    tf.keras.layers.LSTM(8, input_shape=input_shape, return_sequences=True, activation='tanh'),
	    tf.keras.layers.LSTM(16, input_shape=input_shape, return_sequences=True, activation='tanh'),
	    tf.keras.layers.LSTM(32, input_shape=input_shape, return_sequences=False, activation='relu'),
	    #tf.keras.layers.Dense(7, input_shape=frame_shape),
	    tf.keras.layers.Dense(units=256, activation='relu'),
	    tf.keras.layers.Dropout(0.25),
	    tf.keras.layers.Dense(units=128, activation='softmax'),
	    tf.keras.layers.Dense(units=64, activation='relu', kernel_regularizer=l2(0.05)),
	    tf.keras.layers.Dense(units=32, activation='tanh', kernel_regularizer=l2(0.05)),
	    tf.keras.layers.Dense(units=16, activation='relu', kernel_regularizer=l2(0.05)),
	    tf.keras.layers.Dense(units=8, activation='relu', kernel_regularizer=l2(0.05)),
	    tf.keras.layers.Dense(units=1)
	])

	early_stopping = tf.keras.callbacks.EarlyStopping(monitor='val_loss',
	                                                    patience=PATIENCE,
	                                                    mode='min')

	model.compile(loss=elliptic_paraboloid_loss,
	                optimizer=tf.optimizers.Adam(),
	                metrics=[elliptic_paraboloid_loss])

	return model


# Train the model (and validate)
def train_model(model, train_x, train_y, val_x, val_y):
	print("************** TRAINING MODEL **************")
	model.fit(train_x, train_y, epochs=MAX_EPOCHS, validation_data=(val_x, val_y))

# Evaluate model
def eval_model(stock_ticker, model, test_x, test_y, display=False):
	test_predict = model.predict(test_x)
	indices = list(range(len(test_predict)))

	buys, sells = [0, 0], [0, 0]
	all_trades = [buys, sells]

	for i in range(len(test_predict)):
		trade_type = int(test_predict[i] <= 0)
		trade_result = int(test_predict[i] * test_y[i] >= 0)
		all_trades[trade_type][trade_result] += 1
	            
	print("")
	print("CORRECT BUYS:  %d  |  WRONG BUYS:    %d" % (buys[1], buys[0]))
	print("CORRECT SELLS: %d  |  WRONG SELLS:   %d" % (sells[1], sells[0]))

	if display:
		plt.title(stock_ticker + " Stock Prediction")
		ax = plt.axes()
		ax.set_xlabel("Time")
		ax.set_ylabel("Price Deviation")
		plt.plot(indices, [y[0] for y in test_predict], 'b-', marker='.', label='Predict')
		plt.plot(indices, [y[0] for y in test_y], 'r-', marker='.', label='Actual')
		plt.plot(indices, [0 for _ in test_predict], 'k-')
		plt.legend()
		plt.show()



# Run `python3 model.py` to see how it measures up against validation data
if __name__ == '__main__':

	if len(sys.argv) < 2:
		print('ERROR: Need to specify a ticker')
		exit(1)

	stock_ticker = sys.argv[1]

	stock_raw, stock_dat, stock_labels = model_stock_data(stock_ticker)
	train_x, train_y, test_x, test_y = partition_data(TRAINING_SET_THRESH, stock_dat, stock_labels)
	train_x, train_y, val_x, val_y = partition_data(TRAINING_SET_THRESH, train_x, train_y)
	input_frame_shape = (stock_dat.shape[1], stock_dat.shape[2])

	model = generate_model(input_frame_shape)
	train_model(model, train_x, train_y, val_x, val_y)

	eval_model(stock_ticker, model, test_x, test_y, display=True)