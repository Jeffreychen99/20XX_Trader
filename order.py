# Should not directly use the Order class
class Order:
	def __init__(self, symbol, qty=0):
		self.symbol = symbol.upper()
		self.qty = qty
		self.filled_qty = 0

	def validate(self):
		assert type(self.qty) == float or type(self.qty) == int

		assert hasattr(self, "action")
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



class BuyOrder(Order):
	action = "BUY"

class SellOrder(Order):
	action = "SELL"


class MarketOrder(Order):
	price_type = "MARKET"

class LimitOrder(Order):
	price_type = "LIMIT"

	def __init__(self, symbol, limit_price, qty=0):
		super().__init__(symbol, qty)
		self.limit_price = limit_price

	def validate(self):
		super().validate()
		assert type(self.limit_price) == float or type(self.limit_price) == int
		assert self.limit_price > 0.0 

	def dict(self):
		order = super().dict()
		order["limit_price"] = self.limit_price
		return order



# Dynamic inheritance function
def newOrder(symbol, order_action_class, price_type_class, limit_price=0.0, qty=0):
	class DynamicOrder(order_action_class, price_type_class):
		pass
	order = DynamicOrder(symbol, qty) if price_type_class != LimitOrder else DynamicOrder(symbol, limit_price, qty)
	return order
