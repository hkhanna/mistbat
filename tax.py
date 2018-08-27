class Form8949(object):
    def __init__(self, transactions):
        self.method = "FIFO"  # This class only works for FIFO
        self.assets = self.generate_assets(transactions)

    def generate_assets(self, transactions):
        assets = {}
        for tx in transactions:
            for coin in tx.affected_coins:
                asset = assets.setdefault(coin, Asset(coin))
                asset.add_tx(tx)
        return assets

    def short_term(self):
        pass  # TODO

    def long_term(self):
        pass  # TODO

    def all_term(self):
        all_rows = []
        for asset in self.assets.values():
            all_rows.extend(asset.tax_history())
        return all_rows


class Asset(object):
    """Asset class used for tracking tax basis of each asset"""

    def __init__(self, coin):
        self.coin = coin
        self.transactions = []

    def add_tx(self, tx):
        self.transactions.append(tx)

    def tax_history(self):
        self.transactions.sort(key=lambda x: x.time)
        tax_history = []
        for tx in self.transactions:
            tax_history.extend(self._tax_impact(tx))
        return tax_history

    def _tax_impact(self, tx):
        """Return an array that represents a row of Form 8949"""
        assert tx in self.transactions
        available_basis = []

        for tx_iter in self.transactions:
            available_basis += filter(None, [tx_iter.basis_contribution(self.coin)])
            amount_realized = tx_iter.amount_realized(self.coin)
            # TODO: START: Eat up basis for AR
            used_basis = []
            if tx == tx_iter:
                break

        for row in used_basis:
            pass  # TODO


# class Asset(object):
#     """Asset class used for tracking tax basis of each asset"""
#     def __init__(self, coin):
#         self.method = 'FIFO' # this class only works for FIFO
#         self.coin = coin # coin means symbol basically, like "BTC" or "LTC"
#         self.mutable_ledger = []

#     def buy(self, tx_id, buy_amount, total_usd_cost):
#         self.mutable_ledger.append((tx_id, buy_amount, total_usd_cost))

#     def sell(self, sell_amount):
#         """Returns combined basis of sold amounts"""
#         tx_basis = 0.00
#         transactions_used = []
#         uncaptured_sell_amount = sell_amount
#         for tx_id, ledger_amount, total_usd_cost in list(self.mutable_ledger):
#             if uncaptured_sell_amount <= ledger_amount:
#                 tx_basis += (uncaptured_sell_amount / ledger_amount) * total_usd_cost # use a proportional amount of the cost basis
#                 uncaptured_sell_amount = 0.00
#                 transactions_used.append(tx_id)
#                 self.mutable_ledger[0][1] -= uncaptured_sell_amount
#             else:
#                 tx_basis += total_usd_cost
#                 uncaptured_sell_amount -= ledger_amount
#                 transactions_used.append(tx_id)
#                 del self.mutable_ledger[0]
#         return tx_basis, transactions_used
