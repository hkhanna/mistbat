# mistbat cryptocurrency portfolio and tax analyzer
## Usage
`python mistbat.py --help` - information on commands and options

- `python mistbat.py lsev [--remote-update]` - list all events
- `python mistbat.py lstx [--no-group]` - list all transactions
- `python mistbat.py holdings [--aggregated]` - list all current holdings
- `python mistbat.py updatefmv` - update any missing fmvs
- `python mistbat.py tax [--aggregated] [--year]` - prepare form 8949. Use the aggregated switch and pass the year.
- `python mistbat.py currentbasis [--harvest]` - show available basis, with optional insight into how to harvest tax losses

## Configuration
All configuration files are stored in `~/.config/mistbat/` or another directory defined by the XDG_CONFIG_HOME environment variables.

### secrets.yaml
Contains the API keys and secrets for exchanges.
```
binance:
  api_key: KEY
  secret_key: KEY
coinbase:
  api_key: KEY
  secret_key: KEY
gdax:
  api_key: KEY
  secret_key: KEY
  passphrase: PHRASE
```

### tx_match.yaml
Contains information on how to match Send and Recv events and Shapeshift events.

### tx_annotations.yaml
Annotations to apply to each transaction. Annotations are things like notes and which groups the transaction belongs to.

### manual_obs.yaml
Any manually specified observations go in this file. This would include things like transactions that are not on an exchange, e.g., between electrum wallets.

## How It Works
### Nomenclature 
- "observations" (obs) are raw transaction data I'm getting from somewhere like coinbase
- "events" (ev) are objects Send, Receive, Exchange generated directly from observations
- "transactions" (tx) are SendReceive (a pair of Send and Receive events) or, if it's not a transaction between my wallets, it can be a Spend (lone Send) or Earn (lone Receive for earning/gaining money). It can also be ExchangeTx which is just an Exchange event promoted to a transaction.

### Procedure
1. Loads the transaction history for each exchange via the API if possible
1. Saves the raw responses from each service
1. Loader for each exchange has a parser that parses raw response and turns it into Event objects (e.g., Send, Receive, Exchange)
1. A separate "annotations" file adds information to each transaction that cannot be obtained from the exchange (e.g., my notes about the trade).
1. The fmv information is added to each transaction where it hasn't been provided by the loader. It pulls the data from a cached file. If the fmv info isn't available, it will exit and ask you to run `updatefmv` to get the data.
1. The transactions are processed with the annotations and the modified transactions are returned.
1. Every Send event must have a corresponding Receive event and it can imply the fee
implied fee
1. On coinbase, sent amount includes fee, received amount does not
1. Event ids are in the form of a three letter code for the exchange and a 5 char hash generated from the event data. e.g., coi-42ih5 
1. Transaction ids are in the same form, except the exchange code has x appended, and 
1. If its a SendReceive tx, then the four letter code is srtx (since its not just one exchange). The 5 character hash is the last two characters from the send hash, a '/' character and the last two characters from the receive hash.
1. With a list of all transactions, can do whatever analysis that needs to be done.

### Tax
1. We get the fmv of cryptocurrencies that were not provided by the loader by polling the cryptocompare API and saving the fmv of the currency. The number we get is for EOD GMT.
2. For exchanges between cryptocurrencies, we "imply" the fee based on the fmvs of the exchanged coins. A lot of times, this results in a negative fee (probably due to fluctuations in prices before fmv is captured at EOD), in which case we just say the fee is 0 for tax purposes. 
3. We always use the "implied" fee rather than the reported fee, since the missing value in the exchange is really the fee in the transaction.
