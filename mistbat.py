import click
import time
import loaders
import yaml
from prettytable import PrettyTable
from xdg import XDG_CONFIG_HOME, XDG_DATA_HOME
from cryptocompare import get_historical_close, get_coin_spot_prices
from events import get_events
from transactions import (
    get_transactions,
    annotate_transactions,
    fmv_transactions,
    imply_fees,
)
from tax import Form8949


def print_usd_exposure():
    """Calculate total amount of USD invested and not redeemed and total fees spent."""
    fiat_events = get_events(loaders.all, "FiatExchange")
    invested = round(sum(ev.sell_amount for ev in fiat_events if ev.investing), 2)
    redeemed = round(sum(ev.buy_amount for ev in fiat_events if ev.redeeming), 2)
    net_invested = round(invested - redeemed, 2)

    fees = round(sum(ev.fee_amount for ev in fiat_events), 2)
    print(
        "USD Exposure: {} + {} fees (FIAT ONLY) = {:.2f}".format(
            net_invested, fees, net_invested + fees
        )
    )
    print("Aggregate Fee %: {:.2f}%".format(fees * 100 / (invested - redeemed)))


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--remote-update",
    help="Request updated events from exchange APIs",
    is_flag=True,
    default=False,
)
def lsev(remote_update):
    """List all events parsed from observations."""
    events = get_events(loaders.all, remote_update=remote_update)
    for ev in events:
        print(ev)

    print("--------------------")
    print("{} total events".format(len(events)))
    print_usd_exposure()


@cli.command()
@click.option(
    "--no-group",
    help="Only show transactions without a group",
    is_flag=True,
    default=False,
)
@click.option("--no-annotations", help="Omit annotations", is_flag=True, default=False)
@click.option(
    "--minimal", help="Omit everything other than headline", is_flag=True, default=False
)
def lstx(no_group, no_annotations, minimal):
    """List all transactions that have been derived from events and annotated."""
    events = get_events(loaders.all)
    transactions = get_transactions(events, XDG_CONFIG_HOME + "/mistbat/tx_match.yaml")
    if not no_annotations:
        transactions = annotate_transactions(
            transactions, XDG_CONFIG_HOME + "/mistbat/tx_annotations.yaml"
        )
    transactions = fmv_transactions(
        transactions, XDG_DATA_HOME + "/mistbat/tx_fmv.yaml"
    )
    transactions = imply_fees(transactions)

    if no_group:
        transactions = [
            tx for tx in transactions if getattr(tx, "groups", None) is None
        ]

    # Print transactions
    for tx in transactions:
        if minimal:
            print(tx)
        else:
            print(tx.description())

    print("--------------------")
    print("{} total transactions".format(len(transactions)))
    print_usd_exposure()


@cli.command()
def fees():
    events = get_events(loaders.all)
    transactions = get_transactions(events, XDG_CONFIG_HOME + "/mistbat/tx_match.yaml")
    transactions = fmv_transactions(
        transactions, XDG_DATA_HOME + "/mistbat/tx_fmv.yaml"
    )
    transactions = imply_fees(transactions)

    print("\nFees Incurred")
    print("-------------")
    fees = {}
    for tx in transactions:
        fees[tx.__class__.__name__] = fees.get(tx.__class__.__name__, 0) + tx.fee_usd
    for k, v in fees.items():
        print(f"{k}: USD {v:0.2f}")
    print("TOTAL: USD {:0.2f}\n".format(sum(fees.values())))

    print("\nFees Incurred (negative values ignored)")
    print("-----------------------------------------")
    fees = {}
    for tx in transactions:
        fees[tx.__class__.__name__] = fees.get(tx.__class__.__name__, 0) + max(
            tx.fee_usd, 0
        )
    for k, v in fees.items():
        print(f"{k}: USD {v:0.2f}")
    print("TOTAL: USD {:0.2f}\n".format(sum(fees.values())))


