from eth_typing import (
    ChecksumAddress,
    HexAddress,
    HexStr,
)
from hexbytes import (
    HexBytes,
)

ACCEPTABLE_STALE_HOURS = 48

AUCTION_START_GAS_CONSTANT = 25000
AUCTION_START_GAS_MARGINAL = 39000

EMPTY_SHA3_BYTES = HexBytes(b'\0' * 32)
EMPTY_ADDR_HEX = HexAddress(HexStr('0x' + '00' * 20))

REVERSE_REGISTRAR_DOMAIN = 'addr.reverse'

RESOLVER_EIP1577_INTERFACE = '0xbc1c58d1'
RESOLVER_LEGACY_INTERFACE = '0xd8389dc5'

ENS_PUBLIC_ADDR = ChecksumAddress(HexAddress(HexStr('0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e')))
