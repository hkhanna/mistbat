class Asset(object):
    """Asset class used for tracking tax basis of each asset"""
    def __init__(self, coin):
        self.method = 'FIFO' # this class only works for FIFO
        self.coin = coin # coin means symbol basically, like "BTC" or "LTC"
        self.mutable_ledger = []
    
    def buy(self, buy_amount, total_usd_cost):
        self.mutable_ledger.append((buy_amount, total_usd_cost))
    
    def sell(self, sell_amount):
        """Returns combined basis of sold amounts"""
        tx_basis = 0.00
        uncaptured_sell_amount = sell_amount
        for ledger_amount, total_usd_cost in list(self.mutable_ledger):
            if uncaptured_sell_amount <= ledger_amount:
                tx_basis += (uncaptured_sell_amount / ledger_amount) * total_usd_cost # use a proportional amount of the cost basis
                uncaptured_sell_amount = 0.00
                self.mutable_ledger[0][0] -= uncaptured_sell_amount
            else:
                tx_basis += total_usd_cost
                uncaptured_sell_amount -= ledger_amount
                del self.mutable_ledger[0]
        return tx_basis
