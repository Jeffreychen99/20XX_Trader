import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import sys
import matplotlib.pyplot as plt

import warnings
warnings.filterwarnings('ignore')

from config_20XX import *
from data_util import *



dtype = torch.float32
if USE_GPU and torch.cuda.is_available():
	device = torch.device('cuda')
else:
	device = torch.device('cpu')

# Custom Flatten layer 
class Flatten(nn.Module):
	def forward(self, x):
		N = x.shape[0] # read in N, C, H, W
		x_new = x.view(N, -1)
		return x.view(N, -1)  # "flatten" the C * H * W values into a single vector per image

# Custom LSTM layer 
class nnLSTM(nn.Module):
	def __init__(self, input_size, hidden_size, num_layers=1, bias=True):
		super().__init__()
		self.lstm = nn.LSTM(input_size, hidden_size, num_layers, bias)

	def forward(self, x):
		out, (h_n, c_n) = self.lstm.forward(x)
		return out

def elliptic_paraboloid_loss(x, y):
    # Compute a rotated elliptic parabaloid.
    t = np.pi / 4
    x_rot = (x * np.cos(t)) + (y * np.sin(t))
    y_rot = (x * -np.sin(t)) + (y * np.cos(t))
    z = ((x_rot**2) / C_DIFF_SIGN) + ((y_rot**2) / C_SAME_SIGN)
    return z

class EllipticParaboloidLoss(nn.Module):
	def forward(self, x, y):
	    # Compute a rotated elliptic parabaloid.
	    t = np.pi / 4
	    x_rot = (x * np.cos(t)) + (y * np.sin(t))
	    y_rot = (x * -np.sin(t)) + (y * np.cos(t))
	    z = ((x_rot**2) / C_DIFF_SIGN) + ((y_rot**2) / C_SAME_SIGN)
	    return z



# Create the model
def generate_model(stock_ticker):
	stock_raw, stock_dat, stock_labels = model_stock_data(stock_ticker)
	model_data = partition_data(TRAINING_SET_THRESH, stock_dat, stock_labels)
	training_x, training_y, validation_x, validation_y = model_data

	############## THE MODEL ##############
	model = nn.Sequential(
		nnLSTM(input_size=NUM_FEATURES, hidden_size=8, num_layers=1, bias=True),
		#nnLSTM(input_size=8, hidden_size=16, bias=True),

		Flatten(),
		#nn.Linear(320, 256), nn.ReLU(),
		#nn.Linear(256, 128), nn.ReLU(),
		#nn.Linear(128, 64), nn.ReLU(),
		#nn.Linear(64, 32), nn.ReLU(),
		nn.Linear(80, 160), nn.Tanh(),
		nn.Linear(160, 64), nn.ReLU(),
		nn.Linear(64, 32), nn.Tanh(),
		nn.Linear(32, 16), nn.ReLU(),
		nn.Linear(16, 1, bias=False)
	)

	return model, model_data


# Optimizer for the model
def get_optimizer(model):
	optimizer = optim.SGD(model.parameters(), lr=LEARNING_RATE, momentum=MOMENTUM, nesterov=True)
	return optimizer


# Train the model (and validate)
def train_model(model, optimizer, model_data, loss_module=nn.L1Loss):
	loss_func = loss_module()
	training_x, training_y, validation_x, validation_y = model_data

	training_dset, training_loader = get_dataset_and_loader(training_x, training_y)
	validation_dset, validation_loader = get_dataset_and_loader(validation_x, validation_y)

	model = model.to(device=device)
	train_accs = []
	val_losses = []
	for e in range(MAX_EPOCHS):
		for t, (x, y) in enumerate(training_loader):
			model.train()  # put model to training mode
			x = x.to(device=device, dtype=dtype)
			y = y.to(device=device, dtype=torch.long)
			scores = model(x)
			loss = loss_func(scores, y)

			optimizer.zero_grad()
			loss.backward()
			optimizer.step()

			if t % PRINT_EVERY == 0:
				print('Iteration %d, loss = %.4f' % (t, loss.item()))

		val_loss = check_accuracy(validation_loader, model, loss_module)
		val_losses.append(val_loss)
		print("--> EPOCH %d AVG_LOSS = %.4f\n" % (e, val_loss))
		if val_loss < 0.05:
			break
	return val_losses
		
def check_accuracy(loader, model, loss_module=nn.L1Loss):
	loss_func = loss_module()
	num_samples = 0
	total_loss = 0.0
	avg_loss = 0.0
	model.eval()
	with torch.no_grad():
		for x, y in loader:
			x = x.to(device=device, dtype=dtype)
			y = y.to(device=device, dtype=torch.long)
			predictions = model(x)
			loss = loss_func(predictions, y)
			if loss > 2:
				print(loss)
			total_loss += loss_func(predictions, y)
			num_samples += 1
		avg_loss = total_loss / num_samples
	return avg_loss


# Run `python3 model.py TICKER` to see how it measures up against validation data
if __name__ == '__main__':
	if len(sys.argv) < 2:
		print('ERROR: Need to specify a ticker')
		exit(1)

	stock_ticker = sys.argv[1]

	model, model_data = generate_model(stock_ticker)
	optimizer = get_optimizer(model)
	train_model(model, optimizer, model_data, loss_module=EllipticParaboloidLoss)

	training_x, training_y, validation_x, validation_y = model_data
	validation_dset, validation_loader = get_dataset_and_loader(validation_x, validation_y)

	v_predict = [model(x)[0][0].item() for x, y in validation_loader]
	indices = list(range(len(v_predict)))

	buys, sells = [0, 0], [0, 0]
	all_trades = [buys, sells]

	for i in range(len(v_predict)):
		trade_type = int(v_predict[i] <= 0)
		trade_result = int(v_predict[i] * validation_y[i] >= 0)
		all_trades[trade_type][trade_result] += 1
				
	print("")
	print("CORRECT BUYS:  %d  |  WRONG BUYS:    %d" % (buys[1], buys[0]))
	print("CORRECT SELLS: %d  |  WRONG SELLS:   %d" % (sells[1], sells[0]))

	plt.title(stock_ticker + " Stock Prediction")
	ax = plt.axes()
	ax.set_xlabel("Time")
	ax.set_ylabel("Price Deviation")
	plt.plot(indices, [y for y in v_predict], 'b-', marker='.', label='Predict')
	plt.plot(indices, [y[0] for y in validation_y], 'r-', marker='.', label='Actual')
	plt.plot(indices, [0 for _ in v_predict], 'k-')
	plt.legend()
	plt.show()