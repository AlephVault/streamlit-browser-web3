from __future__ import annotations
import json
import time
from dataclasses import dataclass
from importlib.resources import as_file, files
from typing import Any
import streamlit as st
import streamlit.components.v1 as components


with as_file(files("streamlit_web3").joinpath("frontend/provider")) as _component_root:
    _wallet_component = components.declare_component(
        "streamlit_browser_web3_wallet_component",
        path=str(_component_root),
    )


INTERACTIVE_METHODS = {
    "eth_requestAccounts",
    "eth_sendTransaction",
    "eth_sign",
    "eth_signTransaction",
    "eth_signTypedData",
    "eth_signTypedData_v1",
    "eth_signTypedData_v3",
    "eth_signTypedData_v4",
    "personal_sign",
    "wallet_addEthereumChain",
    "wallet_requestPermissions",
    "wallet_revokePermissions",
    "wallet_switchEthereumChain",
}


IMMEDIATE_METHODS = {
    "eth_accounts",
    "eth_chainId",
    "eth_coinbase",
    "net_version",
}


@dataclass(frozen=True)
class WalletSnapshot:
    status: str
    busy: bool
    chain_id: int | None
    chain_id_hex: str | None
    accounts: list[str]
    available: bool
    connected: bool
    last_error: str | None


_STATE_DEFAULTS: dict[str, Any] = {
    "snapshot": {
        "providerAvailable": False,
        "connected": False,
        "accounts": [],
        "chainIdHex": None,
        "chainIdDecimal": None,
    },
    "pending_action": None,
    "action_counter": 0,
    "request_counter": 0,
    "requests": {},
    "last_error": None,
}


def _namespace(key: str) -> str:
    return f"streamlit_web3:{key}"


def _state_get(key: str) -> dict[str, Any]:
    namespaced = _namespace(key)
    if namespaced not in st.session_state:
        st.session_state[namespaced] = {
            name: value.copy() if isinstance(value, dict) else value
            for name, value in _STATE_DEFAULTS.items()
        }
    return st.session_state[namespaced]


def _json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _fingerprint(method: str, params: Any) -> str:
    return json.dumps({"method": method, "params": params}, sort_keys=True, default=_json_default)


def _is_interactive(method: str) -> bool:
    return method in INTERACTIVE_METHODS


