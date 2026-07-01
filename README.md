# RETINA — Review of Entitlements, Tokens, Identities and Networked Access

A self-hosted access review tool that connects to your SaaS applications, pulls a snapshot of every user and their permissions, and cross-references it against your identity provider to surface accounts that shouldn't exist — orphaned users, stale access, and people who were offboarded but still have active logins.

Instead of manually exporting users from 15 different apps every quarter, RETINA syncs them on a schedule, stores historical snapshots, and shows you the drift between review periods. Everything stays in your environment — no data leaves your network.

**What it finds:**
- **Orphaned accounts** — users active in an app but no longer in Okta (potential ex-employees)
- **Inactive users** — suspended in Okta but still enabled in other systems
- **Stale access** — no login activity in 90+ days
- **MFA gaps** — users without MFA enrolled

**Supports 51 SaaS connectors** including Okta, AWS, GitHub, Google Workspace, Slack, Jira, Salesforce, Snowflake, CrowdStrike, Kandji, Zendesk, and more. See the [full list](#supported-connectors).

---

## Table of Contents

1. [What you need before starting](#1-what-you-need-before-starting)
2. [Setup: Docker (recommended)](#2-setup-docker-recommended)
3. [Setup: Local development](#3-setup-local-development)
4. [Adding your first connector](#4-adding-your-first-connector)
5. [Running an access review](#5-running-an-access-review)
6. [Understanding the analysis](#6-understanding-the-analysis)
7. [Scheduling automatic syncs](#7-scheduling-automatic-syncs)
8. [Exporting for audits](#8-exporting-for-audits)
9. [Supported connectors](#9-supported-connectors)
10. [Security notes](#10-security-notes)
11. [Troubleshooting](#11-troubleshooting)
12. [For developers](#12-for-developers)

---

## 1. What you need before starting

**For Docker setup (recommended):**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

**For local development:**
- Python 3.9 or later
- `uv` package manager (faster than pip — install with `pip install uv`)

**Credentials:** You'll add API credentials for each system through RETINA's web interface — not in a configuration file. RETINA encrypts all credentials immediately when you save them.

---

## 2. Setup: Docker (recommended)

### Step 1 — Install Docker Desktop

Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/). Confirm it's running (whale icon in menu bar/system tray).

### Step 2 — Clone RETINA

```bash
git clone https://github.com/DuuMayne/RETINA.git
cd RETINA
```

### Step 3 — Start RETINA

```bash
docker compose up -d --build
```

- **`--build`** — builds the image the first time (takes 2–3 minutes)
- **`-d`** — runs in the background

### Step 4 — Open RETINA

Go to **[http://localhost:8000](http://localhost:8000)** in any browser.

Your data — the SQLite database and the encryption key — are stored in a Docker volume and persist between restarts.

**To stop:**
```bash
docker compose down
```

**To start again later:**
```bash
docker compose up -d
```

**To update:**
```bash
git pull
docker compose up -d --build
```

> **Important:** Before updating, back up the volume containing your encryption key. Without the key, saved credentials cannot be decrypted. See [Security notes](#10-security-notes).

---

## 3. Setup: Local development

### Step 1 — Install uv

```bash
pip install uv
```

`uv` is a fast Python package manager used by this project.

### Step 2 — Install dependencies

```bash
cd RETINA
uv sync
```

### Step 3 — Start RETINA

```bash
uv run python main.py
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.

Data is stored in the current working directory by default (or set `RETINA_DATA_DIR` to specify a different location).

---

## 4. Adding your first connector

All credential management happens in the RETINA web interface — nothing goes in a config file.

### Step 1 — Click "Add Application"

On the main dashboard, click **Add Application** in the top right.

### Step 2 — Choose your connector

Select from the list of 51 supported applications. Each connector shows what credentials it needs (API token, client ID + secret, OAuth, etc.).

### Step 3 — Enter credentials

Fill in the required fields. RETINA encrypts these immediately when you click **Save** — they're stored in encrypted form and never shown in full again.

### Step 4 — Run your first sync

Click **Sync Now** next to the new connector. RETINA pulls the full user list from that application and stores a snapshot.

### Repeat for each system

Add Okta first — it becomes the baseline identity provider for cross-reference analysis. Then add your other systems.

---

## 5. Running an access review

### Manual review (quarterly or on-demand)

1. Sync each connector individually using **Sync Now** to refresh data before starting a review
2. Go to **Cross-Reference** in the navigation
3. Select Okta (or your identity provider) as the baseline
4. Review the flagged accounts in each category (orphaned, inactive, stale, MFA gap)

### What to do with flagged accounts

RETINA identifies issues — it doesn't take action in external systems. For each flagged account:
- **Orphaned account:** Log into the relevant system and disable or delete the account
- **Stale access:** Check with the user's manager, then remove if no longer needed
- **Inactive user:** Confirm offboarding completed in all systems
- **MFA gap:** Contact the user or their manager to enroll

---

## 6. Understanding the analysis

### Cross-reference flags

| Flag | What it means | What to do |
|---|---|---|
| **Orphaned** | User is active in the app but doesn't exist in Okta | Likely an ex-employee or service account — verify and disable if unneeded |
| **Inactive** | User is suspended in Okta but still active elsewhere | Check if offboarding was completed across all systems |
| **Stale** | No login in 90+ days | Confirm with the user's team — may indicate role change or unused account |
| **MFA gap** | User doesn't have MFA enrolled | Remediate before the next audit |

### Snapshots

Every sync creates a timestamped snapshot. The **History** view shows historical point-in-time snapshots of the user list for any application. This is the evidence you need for audit questions like "what did access look like on date X?"

---

## 7. Scheduling automatic syncs

Set each connector to sync automatically so your data stays current between reviews. Scheduling is available via the API (there is no scheduling UI in the web interface).

Configure schedules using the scheduling API endpoints: **Hourly, Daily, Weekly, Monthly**, or a custom cron expression.

**Recommended schedules:**
- Identity providers (Okta, Google Workspace): Daily
- High-risk systems (AWS, GitHub, Snowflake): Daily or twice daily
- Lower-risk collaboration tools (Zoom, Slack): Weekly

---

## 8. Exporting for audits

RETINA generates CSV exports for individual connector snapshots.

**Export a connector snapshot:**
1. Go to the connector's history view
2. Select the snapshot date
3. Click **Export CSV**

The export includes all user attributes (name, email, role, last login, MFA status) — suitable for submitting as audit evidence.

---

## 9. Supported connectors

**Identity & Access**
Okta, Microsoft Entra ID (Azure AD), Google Workspace, JumpCloud, Duo, 1Password, CrowdStrike

**Endpoint & MDM**
Kandji, Jamf, SentinelOne, UniFi

**Cloud & Infrastructure**
AWS IAM, Cloudflare, Snowflake, MongoDB Atlas, Terraform Cloud

**Development & DevOps**
GitHub, GitLab, Docker Hub, npm, Snyk, Apache Airflow

**Collaboration & Communication**
Slack, Zoom, Webex, Jira, Zendesk, Figma

**Business & CRM**
Salesforce, HubSpot, DocuSign, ServiceNow

**Human Resources**
Workday, BambooHR

**Security & Observability**
Lacework, HackerOne, Vanta, Cisco Umbrella, Datadog, New Relic, PagerDuty, Looker, Splunk

**File Storage & Transfer**
Box, Dropbox, Files.com

**Other**
SendGrid, Segment, HelloSign, Namecheap, Experian

---

## 10. Security notes

**Credentials are encrypted at rest.** RETINA generates a Fernet encryption key on first startup and uses it to encrypt all API credentials before writing them to the database. The key is stored at `{RETINA_DATA_DIR}/encryption.key` with restricted file permissions.

**Back up your encryption key.** If you lose `encryption.key`, you cannot decrypt saved credentials and will need to re-enter them all. Back it up to a secure location separate from the database.

**No built-in authentication.** RETINA does not have a login screen. Deploy it on a trusted internal network, behind a VPN, or with a reverse proxy that handles authentication (e.g. Cloudflare Access, nginx + basic auth). Do not expose it directly to the internet.

**Credentials are masked in the UI.** Once saved, API keys and secrets are shown only as `***` — they cannot be retrieved through the interface.

---

## 11. Troubleshooting

### "This site can't be reached" at localhost:8000

The container isn't running:
```bash
docker compose ps
```
If `retina` isn't listed as `Up`:
```bash
docker compose up -d
```

### A connector shows "Auth failed" after saving credentials

The credentials are correct in format but rejected by the API. Common causes:
- **Okta:** The API token needs Read Only Admin or Super Admin role; tokens expire after 30 days
- **GitHub:** Personal access tokens expire — check [github.com/settings/tokens](https://github.com/settings/tokens)
- **AWS:** Verify the access key is active in the IAM console and has appropriate read permissions

### Sync is showing 0 users

The connector authenticated but found no users — either the credentials don't have permission to list users, or the organization/tenant ID is wrong. Check the specific credential requirements for that connector type.

### "Encryption key not found" error

The Docker volume was removed. RETINA cannot decrypt saved credentials without the key. Options:
1. Restore the key from your backup to `{RETINA_DATA_DIR}/encryption.key`
2. If no backup exists, you'll need to delete the database and re-enter credentials: `docker volume rm retina-data && docker compose up -d`

### Cross-reference shows everyone as orphaned

Okta isn't set as the baseline, or the Okta sync hasn't run yet. Go to **Cross-Reference**, confirm Okta is selected as the identity provider, and click **Sync Now** on the Okta connector first.

---

## 12. For developers

### Adding a new connector

1. Create `connectors/my_system.py` extending `BaseConnector`
2. Implement `get_users()` returning a list of standardized user objects
3. Add the connector definition to `connectors/__init__.py`
4. Add the credential schema to `database.py`

### Tech stack
- **Python 3.9+** with FastAPI
- **SQLAlchemy** ORM + SQLite
- **Cryptography (Fernet)** for credential encryption
- **APScheduler** for background sync jobs
- **Jinja2** templates for the frontend

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `RETINA_DATA_DIR` | `.` (current directory) | Directory for database and encryption key |

---

## License

| What | License |
|---|---|
| Source code | [Elastic License 2.0](LICENSE) |
| Documentation & templates | [CC BY-NC 4.0](LICENSE-docs) |

Free for anyone to use, fork, and build on — including commercially within your own organization. The one restriction: you cannot offer this software as a paid hosted or managed service. See [LICENSE](LICENSE) for full terms.

Copyright 2026 Adam Duman