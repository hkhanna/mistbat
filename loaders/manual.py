import yaml
from events import *
from xdg import XDG_CONFIG_HOME


def update_from_remote():
    pass


def parse_events():
    # Return Exchanges, Sends, Receives
    events = []

    # Load up the YAML file
    with open(XDG_CONFIG_HOME + "/mistbat/manual_obs.yaml", "r") as f:
        observations = yaml.load(f)

    for obs in observations:
        if obs["type"] == "exchange":
            exchange = Exchange(
                time=obs["time"],
                location=obs["location"],
                buy_coin=obs["buy_coin"],
                buy_amount=float(obs["buy_amount"]),
                sell_coin=obs["sell_coin"],
                sell_amount=float(obs["sell_amount"]),
                buy_fmv=obs.get("buy_fmv", None),
                sell_fmv=obs.get("sell_fmv", None),
                fee_with=obs.get("fee_with", None),
                fee_amount=obs.get("fee_amount", None),
            )
            events.append(exchange)

        elif obs["type"] == "fiat-exchange":
            fexchange = FiatExchange(
                time=obs["time"],
                location=obs["location"],
                buy_coin=obs["buy_coin"],
                buy_amount=float(obs["buy_amount"]),
                sell_coin=obs["sell_coin"],
                sell_amount=float(obs["sell_amount"]),
                fee_with=obs.get("fee_with", None),
                fee_amount=obs.get("fee_amount", None),
            )
            events.append(fexchange)
        elif obs["type"] == "send":
            send = Send(
                time=obs["time"],
                location=obs["location"],
                coin=obs["coin"],
                amount=obs["amount"],
                txid=obs["txid"],
                fmv=obs.get("fmv", None),
            )
            events.append(send)

        elif obs["type"] == "receive":
            receive = Receive(
                time=obs["time"],
                location=obs["location"],
                coin=obs["coin"],
                amount=obs["amount"],
                txid=obs["txid"],
                fmv=obs.get("fmv", None),
            )
            events.append(receive)
        else:
            raise Exception("Unrecognized type: " + obs["type"])

    return events