@cli.command()
@click.option("--verbose", help="Print progress", is_flag=True, default=False)
def updatefmv(verbose):
    """Update the tx_fmv.yaml file for any missing figures"""
    # Load storage file and events and transactions
    try:
        fmv_raw = yaml.load(open(XDG_DATA_HOME + "/mistbat/tx_fmv.yaml"))
    except FileNotFoundError:
        fmv_raw = {}
    fmv_data = {}
    for id in fmv_raw:
        fmvs = fmv_raw[id].split(" -- ")
        comment = None
        if len(fmvs) == 2:  # If there is a comment
            comment = fmvs[1]
        fmvs = fmvs[0].split()
        fmvs = {fmv.split("@")[0]: fmv.split("@")[1] for fmv in fmvs}
        fmvs["comment"] = comment
        fmv_data[id] = fmvs

    events = get_events(loaders.all)
    transactions = get_transactions(events, XDG_CONFIG_HOME + "/mistbat/tx_match.yaml")

    # Identify missing transactions
    missing = [tx for tx in transactions if tx.missing_fmv and tx.id not in fmv_data]

    # Error-check that stored transactions have necessary FMV info
    stored = [tx for tx in transactions if tx.id in fmv_data]
    for tx in stored:
        stored_coins = set(fmv_data[tx.id].keys())
        stored_coins.remove("comment")
        if set(tx.affected_coins) != stored_coins:
            raise RuntimeError(f"Transaction {tx.id} does not have correct fmv info")

    # Confirm that the tx_fmv file doesn't have any unknown tx ids
    diff = set(id for id in fmv_data) - set(tx.id for tx in transactions)
    diff = ", ".join(diff)
    if len(diff) != 0:
        raise RuntimeError(
            f"Unrecognized transaction ids in tx_fmv.yaml: {diff}. Tip: Dont inlude fiat transaction fmvs."
        )

    # Fill remaining missing transactions with public closing price
    print(f"{len(missing)} missing transactions") if verbose else None
    for tx in missing:
        print(f"{tx.id}")
        fmv_data[tx.id] = {"comment": "from crytpocompare daily close api"}
        for coin in tx.affected_coins:
            coin_fmv = get_historical_close(coin, int(tx.time.timestamp()))
            fmv_data[tx.id][coin] = coin_fmv
            print(f"{coin}@{coin_fmv}\n") if verbose else None
            time.sleep(0.1)

    # Convert fmv_data back into fmv_raw and dump to disk
    fmv_raw = {}
    for id, coins in fmv_data.items():
        comment = coins.pop("comment")
        fmv_raw[id] = " ".join(f"{coin}@{price}" for coin, price in coins.items())
        if comment:
            fmv_raw[id] += " -- " + comment

    yaml.dump(
        fmv_raw,
        open(XDG_DATA_HOME + "/mistbat/tx_fmv.yaml", "w"),
        default_flow_style=False,
    )


@cli.command()
@click.option(
    "--aggregated",
    help="Aggregate single dispositions that can be traced to multiple acquisitions",
    is_flag=True,
    default=False,
)
@click.option(
    "--year", help="Limit report to a particular year", is_flag=False, default=None
)
def tax(aggregated, year):
    """Generate the information needed for IRS Form 8949"""
    events = get_events(loaders.all)
    transactions = get_transactions(events, XDG_CONFIG_HOME + "/mistbat/tx_match.yaml")
    transactions = annotate_transactions(
        transactions, XDG_CONFIG_HOME + "/mistbat/tx_annotations.yaml"
    )
    transactions = fmv_transactions(
        transactions, XDG_DATA_HOME + "/mistbat/tx_fmv.yaml"
    )
    transactions = imply_fees(transactions)

    form_8949 = Form8949(transactions)

    print("SHORT-TERM CAPITAL GAINS")
    table = PrettyTable(
        [
            "(a) Description",
            "(b) Date acquired",
            "(c) Date sold",
            "(d) Proceeds",
            "(e) Basis",
            "(h) Gain",
        ]
    )
    total_gain = 0.00
    for line in form_8949.generate_form(term="short", aggregated=aggregated, year=year):
        table.add_row(line)
        if str(line[-1]).strip():
            total_gain += line[-1]
    print(table)
    print(f"TOTAL SHORT-TERM CAPITAL GAIN: USD {total_gain:0.2f}")

    print("\nLONG-TERM CAPITAL GAINS")
    table = PrettyTable(
        [
            "(a) Description",
            "(b) Date acquired",
            "(c) Date sold",
            "(d) Proceeds",
            "(e) Basis",
            "(h) Gain",
        ]
    )
    total_gain = 0.00
    for line in form_8949.generate_form(term="long", aggregated=aggregated, year=year):
        table.add_row(line)
        if str(line[-1]).strip():
            total_gain += line[-1]
    print(table)
    print(f"TOTAL LONG-TERM CAPITAL GAIN: USD {total_gain:0.2f}")


@cli.command()
@click.option(
    "--harvest",
    help="Add column showing cumulative gain or loss of selling that particular coin",
    is_flag=True,
    default=False,
)
def currentbasis(harvest):
    """See available basis by coin"""
    events = get_events(loaders.all)
    transactions = get_transactions(events, XDG_CONFIG_HOME + "/mistbat/tx_match.yaml")
    transactions = annotate_transactions(
        transactions, XDG_CONFIG_HOME + "/mistbat/tx_annotations.yaml"
    )
    transactions = fmv_transactions(
        transactions, XDG_DATA_HOME + "/mistbat/tx_fmv.yaml"
    )
    transactions = imply_fees(transactions)

    form_8949 = Form8949(transactions)
    print("\nAVAILABLE BASIS REPORT")
    print(
        "Note: Coin totals will slighly deviate from 'holdings' since SENDRECV fees do not impact basis.\n"
    )
    table_headings = [
        "Coin",
        "Date Acquired",
        "Amount",
        "Basis per Coin",
        "Total Basis",
    ]
    if harvest:
        table_headings.append("Cum. G/L at Spot Price")
        spot_prices = get_coin_spot_prices(
            set(form_8949.current_available_basis().keys()))
    table = PrettyTable(table_headings)

    for coin, available_basis in form_8949.current_available_basis().items():
        coin_usd_total = 0.00
        coin_amount_total = 0.00
        cumulative_gain_or_loss = 0.00
        for basis in available_basis:
            time = basis[0].strftime("%Y-%m-%d %H:%M:%S")
            amount = round(basis[1], 8)
            fmv = round(basis[2], 2)
            total = round(amount * fmv, 2)
            row = [coin, time, amount, fmv, total]
            if harvest:
                cumulative_gain_or_loss += (spot_prices[coin] * amount) - (fmv * amount)
                row.append(round(cumulative_gain_or_loss, 2))
            table.add_row(row)
            coin_usd_total += total
            coin_amount_total += amount
        row = ["", "TOTAL", round(coin_amount_total, 8), "", round(coin_usd_total, 2)]
        if harvest:
            row.append("")
        table.add_row(row)
        table.add_row([" "] * len(table.field_names))
    print(table)


