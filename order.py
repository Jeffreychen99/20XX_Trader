from config_20XX import *

# Should not directly use the Order class
class Order:
	def __init__(self, symbol, action, qty=0):
		self.symbol = symbol.upper()
		self.action = action.upper()
		self.qty = qty
		self.filled_qty = 0
		self.active = False

	def validate(self):
		assert type(self.qty) == float or type(self.qty) == int
		assert self.action == "BUY" or self.action == "SELL"

	def is_filled(self, client):
		if self.filled_qty == self.qty:
			return True

		prev_filled_shares = self.filled_qty
		order_info = client.get_order_info(self.id)
		self.filled_qty = order_info['filled_qty']
		self.avg_price = order_info['avg_price'] if self.price_type == "MARKET" else self.limit_price

		if self.active:
			s = (self.action, self.filled_qty, self.qty, self.avg_price)
			if self.filled_qty == self.qty:
				print("--> ORDER FILLED: %s %s/%s shares @ avg price $%.2f" % s)
			else:
				print("--> ORDER NOT YET FILLED: %s %s/%s shares @ avg price $%.2f" % s)

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
		self.active = True
		print("--> ORDER PLACED: %s %s shares " % (self.action, self.qty), end='')
		if isinstance(self, MarketOrder):
			print("@ Market price")
		elif isinstance(self, LimitOrder):
			print("@ $%.2f" % self.limit_price)
		return self.id

	def cancel(self, client):
		client.cancel_order(self.id)
		self.active = False
		print("--> ORDER CANCELLED: %s %s shares " % (self.action, self.qty))




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
