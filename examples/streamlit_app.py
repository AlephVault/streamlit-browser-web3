from __future__ import annotations

ddfrom typing import Any

import streamlit as st
from evm import (
    NETWORKS,
    build_transfer_transaction,
    format_units,
    get_token_balance,
    inspect_erc20,
    parse_address,
)
from streamlit_browser_web3 import wallet_get


st.set_page_config(page_title="streamlit-web3 demo", page_icon=":material/account_balance_wallet:")


def init_state() -> None:
    defaults: dict[str, Any] = {
        "selected_account": None,
        "selected_chain_id": 137,
        "active_chain_request": None,
        "chain_feedback": None,
        "chain_error": None,
        "message_to_sign": "",
        "sign_pending": False,
        "signature_result": None,
        "signature_error": None,
        "token_input": "",
        "token_metadata": None,
        "token_chain_id": None,
        "token_error": None,
        "token_balance": None,
        "recipient_address": "",
        "transfer_amount_wei": "",
        "transfer_pending": False,
        "token_transfer_result": None,
        "token_transfer_error": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def selected_account(handler) -> str | None:
    accounts = handler.accounts
    if not accounts:
        st.session_state.selected_account = None
        return None
    if st.session_state.selected_account not in accounts:
        st.session_state.selected_account = accounts[0]
    return st.session_state.selected_account


def render_section(label: str, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception as exc:
        st.error(f"{label} failed: {exc}")


def render_chain_controls(handler, account: str, *, disabled: bool) -> None:
    st.subheader("Chains")
    current_chain_id = handler.chain_id
    current_label = NETWORKS[current_chain_id].label if current_chain_id in NETWORKS else f"{current_chain_id} - Unknown"

    st.write("Current chain:", current_label)
    st.write("Available chains:", ", ".join(network.label for network in NETWORKS.values()))

    chain_ids = list(NETWORKS.keys())
    if st.session_state.selected_chain_id not in NETWORKS:
        st.session_state.selected_chain_id = chain_ids[0]

    st.selectbox(
        "Choose a chain",
        options=chain_ids,
        format_func=lambda chain_id: NETWORKS[chain_id].label,
        key="selected_chain_id",
        disabled=disabled,
    )
    st.selectbox("Choose an account", options=handler.accounts, key="selected_account", disabled=disabled)

    if st.button("Switch current chain", disabled=disabled or st.session_state.selected_chain_id == current_chain_id):
        target_chain_id = st.session_state.selected_chain_id
        st.session_state.active_chain_request = {
            "stage": "switch",
            "chain_id": target_chain_id,
        }
        st.session_state.chain_feedback = None
        st.session_state.chain_error = None
        handler.forget("switch_chain")
        handler.forget("add_chain")
        handler.forget("switch_chain_after_add")

    active_chain_request = st.session_state.active_chain_request
    if active_chain_request:
        network = NETWORKS[active_chain_request["chain_id"]]
        stage = active_chain_request["stage"]
        if stage == "switch":
            status, result = handler.request(
                "wallet_switchEthereumChain",
                [{"chainId": network.hex_chain_id}],
                key="switch_chain",
            )
            if status == "success":
                st.session_state.chain_feedback = f"Wallet switched to {network.label}."
                st.session_state.active_chain_request = None
            elif status == "error":
                if "4902" in str(result) or "Unrecognized chain ID" in str(result):
                    handler.forget("switch_chain")
                    st.session_state.active_chain_request = {
                        "stage": "add",
                        "chain_id": active_chain_request["chain_id"],
                    }
                else:
                    st.session_state.chain_error = str(result)
                    st.session_state.active_chain_request = None
        elif stage == "add":
            status, result = handler.request("wallet_addEthereumChain", [network.wallet_dict()], key="add_chain")
            if status == "success":
                handler.forget("add_chain")
                st.session_state.active_chain_request = {
                    "stage": "switch-after-add",
                    "chain_id": active_chain_request["chain_id"],
                }
            elif status == "error":
                st.session_state.chain_error = str(result)
                st.session_state.active_chain_request = None
        elif stage == "switch-after-add":
            status, result = handler.request(
                "wallet_switchEthereumChain",
                [{"chainId": network.hex_chain_id}],
                key="switch_chain_after_add",
            )
            if status == "success":
                st.session_state.chain_feedback = f"Wallet added and switched to {network.label}."
                st.session_state.active_chain_request = None
            elif status == "error":
                st.session_state.chain_error = str(result)
                st.session_state.active_chain_request = None

    if st.session_state.active_chain_request:
        st.info("Waiting for wallet confirmation to change chain.")
    if st.session_state.chain_feedback:
        st.success(st.session_state.chain_feedback)
    if st.session_state.chain_error:
        st.error(st.session_state.chain_error)
    st.caption(f"Active account for wallet actions: `{account}`")


def render_personal_sign(handler, account: str, *, disabled: bool) -> None:
    st.subheader("personal_sign")
    st.text_area("Message", key="message_to_sign", height=160, disabled=disabled)

    if st.button("Sign message", disabled=disabled):
        st.session_state.sign_pending = True
        st.session_state.signature_result = None
        st.session_state.signature_error = None
        handler.forget("personal_sign")

    if st.session_state.sign_pending:
        status, result = handler.request(
            "personal_sign",
            ["0x" + st.session_state.message_to_sign.encode("utf-8").hex(), account],
            key="personal_sign",
        )
        if status == "success":
            st.session_state.signature_result = result
            st.session_state.signature_error = None
            st.session_state.sign_pending = False
        elif status == "error":
            st.session_state.signature_error = str(result)
            st.session_state.sign_pending = False

    if st.session_state.sign_pending:
        st.info("Waiting for wallet confirmation to sign the message.")
    st.write("Signature:", st.session_state.signature_result)
    if st.session_state.signature_error:
        st.error(st.session_state.signature_error)


def render_token_selector(chain_id: int, *, disabled: bool) -> None:
    st.subheader("ERC-20 Contract")
    if st.session_state.token_chain_id != chain_id:
        st.session_state.token_metadata = None
        st.session_state.token_error = None
        st.session_state.token_balance = None
        st.session_state.token_transfer_result = None
        st.session_state.token_transfer_error = None
        st.session_state.token_chain_id = chain_id

    st.text_input("Token contract address", key="token_input", disabled=disabled)
    if st.button("Use this contract", disabled=disabled):
        is_token, metadata, error = inspect_erc20(chain_id, st.session_state.token_input.strip())
        st.session_state.token_metadata = metadata if is_token else None
        st.session_state.token_error = error
        st.session_state.token_chain_id = chain_id
        st.session_state.token_balance = None
        st.session_state.token_transfer_result = None
        st.session_state.token_transfer_error = None

    if st.session_state.token_error:
        st.warning(st.session_state.token_error)

    metadata = st.session_state.token_metadata
    if metadata:
        st.write(f"Selected token: {metadata['name']} ({metadata['symbol']}) with {metadata['decimals']} decimals.")


def render_token_balance(chain_id: int, account: str, *, disabled: bool) -> None:
    metadata = st.session_state.token_metadata
    if not metadata:
        return

    st.subheader("Token Balance")
    if st.button("Get token balance", disabled=disabled):
        st.session_state.token_balance = get_token_balance(chain_id, metadata["address"], account)

    st.write("Account:", account)
    st.write("Balance (wei/raw units):", st.session_state.token_balance)
    if st.session_state.token_balance is not None:
        st.write("Balance (formatted):", f"{format_units(st.session_state.token_balance, metadata['decimals'])} {metadata['symbol']}")


def render_token_transfer(handler, account: str, chain_id: int, *, disabled: bool) -> None:
    metadata = st.session_state.token_metadata
    if not metadata:
        return

    st.subheader("Transfer Token")
    st.text_input("Recipient address", key="recipient_address", disabled=disabled)
    st.text_input("Amount in wei", key="transfer_amount_wei", disabled=disabled)

    if st.button("Transfer amount in wei", disabled=disabled):
        st.session_state.transfer_pending = True
        st.session_state.token_transfer_result = None
        st.session_state.token_transfer_error = None
        handler.forget("token_transfer")

    if st.session_state.transfer_pending:
        try:
            recipient = parse_address(st.session_state.recipient_address.strip())
            amount_wei = int(st.session_state.transfer_amount_wei.strip())
            if amount_wei < 0:
                raise ValueError("Amount in wei must be zero or greater.")
            tx = build_transfer_transaction(chain_id, metadata["address"], account, recipient, amount_wei)
            status, result = handler.request(
                "eth_sendTransaction",
                [
                    {
                        key: value
                        for key, value in tx.items()
                        if key in {"from", "to", "data", "value"}
                    }
                ],
                key="token_transfer",
            )
            if status == "success":
                st.session_state.token_transfer_result = result
                st.session_state.token_transfer_error = None
                st.session_state.transfer_pending = False
            elif status == "error":
                st.session_state.token_transfer_error = str(result)
                st.session_state.transfer_pending = False
        except ValueError as exc:
            st.session_state.token_transfer_error = str(exc)
            st.session_state.transfer_pending = False

    if st.session_state.transfer_pending:
        st.info("Waiting for wallet confirmation to send the token transfer.")
    st.write("Transfer result:", st.session_state.token_transfer_result)
    if st.session_state.token_transfer_error:
        st.error(st.session_state.token_transfer_error)


def page_body(handler) -> None:
    account = selected_account(handler)
    if not account:
        st.write("Please disconnect and reconnect after authorizing at least one account.")
        return

    disabled = handler.busy
    chain_id = handler.chain_id
    render_section("Chain controls", render_chain_controls, handler, account, disabled=disabled)
    render_section("Message signing", render_personal_sign, handler, account, disabled=disabled)
    render_section("Token selection", render_token_selector, chain_id, disabled=disabled)
    render_section("Token balance", render_token_balance, chain_id, account, disabled=disabled)
    render_section("Token transfer", render_token_transfer, handler, account, chain_id, disabled=disabled)


def main() -> None:
    init_state()
    st.title("streamlit-web3 demo")
    st.caption("The hidden iframe keeps wallet state and keyed request tracking; interactive wallet requests lock the app UI.")

    handler = wallet_get()
    if handler.last_error:
        st.warning(handler.last_error)

    match handler.status:
        case "not-available":
            st.error("window.ethereum is not available.")
        case "disconnected":
            if st.button("Connect", disabled=handler.busy):
                handler.connect()
        case "connected":
            if st.button("Disconnect", disabled=handler.busy):
                handler.disconnect()
            if handler.busy:
                st.info("A wallet confirmation is pending. Interactive controls are temporarily disabled.")
            page_body(handler)


if __name__ == "__main__":
    main()
