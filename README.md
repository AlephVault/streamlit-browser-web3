# streamlit-web3

`streamlit-web3` packages a hidden Streamlit component that bridges a browser-injected EIP-1193 wallet provider into
Web3.py.

## Install

```bash
pip install streamlit-web3
```

## Minimal usage

```python
import streamlit as st

from streamlit_browser_web3 import wallet_get

handler = wallet_get()
if handler.status == "connected":
    if st.button("Disconnect your wallet"):
        handler.disconnect()
    page_body(handler)
else:
    if st.button("Connect your wallet"):
        handler.connect()
```

## Important Streamlit behavior

Wallet operations are asynchronous in the browser but Streamlit scripts are synchronous and rerun-driven.

- `wallet_get()` must be rendered on every rerun.
- A wallet request may complete over multiple reruns.
- For button-triggered Web3 calls, persist the user intent in `st.session_state` until the call returns.
- Requests are serialized through the hidden browser bridge.

Chain metadata and ERC-20 helper code are intentionally kept in the example app, not in the package.

## Handler API

`wallet_get()` returns a `WalletHandler` instance. Render it on every rerun and use the same handler object as your app's wallet state interface.

### State properties

- `handler.status`: One of `"not-available"`, `"disconnected"`, or `"connected"`.
- `handler.available`: `True` when an injected browser provider such as `window.ethereum` exists.
- `handler.connected`: `True` when the wallet is connected and at least one account is available.
- `handler.accounts`: List of currently exposed account addresses.
- `handler.chain_id`: Current chain id as an `int`, or `None`.
- `handler.chain_id_hex`: Current chain id as a hex string such as `"0x1"`, or `None`.
- `handler.busy`: `True` while a connect/disconnect action or an interactive wallet request is still pending.
- `handler.last_error`: Last wallet or bridge error message, if any.
- `handler.snapshot`: Raw snapshot dictionary returned by the hidden browser component.

### Methods

- `handler.connect()`: Starts the wallet connection flow and reruns the Streamlit script.
- `handler.disconnect()`: Starts the wallet disconnect flow and reruns the Streamlit script.
- `handler.request(method, params=None, *, key)`: Sends an EIP-1193 request and returns `(status, result)`.
- `handler.get_request_status(key)`: Returns the current status + result of a given request, or `None` if it does not exist.
- `handler.forget(key)`: Removes a tracked request so the same key can be reused for a new flow.
- `handler.snapshot_view()`: Returns a typed `WalletSnapshot` dataclass with the main handler fields.

### `request()` status values

`handler.request(...)` returns a `(status, result)` tuple:

- `"pending"`: The wallet request is still waiting for completion in the browser.
- `"success"`: The request completed successfully and `result` contains the returned value.
- `"error"`: The request failed and `result` contains an error message.

The `key` argument is required. Requests are tracked by key across reruns, which lets button-triggered flows continue until the browser returns a result.

### Supported request methods

The handler has built-in support for these immediate methods, which resolve from the current snapshot without opening a wallet prompt:

- `eth_accounts`
- `eth_chainId`
- `eth_coinbase`
- `net_version`

The handler also marks these methods as interactive, meaning they can leave `handler.busy == True` while the wallet is waiting for user confirmation:

- `eth_requestAccounts`
- `eth_sendTransaction`
- `eth_sign`
- `eth_signTransaction`
- `eth_signTypedData`
- `eth_signTypedData_v1`
- `eth_signTypedData_v3`
- `eth_signTypedData_v4`
- `personal_sign`
- `wallet_addEthereumChain`
- `wallet_requestPermissions`
- `wallet_revokePermissions`
- `wallet_switchEthereumChain`

Other provider methods can still be passed to `handler.request(...)`. They are tracked as non-interactive requests unless they are in the interactive list above.

## Build

```bash
python -m build
```

## Example app

An end-to-end example is included at `examples/streamlit_app.py`.
