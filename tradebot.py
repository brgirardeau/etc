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
import time

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
test_exchange_index=0
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
        self.book = book # { stock : ([(buy_price, q),...], [(sell_price, q),...]) }
        self.open_stocks = []
        self.trades = {} # {id : (trade, timestamp, success)}
        self.other_trades = [] # {"type":"trade","symbol":"SYM","price":N,"size":N}
        self.fair_value = {} # { stock : fair_value }
        self.tid = 0

    def __repr__(self):
        b = "Book: %s" % (self.book)
        c = "Cash %d" % (self.cash)
        s = "Securities %s" % (self.securities)
        o = "open_stocks %s" % (self.open_stocks)
        t = "trades %s" % (self.trades)
        ot = "other_trades %s" % (self.other_trades)
        return b + "\n" + c + "\n" + s + "\n" + o + "\n" + t + "\n" + ot

    def update(self, message):
        if message["type"] == "hello":
            self.hello(message)
        elif message["type"] == "open":
            self.open(message)
        elif message["type"] == "close":
            self.close(message)
        elif message["type"] == "error":
            self.error(message)
        elif message["type"] == "book":
            self.book_m(message)
        elif message["type"] == "trade":
            self.trade(message)
        elif message["type"] == "ack":
            self.ack(message)
        elif message["type"] == "reject":
            self.reject(message)
        elif message["type"] == "fill":
            self.fill(message)
        elif message["type"] == "out":
            self.out(message)

    def hello(self, message):
        symbols = message["symbols"]
        for sym in symbols:
            self.securities[sym.symbol] = sym.position

    def open(self, message):
        symbols = message["symbols"]
        for sym in symbols:
            self.open_stocks.append(sym)
            self.securities[sym] = 0

    def close(self, message):
        symbols = message["symbols"]
        for sym in symbols:
            self.open_stocks.remove(sym)

    def error(self, message):
        return

    def book_m(self, message):
        symbol = message["symbol"]
        buys = [(buy[0], buy[1]) for buy in message["buy"]]
        sells = [(sell[0], sell[1]) for sell in message["sell"]]
        # fair value should be right in the middle of the buy and sell price for non baskets
        if symbol in [Security.AAPL, Security.GOOG, Security.MSFT]:
            best_buy_p, bq = buys[0]
            best_sell_p, sq = sells[0]
            self.fair_value[symbol] = (best_buy_p + best_sell_p) / 2.0
        self.book[symbol] = (buys, sells)

    def trade(self, message):
        self.other_trades.append(message)

    def ack(self, message):
        order_id = message["order_id"]
        trade = self.trades[order_id]

    def reject(self, message):
        order_id = message["order_id"]
        error = message["error"]

    def fill(self, message):
        print("!!!!!!!!! FILL !!!!!!!!!!!!!")
        print(message)
        order_id = message["order_id"]
        symbol = message["symbol"]
        dire = message["dir"]
        price = message["price"]
        size = message["size"]
        if dire == "SELL":
            print(self.securities, symbol)
            self.securities[symbol] -= size
            self.cash += (price * size)
        elif dire == "BUY":
            self.securities[symbol] += size
            self.cash -= (price * size)


    def out(self, message):
        order_id = message["order_id"]
        return

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
        actions = decide_action(exchange_state)
        if actions != None:
            print("TRYING TO DO THIS: ", actions)
            for action in actions:
                write_to_exchange(exchange, action)
        exchange_msg = read_from_exchange(exchange)
        exchange_state.update(exchange_msg)
        print("Message received from exchange: ", exchange_msg, file=sys.stderr)
        print("---------------------------")
        print("ExchangeState: ")
        print(exchange_state.securities)
        print(exchange_state.cash)
        print("---------------------------")
        time.sleep(.1)

def decide_action(exchange_state):
    book = exchange_state.book
    securities = exchange_state.securities

    # Try to take advantage of people being dumb with bonds
    if Security.BOND in book:
        bond_buys, bond_sells = book[Security.BOND]
        best_bond_sell_p, best_bond_sell_q = bond_sells[0]
        best_bond_buy_p, best_bond_buy_q = bond_buys[0]

        if best_bond_sell_p < 1000:
            return [buy(Security.BOND, best_bond_sell_p, best_bond_sell_q, exchange_state)]

        if best_bond_buy_p > 1000:
            # return sell(Security.BOND, best_bond_buy_p, min(best_bond_buy_q, securities[Security.BOND]))
            return [sell(Security.BOND, best_bond_buy_p, best_bond_buy_q, exchange_state)]

    for symbol in book:
        if symbol in exchange_state.open_stocks:
            buys, sells = book[symbol]
            if (len(buys) > 0 and len(sells) > 0):
                bb, bq = buys[0]                # best buy
                bs, sq = sells[0]
                action = [buy(symbol, bb + 1, 1, exchange_state), sell(symbol, bs - 1, 1, exchange_state)]
                return action

    return None

def buy(security, price, quantity, exchange_state):
    trade_id = exchange_state.tid
    exchange_state.tid += 1
    trade = {"type": "add", "order_id": trade_id, "symbol": security, "dir": "BUY", "price": price, "size": quantity}
    exchange_state.trades[trade_id] = (trade, datetime.datetime.now(), False)
    return trade

def sell(security, price, quantity, exchange_state):
    trade_id = exchange_state.tid
    exchange_state.tid += 1
    trade = {"type": "add", "order_id": trade_id, "symbol": security, "dir": "SELL", "price": price, "size": quantity}
    exchange_state.trades[trade_id] = (trade, datetime.datetime.now(), False)

    return trade



if __name__ == "__main__":
    main()