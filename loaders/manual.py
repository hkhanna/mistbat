import yaml
from events import *
from xdg import XDG_CONFIG_HOME


def update_from_remote():
    pass


def parse_events():
    # Return Exchanges, Sends, Receives
    # Does not parse into Coins
    events = []

    # Load up the YAML file
    with open(XDG_CONFIG_HOME + "/mistbat/manual_obs.yaml", "r") as f:
        observations = yaml.load(f)

    for obs in observations:
        # TODO: how are fees handled?
        if obs["type"] == "exchange":
            exchange = Exchange(
                time=obs["time"],
                location=obs["location"],
                buy_coin=obs["buy_coin"],
                buy_amount=float(obs["buy_amount"]),
                sell_coin=obs["sell_coin"],
                sell_amount=float(obs["sell_amount"]),
                buy_fmv=getattr(obs, "buy_fmv", None),
                sell_fmv=getattr(obs, "sell_fmv", None),
                fee_with=obs["buy_coin"],  # TODO FIXME
                fee_amount=0,  # TODO FIXME
            )
            events.append(exchange)

        elif obs["type"] == "send":
            send = Send(
                time=obs["time"],
                location=obs["location"],
                coin=obs["coin"],
                amount=obs["amount"],
                txid=obs["txid"],
                fmv=getattr(obs, "fmv", None),
            )
            events.append(send)

        elif obs["type"] == "receive":
            receive = Receive(
                time=obs["time"],
                location=obs["location"],
                coin=obs["coin"],
                amount=obs["amount"],
                txid=obs["txid"],
                fmv=getattr(obs, "fmv", None),
            )
            events.append(receive)
        else:
            raise Exception("Unrecognized type: " + obs["type"])

    return events
