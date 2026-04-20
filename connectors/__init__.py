from __future__ import annotations
from typing import Optional

from .base import BaseConnector
from .crowdstrike import CrowdStrikeConnector
from .airflow import AirflowConnector
from .atlassian import AtlassianConnector
from .aws import AWSConnector
from .cisco_umbrella import CiscoUmbrellaConnector
from .cloudflare import CloudflareConnector
from .docker_hub import DockerHubConnector
from .experian import ExperianConnector
from .files_com import FilesComConnector
from .github import GitHubConnector
from .google_workspace import GoogleWorkspaceConnector
from .hackerone import HackerOneConnector
from .hellosign import HelloSignConnector
from .kandji import KandjiConnector
from .lacework import LaceworkConnector
from .looker import LookerConnector
from .namecheap import NameCheapConnector
from .newrelic import NewRelicConnector
from .npm import NPMConnector
from .okta import OktaConnector
from .segment import SegmentConnector
from .sendgrid import SendGridConnector
from .slack import SlackConnector
from .snowflake import SnowflakeConnector
from .splunk import SplunkConnector
from .unifi import UniFiConnector
from .zendesk import ZendeskConnector

CONNECTORS = {
    "airflow": AirflowConnector,
    "atlassian": AtlassianConnector,
    "aws": AWSConnector,
    "cisco_umbrella": CiscoUmbrellaConnector,
    "cloudflare": CloudflareConnector,
    "crowdstrike": CrowdStrikeConnector,
    "docker_hub": DockerHubConnector,
    "experian": ExperianConnector,
    "files_com": FilesComConnector,
    "github": GitHubConnector,
    "google_workspace": GoogleWorkspaceConnector,
    "hackerone": HackerOneConnector,
    "hellosign": HelloSignConnector,
    "kandji": KandjiConnector,
    "lacework": LaceworkConnector,
    "looker": LookerConnector,
    "namecheap": NameCheapConnector,
    "newrelic": NewRelicConnector,
    "npm": NPMConnector,
    "okta": OktaConnector,
    "segment": SegmentConnector,
    "sendgrid": SendGridConnector,
    "slack": SlackConnector,
    "snowflake": SnowflakeConnector,
    "splunk": SplunkConnector,
    "unifi": UniFiConnector,
    "zendesk": ZendeskConnector,
}


def get_connector(connector_type: str, credentials: dict, base_url: Optional[str] = None) -> BaseConnector:
    cls = CONNECTORS.get(connector_type)
    if not cls:
        raise ValueError(f"Unknown connector type: {connector_type}")
    return cls(credentials, base_url)
