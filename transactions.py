import dateutil.parser
import pytz
import hashlib
import yaml


class Transaction:
    def basis_contribution(self, coin):
        raise NotImplementedError

    def amount_realized(self, coin):
        raise NotImplementedError

    def description(self):
        notes = getattr(self, "notes", None)
        groups = getattr(self, "groups", "N/A")
        annotated = getattr(self, "annotated", False)
        reported_fee = getattr(self, "fee_amount", None)
        implied_fee = getattr(self, "implied_fee_usd", None)

        desc = self.__str__()
        if notes:
            desc += "\n   |-> {}".format(notes)
        if annotated:
            desc += "\n   |-> Groups: {}".format(groups)
        if implied_fee is not None:
            desc += "\n   |-> Implied Fee: USD {}".format(self.implied_fee_usd)
        if reported_fee is not None:
            desc += "\n   |-> Reported Fee: {} {}".format(self.fee_amount, self.fee_with)
            if self.fee_with != 'USD':
                if self.fee_with == self.buy_coin:
                    converted_fee = self.buy_fmv * self.fee_amount
                elif self.fee_with == self.sell_coin:
                    converted_fee = self.sell_fmv * self.fee_amount
                desc += " ({:0.2f} USD)".format(converted_fee)

        return desc

    @property
    def affected_coins(self):
        # Sanity checking
        if hasattr(self, "coin"):
            assert not hasattr(self, "buy_coin")
            assert not hasattr(self, "sell_coin")
            affected = [self.coin]

        elif hasattr(self, "buy_coin"):
            assert hasattr(self, "sell_coin")
            assert not hasattr(self, "coin")
            affected = [self.buy_coin, self.sell_coin]

        else:
            # It's a shapeshift
            assert not hasattr(self, "coin")
            assert not hasattr(self, "buy_coin")
            assert not hasattr(self, "sell_coin")
            affected = [self.send.coin, self.receive.coin]

        if "USD" in affected:
            affected.remove("USD")
        return affected
    
    @property
    def missing_fmv(self):
        # All fiat transactions have fmv instrinsic in it.
        if self.__class__.__name__ == 'FiatExchangeTx':
            return False

        if getattr(self, 'fmv', None) or getattr(self, 'buy_fmv', None):
           return False
        else:
            return True

    @property
    def fee_usd(self): 
        raise NotImplementedError


class ExchangeTx(Transaction):
    def __init__(self, exchange):
        self.exchange = exchange
        self.generate_id()

    def generate_id(self):
        # Only change is to make the prefix 4 characters
        self.id = self.exchange.id[:3] + "x" + self.exchange.id[3:]

    def entries(self):
        return [
            [self.buy_coin, self.sell_coin, self.fee_with],
            [self.buy_amount, -self.sell_amount, -self.fee_amount],
        ]

    def __getattr__(self, attr):
        return getattr(self.exchange, attr)

    def __str__(self):
        return "{} ({}) - EXCH {} {} (USD {}) -> {} {} (USD {})".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.sell_coin,
            self.sell_amount,
            round(self.sell_amount * self.sell_fmv, 2),
            self.buy_coin,
            self.buy_amount,
            round(self.buy_amount * self.buy_fmv, 2),
        )

    def basis_contribution(self, coin):
        """Returns tuple of (datetime of tx, number of coins received, cost per coin)
        Fees are not added to basis here. They are instead removed from the amount realized of the ExchangeTx"""
        if coin == self.buy_coin:
           return [self.time, self.buy_amount, self.buy_fmv]
        else:
            return None
    
    def amount_realized(self, coin):
        """Returns tuple of (datetime of tx, number of coins exchanged, amount sold per coin net of fees)"""
        if coin == self.sell_coin:
            fee = max(0, self.fee_usd) # Ignore the fee if its negative
            ar_per_coin = ((self.sell_amount * self.sell_fmv) - fee) / self.sell_amount
            return [self.time, self.sell_amount, ar_per_coin]
        else:
            return None

    @property
    def fee_usd(self):
        return self.implied_fee_usd

