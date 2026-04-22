# RETINA

**Review of Entitlements, Tokens, Identities and Networked Access**

A self-hosted access review tool for security and compliance teams. RETINA connects to your SaaS applications, pulls user entitlement snapshots, and cross-references them against your identity provider to surface orphaned accounts, stale access, and compliance gaps.

## Why This Exists

User access reviews are a baseline requirement across SOC 2, ISO 27001, HIPAA, and PCI DSS — and they're consistently one of the most painful parts of a compliance program. Most teams run them quarterly in spreadsheets: someone exports user lists from each application, pastes them side by side, and manually checks who should still have access. It takes days, it's error-prone, and the evidence is stale by the time the auditor looks at it.

RETINA was built by a GRC practitioner who got tired of doing this manually. It automates the data collection, normalizes user records across 51 platforms into a consistent schema, and runs the cross-reference analysis that would otherwise take hours with VLOOKUP. The goal isn't to replace your GRC platform — it's to eliminate the manual data gathering that makes access reviews so painful, and produce evidence that's actually current.

## Features

- **51 SaaS connectors** — Okta, Entra ID, AWS, GitHub, Google Workspace, CrowdStrike, Salesforce, Zoom, and more
- **Scheduled syncing** — Hourly, daily, weekly, monthly, or custom cron
- **Cross-reference analysis** — Compare all apps against Okta as identity baseline to flag orphaned accounts, inactive users, stale access, and missing MFA
- **Historical snapshots** — Browse and compare access state over time
- **Encrypted credential storage** — API keys and tokens encrypted at rest with Fernet
- **CSV export** — Export user access data for audits and reviews
- **Single-page UI** — Dark-themed dashboard with search, filtering, and per-app drill-down

## Supported Connectors

| Category | Connectors |
|----------|-----------|
| **Identity & Access** | Okta, Microsoft Entra ID, Google Workspace, JumpCloud, CrowdStrike, Duo Security, 1Password |
| **MDM & Endpoint** | Jamf Pro, Kandji, SentinelOne, UniFi |
| **Cloud & Infrastructure** | AWS IAM, Cloudflare, Snowflake, MongoDB Atlas, Terraform Cloud |
| **DevOps & Engineering** | GitHub, GitLab, Docker Hub, npm, Snyk, Airflow |
| **Collaboration** | Slack, Atlassian (Jira), Zendesk, Zoom, Webex, Figma |
| **Business & CRM** | Salesforce, HubSpot, DocuSign, ServiceNow |
| **HR** | Workday, BambooHR |
| **Security & Compliance** | Vanta, Splunk, Lacework, HackerOne, Cisco Umbrella |
| **Observability** | Datadog, New Relic, PagerDuty, Looker |
| **File Storage** | Box, Dropbox Business, Files.com |
| **Other SaaS** | SendGrid, Segment, HelloSign, Namecheap, Experian |

## Quick Start

### Prerequisites

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install & Run

```bash
git clone https://github.com/DuuMayne/retina.git
cd retina
uv sync
uv run python main.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

On first launch, RETINA automatically creates the SQLite database and generates an encryption key.

### Connect an Application

1. Click **Add Application** in the dashboard
2. Select a connector type (e.g., Okta)
3. Enter your API credentials — these are encrypted immediately
4. Click **Sync Now** to pull your first user snapshot
5. Optionally set a sync schedule for automatic updates

### Cross-Reference Analysis

Once Okta and at least one other application are synced, use the **Cross-Reference** view to flag:

- **Orphaned accounts** — Users in an app but not in Okta
- **Inactive users** — Suspended or deprovisioned in Okta but still active elsewhere
- **Stale access** — No login in 90+ days
- **MFA disabled** — Users without multi-factor authentication

## Architecture

```
retina/
├── main.py              # FastAPI application and API routes
├── database.py          # SQLAlchemy models (applications, snapshots)
├── scheduler.py         # APScheduler for background sync jobs
├── crypto.py            # Fernet encryption for stored credentials
├── connectors/          # 51 connector modules with shared interface
│   ├── base.py          # Abstract BaseConnector class
│   ├── okta.py
│   ├── aws.py
│   └── ...
├── templates/
│   └── index.html       # Jinja2 SPA template
└── static/
    ├── style.css
    └── app.js
```

**Stack:** Python · FastAPI · SQLAlchemy · SQLite · Jinja2 · Vanilla JS

## Adding a Connector

Each connector extends `BaseConnector` and implements three methods:

```python
class MyConnector(BaseConnector):
    @staticmethod
    def credential_fields() -> list[dict]:
        return [{"name": "api_token", "label": "API Token", "type": "password"}]

    @staticmethod
    def default_base_url() -> str | None:
        return "https://api.example.com"

    async def fetch_users(self) -> list[dict]:
        # Return normalized user records with:
        # id, email, name, roles, status, last_login, created_at
        ...
```

Register it in `connectors/__init__.py` and it will appear in the UI automatically.

## Security Notes

- Credentials are encrypted at rest using Fernet symmetric encryption
- The encryption key file (`encryption.key`) is created with `0600` permissions
- Credentials are masked in the UI and API responses
- **RETINA does not include authentication on the web interface itself** — deploy it on a trusted network or behind a reverse proxy with auth
- Back up your `encryption.key` file securely — without it, stored credentials cannot be decrypted

## Development

Designed, spec'd, and directed by a security/compliance practitioner. AI-assisted implementation using [Claude Code](https://claude.ai/code).

The domain knowledge — what to build, why it matters, which APIs to connect, what the cross-reference logic should flag — comes from hands-on GRC engineering work. The implementation was accelerated with AI tooling. This is how GRC engineers build internal tooling when they understand the problem better than any vendor does.

## License

Apache 2.0 with Commons Clause — see [LICENSE](LICENSE).
