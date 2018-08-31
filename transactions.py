import dateutil.parser
import pytz
import hashlib
import yaml


class Transaction:
    def basis_contribution(self, coin):
        return None  # TODO: raise NotImplementedError

    def amount_realized(self, coin):
        return None  # TODO: raise NotImplementedError

    def description(self):
        notes = getattr(self, "notes", None)
        groups = getattr(self, "groups", "N/A")
        annotated = getattr(self, "annotated", False)

        desc = self.__str__()
        if notes:
            desc += "\n   |-> {}".format(notes)
        if annotated:
            desc += "\n   |-> Groups: {}".format(groups)

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
        if hasattr(self, 'fmv') or hasattr(self,'buy_fmv'):
           return False
        else:
            return True

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
        return self.exchange.__str__(self.id)


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


class SendReceive(Transaction):
    def __init__(self, send, receive):
        self.send = send
        self.receive = receive
        self.time = self.send.time  # Time is time of sending
        self.origin = self.send.location
        self.destination = self.receive.location
        self.coin = self.send.coin
        self.amount = self.send.amount
        self.fee = round(self.send.amount - self.receive.amount, 8)
        self.generate_id()

    def entries(self):
        return (self.coin, -self.fee)

    def generate_id(self):
        # Id is 'srtx-' with last 2 chars of send a '/' and last two chars of recv
        self.id = "srtx-" + self.send.id[-2:] + "/" + self.receive.id[-2:]

    def __str__(self):
        return "{} ({}) - SENDRECV {} {} (- {} {} fee) from {} to {}".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.coin,
            self.amount,
            self.coin,
            self.fee,
            self.origin,
            self.destination,
        )


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


class Earn(Transaction):
    def __init__(self, receive):
        self.receive = receive
        self.generate_id()

    def generate_id(self):
        # Only change is to make the prefix 4 characters
        self.id = self.receive.id[:3] + "x" + self.receive.id[3:]

    def entries(self):
        return (self.coin, self.amount)

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


class Shapeshift(Transaction):
    def __init__(self, send, receive):
        self.send = send
        self.receive = receive
        self.time = self.send.time  # Time is time of sending
        self.fee_amount = 0  # FIXME TODO
        self.fee_with = "USD"  # FIXME TODO
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
        return "{} ({}) - SHAPESHIFT {} {} on {} -> {} {} on {} [fee?]".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.send.coin,
            self.send.amount,
            self.send.location,
            self.receive.coin,
            self.receive.amount,
            self.receive.location,
        )


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

def fmv_transactions(transactions, tx_annotation_file):
    raise NotImplementedError
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
