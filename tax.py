import pytz
import datetime as dt


def _held_1yr(acquired, disposed):
    """Determine whether the trade qualifies for LT treatment"""
    acquired = acquired.date()
    min_date = dt.date(
        year=acquired.year + 1, month=acquired.month, day=acquired.day + 1
    )
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

    def current_available_basis(self):
        basis = {}
        for asset in self.assets.values():
            basis[asset.coin] = asset.current_available_basis()
        return basis

    def generate_form(self, term, aggregated, year):
        """Term argument is 'short', 'long' or 'all'. Aggregate is whether to have a single disposition that is traced to multiple acquisitions appear as a single row."""
        all_rows = []
        for asset in self.assets.values():
            tax_history = asset.tax_history(term, aggregated, year)
            if len(tax_history):
                all_rows.append([" "] * 6)
            all_rows.extend(tax_history)
        return all_rows


class Asset(object):
    """Asset class used for tracking tax basis of each asset"""

    def __init__(self, coin):
        self.coin = coin
        self.transactions = []

    def add_tx(self, tx):
        self.transactions.append(tx)

    def current_available_basis(self):
        self.transactions.sort(key=lambda x: x.time)
        available_basis = self._tx_used_basis(self.transactions[-1], True)
        return available_basis

    def tax_history(self, term, aggregated, year):
        self.transactions.sort(key=lambda x: x.time)
        tax_history = []
        for tx in self.transactions:
            if year and tx.time.year != int(year):
                continue
            used_basis = self._tx_used_basis(
                tx
            )  # What basis did the tx use up, if any.
            tax_impact = self._tax_impact(
                tx, used_basis, term, aggregated
            )  # Calculate the tax impact of the tx based on the used basis and in the way we specify
            if tax_impact:
                tax_history.extend(tax_impact)
        return tax_history

    def _tx_used_basis(self, tx, return_available_basis=False):
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
                        available_basis[0][1] -= amount_realized[1] - matched_ar
                        used_basis += [
                            [basis[0], (amount_realized[1] - matched_ar), basis[2]]
                        ]
                        matched_ar += amount_realized[1] - matched_ar
                        break
                    elif (amount_realized[1] - matched_ar) >= basis[1]:
                        # Chews up all of or more than this basis item
                        del available_basis[0]
                        used_basis += [basis]
                        matched_ar += basis[1]
                assert round(matched_ar, 8) == round(amount_realized[1], 8), "Not enough basis to match"
            if tx == tx_iter:
                if return_available_basis:
                    return available_basis
                else:
                    return used_basis

    def _tax_impact(self, tx, used_basis, term, aggregated):
        # If this is the transaction of interest, we need to report the used basis aka rows of 8949
        # Map each item of used_basis into a row of Form 8949
        amount_realized = tx.amount_realized(self.coin)
        if amount_realized is None:
            # If this is purely a basis-adding transaction, no rows to report
            return []

        rows = []
        aggregated_row = [
            amount_realized[1],
            None,
            amount_realized[0],
            0.00,
            0.00,
            0.00,
        ]
        for basis in used_basis:
            description = f"{self.coin} {round(basis[1], 8):12.8f}"
            date_acquired = basis[0]
            date_sold = amount_realized[0]
            proceeds = basis[1] * amount_realized[2]
            tx_basis = basis[1] * basis[2]
            gain = proceeds - tx_basis

            if term == "short" and _held_1yr(date_acquired, date_sold):
                continue

            if term == "long" and not _held_1yr(date_acquired, date_sold):
                continue

            rows.append(
                (
                    description,
                    date_acquired,
                    date_sold,
                    round(proceeds, 2),
                    round(tx_basis, 2),
                    round(gain, 2),
                )
            )

            if aggregated_row[1] is None:
                aggregated_row[1] = date_acquired
            else:
                aggregated_row[1] = "Various"

            aggregated_row[3] += proceeds
            aggregated_row[4] += tx_basis
            aggregated_row[5] += gain

        aggregated_row[0] = f"{self.coin} {round(aggregated_row[0], 8):12.8f}"
        aggregated_row[3] = round(aggregated_row[3], 2)
        aggregated_row[4] = round(aggregated_row[4], 2)
        aggregated_row[5] = round(aggregated_row[5], 2)

        if aggregated_row[1] is None:
            aggregated_row = (
                None
            )  # If no entries for that holding period, don't add anything to the table
        else:
            aggregated_row = [aggregated_row]
        return aggregated_row if aggregated else rows
