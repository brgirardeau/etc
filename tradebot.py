#!/usr/bin/python

# ~~~~~==============   HOW TO RUN   ==============~~~~~
# 1) Configure things in CONFIGURATION section
# 2) Change permissions: chmod +x bot.py
# 3) Run in loop: while true; do ./bot.py; sleep 1; done

from __future__ import print_function
from enum import Enum

import sys
import socket
import json
import uuid
import datetime

# ~~~~~============== CONFIGURATION  ==============~~~~~
# replace REPLACEME with your team name!
team_name="TEAMBARN"
# This variable dictates whether or not the bot is connecting to the prod
# or test exchange. Be careful with this switch!
test_mode = True

# This setting changes which test exchange is connected to.
# 0 is prod-like
# 1 is slower
# 2 is empty
test_exchange_index=2
prod_exchange_hostname="production"

port=25000 + (test_exchange_index if test_mode else 0)
exchange_hostname = "test-exch-" + team_name if test_mode else prod_exchange_hostname

# ~~~~~============== NETWORKING CODE ==============~~~~~
def connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((exchange_hostname, port))
    return s.makefile('rw', 1)

def write_to_exchange(exchange, obj):
    json.dump(obj, exchange)
    exchange.write("\n")

def read_from_exchange(exchange):
    return json.loads(exchange.readline())

# ~~~~~============== HELPFUL CLASS STUFF ==============~~~~~
class Security(Enum):
    BOND = "BOND"
    BABZ = "BABZ"
    BABA = "BABA"
    AAPL = "AAPL"
    MSFT = "MSFT"
    GOOG = "GOOG"
    XLK = "XLK"

class ExchangeState:
    def __init__(self, cash=0, securities={}, book={}):
        self.cash = cash
        self.securities = securities # { security : amount_owned }
        self.book = book # { stock : ((best_buy_price, best_buy_quantity), (best_sell_price, best_sell_quantity)) }
        self.open_stocks = []
        self.order_ids = []

    def __repr__(self):
        return "Book: %s" % (self.book), "Cash %d" % (self.cash), "Securities %s" % (self.securities)

    def update(self, message):
        if message.type == "hello":
            self.hello(message)
        elif message.type == "open":
            self.open(message)
        elif message.type == "close":
            self.close(message)
        elif message.type == "error":
            self.error(message)
        elif message.type == "book":
            self.book(message)
        elif message.type == "trade":
            self.trade(message)
        elif message.type == "ack":
            self.ack(message)
        elif message.type == "reject":
            self.reject(message)
        elif message.type == "fill":
            self.fill(message)
        elif message.type == "out":
            self.out(message)

    def hello(self, message):
        symbols = message["symbols"]
        for sym in symbols:
            self.securities[sym.symbol] = sym.position

    def ack(self, message):
        order_id = message["order_id"]
        self.book
        trades[order_id][2] = True

    def reject(self, message):
        order_id = message["order_id"]
        error = message["error"]

        
    def fill(self, message):
        order_id = message["order_id"]
        symbol = message["symbol"]
        dire = message["dir"]
        price = message["price"]
        size = message["size"]

    def out(self, message):
        order_id = message["order_id"]
        self.order_ids.append((order_id, datetime.now()))


trades = {} # {id : (trade, timestamp)}
# ~~~~~============== MAIN LOOP ==============~~~~~

def main():
    exchange = connect()
    write_to_exchange(exchange, {"type": "hello", "team": team_name.upper()})
    hello_from_exchange = read_from_exchange(exchange)
    # A common mistake people make is to call write_to_exchange() > 1
    # time for every read_from_exchange() response.
    # Since many write messages generate marketdata, this will cause an
    # exponential explosion in pending messages. Please, don't do that!
    print("The exchange replied:", hello_from_exchange, file=sys.stderr)

    # important game state variables
    exchange_state = ExchangeState()
    while True:
        action = decide_action(exchange_state)
        if action != None:
            write_to_exchange(action)
        exchange_msg = read_from_exchange(exchange)
        exchange_state.update(exchange_msg)
        print("Message received from exchange:", exchange_msg, file=sys.stderr)

def decide_action(exchange_state):
    book = exchange_state.book
    securities = exchange_state.securities

    # Try to take advantage of people being dumb with bonds
    if Security.BOND in book:
        (best_bond_buy_p, best_bond_buy_q), (best_bond_sell_p, best_bond_sell_q) = book[Security.BOND]
        if best_bond_sell_p < 1000:
            return buy(Security.BOND, best_bond_sell_p, best_bond_sell_q)

        if best_bond_buy_p > 1000:
            # return sell(Security.BOND, best_bond_buy_p, min(best_bond_buy_q, securities[Security.BOND]))
            return sell(Security.BOND, best_bond_buy_p, best_bond_buy_q)
    return None

def buy(security, price, quantity):
    trade_id = uuid.uuid4()
    trade = {"type": "add", "order_id": trade_id, "symbol": security, "dir": "BUY", "price": price, "size": quantity}
    trades[trade_id] = (trade, datetime.now())
    return trade + "\n"

def sell(security, price, quantity):
    trade_id = uuid.uuid4()
    trade = {"type": "add", "order_id": trade_id, "symbol": security, "dir": "SELL", "price": price, "size": quantity}
    trades[trade_id] = (trade, datetime.now())

    return trade + "\n"



if __name__ == "__main__":
    main()