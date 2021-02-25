import datetime
import yfinance as yf
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from torch.utils.data import Dataset
from torch.utils.data import sampler

import warnings
warnings.filterwarnings('ignore')

np.random.seed(150)


# Data params
NUM_FEATURES = 4
NUM_WEEKS = 3
UNITS = 'm'
INTERVAL_UNITS = 1
INTERVAL = str(INTERVAL_UNITS) + UNITS
POINTS_PER_PERIOD = 10
LABEL_FUNC = np.mean


class StockDataset(Dataset):
    def __init__(self, data, labels, transform=None):
        self.data = torch.from_numpy(data).float()
        self.target = torch.from_numpy(labels).long()
        self.transform = transform
        
    def __getitem__(self, index):
        x = self.data[index]
        y = self.target[index]
        
        if self.transform:
            x = self.transform(x)
        
        return x, y
    
    def __len__(self):
        return len(self.data)


# Turn numpy arrays into pytorch dataset and loader
def get_dataset_and_loader(data, labels):
    dataset = StockDataset(data, labels)
    n = len(data)
    loader = DataLoader(dataset, sampler=sampler.SubsetRandomSampler(range(n)))
    return dataset, loader


# Data cleaning
def clean_data(stock_raw):
    r = len(stock_raw) % POINTS_PER_PERIOD
    for _ in range(r):
        stock_raw = np.delete(stock_raw, 0, 0)
    dat_shape = (len(stock_raw) // POINTS_PER_PERIOD, POINTS_PER_PERIOD, stock_raw.shape[1])

    stock_dat = np.ndarray(shape=dat_shape, dtype=np.float64)
    stock_labels = np.zeros(shape=(dat_shape[0], 1))
    for i in range(len(stock_raw)):
        r, t = i // POINTS_PER_PERIOD, i % POINTS_PER_PERIOD
        stock_dat[r][t] = stock_raw[i]
    for i in range(dat_shape[0] - 1):
        stock_labels[i] = LABEL_FUNC(stock_dat[i + 1])
        
    if dat_shape[0] > 1:
        stock_dat = stock_dat[:-1]
        stock_labels = stock_labels[:-1]
    return stock_dat, stock_labels


# Normalize the data
def normalize_data(stock_dat, stock_labels):
    for r in range(len(stock_dat)):
        curr = stock_dat[r]
        o = curr[0][0]
        open_stdev = np.sqrt( np.sum(np.vectorize(lambda x: (x-o)**2)(curr))/(curr.size) )
        stock_labels[r][0] = (stock_labels[r][0] - o) / open_stdev
        stock_dat[r] = (curr - o) / open_stdev
    return stock_dat


# Unnormalize the data (for prediction purposes)
def unnormalize_data(stock_raw, stock_dat, stock_labels):
    for r in range(len(stock_raw)):
        curr = stock_raw[r]
        o = curr[0][0]
        open_stdev = np.sqrt( np.sum(np.vectorize(lambda x: (x-o)**2)(curr))/(curr.size) )
        stock_labels[r][0] = stock_labels[r][0] * open_stdev + o
        stock_dat[r] = stock_dat[r] * open_stdev + o
    return stock_dat, stock_labels


# Pull the data in
def model_stock_data(stock_ticker):
    stock = yf.Ticker(stock_ticker)
    stock_raw = np.ndarray(shape=(0, NUM_FEATURES))

    wk_end = datetime.datetime.now()
    wk_start = wk_end - datetime.timedelta(days=7)
    for _ in range(NUM_WEEKS):
        stock_df = stock.history(period='7d', interval=INTERVAL, start=wk_start, end=wk_end)
        stock_raw_week = stock_df.to_numpy()[:,:NUM_FEATURES]
        stock_raw = np.concatenate([stock_raw_week, stock_raw])
        
        wk_end, wk_start = wk_start, wk_start - datetime.timedelta(days=7)

    # Format data
    stock_raw, stock_labels = clean_data(stock_raw)
    stock_dat = normalize_data(np.array(stock_raw, copy=True), stock_labels)

    return stock_raw, stock_dat, stock_labels


# Get last interval of data
def recent_stock_data(stock_ticker):
    stock = yf.Ticker(stock_ticker)
    stock_raw = np.ndarray(shape=(0, NUM_FEATURES))

    period = str(2 * POINTS_PER_PERIOD - 1) + UNITS
    stock_df = stock.history(period=period, interval=INTERVAL)
    stock_raw = stock_df.to_numpy()[:,:NUM_FEATURES]

    # Format data
    stock_raw, _ = clean_data(stock_raw)
    stock_dat = normalize_data(np.array(stock_raw, copy=True), [[0]])

    return stock_raw, stock_dat


# Separate training and validation data
def partition_data(thresh, stock_dat, stock_labels):
    split = int(stock_dat.shape[0] * thresh)
    training_x = stock_dat[:split]
    training_y = stock_labels[:split]
    validation_x = stock_dat[split:]
    validation_y = stock_labels[split:]

    return training_x, training_y, validation_x, validation_y