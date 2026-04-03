"""
config/builder_codes.py — Base ERC-8021 Builder Code Attribution

Base builder codes track our bot's on-chain activity for the Base builder
incentive program. Every transaction sent on Base MUST include the builder
code data suffix to ensure attribution.

Registration:
  - Primary wallet (0x3eb3...): bc_x9vn3djy
  - Wallet B (0x0835...): bc_kfm7ht4z

ERC-8021 spec: The builder code is encoded as a data suffix and appended
to the transaction's `data` field. If no calldata exists, it becomes the
full data payload. If calldata exists, concatenate without the 0x prefix.

⚠️  NEVER send a Base transaction without this suffix.
    There is no error — just silent, permanent invisibility.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Builder Codes (registered via https://api.base.dev/v1/agents/builder-codes)
# ─────────────────────────────────────────────────────────────────────────────

BUILDER_CODES = {
    # Primary wallet
    "0x3eb320fad3f51fe4f2a4531f911ef56694346eef": "bc_x9vn3djy",
    # Wallet B
    "0x0835eb8447f3ac90351951bb5d22e77afd9b81c0": "bc_kfm7ht4z",
}


def get_builder_code(wallet_address: str) -> str:
    """Get the builder code for a registered wallet, or empty string."""
    return BUILDER_CODES.get(wallet_address.lower(), "")


def encode_erc8021_suffix(builder_code: str) -> str:
    """
    Encode a builder code into the ERC-8021 data suffix format.
    
    ERC-8021 format:
      0x + builder_code_utf8_hex + length_prefix
    
    For our codes (e.g., "bc_x9vn3djy" = 12 chars):
      - UTF-8 encode the builder code string
      - Append the byte-length as a 2-byte big-endian value
      - Prepend the ERC-8021 magic bytes (0x00BC8021)
    
    Returns: hex string WITHOUT 0x prefix (ready to concatenate)
    """
    if not builder_code:
        return ""
    
    # Encode builder code as UTF-8 bytes → hex
    code_bytes = builder_code.encode("utf-8")
    code_hex = code_bytes.hex()
    
    # ERC-8021 magic prefix (4 bytes)
    magic = "00bc8021"
    
    # Length of the code in bytes (2-byte big-endian)
    code_len = len(code_bytes)
    length_hex = code_len.to_bytes(2, "big").hex()
    
    # Full suffix: magic + code_hex + length
    return magic + code_hex + length_hex


def get_base_data_suffix(wallet_address: str) -> str:
    """
    Get the full ERC-8021 data suffix for a wallet on Base.
    
    Returns: hex string WITHOUT 0x prefix, ready to concatenate.
    Empty string if wallet not registered.
    """
    code = get_builder_code(wallet_address)
    if not code:
        return ""
    return encode_erc8021_suffix(code)


def append_attribution(tx_data: str, wallet_address: str, chain: str) -> str:
    """
    Append Base builder code attribution to transaction data.
    
    Only applies to Base chain transactions. Returns data unchanged
    for all other chains.
    
    Args:
        tx_data: The transaction's data field (hex string with 0x prefix)
        wallet_address: The sending wallet address
        chain: The chain name (e.g., "base", "ethereum")
    
    Returns:
        Modified data field with ERC-8021 suffix appended (Base only),
        or original data unchanged (other chains).
    """
    if chain != "base":
        return tx_data
    
    suffix = get_base_data_suffix(wallet_address)
    if not suffix:
        return tx_data
    
    # Append suffix to existing data
    if tx_data and tx_data != "0x":
        return tx_data + suffix
    else:
        return "0x" + suffix
