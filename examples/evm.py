from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import streamlit as st
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError


ERC20_ABI: list[dict[str, Any]] = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
        "stateMutability": "view",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
        "stateMutability": "view",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
        "stateMutability": "view",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
        "stateMutability": "nonpayable",
    },
]


@dataclass(frozen=True)
class NetworkConfig:
    chain_id: int
    label: str
    chain_name: str
    rpc_env: str
    default_rpc: str
    native_currency: dict[str, Any]
    block_explorer_urls: list[str]

    @property
    def hex_chain_id(self) -> str:
        return hex(self.chain_id)

    @property
    def rpc_url(self) -> str:
        try:
            secret_value = st.secrets.get(self.rpc_env)
        except Exception:
            secret_value = None
        return secret_value or os.environ.get(self.rpc_env, self.default_rpc)

    def wallet_dict(self) -> dict[str, Any]:
        return {
            "chainId": self.hex_chain_id,
            "chainName": self.chain_name,
            "rpcUrls": [self.rpc_url],
            "nativeCurrency": self.native_currency,
            "blockExplorerUrls": self.block_explorer_urls,
        }


NETWORKS: dict[int, NetworkConfig] = {
    8453: NetworkConfig(
        chain_id=8453,
        label="8453 - Base",
        chain_name="Base Mainnet",
        rpc_env="BASE_RPC_URL",
        default_rpc="https://mainnet.base.org",
        native_currency={"name": "Ether", "symbol": "ETH", "decimals": 18},
        block_explorer_urls=["https://basescan.org"],
    ),
    84532: NetworkConfig(
        chain_id=84532,
        label="84532 - Base Sepolia",
        chain_name="Base Sepolia",
        rpc_env="BASE_SEPOLIA_RPC_URL",
        default_rpc="https://sepolia.base.org",
        native_currency={"name": "Ether", "symbol": "ETH", "decimals": 18},
        block_explorer_urls=["https://sepolia.basescan.org"],
    ),
    137: NetworkConfig(
        chain_id=137,
        label="137 - Polygon",
        chain_name="Polygon Mainnet",
        rpc_env="POLYGON_RPC_URL",
        default_rpc="https://polygon-rpc.com",
        native_currency={"name": "MATIC", "symbol": "POL", "decimals": 18},
        block_explorer_urls=["https://polygonscan.com"],
    ),
    80002: NetworkConfig(
        chain_id=80002,
        label="80002 - Amoy",
        chain_name="Polygon Amoy",
        rpc_env="AMOY_RPC_URL",
        default_rpc="https://rpc-amoy.polygon.technology",
        native_currency={"name": "MATIC", "symbol": "POL", "decimals": 18},
        block_explorer_urls=["https://amoy.polygonscan.com"],
    ),
    31337: NetworkConfig(
        chain_id=31337,
        label="31337 - Local",
        chain_name="Localhost 8545",
        rpc_env="LOCAL_RPC_URL",
        default_rpc="http://127.0.0.1:8545",
        native_currency={"name": "Ether", "symbol": "ETH", "decimals": 18},
        block_explorer_urls=[],
    ),
    1: NetworkConfig(
        chain_id=1,
        label="1 - Ethereum Mainnet",
        chain_name="Ethereum Mainnet",
        rpc_env="ETHEREUM_RPC_URL",
        default_rpc="https://api.zan.top/eth-mainnet",
        native_currency={"name": "Ether", "symbol": "ETH", "decimals": 18},
        block_explorer_urls=["https://etherscan.io"],
    ),
    11155111: NetworkConfig(
        chain_id=11155111,
        label="11155111 - Ethereum Sepolia",
        chain_name="Ethereum Sepolia",
        rpc_env="SEPOLIA_RPC_URL",
        default_rpc="https://rpc.sepolia.org",
        native_currency={"name": "Ether", "symbol": "ETH", "decimals": 18},
        block_explorer_urls=["https://sepolia.etherscan.io"],
    ),
}


@st.cache_resource(show_spinner=False)
def read_web3(chain_id: int, rpc_url: str) -> Web3:
    return Web3(Web3.HTTPProvider(rpc_url))


def get_read_web3(chain_id: int) -> Web3:
    network = NETWORKS[chain_id]
    return read_web3(chain_id, network.rpc_url)


def parse_address(raw_value: str) -> str:
    if not raw_value:
        raise ValueError("Address is required.")
    if not Web3.is_address(raw_value):
        raise ValueError("Invalid Ethereum address.")
    return Web3.to_checksum_address(raw_value)


def current_contract(chain_id: int, address: str) -> Contract:
    return get_read_web3(chain_id).eth.contract(address=address, abi=ERC20_ABI)


def inspect_erc20(chain_id: int, raw_address: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        address = parse_address(raw_address)
    except ValueError as exc:
        return False, None, str(exc)

    try:
        contract = current_contract(chain_id, address)
        code = contract.w3.eth.get_code(address)
        if not code or code == b"":
            return False, None, "The address has no contract code on the selected chain."

        total_supply = contract.functions.totalSupply().call()
        decimals = contract.functions.decimals().call()
        _ = contract.functions.balanceOf("0x0000000000000000000000000000000000000000").call()

        try:
            symbol = contract.functions.symbol().call()
        except Exception:
            symbol = "UNKNOWN"

        try:
            name = contract.functions.name().call()
        except Exception:
            name = "Unnamed token"

        return True, {
            "address": address,
            "name": name,
            "symbol": symbol,
            "decimals": decimals,
            "total_supply": total_supply,
            "total_supply_formatted": format_units(total_supply, decimals),
        }, None
    except (ContractLogicError, ValueError) as exc:
        return False, None, f"Contract call failed: {exc}"
    except Exception as exc:
        return False, None, f"Could not inspect contract: {exc}"


def get_token_balance(chain_id: int, token_address: str, account: str) -> int:
    return current_contract(chain_id, token_address).functions.balanceOf(parse_address(account)).call()


def build_transfer_transaction(
    chain_id: int,
    token_address: str,
    from_address: str,
    to_address: str,
    amount_wei: int,
) -> dict[str, Any]:
    return current_contract(chain_id, token_address).functions.transfer(
        to_address,
        amount_wei,
    ).build_transaction({"from": from_address})


def format_units(value: int, decimals: int) -> str:
    scaled = Decimal(value) / (Decimal(10) ** decimals)
    return format(scaled.normalize(), "f")