class FiatExchangeTx(ExchangeTx):
    def basis_contribution(self, coin):
        """Returns tuple of (datetime of tx, number of coins bought, cost per coin including fees)"""
        if self.investing:
            assert coin == self.buy_coin
            cost_per_coin = (self.sell_amount + self.fee_amount) / self.buy_amount
            return [self.time, self.buy_amount, cost_per_coin]
        else:
            return None

    def amount_realized(self, coin):
        """Returns tuple of (datetime of tx, number of coins sold, amount sold per coin net of fees)"""
        if self.investing:
            return None
        else:
            assert coin == self.sell_coin
            ar_per_coin = (self.buy_amount - self.fee_amount) / self.sell_amount
            return [self.time, self.sell_amount, ar_per_coin]

    def __str__(self):
        return self.exchange.__str__(self.id)
    
    @property
    def fee_usd(self):
        return self.fee_amount

class SendReceive(Transaction):
    def __init__(self, send, receive):
        self.send = send
        self.receive = receive
        self.time = self.send.time  # Time is time of sending
        self.origin = self.send.location
        self.destination = self.receive.location
        self.coin = self.send.coin
        self.amount = self.send.amount
        self.implied_fee = round(self.send.amount - self.receive.amount, 8)
        self.generate_id()

    def entries(self):
        return (self.coin, -self.fee)

    def generate_id(self):
        # Id is 'srtx-' with last 2 chars of send a '/' and last two chars of recv
        self.id = "srtx-" + self.send.id[-2:] + "/" + self.receive.id[-2:]

    def __str__(self):
        fee_converted = self.implied_fee * self.fmv
        return "{} ({}) - SENDRECV {} {} (- {} {:f} / USD {:.2f} fee) from {} to {}".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.coin,
            self.amount,
            self.coin,
            self.implied_fee,
            fee_converted,
            self.origin,
            self.destination,
        )

    def basis_contribution(self, coin):
        """This takes the position blockchain fees dont add to basis."""
        return None
    
    def amount_realized(self, coin):
        """This takes the position blockchain fees don't trigger any AR."""
        return None

    @property
    def fee_usd(self):
        return self.implied_fee * self.fmv

class Spend(Transaction):
    def __init__(self, send):
        self.send = send
        self.generate_id()

    def generate_id(self):
        # Only change is to make the prefix 4 characters
        self.id = self.send.id[:3] + "x" + self.send.id[3:]

    def entries(self):
        return (self.coin, -self.amount)

    def basis_contribution(self, coin):
        """Spending coins does not add to available basis"""
        return None
        
    def amount_realized(self, coin):
        """Returns tuple of (datetime of tx, number of coins spend, fmv of each coin spent)"""
        assert coin == self.coin
        # Make sure fmv exists
        # TODO: Handle fees (waiting on liqui loader) - may need to create a self.effective_fmv that includes impact of fees
        return [self.time, self.amount, self.fmv]

    def __getattr__(self, attr):
        return getattr(self.send, attr)

    def __str__(self):
        return "{} ({}) - SPEND {} {} from {}".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.coin,
            self.amount,
            self.location,
        )

    @property
    def fee_usd(self):
        # FIXME
        return 0.00

class Earn(Transaction):
    def __init__(self, receive):
        self.receive = receive
        self.generate_id()

    def generate_id(self):
        # Only change is to make the prefix 4 characters
        self.id = self.receive.id[:3] + "x" + self.receive.id[3:]

    def entries(self):
        return (self.coin, self.amount)

    def basis_contribution(self, coin):
        """Earning coins triggers income tax and you get a corresponding basis"""
        return self.amount
        
    def amount_realized(self, coin):
        """No amount realized for cap gains purposes when you earn crypto"""
        return None

    def __getattr__(self, attr):
        return getattr(self.receive, attr)

    def __str__(self):
        return "{} ({}) - EARN {} {} by {}".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.coin,
            self.amount,
            self.location,
        )

    @property
    def fee_usd(self):
        return 0.00

