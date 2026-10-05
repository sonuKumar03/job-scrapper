"""Connector registry for discovering and dispatching scrapers."""

from typing import Type
from job_scrapper.connectors.arbeitnow import ArbeitnowConnector
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.connectors.greenhouse import GreenhouseConnector
from job_scrapper.connectors.hackernews import HackerNewsConnector
from job_scrapper.connectors.himalayas import HimalayasConnector
from job_scrapper.connectors.jobicy import JobicyConnector
from job_scrapper.connectors.lever import LeverConnector
from job_scrapper.connectors.remoteok import RemoteOKConnector
from job_scrapper.connectors.weworkremotely import WeWorkRemotelyConnector

CONNECTORS: dict[str, Type[BaseConnector]] = {
    HimalayasConnector.name: HimalayasConnector,
    JobicyConnector.name: JobicyConnector,
    ArbeitnowConnector.name: ArbeitnowConnector,
    RemoteOKConnector.name: RemoteOKConnector,
    WeWorkRemotelyConnector.name: WeWorkRemotelyConnector,
    GreenhouseConnector.name: GreenhouseConnector,
    LeverConnector.name: LeverConnector,
    HackerNewsConnector.name: HackerNewsConnector,
}


def get_connector(name: str) -> BaseConnector:
    """Retrieve an instantiated connector by name."""
    cls = CONNECTORS.get(name.lower())
    if not cls:
        available = ", ".join(CONNECTORS.keys())
        raise ValueError(f"Unknown connector '{name}'. Available: {available}")
    return cls()


def list_connectors() -> list[str]:
    """Return names of all registered connectors."""
    return list(CONNECTORS.keys())
