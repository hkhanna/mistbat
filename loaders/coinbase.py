import json
from events import *
from xdg import XDG_DATA_HOME, XDG_CONFIG_HOME


# TODO: fix nomenclature in this function
def update_from_remote():
    from coinbase.wallet.client import Client
    import yaml

    keys = yaml.load(open(XDG_CONFIG_HOME + "/mistbat/secrets.yaml"))["coinbase"]
    client = Client(keys["api_key"], keys["secret_key"])

    accounts = [
        {
            "id": account.id,
            "currency": account.balance.currency,
            "amount": account.balance.amount,
        }
        for account in client.get_accounts().data
    ]

    cb_resources = {"buys": {}, "sells": {}, "transactions_filtered": {}}
    for account in accounts:
        # Coinbase Buys
        buys = json.loads(str(client.get_buys(account["id"])))["data"]
        cb_resources["buys"][account["currency"]] = list(
            filter(lambda buy: buy["status"] != "canceled", buys)
        )

        # Coinbase Sells
        sells = json.loads(str(client.get_sells(account["id"])))["data"]
        cb_resources["sells"][account["currency"]] = list(
            filter(lambda sell: sell["status"] != "canceled", sells)
        )

        # Coinbase Transactions (Other)
        # Need to filter buys and sells out of transactions since transactions
        # includes those in addition to the other transactions
        transactions = json.loads(str(client.get_transactions(account["id"])))["data"]
        cb_resources["transactions_filtered"][account["currency"]] = list(
            filter(
                lambda tx: tx["type"] != "buy"
                and tx["type"] != "sell"
                and tx["status"] != "canceled",
                transactions,
            )
        )

        with open(XDG_DATA_HOME + "/mistbat/coinbase.json", "w") as f:
            f.write(json.dumps(cb_resources, indent=2))


def parse_events():
    # Returns Exchanges, Sends, Receives
    # Does not do things like parse into Coins
    # This will IGNORE deposits and withdrawals from GDAX.
    # I.e., GDAX and Coinbase are treated as one location.
    # The GDAX loader only parses "fills" i.e., exchanges and pretends they're happening directly on Coinbase.
    events = []

    # Load up the JSON file
    with open(XDG_DATA_HOME + "/mistbat/coinbase.json", "r") as f:
        json_data = json.load(f)

    # Verify that only known transaction types are present
    buys = json_data.pop("buys")
    sells = json_data.pop("sells")
    transactions_filtered = json_data.pop("transactions_filtered")
    assert len(json_data) == 0  # There should be nothing else in the file
    # The only observations this is set up to parse are send, exchange_deposit
    # and exchange_withdrawal
    types = [
        obs["type"] for coin_val in transactions_filtered.values() for obs in coin_val
    ]
    types = set(types)
    assert {
        "send",
        "exchange_withdrawal",
        "exchange_deposit",
        "fiat_deposit",
        "fiat_withdrawal",
    } == types

    # Parse fiat buys into Exchange objects
    buys_flat = [buy for coin_val in buys.values() for buy in coin_val]
    for buy in buys_flat:
        # Validation checks -- only processing USD
        assert buy["subtotal"]["currency"] == "USD"
        assert all([fee["amount"]["currency"] == "USD" for fee in buy["fees"]])

        fiat_exchange = FiatExchange(
            time=buy["created_at"],
            location="coinbase",
            buy_coin=buy["amount"]["currency"],
            buy_amount=float(buy["amount"]["amount"]),
            sell_coin="USD",
            sell_amount=float(buy["subtotal"]["amount"]),
            fee_with="USD",
            fee_amount=sum([float(fee["amount"]["amount"]) for fee in buy["fees"]]),
            location_id=buy["id"],
        )
        events.append(fiat_exchange)

    # Parse fiat sells into Exchange objects
    sells_flat = [sell for coin_val in sells.values() for sell in coin_val]
    for sell in sells_flat:
        # Validation checks -- only processing USD
        assert sell["subtotal"]["currency"] == "USD"
        assert all([fee["amount"]["currency"] == "USD" for fee in sell["fees"]])

        fiat_exchange = FiatExchange(
            time=sell["created_at"],
            location="coinbase",
            buy_coin="USD",
            buy_amount=float(sell["subtotal"]["amount"]),
            sell_coin=sell["amount"]["currency"],
            sell_amount=float(sell["amount"]["amount"]),
            fee_with="USD",
            fee_amount=sum([float(fee["amount"]["amount"]) for fee in sell["fees"]]),
            location_id=sell["id"],
        )
        events.append(fiat_exchange)

    # Parse sends into Send objects
    # Note the confusion that Coinbase uses "send" to mean both send and receive
    # Need to check for presence of key "from" or "to" to deterine Send or Receive

    send_flat = [
        obs
        for coin_val in transactions_filtered.values()
        for obs in coin_val
        if obs["type"] == "send" and "to" in obs
    ]

    for send_obs in send_flat:
        fmv = float(send_obs["native_amount"]["amount"]) / float(
            send_obs["amount"]["amount"]
        )
        send = Send(
            time=send_obs["created_at"],
            coin=send_obs["amount"]["currency"],
            amount=abs(float(send_obs["amount"]["amount"])),
            location="coinbase",
            fmv=fmv,
            fmv_source="coinbase",
            fee_reported=send_obs["network"]["transaction_fee"]["amount"],
            txid=send_obs["network"]["hash"],
            location_id=send_obs["id"],
        )
        events.append(send)

    # Parse receives into Receive objects
    recv_flat = [
        obs
        for coin_val in transactions_filtered.values()
        for obs in coin_val
        if obs["type"] == "send" and "from" in obs
    ]

    for recv_obs in recv_flat:
        fmv = float(recv_obs["native_amount"]["amount"]) / float(
            recv_obs["amount"]["amount"]
        )
        receive = Receive(
            time=recv_obs["created_at"],
            coin=recv_obs["amount"]["currency"],
            amount=float(recv_obs["amount"]["amount"]),
            fmv=fmv,
            fmv_source="coinbase",
            location="coinbase",
            txid=recv_obs["network"]["hash"],
            location_id=recv_obs["id"],
        )
        events.append(receive)

    return events


if __name__ == "__main__":
    coinbase_update_from_remote()