@cli.command()
@click.option(
    "--aggregated",
    help="Aggregate holdings irrespective of location (exchange)",
    is_flag=True,
    default=False,
)
def holdings(aggregated):
    """List all coins held with USD values. Also list holdings by exchange."""
    totals = {}
    events = get_events(loaders.all)

    # Get raw accounting-style entries for each event e.g., (coinbase, LTC, +1.00)
    all_entries = [[], [], []]  # location, coin, amount (will be zipped)
    for ev in events:
        entries = ev.entries()
        # Try-catch block needed to deal with single vs multiple entries per event
        try:
            locations, coins, amounts = zip(*entries)
            all_entries[0].extend(locations)
            all_entries[1].extend(coins)
            all_entries[2].extend(amounts)
        except TypeError:
            location, coin, amount = entries
            all_entries[0].append(location)
            all_entries[1].append(coin)
            all_entries[2].append(amount)

    # Process the accounting-style entries into a nested dict of
    # location -> coin -> amount
    for location, coin, amount in zip(*all_entries):
        totals.setdefault(location, {}).setdefault(coin, 0)
        totals[location][coin] += amount

    # Get set of coin symbols to prepare to poll coinmarketcap API
    my_coins = set(all_entries[1])
    my_coins.remove("USD")

    # Poll coinmarketcap API for spot prices of all coins and store them in a dict
    coin_spotprices = get_coin_spot_prices(my_coins)

    total_usd = 0
    location_usd = {}
    total_bycoin = {}
    for location in totals:
        if "USD" in totals[location]:
            del totals[location]["USD"]

        location_usd[location] = 0
        for coin, amount in totals[location].items():
            if round(amount, 9) != 0:
                total_bycoin[coin] = total_bycoin.get(coin, 0) + amount
                location_usd[location] += amount * coin_spotprices[coin]
        # print('Total (in USD) at {}: ${:.2f}\n'.format(location, location_usd))
        total_usd += location_usd[location]

    # If the --aggregated option is passed
    if aggregated:
        # Sort total_bycoin by USD value
        coins_sorted_usd = []
        for coin, amount in total_bycoin.items():
            usd_value = amount * coin_spotprices[coin]
            coins_sorted_usd.append((coin, amount, usd_value))
        coins_sorted_usd.sort(key=lambda x: x[2], reverse=True)

        # Print out the total coin values sorted by value
        for coin in coins_sorted_usd:
            print(
                "{} {:.8f} (USD {:.2f} @ USD {:.2f} per {})".format(
                    coin[0], coin[1], coin[2], coin_spotprices[coin[0]], coin[0]
                )
            )
    # If the --aggregated option is not passed
    else:
        # Sort locations by USD value
        locations = list(totals.keys())
        locations.sort(key=lambda x: location_usd[x], reverse=True)
        for location in locations:
            print("\n{} (USD {:.2f})".format(location, location_usd[location]))

            # Sort coins within a location by USD value
            coins_sorted_usd = []
            for coin, amount in totals[location].items():
                usd_value = amount * coin_spotprices[coin]
                coins_sorted_usd.append((coin, amount, usd_value))
            coins_sorted_usd.sort(key=lambda x: x[2], reverse=True)

            # Print out the total coin values sorted by value
            for coin in coins_sorted_usd:
                if round(coin[1], 9) != 0:
                    print(
                        "    {} {:.8f} (USD {:.2f} @ USD {:.2f} per {})".format(
                            coin[0], coin[1], coin[2], coin_spotprices[coin[0]], coin[0]
                        )
                    )

    print("-----------------")
    print("Total Portfolio Value: USD {:.2f}".format(total_usd))


@cli.command()
@click.argument("exchange")
def remoteupdate(exchange):
    """Fetch updated coinbase information from remote"""
    if exchange == "coinbase":
        loaders.coinbase.update_from_remote()
    elif exchange == "gdax":
        loaders.gdax.update_from_remote()
    elif exchange == "binance":
        loaders.binance.update_from_remote()
    else:
        print("Bad exchange specified.")


if __name__ == "__main__":
    cli()
