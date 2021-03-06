import copy
import datetime
import functools
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Dict,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
)

import content_hash
from eth_typing import (
    Address,
    ChecksumAddress,
    HexAddress,
    HexStr,
)
from eth_utils import (
    is_same_address,
    remove_0x_prefix,
    to_normalized_address,
)
from hexbytes import (
    HexBytes,
)
import idna

from ens.constants import (
    ACCEPTABLE_STALE_HOURS,
    AUCTION_START_GAS_CONSTANT,
    AUCTION_START_GAS_MARGINAL,
    EMPTY_ADDR_HEX,
    EMPTY_SHA3_BYTES,
    RESOLVER_EIP1577_INTERFACE,
    RESOLVER_LEGACY_INTERFACE,
    REVERSE_REGISTRAR_DOMAIN,
)
from ens.exceptions import (
    InvalidName,
    NonStandardResolver,
)

default = object()


if TYPE_CHECKING:
    from web3 import Web3 as _Web3  # noqa: F401
    from web3.contract import (  # noqa: F401
        Contract,
    )
    from web3.providers import (  # noqa: F401
        BaseProvider,
    )


def Web3() -> Type['_Web3']:
    from web3 import Web3 as Web3Main
    return Web3Main


TFunc = TypeVar("TFunc", bound=Callable[..., Any])


def dict_copy(func: TFunc) -> TFunc:
    "copy dict keyword args, to avoid modifying caller's copy"
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> TFunc:
        copied_kwargs = copy.deepcopy(kwargs)
        return func(*args, **copied_kwargs)
    return cast(TFunc, wrapper)


def ensure_hex(data: HexBytes) -> HexBytes:
    if not isinstance(data, str):
        return Web3().toHex(data)
    return data


def init_web3(provider: 'BaseProvider'=cast('BaseProvider', default)) -> '_Web3':
    from web3 import Web3 as Web3Main

    if provider is default:
        w3 = Web3Main(ens=None)
    else:
        w3 = Web3Main(provider, ens=None)

    return customize_web3(w3)


def customize_web3(w3: '_Web3') -> '_Web3':
    from web3.middleware import make_stalecheck_middleware
    from web3.middleware import geth_poa_middleware

    w3.middleware_onion.remove('name_to_address')

    w3.middleware_onion.add(
        make_stalecheck_middleware(ACCEPTABLE_STALE_HOURS * 3600),
        name='stalecheck',
    )

    w3.middleware_onion.inject(
        geth_poa_middleware,
        layer=0,
    )

    return w3


def normalize_name(name: str) -> str:
    """
    Clean the fully qualified name, as defined in ENS `EIP-137
    <https://github.com/ethereum/EIPs/blob/master/EIPS/eip-137.md#name-syntax>`_

    This does *not* enforce whether ``name`` is a label or fully qualified domain.

    :param str name: the dot-separated ENS name
    :raises InvalidName: if ``name`` has invalid syntax
    """
    if not name:
        return name
    elif isinstance(name, (bytes, bytearray)):
        name = name.decode('utf-8')

    try:
        return idna.uts46_remap(name, std3_rules=True)
    except idna.IDNAError as exc:
        raise InvalidName(f"{name} is an invalid name, because {exc}") from exc


def is_valid_name(name: str) -> bool:
    """
    Validate whether the fully qualified name is valid, as defined in ENS `EIP-137
    <https://github.com/ethereum/EIPs/blob/master/EIPS/eip-137.md#name-syntax>`_

    :param str name: the dot-separated ENS name
    :returns: True if ``name`` is set, and :meth:`~ens.main.ENS.nameprep` will not raise InvalidName
    """
    if not name:
        return False
    try:
        normalize_name(name)
        return True
    except InvalidName:
        return False


def to_utc_datetime(timestamp: float) -> Optional[datetime.datetime]:
    if timestamp:
        return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
    else:
        return None


