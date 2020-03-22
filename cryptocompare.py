import requests
import pytz

SPOT_ENDPOINT = "https://min-api.cryptocompare.com/data/pricemulti"
HISTORICAL_ENDPOINT = "https://min-api.cryptocompare.com/data/pricehistorical"


def get_coin_spot_prices(coins):
    params = {
        "fsyms": coins,
        "tsyms": ["USD"],
        "extraParams": "mistbat"
    }
    r = requests.get(url=SPOT_ENDPOINT, params=params)
    data = r.json()
    return {coin: data[coin]["USD"] for coin in data}


def get_historical_close(coin, ts):
    params = {
        "fsym": coin,
        "tsyms": "USD",
        "ts": ts,
        "calculationType": "Close",
        "extraParams": "mistbat",
    }

    r = requests.get(url=HISTORICAL_ENDPOINT, params=params)
    data = r.json()

    return data[coin]["USD"]
