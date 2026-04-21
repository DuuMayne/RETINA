from __future__ import annotations
from typing import Optional

from .base import BaseConnector
from .airflow import AirflowConnector
from .atlassian import AtlassianConnector
from .aws import AWSConnector
from .bamboohr import BambooHRConnector
from .box import BoxConnector
from .cisco_umbrella import CiscoUmbrellaConnector
from .cloudflare import CloudflareConnector
from .crowdstrike import CrowdStrikeConnector
from .datadog import DatadogConnector
from .docker_hub import DockerHubConnector
from .docusign import DocuSignConnector
from .dropbox import DropboxConnector
from .duo import DuoConnector
from .entra_id import EntraIDConnector
from .experian import ExperianConnector
from .figma import FigmaConnector
from .files_com import FilesComConnector
from .github import GitHubConnector
from .gitlab import GitLabConnector
from .google_workspace import GoogleWorkspaceConnector
from .hackerone import HackerOneConnector
from .hellosign import HelloSignConnector
from .hubspot import HubSpotConnector
from .jamf import JamfConnector
from .jumpcloud import JumpCloudConnector
from .kandji import KandjiConnector
from .lacework import LaceworkConnector
from .looker import LookerConnector
from .mongodb_atlas import MongoDBAtlasConnector
from .namecheap import NameCheapConnector
from .newrelic import NewRelicConnector
from .npm import NPMConnector
from .okta import OktaConnector
from .onepassword import OnePasswordConnector
from .pagerduty import PagerDutyConnector
from .salesforce import SalesforceConnector
from .segment import SegmentConnector
from .sendgrid import SendGridConnector
from .servicenow import ServiceNowConnector
from .sentinelone import SentinelOneConnector
from .slack import SlackConnector
from .snyk import SnykConnector
from .snowflake import SnowflakeConnector
from .splunk import SplunkConnector
from .terraform_cloud import TerraformCloudConnector
from .unifi import UniFiConnector
from .vanta import VantaConnector
from .webex import WebexConnector
from .workday import WorkdayConnector
from .zendesk import ZendeskConnector
from .zoom import ZoomConnector

CONNECTORS = {
    "airflow": AirflowConnector,
    "atlassian": AtlassianConnector,
    "aws": AWSConnector,
    "bamboohr": BambooHRConnector,
    "box": BoxConnector,
    "cisco_umbrella": CiscoUmbrellaConnector,
    "cloudflare": CloudflareConnector,
    "crowdstrike": CrowdStrikeConnector,
    "datadog": DatadogConnector,
    "docker_hub": DockerHubConnector,
    "docusign": DocuSignConnector,
    "dropbox": DropboxConnector,
    "duo": DuoConnector,
    "entra_id": EntraIDConnector,
    "experian": ExperianConnector,
    "figma": FigmaConnector,
    "files_com": FilesComConnector,
    "github": GitHubConnector,
    "gitlab": GitLabConnector,
    "google_workspace": GoogleWorkspaceConnector,
    "hackerone": HackerOneConnector,
    "hellosign": HelloSignConnector,
    "hubspot": HubSpotConnector,
    "jamf": JamfConnector,
    "jumpcloud": JumpCloudConnector,
    "kandji": KandjiConnector,
    "lacework": LaceworkConnector,
    "looker": LookerConnector,
    "mongodb_atlas": MongoDBAtlasConnector,
    "namecheap": NameCheapConnector,
    "newrelic": NewRelicConnector,
    "npm": NPMConnector,
    "okta": OktaConnector,
    "onepassword": OnePasswordConnector,
    "pagerduty": PagerDutyConnector,
    "salesforce": SalesforceConnector,
    "segment": SegmentConnector,
    "sendgrid": SendGridConnector,
    "servicenow": ServiceNowConnector,
    "sentinelone": SentinelOneConnector,
    "slack": SlackConnector,
    "snyk": SnykConnector,
    "snowflake": SnowflakeConnector,
    "splunk": SplunkConnector,
    "terraform_cloud": TerraformCloudConnector,
    "unifi": UniFiConnector,
    "vanta": VantaConnector,
    "webex": WebexConnector,
    "workday": WorkdayConnector,
    "zendesk": ZendeskConnector,
    "zoom": ZoomConnector,
}


def get_connector(connector_type: str, credentials: dict, base_url: Optional[str] = None) -> BaseConnector:
    cls = CONNECTORS.get(connector_type)
    if not cls:
        raise ValueError(f"Unknown connector type: {connector_type}")
    return cls(credentials, base_url)
