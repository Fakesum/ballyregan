from __future__ import annotations
from itertools import chain
from typing import Any, List, Optional
from asyncio import AbstractEventLoop
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from . import Proxy
from .models import Protocols, Anonymities
from .core.exceptions import NoProxiesFound, NoInternetConnection
from .core.logger import init_logger
from .core.utils import has_internet_connection, get_event_loop
from .validator import ProxyValidator
from .filterer import ProxyFilterer
from .providers import IProxyProvider, FreeProxyListProvider, GeonodeProvider, SSLProxiesProvider, USProxyProvider, ProxyListDownloadProvider, SocksProxyProvider


@dataclass
class ProxyFetcher:
    _proxy_providers: List[IProxyProvider] = field(
        default_factory=lambda: [
            SSLProxiesProvider(),
            FreeProxyListProvider(),
            GeonodeProvider(),
            USProxyProvider(),
            ProxyListDownloadProvider(),
            SocksProxyProvider(),
        ]
    )
    _proxy_validator: ProxyValidator = None
    _proxy_filterer: ProxyFilterer = None
    loop: AbstractEventLoop = None
    debug: bool = False

    def __post_init__(self) -> None:
        if not has_internet_connection():
            raise NoInternetConnection

        if not self._proxy_filterer:
            self._proxy_filterer = ProxyFilterer()

        if not self._proxy_validator:
            self._proxy_validator = self.__new_validator()

    def __setattr__(self, __name: str, __value: Any) -> None:
        if __name == 'debug':
            init_logger(__value)

        super().__setattr__(__name, __value)

    def __new_validator(self) -> ProxyValidator:
        if self.loop:
            return ProxyValidator(loop=self.loop)

        self.loop = get_event_loop()
        return ProxyValidator(loop=self.loop)

    def _get_all_proxies_from_providers(self) -> None:
        """Iterates through all the providers, gather proxies and returns them.
        """
        logger.debug('Gathering all proxies from providers')
        with ThreadPoolExecutor(max_workers=max(len(self._proxy_providers), 1)) as executor:
            proxies_generator = executor.map(
                lambda provider: provider.gather(),
                self._proxy_providers
            )
        logger.debug('Finished gathering all proxies from providers')

        return list(set(chain.from_iterable(proxies_generator)))

    def _gather(self, protocols: List[Protocols] = [], anonymities: List[Anonymities] = [], limit: int = 0) -> None:
        """Gathers proxies from providers, validates them and stores them in the proxies queue.

        Args:
            limit (int, optional): The amount proxies to gather.
            When 0, ProxyManager will gather everything. Defaults to 0.
            protocols (List[str], optional): The allowed protocols of proxy
        """
        logger.debug(f'Proxies gather started.')

        proxies = self._get_all_proxies_from_providers()
        filtered_proxies = self._proxy_filterer.filter(
            proxies,
            protocols=protocols,
            anonymities=anonymities,
        )
        valid_proxies = self._proxy_validator.filter_valid_proxies(
            proxies=filtered_proxies,
            limit=limit,
        )
        logger.debug(
            f'Finished proxies gather, {len(valid_proxies)} proxies were found.'
        )

        if not valid_proxies:
            raise NoProxiesFound

        return valid_proxies

    def get_one(self, protocols: List[Protocols] = [], anonymities: List[Anonymities] = []) -> Proxy:
        """Get one proxy

        Args:
            protocols (List[str], optional): The allowed protocols of proxy

        Returns:
            Proxy: Proxy
        """
        return self._gather(
            protocols=protocols,
            anonymities=anonymities,
            limit=1
        )

    def get(self, protocols: List[Protocols] = [], anonymities: List[Anonymities] = [], limit: int = 0) -> List[Proxy]:
        """Get multiple proxies.

        Args:
            limit (int, optional): The amount of proxies to return.
            When 0 returns all the proxies available. Defaults to 0.
            protocols (List[str], optional): The allowed protocols of proxy

        Returns:
            List[Proxy]: List of proxies
        """
        proxies = self._gather(
            protocols=protocols,
            anonymities=anonymities,
            limit=limit
        )
        return proxies
