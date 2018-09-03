import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME


def update_from_remote():
    import gdax
    import yaml

    keys = yaml.load(open(XDG_CONFIG_HOME + "/mistbat/secrets.yaml"))["gdax"]
    client = gdax.AuthenticatedClient(
        keys["api_key"], keys["secret_key"], keys["passphrase"]
    )

    # Get list of USD products
    product_ids = [p["id"] for p in client.get_products() if p["id"][-3:] == 'USD']

    # Exchange history is in the "fills" API
    # No need for deposit/withdrawal info since that is in the Coinbase data
    fills = []
    for product_id in product_ids:
        fills_paginated = client.get_fills(product_id=product_id)
        for page in fills_paginated:
            fills.extend(page)

    with open(XDG_DATA_HOME + "/mistbat/gdax.json", "w") as f:
        f.write(json.dumps(fills, indent=2))


def parse_events():
    # Returns Exchanges ("fills") only.
    # Sends and Receives are handled by the Coinbase loader.
    events = []

    # Load up the JSON file
    with open(XDG_DATA_HOME + "/mistbat/gdax.json", "r") as f:
        json_data = json.load(f)

    # Parse fiat buys into Exchange objects
    buys = [fill for fill in json_data if fill["side"] == "buy"]
    for buy in buys:
        # Validation checks -- only processing exchanges to/from USD
        assert buy["product_id"][-3:] == "USD"
        buy_coin = buy["product_id"][:3]

        fiat_exchange = FiatExchange(
            time=buy["created_at"],
            location="coinbase",
            buy_coin=buy_coin,
            buy_amount=float(buy["size"]),
            sell_coin="USD",
            sell_amount=float(buy["usd_volume"]),
            fee_with="USD",
            fee_amount=float(buy["fee"]),
        )
        events.append(fiat_exchange)

    # Parse fiat sells into Exchange objects
    sells = [fill for fill in json_data if fill["side"] == "sell"]
    for sell in sells:
        # Validation checks -- only processing exchanges to/from USD
        assert sell["product_id"][-3:] == "USD"
        sell_coin = sell["product_id"][:3]

        fiat_exchange = FiatExchange(
            time=sell["created_at"],
            location="coinbase",
            buy_coin="USD",
            buy_amount=float(sell["usd_volume"]),
            sell_coin=sell_coin,
            sell_amount=float(sell["size"]),
            fee_with="USD",
            fee_amount=float(sell["fee"]),
        )
        events.append(fiat_exchange)

    return events
