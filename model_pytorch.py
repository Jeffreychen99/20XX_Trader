import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import sys
import matplotlib.pyplot as plt

import warnings
warnings.filterwarnings('ignore')

from config_20XX import *
from data_util import *


list_to_device = lambda th_obj: [tensor.to(device) for tensor in th_obj]
device = th.device("cuda" if th.cuda.is_available() else "cpu")

class EllipticParaboloidLoss(nn.Module):
	def forward(self, x, y):
		# Compute a rotated elliptic parabaloid.
		t = np.pi / 4
		x_rot = (x * np.cos(t)) + (y * np.sin(t))
		y_rot = (x * -np.sin(t)) + (y * np.cos(t))
		z = ((x_rot**2) / C_DIFF_SIGN) + ((y_rot**2) / C_SAME_SIGN)
		return z

# Custom Flatten layer 
class Flatten(nn.Module):
	def forward(self, x):
		return th.flatten(x, -2, -1)

# Custom LSTM layer 
class nnLSTM(nn.Module):
	def __init__(self, input_size, hidden_size, num_layers=1, bias=True, batch_first=True, dropout=0.0):
		super().__init__()
		self.lstm = nn.LSTM(input_size, hidden_size, num_layers, bias, batch_first, dropout)

	def forward(self, x):
		out, (h_n, c_n) = self.lstm.forward(x)
		return out

# Create the model
def generate_model(input_shape, dropout=0.0):
	model = nn.Sequential(
		nnLSTM(input_shape[1], 4, num_layers=1, batch_first=True), nn.ReLU(),
		nnLSTM(4, 8, num_layers=1, batch_first=True), nn.Tanh(),
		nnLSTM(8, 16, num_layers=1, batch_first=True), nn.Tanh(),
		nnLSTM(16, 32, num_layers=1, batch_first=True), nn.ReLU(),

		Flatten(),
		nn.Linear(32 * POINTS_PER_PERIOD, 256), nn.ReLU(),
		nn.Dropout(0.25),
		nn.Linear(256, 128), nn.Softmax(),
		nn.Linear(128, 64), nn.ReLU(),
		nn.Linear(64, 32), nn.Tanh(),
		nn.Linear(32, 16), nn.ReLU(),
		nn.Linear(16, 8), nn.ReLU(),
		nn.Linear(8, 1)
	)
	return model


# Optimizer for the model
def get_optimizer(model):
	optimizer = optim.SGD(model.parameters(), lr=LEARNING_RATE, momentum=MOMENTUM, nesterov=True)
	return optimizer


# Train the model (and validate)
def train_model(model, optimizer, train_x, train_y, val_x, val_y, loss_module=nn.L1Loss):
	print("************** TRAINING MODEL **************")
	loss_fn = loss_module()
	losses = []
	for epoch in range(EPOCHS):
		indices = np.random.permutation(range(len(train_x)))
		t = range(0,(len(train_x)//BATCH_SIZE)+1)
		print("---")
		for i in t:
			batch_input = train_x[ indices[i*BATCH_SIZE:(i+1)*BATCH_SIZE] ]
			batch_target = train_y[ indices[i*BATCH_SIZE:(i+1)*BATCH_SIZE] ]
			model.to(device)
			
			prediction = model(batch_input)
			loss = loss_fn(prediction, batch_target)
			losses.append(loss.mean().item())

			model.zero_grad()
			loss.sum().backward()
			optimizer.step()
			
			if i == 0:
				print( f"Epoch: {epoch} Loss: {np.mean(losses[-10:])}" )


# Evaluate model
def eval_model(stock_ticker, model, test_x, test_y, display=False):
	predict = [model(th.unsqueeze(x, 0))[0][0].item() for x in test_x]
	indices = list(range(len(predict)))

	buys, sells = [0, 0], [0, 0]
	all_trades = [buys, sells]

	for i in range(len(predict)):
		trade_type = int(predict[i] <= 0)
		trade_result = int(predict[i] * test_y[i] >= 0)
		all_trades[trade_type][trade_result] += 1
				
	print("")
	print("CORRECT BUYS:  %d  |  WRONG BUYS:    %d" % (buys[1], buys[0]))
	print("CORRECT SELLS: %d  |  WRONG SELLS:   %d" % (sells[1], sells[0]))

	plt.title(stock_ticker + " Stock Prediction")
	ax = plt.axes()
	ax.set_xlabel("Time")
	ax.set_ylabel("Price Deviation")
	plt.plot(indices, [y for y in predict], 'b-', marker='.', label='Predict')
	plt.plot(indices, [y[0] for y in test_y], 'r-', marker='.', label='Actual')
	plt.plot(indices, [0 for _ in predict], 'k-')
	plt.legend()
	plt.show()


# Run `python3 model.py TICKER` to see how it measures up against validation data
if __name__ == '__main__':
	if len(sys.argv) < 2:
		print('ERROR: Need to specify a ticker')
		exit(1)

	stock_ticker = sys.argv[1]

	stock_raw, stock_dat, stock_labels = model_stock_data(stock_ticker)
	stock_dat = th.from_numpy(stock_dat).float()
	stock_labels = th.from_numpy(stock_labels).float()

	train_x, train_y, test_x, test_y = partition_data(TRAINING_SET_THRESH, stock_dat, stock_labels)
	train_x, train_y, val_x, val_y = partition_data(TRAINING_SET_THRESH, train_x, train_y)
	input_frame_shape = (stock_dat.shape[1], stock_dat.shape[2])

	model = generate_model(input_frame_shape)
	optimizer = get_optimizer(model)
	train_model(model, optimizer, train_x, train_y, val_x, val_y, loss_module=EllipticParaboloidLoss)

	eval_model(stock_ticker, model, test_x, test_y, display=True)