class Shapeshift(Transaction):
    def __init__(self, send, receive):
        self.send = send
        self.receive = receive
        self.time = self.send.time  # Time is time of sending
        self.generate_id()

    def generate_id(self):
        # Id is 'shax-' with last 2 chars of send a '/' and last two chars of recv
        self.id = "shax-" + self.send.id[-2:] + "/" + self.receive.id[-2:]

    def entries(self):
        return [
            [self.receive.coin, self.send.coin, self.fee_with],
            [self.receive.amount, -self.send.amount, -self.fee_amount],
        ]

    def __str__(self):
        return "{} ({}) - SHAPESHIFT {} {} (USD {}) on {} -> {} {} (USD {}) on {}".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.send.coin,
            self.send.amount,
            round(self.send.amount * self.send.fmv, 2),
            self.send.location,
            self.receive.coin,
            self.receive.amount,
            round(self.receive.amount * self.receive.fmv, 2),
            self.receive.location,
        )
 
    def basis_contribution(self, coin):
        """Returns tuple of (datetime of tx, number of coins received, cost per coin)
        Fees are not added to basis here. They are instead removed from the amount realized of the Shapeshift"""
        if coin == self.receive.coin:
           return [self.time, self.receive.amount, self.receive.fmv]
        else:
            return None
    
    def amount_realized(self, coin):
        """Returns tuple of (datetime of tx, number of coins exchanged, amount sold per coin net of fees)"""
        if coin == self.send.coin:
            fee = max(0, self.fee_usd) # Ignore the fee if its negative
            ar_per_coin = ((self.send.amount * self.send.fmv) - fee) / self.send.amount
            return [self.time, self.send.amount, ar_per_coin]
        else:
            return None

    @property
    def fee_usd(self):
        return self.implied_fee_usd


def get_transactions(events, tx_data_file):
    """Convert a list of events into a list of transactions using
    the data in the tx_data_file.

    Args:
       events: list of events to parse
       tx_data_file: File containing matching data (for SendReceive) and
           Shapeshift data

    Returns:
        List of transactions, sorted by time.
    """
    all_transactions = []

    tx_data = yaml.load(open(tx_data_file))

    # Send Receive Pairs
    sendreceive_pairs = tx_data.pop("SendReceive")
    for sendreceive_pair in sendreceive_pairs:
        send_id, receive_id = sendreceive_pair.split()

        # Pop the appropriate Send and Receive events from the events array
        # Also error check for bad ids in the tx file
        try:
            send = next(filter(lambda x: x.id == send_id, events))
            assert send.__class__.__name__ == "Send"
            events.remove(send)
        except (StopIteration, AssertionError):
            raise Exception("Bad event id: {}".format(send_id))

        try:
            receive = next(filter(lambda x: x.id == receive_id, events))
            events.remove(receive)
            assert receive.__class__.__name__ == "Receive"
        except (StopIteration, AssertionError):
            raise Exception("Bad event id: {}".format(receive_id))

        sendreceive = SendReceive(send, receive)
        all_transactions.append(sendreceive)

    # Shapeshift Pairs
    sendreceive_pairs = tx_data.pop("Shapeshift")
    for sendreceive_pair in sendreceive_pairs:
        send_id, receive_id = sendreceive_pair.split()

        # Pop the appropriate Send and Receive events from the events array
        # Also error check for bad ids in the tx file
        try:
            send = next(filter(lambda x: x.id == send_id, events))
            assert send.__class__.__name__ == "Send"
            events.remove(send)
        except (StopIteration, AssertionError):
            raise Exception("Bad event id: {}".format(send_id))

        try:
            receive = next(filter(lambda x: x.id == receive_id, events))
            events.remove(receive)
            assert receive.__class__.__name__ == "Receive"
        except (StopIteration, AssertionError):
            raise Exception("Bad event id: {}".format(receive_id))

        shapeshift = Shapeshift(send, receive)
        all_transactions.append(shapeshift)

    # Spend Txs
    spend_events = [event for event in events if event.__class__.__name__ == "Send"]
    for event in spend_events:
        all_transactions.append(Spend(event))
        events.remove(event)

    # Receive Txs
    receive_events = [
        event for event in events if event.__class__.__name__ == "Receive"
    ]
    for event in receive_events:
        all_transactions.append(Earn(event))
        events.remove(event)

    # FiatExchange event passthrough
    fexchange_events = [
        event for event in events if event.__class__.__name__ == "FiatExchange"
    ]
    for event in fexchange_events:
        all_transactions.append(FiatExchangeTx(event))
        events.remove(event)

    # Exchange event passthrough
    exchange_events = [
        event for event in events if event.__class__.__name__ == "Exchange"
    ]

    for event in exchange_events:
        all_transactions.append(ExchangeTx(event))
        events.remove(event)

    # There should be no events left
    assert len(events) == 0

    # Sort all transactions by time
    all_transactions.sort(key=lambda x: x.time)
    return all_transactions


