import json
from datetime import datetime as dt
from events import *
from xdg import XDG_DATA_HOME

coinmap = {
    'Bitcoin': 'BTC',
    'Ethereum': 'ETH',
    'Litecoin': 'LTC'
}

def update_from_remote():
    pass

def parse_history_txt(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()

    events = []
    for line in lines:
        if len(line.strip()) == 0:
            continue

        fields = line.strip().split('\t')
        if fields[1] == 'Deposit':
            event = Receive(
                time=fields[2],
                coin=coinmap[fields[0]],
                amount=float(fields[3]),
                location='liqui',
                txid=fields[5]
            )
        elif fields[2] == 'Withdraw':
            event = Send(
                time=fields[3],
                coin=coinmap[fields[1]],
                amount=float(fields[4]),
                location='liqui',
                txid=fields[6]
            )
        else:
            raise Exception('Bad liqui history txt file')

        events.append(event)

    return events

def parse_events():
    return parse_history_txt(XDG_DATA_HOME + '/mistbat/liqui_history.txt')

