import pytz
import datetime as dt

def _held_1yr(acquired, disposed):
    acquired = acquired.date()
    min_date = dt.date(year= acquired.year + 1, month=acquired.month, day= acquired.day + 1)
    if disposed.date() >= min_date:
        return True
    else:
        return False


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
        return [row for row in self.all_term() if not _held_1yr(row[1], row[2])]

    def long_term(self):
        return [row for row in self.all_term() if _held_1yr(row[1], row[2])]

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
                    basis = list(basis)
                    if (amount_realized[1] - matched_ar) < basis[1]:
                        # Chews up some but not all of this basis item
                        available_basis[0][1] -= (amount_realized[1] - matched_ar)
                        used_basis += [[basis[0], (amount_realized[1] - matched_ar), basis[2]]]
                        matched_ar += amount_realized[1] - matched_ar
                        break
                    elif (amount_realized[1] - matched_ar) >= basis[1]:
                        # Chews up all of or more than this basis item
                        del available_basis[0]
                        used_basis += [basis]
                        matched_ar += basis[1]
                # TODO: assert matched_ar == amount_realized[1], "Not enough basis to match"
            if tx == tx_iter:
                # If this is the transaction of interest, we need to report the used basis aka rows of 8949
                # Map each item of used_basis into a row of Form 8949
                if amount_realized is None:
                    # If this is purely a basis-adding transaction, no rows to report
                    return []

                rows = []
                for basis in used_basis:
                    description = f"{round(basis[1], 8)} {self.coin}"
                    date_acquired = basis[0].astimezone(
                        pytz.timezone("America/Los_Angeles")
                    )
                    date_sold = amount_realized[0].astimezone(
                        pytz.timezone("America/Los_Angeles")
                    )
                    proceeds = round(basis[1] * amount_realized[2], 2)
                    tx_basis = round(basis[1] * basis[2], 2)
                    gain = round(proceeds - tx_basis, 2)
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
