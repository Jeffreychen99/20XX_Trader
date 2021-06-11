from config_20XX import *

# Should not directly use the Order class
class Order:
	def __init__(self, symbol, action, qty=0):
		self.symbol = symbol.upper()
		self.action = action.upper()
		self.qty = qty
		self.filled_qty = 0

	def validate(self):
		assert type(self.qty) == float or type(self.qty) == int
		assert self.action == "BUY" or self.action == "SELL"

	def is_filled(self):
		return self.filled_qty == self.qty

	def dict(self):
		self.validate()
		order = {
			"price_type": self.price_type,
			"symbol": self.symbol,
			"action": self.action,
			"qty": self.qty
		}
		return order

	def place(self, client):
		self.id = client.place_order(self.dict()).id
		return self.id



class MarketOrder(Order):
	def __init__(self, symbol, action, qty=0):
		super().__init__(symbol, action, qty)
		self.price_type = "MARKET"



class LimitOrder(Order):
	def __init__(self, symbol, action, limit_price, qty=0):
		super().__init__(symbol, action, qty)
		self.price_type = "LIMIT"
		self.limit_price = limit_price

	def validate(self):
		super().validate()
		assert 	type(self.limit_price) == float or type(self.limit_price) == int

	def dict(self):
		order = super().dict()
		order["limit_price"] = self.limit_price
		return order