def _pending_requests_payload(state: dict[str, Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for slot in state["requests"].values():
        if slot.get("status") != "pending":
            continue
        payload.append(
            {
                "requestId": slot["request_id"],
                "method": slot["method"],
                "params": slot["params"],
                "interactive": slot["interactive"],
            }
        )
    return payload


class WalletHandler:
    def __init__(self, *, state: dict[str, Any]) -> None:
        self._state = state

    def connect(self) -> None:
        self._state["action_counter"] = int(self._state.get("action_counter", 0)) + 1
        self._state["pending_action"] = {
            "action": "connect",
            "nonce": self._state["action_counter"],
            "created_at": time.time(),
        }
        st.rerun()

    def disconnect(self) -> None:
        self._state["action_counter"] = int(self._state.get("action_counter", 0)) + 1
        self._state["pending_action"] = {
            "action": "disconnect",
            "nonce": self._state["action_counter"],
            "created_at": time.time(),
        }
        st.rerun()

    @property
    def available(self) -> bool:
        """
        Tells whether the provider is available in the browser
        or not (i.e. window.ethereum being injected or not).
        """

        return bool(self.snapshot.get("providerAvailable"))

    @property
    def connected(self) -> bool:
        """
        Tells whether the wallet is connected or not.
        """

        snapshot = self.snapshot
        return bool(snapshot.get("connected")) and bool(snapshot.get("accounts"))

    @property
    def accounts(self) -> list[str]:
        """
        Gets the list of available accounts.
        """

        return list(self.snapshot.get("accounts") or [])

    @property
    def chain_id(self) -> int | None:
        """
        Gets the current chain id.
        """

        return self.snapshot.get("chainIdDecimal")

    @property
    def chain_id_hex(self) -> str | None:
        """
        Returns the hex. version of the chain id.
        """
        return self.snapshot.get("chainIdHex")

    @property
    def snapshot(self) -> dict[str, Any]:
        """
        Gets a snapshot of the current state.
        """

        return self._state["snapshot"]

    @property
    def busy(self) -> bool:
        """
        Tells whether there is a long-running interactive
        method being executed at this time. Only one of
        those methods can run at once.
        """

        if self._state.get("pending_action"):
            return True
        return any(slot.get("status") == "pending" and slot.get("interactive")
                   for slot in self._state["requests"].values())

    @property
    def last_error(self) -> str | None:
        """
        Gets the last error, if any.
        """

        return self._state.get("last_error")

    @property
    def status(self) -> str:
        """
        The status means:
        - not-available: There's no injected provider like window.ethereum.
        - disconnected: The provider exists, but it is not connected.
        - connected: The provider is connected and can be used.
        :return:
        """

        if not self.available:
            return "not-available"
        if not self.connected:
            return "disconnected"
        return "connected"

    def snapshot_view(self) -> WalletSnapshot:
        """
        Gets a snapshot of the current state, in a structured
        format.
        """

        return WalletSnapshot(
            status=self.status,
            busy=self.busy,
            chain_id=self.chain_id,
            chain_id_hex=self.chain_id_hex,
            accounts=self.accounts,
            available=self.available,
            connected=self.connected,
            last_error=self.last_error,
        )

    def forget(self, key: str) -> None:
        """
        Pops a particular request.
        :param key: The request key to forget / stop tracking.
        """

        self._state["requests"].pop(key, None)

    def request(self, method: str, params: list[Any] | None = None, *, key: str) -> tuple[str, Any]:
        """
        Performs a request with the given method and params. Certain
        methods are deemed interactive. A key is always mandatory so
        the request can be tracked.

        Certain methods are interactive and will mark this provider
        as .busy. Make sure you don't invoke two concurrent methods
        like this, and always account for the .busy flag somewhere
        before invoking these methods.
        :param method: The RPC method name.
        :param params: The RPC method params.
        :param key: The key of this request.
        :return: The result of the request (status, content), where
            status is "success", "error" or "pending" and the content
            can be any valid content for the "error" status (a detail
            on the failure) or "success" (e.g. the tx. receipt hash).
        """

        params = params or []

        if method in IMMEDIATE_METHODS:
            return "success", self._immediate_result(method)

        if not self.available:
            return "error", "window.ethereum is not available"

        interactive = _is_interactive(method)
        slot = self._state["requests"].get(key)
        fingerprint = _fingerprint(method, params)

        if slot and slot["fingerprint"] != fingerprint:
            if slot["status"] == "pending":
                return "error", f"Request key `{key}` already has a different pending request."
            self.forget(key)
            slot = None

        if interactive and self.busy and not (slot and slot["status"] == "pending" and slot["interactive"]):
            return "error", "Another interactive wallet request is already pending."

        if slot:
            if slot["status"] == "pending":
                return "pending", None
            if slot["status"] == "success":
                return "success", slot.get("result")
            return "error", slot.get("error")

        request_id = self._next_counter("request_counter")
        self._state["requests"][key] = {
            "request_id": request_id,
            "key": key,
            "method": method,
            "params": params,
            "fingerprint": fingerprint,
            "interactive": interactive,
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }
        st.rerun()

    def _immediate_result(self, method: str) -> Any:
        if method == "eth_accounts":
            return self.accounts
        if method == "eth_chainId":
            return self.chain_id_hex
        if method == "eth_coinbase":
            return self.accounts[0] if self.accounts else None
        if method == "net_version":
            return str(self.chain_id) if self.chain_id is not None else None
        raise ValueError(f"Unsupported immediate method: {method}")

    def _next_counter(self, counter_name: str) -> int:
        self._state[counter_name] = int(self._state.get(counter_name, 0)) + 1
        return self._state[counter_name]


def _sync_component_value(state: dict[str, Any], component_value: dict[str, Any]) -> None:
    if not isinstance(component_value, dict):
        return

    snapshot = component_value.get("snapshot")
    if isinstance(snapshot, dict):
        state["snapshot"] = snapshot

    error = component_value.get("error")
    if error:
        state["last_error"] = error

    action_result = component_value.get("lastActionResult") or {}
    pending_action = state.get("pending_action")
    if pending_action and action_result.get("nonce") == pending_action.get("nonce"):
        state["pending_action"] = None
        if action_result.get("error"):
            state["last_error"] = action_result["error"]

    request_results = component_value.get("requestResults") or {}
    requests_by_id = {slot["request_id"]: slot for slot in state["requests"].values()}
    for raw_request_id, result in request_results.items():
        try:
            request_id = int(raw_request_id)
        except (TypeError, ValueError):
            continue
        slot = requests_by_id.get(request_id)
        if not slot or slot["status"] != "pending":
            continue
        if result.get("status") == "success":
            slot["status"] = "success"
            slot["result"] = result.get("result")
            slot["error"] = None
        else:
            slot["status"] = "error"
            slot["error"] = result.get("error") or "Wallet request failed."
            slot["result"] = None
            state["last_error"] = slot["error"]


def wallet_get() -> WalletHandler:
    """
    Gets a wallet handler. Meant to be used as a singleton call.
    :return:
    """

    key = "__handler__"
    state = _state_get(key)
    component_value = _wallet_component(
        key=f"streamlit_web3_wallet_component:{key}",
        default={},
        action=state.get("pending_action"),
        requests=_pending_requests_payload(state),
        hidden=True,
    )
    _sync_component_value(state, component_value if isinstance(component_value, dict) else {})
    return WalletHandler(state=state)
