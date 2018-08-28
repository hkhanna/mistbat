import pytz


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
            used_basis = []
            matched_ar = 0.00
            available_basis += filter(None, [tx_iter.basis_contribution(self.coin)])
            amount_realized = tx_iter.amount_realized(self.coin)
            if amount_realized:
                # Match basis to amount realized
                for basis in list(available_basis):
                    if (amount_realized[1] - matched_ar) < basis[1]:
                        # Chews up some but not all of this basis item
                        available_basis[0][1] -= amount_realized[1]
                        used_basis += [[basis[0], amount_realized[1], basis[2]]]
                        matched_ar += amount_realized[1] - matched_ar
                        break
                    elif (amount_realized[1] - matched_ar) >= basis[1]:
                        # Chews up all of or more than this basis item
                        del available_basis[0]
                        used_basis += basis
                        matched_ar += amount_realized[1] - matched_ar
            if tx == tx_iter:
                # If this is the transaction of interest, we need to report the used basis aka rows of 8949
                # Map each item of used_basis into a row of Form 8949
                rows = []
                for basis in used_basis:
                    description = f"{basis[1]} {self.coin}"
                    date_acquired = basis[0].astimezone(
                        pytz.timezone("America/Los_Angeles")
                    )
                    date_sold = amount_realized[0].astimezone(
                        pytz.timezone("America/Los_Angeles")
                    )
                    proceeds = round(amount_realized[1] * amount_realized[2], 3)
                    tx_basis = round(basis[1] * basis[2], 3)
                    gain = proceeds - tx_basis
                    rows.append(
                        (
                            description,
                            date_acquired,
                            date_sold,
                            proceeds,
                            tx_basis,
                            gain,
                        )
                    )
                return rows