def sha3_text(val: Union[str, bytes]) -> HexBytes:
    if isinstance(val, str):
        val = val.encode('utf-8')
    return Web3().keccak(val)


def label_to_hash(label: str) -> HexBytes:
    label = normalize_name(label)
    if '.' in label:
        raise ValueError("Cannot generate hash for label %r with a '.'" % label)
    return Web3().keccak(text=label)


def normal_name_to_hash(name: str) -> HexBytes:
    node = EMPTY_SHA3_BYTES
    if name:
        labels = name.split(".")
        for label in reversed(labels):
            labelhash = label_to_hash(label)
            assert isinstance(labelhash, bytes)
            assert isinstance(node, bytes)
            node = Web3().keccak(node + labelhash)
    return node


def raw_name_to_hash(name: str) -> HexBytes:
    """
    Generate the namehash. This is also known as the ``node`` in ENS contracts.

    In normal operation, generating the namehash is handled
    behind the scenes. For advanced usage, it is a helpful utility.

    This normalizes the name with `nameprep
    <https://github.com/ethereum/EIPs/blob/master/EIPS/eip-137.md#name-syntax>`_
    before hashing.

    :param str name: ENS name to hash
    :return: the namehash
    :rtype: bytes
    :raises InvalidName: if ``name`` has invalid syntax
    """
    normalized_name = normalize_name(name)
    return normal_name_to_hash(normalized_name)


def address_in(address: ChecksumAddress, addresses: Collection[ChecksumAddress]) -> bool:
    return any(is_same_address(address, item) for item in addresses)


def address_to_reverse_domain(address: ChecksumAddress) -> str:
    lower_unprefixed_address = remove_0x_prefix(HexStr(to_normalized_address(address)))
    return lower_unprefixed_address + '.' + REVERSE_REGISTRAR_DOMAIN


def estimate_auction_start_gas(labels: Collection[str]) -> int:
    return AUCTION_START_GAS_CONSTANT + AUCTION_START_GAS_MARGINAL * len(labels)


def assert_signer_in_modifier_kwargs(modifier_kwargs: Any) -> ChecksumAddress:
    ERR_MSG = "You must specify the sending account"
    assert len(modifier_kwargs) == 1, ERR_MSG

    _modifier_type, modifier_dict = dict(modifier_kwargs).popitem()
    if 'from' not in modifier_dict:
        raise TypeError(ERR_MSG)

    return modifier_dict['from']


def is_none_or_zero_address(addr: Union[Address, ChecksumAddress, HexAddress]) -> bool:
    return not addr or addr == EMPTY_ADDR_HEX


def resolve_content_record(
    resolver: 'Contract', name: str
) -> Optional[Dict[str, str]]:
    is_eip1577 = resolver.functions.supportsInterface(RESOLVER_EIP1577_INTERFACE).call()
    is_legacy = resolver.functions.supportsInterface(RESOLVER_LEGACY_INTERFACE).call()

    namehash = normal_name_to_hash(name)

    if is_eip1577:
        raw_content_hash = resolver.functions.contenthash(namehash).call().hex()

        if is_none_or_zero_address(raw_content_hash):
            return None

        decoded_content_hash = content_hash.decode(raw_content_hash)
        type_content_hash = content_hash.get_codec(raw_content_hash)

        return {
            'type': type_content_hash,
            'hash': decoded_content_hash,
        }

    if is_legacy:
        content = resolver.functions.content(namehash).call()

        if is_none_or_zero_address(content):
            return None

        return {
            'type': None,
            'hash': content.hex(),
        }

    raise NonStandardResolver('Resolver should either supports contenthash() or content()')


def resolve_other_record(
    resolver: 'Contract', get: str, name: str
) -> Optional[Union[ChecksumAddress, str]]:
    lookup_function = getattr(resolver.functions, get)
    namehash = normal_name_to_hash(name)
    address = lookup_function(namehash).call()

    if is_none_or_zero_address(address):
        return None

    return address
