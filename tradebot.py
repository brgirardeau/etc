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
import math

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
test_exchange_index=1
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
class Security:
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

    def error(self, message):
        return

    def book_m(self, message):
        symbol = message["symbol"]
        buys = [(buy[0], buy[1]) for buy in message["buy"]]
        sells = [(sell[0], sell[1]) for sell in message["sell"]]
        # fair value should be right in the middle of the buy and sell price for non baskets
        if (len(buys) > 0 and len(sells) > 0):
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
            print(self.securities, symbol, self.fair_value)
            self.securities[symbol] -= size
            self.cash -= ((-1 * price * size) + self.fair_value[symbol] * size)
        elif dire == "BUY":
            self.securities[symbol] += size
            self.cash += ((-1 * price * size) + self.fair_value[symbol] * size)

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
        time.sleep(.05)

def decide_action(exchange_state):
    book = exchange_state.book
    securities = exchange_state.securities

    actions = []
    # Try to take advantage of people being dumb with bonds
    if Security.BOND in book:
        bond_buys, bond_sells = book[Security.BOND]
        if len(bond_sells) > 0 and len(bond_buys) > 0:
            best_bond_sell_p, best_bond_sell_q = bond_sells[0]
            best_bond_buy_p, best_bond_buy_q = bond_buys[0]

            if best_bond_sell_p < 1000:
                actions.append(buy(Security.BOND, best_bond_sell_p, best_bond_sell_q, exchange_state))

            if best_bond_buy_p > 1000:
                # return sell(Security.BOND, best_bond_buy_p, min(best_bond_buy_q, securities[Security.BOND]))
                actions.append(sell(Security.BOND, best_bond_buy_p, best_bond_buy_q, exchange_state))

    fair_value = exchange_state.fair_value
    # print(fair_value)
    # print(Security.AAPL)
    # print(Security.AAPL in fair_value)
    # time.sleep(1)
    if (Security.AAPL in fair_value.keys() and Security.MSFT in fair_value.keys() and Security.GOOG in fair_value.keys()):
        xlk_fmv_theory = (3000 + 2 * (fair_value[Security.AAPL] - 1)  + 3 * (fair_value[Security.MSFT] - 1) + 2 * (fair_value[Security.GOOG] - 1)) / 10.0
        xlk_fmv_actual = fair_value[Security.XLK]
        print(xlk_fmv_theory, xlk_fmv_actual)
        print(fair_value)
        # time.sleep(1)

        xlk_b, xlk_s = book[Security.XLK]
        xlk_b_p, xlk_b_q = xlk_b[0]
        xlk_s_p, xlk_s_q = xlk_s[0]
        b_b, b_s = book[Security.BOND]
        b_s_p, b_s_q = b_s[0]
        b_b_p, b_b_q = b_b[0]
        a_b, a_s = book[Security.AAPL]
        a_s_p, a_s_q = a_s[0]
        a_b_p, a_b_q = a_b[0]
        m_b, m_s = book[Security.MSFT]
        m_s_p, m_s_q = m_s[0]
        m_b_p, m_b_q = m_b[0]
        g_b, g_s = book[Security.GOOG]
        g_s_p, g_s_q = g_s[0]
        g_b_p, g_b_q = g_b[0]

        num_xlk_from_components = min(
            xlk_b_q,
            math.floor(b_b_q / 3.0) * 10,
            math.floor(a_b_q / 2.0) * 10,
            math.floor(m_b_q / 3.0) * 10,
            math.floor(g_b_q / 2.0) * 10)

        profit_from_selling_xlk = num_xlk_from_components * xlk_b_p
        cost_of_converting_to_xlk = num_xlk_from_components * xlk_fmv_theory + 100
        # print(book)
        # print(num_xlk_from_components, profit_from_selling_xlk, cost_of_converting_to_xlk)
        # time.sleep(5)
        if  profit_from_selling_xlk > cost_of_converting_to_xlk:
            # create one out of parts then sell it
            # actions.append(buy(Security.XLK, xlk_fmv_theory, 1, exchange_state))
            # actions.append(sell(Security.XLK, s[0] - 1, s[1]), exchange_rate)
            print("XLK")
            time.sleep(1)
            actions.append(buy(Security.BOND, b_b_p + 1, 3 * num_xlk_from_components, exchange_state))
            actions.append(buy(Security.AAPL, a_b_p + 1, 2 * num_xlk_from_components, exchange_state))
            actions.append(buy(Security.MSFT, m_b_p + 1, 3 * num_xlk_from_components, exchange_state))
            actions.append(buy(Security.GOOG, g_b_p + 1, 2 * num_xlk_from_components, exchange_state))
            actions.append(convert_from_components(Security.XLK, num_xlk_from_components, exchange_state))
            actions.append(sell(Security.XLK, xlk_s_p - 1, num_xlk_from_components, exchange_state))
        # if xlk_fmv_theory > xlk_fmv_actual:
            # time.sleep(1)
            # print("XLK2")
            # print(xlk_fmv_theory, xlk_fmv_actual)
            # xlk_b, xlk_s = book[Security.XLK]
            # xlk_b_p, xlk_b_q = xlk_b[0]
            # print(xlk_b_p)
            # actions.append(buy(Security.XLK, xlk_b_p + 1, 10, exchange_state))
            # actions.append(convert_to_components(Security.XLK, 10, exchange_state))
            # b_b, b_s = book[Security.BOND]
            # b_s_p, b_s_q = b_s[0]
            # actions.append(sell(Security.BOND, b_s_p - 1, 3, exchange_state))
            # a_b, a_s = book[Security.AAPL]
            # a_s_p, a_s_q = a_s[0]
            # actions.append(sell(Security.AAPL, a_s_p - 1, 2, exchange_state))
            # m_b, m_s = book[Security.MSFT]
            # m_s_p, m_s_q = m_s[0]
            # actions.append(sell(Security.MSFT, m_s_p - 1, 3, exchange_state))
            # g_b, g_s = book[Security.GOOG]
            # g_s_p, g_s_q = g_s[0]
            # actions.append(sell(Security.GOOG, g_s_p - 1, 2, exchange_state))
            # time.sleep(5)

    # Arbitrage
    if (Security.BABA in book and Security.BABZ in book):
        a_buys, a_sells = book[Security.BABA]
        z_buys, z_sells = book[Security.BABZ]

        if (len(a_buys) > 0 and len(a_sells) > 0 and len(z_buys) > 0 and len(z_sells) > 0):
            a_b_p, a_b_q = a_buys[0]
            a_s_p, a_s_q = a_sells[0]

            z_b_p, z_b_q = z_buys[0]
            z_s_p, z_s_q = z_sells[0]

            fv_a = (a_b_p + a_s_p) / 2.0
            fv_z = (z_b_p + z_s_p) / 2.0

            z_to_a_max = min(z_b_q, a_s_q)
            a_to_z_max = min(a_b_q, z_s_q)
            if (z_to_a_max * z_b_p) + 10 < a_s_p * z_to_a_max:
                actions.append(buy(Security.BABZ, z_b_p, z_to_a_max, exchange_state))
                actions.append(convert_to_components(Security.BABZ, z_to_a_max, exchange_state))
                actions.append(sell(Security.BABA, a_s_p, z_to_a_max, exchange_state))
                print("Z TO A")
                print(z_b_p, a_s_p, z_to_a_max)
                # time.sleep(5)

            if (a_to_z_max * a_b_p) + 10 < z_s_p * a_to_z_max:
                actions.append(buy(Security.BABA, a_b_p, a_to_z_max, exchange_state))
                actions.append(convert_to_components(Security.BABA, a_to_z_max, exchange_state))
                actions.append(sell(Security.BABZ, z_s_p, a_to_z_max, exchange_state))
                print("A TO Z")
                print(a_b_p, z_s_p, a_to_z_max)
                # time.sleep(5)


    for symbol in book:
        if symbol in exchange_state.open_stocks and symbol == Security.XLK:# and not symbol == Security.XLK and not symbol == Security.BABA and not symbol == Security.BABZ:
            buys, sells = book[symbol]
            if (len(buys) > 0 and len(sells) > 0):
                bb, bq = buys[0]                # best buy
                bs, sq = sells[0]
                actions.append(buy(symbol, bb + 1, 1, exchange_state))
                actions.append(sell(symbol, bs - 1, 1, exchange_state))

    if len(actions) == 0:
        return None
    return actions

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

def convert_to_components(security, quantity, exchange_state):
    trade_id = exchange_state.tid
    exchange_state.tid += 1
    trade = {"type": "convert", "order_id": trade_id, "symbol": security, "dir": "SELL", "size": quantity}
    exchange_state.trades[trade_id] = (trade, datetime.datetime.now(), False)
    return trade

def convert_from_components(security, quantity, exchange_state):
    trade_id = exchange_state.tid
    exchange_state.tid += 1
    trade = {"type": "convert", "order_id": trade_id, "symbol": security, "dir": "BUY", "size": quantity}
    exchange_state.trades[trade_id] = (trade, datetime.datetime.now(), False)
    return trade

if __name__ == "__main__":
    main()