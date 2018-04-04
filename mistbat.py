import click
import loaders
from xdg import XDG_CONFIG_HOME
import coinmarketcap
from events import get_events
from transactions import get_transactions, annotate_transactions

def print_usd_exposure():
    """Calculate total amount of USD invested and not redeemed and total fees spent."""
    fiat_events = get_events(loaders.all, 'FiatExchange')
    invested = round(sum(ev.sell_amount for ev in fiat_events if ev.investing), 2)
    redeemed = round(sum(ev.buy_amount for ev in fiat_events if ev.redeeming), 2)
    net_invested = round(invested - redeemed, 2)

    # TODO: should be able to handle things other than FiatExchange
    fees = round(sum(ev.fee_amount for ev in fiat_events), 2)
    print("USD Exposure: {} + {} fees (FIAT ONLY) = {:.2f}".format(net_invested, fees, net_invested + fees))
    print("Aggregate Fee %: {:.2f}%".format(fees * 100 / (invested - redeemed)))

@click.group()
def cli():
    pass

@cli.command()
@click.option('--remote-update', help='Request updated events from exchange APIs',
              is_flag=True, default=False)
def lsev(remote_update):
    """List all events parsed from observations."""
    events = get_events(loaders.all, remote_update=remote_update)
    for ev in events:
        print(ev)

    print("--------------------")
    print("{} total events".format(len(events)))
    print_usd_exposure()

@cli.command()
@click.option('--no-group', help='Only show transactions without a group',
              is_flag=True, default=False)
def lstx(no_group):
    """List all transactions that have been derived from events and annotated."""
    events = get_events(loaders.all)
    transactions = get_transactions(
        events, XDG_CONFIG_HOME + '/mistbat/tx_match.yaml')
    transactions = annotate_transactions(transactions,
                                         XDG_CONFIG_HOME + '/mistbat/tx_annotations.yaml')

    if no_group:
        transactions = [tx for tx in transactions if getattr(tx, 'groups', None) is None]

    # Print transactions
    for tx in transactions:
        print(tx.description())

    print("--------------------")
    print("{} total transactions".format(len(transactions)))
    print_usd_exposure()

@cli.command()
@click.option('--aggregated',
              help='Aggregate holdings irrespective of location (exchange)',
              is_flag=True, default=False)
def holdings(aggregated):
    """List all coins held with USD values. Also list holdings by exchange."""
    totals = {}
    events = get_events(loaders.all)

    # Get raw accounting-style entries for each event e.g., (coinbase, LTC, +1.00)
    all_entries = [[], [], []] # location, coin, amount (will be zipped)
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

    # Poll coinmarketcap API for spot prices of all coins and store them in a dict
    coinstats = coinmarketcap.Market().ticker(limit=0)
    coin_spotprices = {}
    for stat in coinstats:
        # If two or more coins have the same symbol, use the higher-ranked one
        if stat['symbol'] in coin_spotprices:
            continue
        # Some coins are so worthless, their price is 'None'
        if stat['price_usd'] is not None:
            coin_spotprices[stat['symbol']] = float(stat['price_usd'])
        else:
            coin_spotprices[stat['symbol']] = 0.0

    total_usd = 0
    location_usd = {}
    total_bycoin = {}
    for location in totals:
        if 'USD' in totals[location]:
            del totals[location]['USD']

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
            print('{} {:.8f} (USD {:.2f} @ USD {:.2f} per {})'.format(coin[0], coin[1], coin[2], coin_spotprices[coin[0]], coin[0]))
    # If the --aggregated option is not passed
    else:
        # Sort locations by USD value
        locations = list(totals.keys())
        locations.sort(key=lambda x: location_usd[x], reverse=True)
        for location in locations:
            print('\n{} (USD {:.2f})'.format(location, location_usd[location]))

            # Sort coins within a location by USD value
            coins_sorted_usd = []
            for coin, amount in totals[location].items():
                usd_value = amount * coin_spotprices[coin]
                coins_sorted_usd.append((coin, amount, usd_value))
            coins_sorted_usd.sort(key=lambda x: x[2], reverse=True)

            # Print out the total coin values sorted by value
            for coin in coins_sorted_usd:
                if round(coin[1], 9) != 0:
                    print('    {} {:.8f} (USD {:.2f} @ USD {:.2f} per {})'.format(coin[0], coin[1], coin[2], coin_spotprices[coin[0]], coin[0]))

    print("-----------------")
    print("Total Portfolio Value: USD {:.2f}".format(total_usd))

if __name__ == '__main__':
    cli()
