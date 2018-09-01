import requests
import pytz

ENDPOINT = 'https://min-api.cryptocompare.com/data/pricehistorical'

def get_historical_close(coin, ts):
    params = {
        "fsym": coin,
        "tsyms": 'USD',
        "ts": ts,
        "calculationType": "Close",
        "extraParams": "mistbat"
    }

    r = requests.get(url=ENDPOINT, params=params)
    data = r.json()

    return data[coin]['USD']