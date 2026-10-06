"""Connector registry for discovering and dispatching scrapers."""

from typing import Type
from job_scrapper.connectors.arbeitnow import ArbeitnowConnector
from job_scrapper.connectors.ashby import AshbyConnector
from job_scrapper.connectors.base import BaseConnector
from job_scrapper.connectors.builtin import BuiltInConnector
from job_scrapper.connectors.greenhouse import GreenhouseConnector
from job_scrapper.connectors.hackernews import HackerNewsConnector
from job_scrapper.connectors.himalayas import HimalayasConnector
from job_scrapper.connectors.indeed import IndeedConnector
from job_scrapper.connectors.instahyre import InstahyreConnector
from job_scrapper.connectors.jobicy import JobicyConnector
from job_scrapper.connectors.lever import LeverConnector
from job_scrapper.connectors.linkedin import LinkedInConnector
from job_scrapper.connectors.remoteok import RemoteOKConnector
from job_scrapper.connectors.weworkremotely import WeWorkRemotelyConnector
from job_scrapper.utils.http_client import ResilientHttpClient

CONNECTORS: dict[str, Type[BaseConnector]] = {
    HimalayasConnector.name: HimalayasConnector,
    IndeedConnector.name: IndeedConnector,
    InstahyreConnector.name: InstahyreConnector,
    JobicyConnector.name: JobicyConnector,
    ArbeitnowConnector.name: ArbeitnowConnector,
    RemoteOKConnector.name: RemoteOKConnector,
    WeWorkRemotelyConnector.name: WeWorkRemotelyConnector,
    GreenhouseConnector.name: GreenhouseConnector,
    LeverConnector.name: LeverConnector,
    LinkedInConnector.name: LinkedInConnector,
    AshbyConnector.name: AshbyConnector,
    BuiltInConnector.name: BuiltInConnector,
    HackerNewsConnector.name: HackerNewsConnector,
}


def get_connector(name: str, http_client: ResilientHttpClient | None = None) -> BaseConnector:
    """Retrieve an instantiated connector by name."""
    cls = CONNECTORS.get(name.lower())
    if not cls:
        available = ", ".join(CONNECTORS.keys())
        raise ValueError(f"Unknown connector '{name}'. Available: {available}")
    return cls(http_client=http_client)


def list_connectors() -> list[str]:
    """Return names of all registered connectors."""
    return list(CONNECTORS.keys())