def annotate_transactions(transactions, tx_annotation_file):
    """Annotate transactions with information in an annotation file."""
    annotations = yaml.load(open(tx_annotation_file))

    for ann_id, ann_data in annotations.items():
        try:
            (tx,) = [tx for tx in transactions if tx.id == ann_id]
        except ValueError:
            raise Exception("Bad annotation id: " + ann_id)

        related_txids = ann_data.get("related", [])
        groups = ann_data["groups"]
        notes = ann_data["notes"]

        tx.notes = notes
        tx.groups = groups
        tx.annotated = True

        for rid in related_txids:
            try:
                (rtx,) = [tx for tx in transactions if tx.id == rid]
            except ValueError:
                raise Exception("Bad annotation id: " + rid)

            rtx.notes = notes
            rtx.groups = groups
            rtx.annotated = True

    return transactions

def fmv_transactions(transactions, tx_fmv_file):
    """Make sure all transactions have fmv information"""
    fmv_raw = yaml.load(open(tx_fmv_file))
    fmv_data = {}
    for id in fmv_raw:
        fmvs = fmv_raw[id].split(' -- ')
        comment = None
        if len(fmvs) == 2: # If there is a comment
            comment = fmvs[1]
        fmvs = fmvs[0].split()
        fmvs = {fmv.split('@')[0]: fmv.split('@')[1] for fmv in fmvs}
        fmvs['comment'] = comment
        fmv_data[id] = fmvs

    for tx in transactions:
        if not tx.missing_fmv:
            continue
        try:
            fmvs = fmv_data[tx.id]
        except KeyError:
            raise RuntimeError(f"{tx.id} missing fmv information. Run updatefmv?")
        fmvs.pop("comment")

        if hasattr(tx, "coin"):
            tx.fmv = float(fmvs[tx.coin])
        elif hasattr(tx, "buy_coin"):
            tx.buy_fmv = float(fmvs[tx.buy_coin])
            tx.sell_fmv = float(fmvs[tx.sell_coin])
        else:
            # It's a shapeshift
            tx.send.fmv = float(fmvs[tx.send.coin])
            tx.receive.fmv = float(fmvs[tx.receive.coin])

    return transactions 

def imply_fees(transactions):
    """Imply the USD fees in Shapeshift or Exchange types based on fmv of the exchanged"""
    for tx in transactions:
        if tx.__class__.__name__ == 'ExchangeTx':
            tx.implied_fee_usd = (tx.sell_amount * tx.sell_fmv) - (tx.buy_amount * tx.buy_fmv)
            tx.implied_fee_usd = round(tx.implied_fee_usd, 2)
        if tx.__class__.__name__ == 'Shapeshift':
            tx.implied_fee_usd = (tx.send.amount * tx.send.fmv) - (tx.receive.amount * tx.receive.fmv)
            tx.implied_fee_usd = round(tx.implied_fee_usd, 2)
    return transactions