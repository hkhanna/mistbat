import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME


def update_from_remote():
    """Poll the binance API for transaction history and save as json file."""
    from binance.client import Client
    import yaml

    keys = yaml.load(open(XDG_CONFIG_HOME + "/mistbat/secrets.yaml"))["binance"]
    client = Client(keys["api_key"], keys["secret_key"])

    deposits = client.get_deposit_history()
    withdraws = client.get_withdraw_history()
    b_resources = {"deposits": deposits, "withdraws": withdraws}

    exchange_info = client.get_exchange_info()
    all_pairs = [sym["symbol"] for sym in exchange_info["symbols"]]

    trades = {}
    for pair in all_pairs:
        trades[pair] = client.get_my_trades(symbol=pair)

        # 500 trades max per pair
        assert len(trades[pair]) < 500

    b_resources["trades"] = trades

    with open(XDG_DATA_HOME + "/mistbat/binance.json", "w") as f:
        f.write(json.dumps(b_resources, indent=2))


def parse_events():
    """Take json file of binance transactions and parse into Event instances.
    Returns:
      A list of instances of Event subclasses (e.g., Exchange, FiatExchange, Send)
    """
    # Returns Exchanges, Sends, Receives
    # Does not do things like parse into Coins
    events = []

    # Load up the JSON file
    with open(XDG_DATA_HOME + "/mistbat/binance.json", "r") as f:
        json_data = json.load(f)

    for obs in json_data["deposits"]["depositList"]:
        # Handle differing Bitcoin Cash symbols
        if obs["asset"] == "BCC":
            obs["asset"] = "BCH"

        receive = Receive(
            time=obs["insertTime"],
            location="binance",
            coin=obs["asset"],
            amount=float(obs["amount"]),
            txid=obs["txId"],
        )
        events.append(receive)

    for obs in json_data["withdraws"]["withdrawList"]:
        # Handle differing Bitcoin Cash symbols
        if obs["asset"] == "BCC":
            obs["asset"] = "BCH"

        send = Send(
            time=obs["applyTime"],
            location="binance",
            coin=obs["asset"],
            amount=float(obs["amount"]),
            txid=obs["txId"],
        )
        events.append(send)

    trades = json_data["trades"]
    for pair in trades:
        if len(trades[pair]) == 0:
            continue

        # Only handle 3 char coins for now
        assert len(pair) == 6
        base_currency = pair[:3]
        quote_currency = pair[3:]

        # Handle differing Bitcoin Cash symbols
        if base_currency == "BCC":
            base_currency = "BCH"
        if quote_currency == "BCC":
            quote_currency = "BCH"

        for obs in trades[pair]:
            if obs["isBuyer"]:
                buy_coin = base_currency
                sell_coin = quote_currency
                buy_amount = float(obs["qty"])
                sell_amount = round(float(obs["price"]) * float(obs["qty"]), 8)
            else:
                buy_coin = quote_currency
                sell_coin = base_currency
                sell_amount = float(obs["qty"])
                buy_amount = round(float(obs["price"]) * float(obs["qty"]), 8)

            exchange = Exchange(
                time=obs["time"],
                location="binance",
                buy_coin=buy_coin,
                buy_amount=buy_amount,
                sell_coin=sell_coin,
                sell_amount=sell_amount,
                fee_with=obs["commissionAsset"],
                fee_amount=float(obs["commission"]),
            )
            events.append(exchange)

    return events
