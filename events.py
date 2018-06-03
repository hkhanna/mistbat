import dateutil.parser
import datetime
import pytz
import hashlib


class Event:
    def __init__(self, **kwargs):
        for name, val in kwargs.items():
            setattr(self, name, val)

        # Parse strings into datetime
        if type(self.time) == str:
            self.time = dateutil.parser.parse(self.time)
        # Parse unix timestamps into datetime
        elif type(self.time) == int:
            self.time = datetime.datetime.fromtimestamp(self.time / 1e3, tz=pytz.utc)

        # Assume UTC timezone if not specified
        # Otherwise, convert to UTC
        if self.time.tzinfo is None:
            self.time = self.time.replace(tzinfo=pytz.utc)
        else:
            self.time = self.time.astimezone(pytz.utc)

        # Generate unique ID based on available info
        self.generate_id()

    def generate_id(self):
        id = self.location[:3]
        # If there's an id provided by the exchange leverage that
        if hasattr(self, "location_id"):
            id += "-" + self.location_id[-5:]
        # Otherwise, hash a few things we have to get the id
        else:
            hashstr = (
                getattr(self, "location", "")
                + str(self.time)
                + self.__class__.__name__
                + getattr(self, "coin", "")
                + getattr(self, "buy_coin", "")
                + getattr(self, "sell_coin", "")
                + str(getattr(self, "amount", ""))
                + str(getattr(self, "buy_amount", ""))
                + str(getattr(self, "sell_amount", ""))
                + getattr(self, "txid", "")
            )
            id += "-" + hashlib.sha256(hashstr.encode()).hexdigest()[-5:]
        self.id = id


class Exchange(Event):
    def entries(self):
        return (
            (self.location, self.buy_coin, self.buy_amount),
            (self.location, self.sell_coin, -self.sell_amount),
            (self.location, self.fee_with, -self.fee_amount),
        )

    def __str__(self, alt_id=None):
        return "{} ({}) - EXCH {} {} -> {} {} [rate?] [fee?]".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            alt_id or self.id,
            self.sell_coin,
            self.sell_amount,
            self.buy_coin,
            self.buy_amount,
        )


class FiatExchange(Exchange):
    def __init__(self, **kwargs):
        Exchange.__init__(self, **kwargs)
        if self.sell_coin == "USD":
            self.investing = True
            self.redeeming = False
            self.rate = round(self.sell_amount / self.buy_amount, 2)
        else:
            self.investing = False
            self.redeeming = True
            self.rate = round(self.buy_amount / self.sell_amount, 2)

    def __str__(self, alt_id=None):
        if self.investing:
            return "{} ({}) - FXCH {} {} (+ USD {} fee) -> {} {} (@ USD {} per {})".format(
                self.time.strftime("%Y-%m-%d %H:%M:%S"),
                alt_id or self.id,
                self.sell_coin,
                self.sell_amount,
                self.fee_amount,
                self.buy_coin,
                self.buy_amount,
                self.rate,
                self.buy_coin,
            )
        else:
            return "{} ({}) - FXCH {} {} -> {} {} (+ USD {} fee) (@ USD {} per {})".format(
                self.time.strftime("%Y-%m-%d %H:%M:%S"),
                alt_id or self.id,
                self.sell_coin,
                self.sell_amount,
                self.buy_coin,
                self.buy_amount,
                self.fee_amount,
                self.rate,
                self.buy_coin,
            )


class Send(Event):
    def entries(self):
        return (self.location, self.coin, -self.amount)

    def __str__(self):
        return "{} ({}) - SEND {} {} from {}".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.coin,
            self.amount,
            self.location,
        )


class Receive(Event):
    def entries(self):
        return (self.location, self.coin, self.amount)

    def __str__(self):
        return "{} ({}) - RECV {} {} by {}".format(
            self.time.strftime("%Y-%m-%d %H:%M:%S"),
            self.id,
            self.coin,
            self.amount,
            self.location,
        )


def get_events(loaders, typ=None, remote_update=False):
    """Return events from exchange loaders.
    Args:
        loaders: A list of all the loader modules to be used.
        typ: A filter for specific event types (e.g., 'Send')
        remote_update: Poll the exchange APIs and update the transaction records.

    Returns:
        A list of events from all loaders, sorted by time.
    """
    all_events = []

    for loader in loaders:
        if remote_update:
            print("Remote update from {}".format(loader.__name__))
            loader.update_from_remote()
        all_events.extend(loader.parse_events())

    # TODO: create another function in the liqui loader for anything else to be done
    # TODO: confirm all events have unique id attribute

    # Sort all events by time
    all_events.sort(key=lambda x: x.time)

    # Filter by type if requested
    if typ == None:
        return all_events
    else:
        if type(typ) == list or type(typ) == tuple:
            return [ev for ev in all_events if isinstance(ev, tuple(typ))]
        else:
            return [ev for ev in all_events if ev.__class__.__name__ == typ]
