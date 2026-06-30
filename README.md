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

**Login:** RETINA requires authentication via Okta or Google. You'll need an OAuth app set up in one or both — see [Step 2a](#step-2a--configure-okta-or-google-oauth) below.

**Credentials:** You'll add API credentials for each connected system through RETINA's web interface — not in a configuration file. RETINA encrypts all credentials immediately when you save them.

---

## 2. Setup: Docker (recommended)

### Step 1 — Install Docker Desktop

Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/). Confirm it's running (whale icon in menu bar/system tray).

### Step 2 — Clone RETINA

```bash
git clone https://github.com/DuuMayne/RETINA.git
cd RETINA
```

### Step 2a — Configure Okta or Google OAuth

RETINA requires at least one OAuth provider configured before anyone can log in.

**Option A: Okta**

1. In Okta Admin → **Applications** → **Create App Integration**
2. Choose **OIDC - OpenID Connect** → **Web Application**
3. Set **Sign-in redirect URI** to `http://your-host:8000/auth/callback`
4. Set **Sign-out redirect URI** to `http://your-host:8000/login`
5. Copy the **Client ID**, **Client Secret**, and your **Okta domain** (e.g. `yourorg.okta.com`)
6. Assign the app to the users or groups who should have access

**Option B: Google**

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → **APIs & Services** → **Credentials**
2. **Create Credentials** → **OAuth 2.0 Client ID** → **Web application**
3. Add to **Authorized redirect URIs**: `http://your-host:8000/auth/google/callback`
4. Copy the **Client ID** and **Client Secret**
5. Ensure the **Google People API** is enabled in your project

Both providers can be active at the same time. Users are identified by email address regardless of which they use to log in.

### Step 3 — Set environment variables

Edit `docker-compose.yml` and fill in the values for the providers you configured:

```yaml
environment:
  - RETINA_DATA_DIR=/app/data
  - APP_BASE_URL=http://localhost:8000   # change to your actual host/domain
  - OKTA_DOMAIN=yourorg.okta.com
  - OKTA_CLIENT_ID=0oaxxxxxxxxxxxxxxxx
  - OKTA_CLIENT_SECRET=xxxxxxxxxxxxxxxx
  - GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
  - GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
```

Leave any provider's fields blank if you're not using it. The session signing key is auto-generated on first startup and stored in the data volume — you don't need to set it manually.

### Step 4 — Start RETINA

```bash
docker compose up -d --build
```

- **`--build`** — builds the image the first time (takes 2–3 minutes)
- **`-d`** — runs in the background

### Step 5 — Log in

Go to **[http://localhost:8000](http://localhost:8000)** in any browser. You'll see the login screen. The first user to log in is automatically made an **admin**. Everyone who logs in after that gets the **reviewer** role.

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

> **Important:** Before updating, back up the data volume containing your encryption key and session key. Without the encryption key, saved credentials cannot be decrypted. See [Security notes](#10-security-notes).

---

## 3. Setup: Local development

### Step 1 — Install uv

```bash
pip install uv
```

### Step 2 — Install dependencies

```bash
cd RETINA
uv sync
```

### Step 3 — Set environment variables

```bash
export RETINA_DATA_DIR=./data
export APP_BASE_URL=http://localhost:8000
export OKTA_DOMAIN=yourorg.okta.com
export OKTA_CLIENT_ID=your-client-id
export OKTA_CLIENT_SECRET=your-client-secret
# or for Google:
export GOOGLE_CLIENT_ID=your-client-id
export GOOGLE_CLIENT_SECRET=your-client-secret
```

### Step 4 — Start RETINA

```bash
uv run python main.py
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.

---

## 4. Adding your first connector

All credential management happens in the RETINA web interface — nothing goes in a config file. You must be logged in as an **admin** to add or edit connectors.

### Step 1 — Click "Add Application"

On the main dashboard, click **Add Application** in the top right.

### Step 2 — Choose your connector

Select from the list of 51 supported applications. Each connector shows what credentials it needs (API token, client ID + secret, etc.).

### Step 3 — Enter credentials

Fill in the required fields. RETINA encrypts these immediately when you click **Save** — they're stored in encrypted form and never shown in full again.

### Step 4 — Run your first sync

Click **Pull Access** next to the new connector. RETINA pulls the full user list from that application and stores a snapshot.

### Repeat for each system

Add Okta first — it becomes the baseline identity provider for cross-reference analysis. Then add your other systems.

---

## 5. Running an access review

RETINA has two complementary review workflows.

### Cross-reference analysis (automated flagging)

Runs automatically across all connected systems using Okta as the baseline. It surfaces accounts that look risky so you can investigate them.

1. Make sure Okta is synced — click **Pull Access** on your Okta connector
2. Click **Cross-Reference** in the top navigation
3. Review flagged accounts in each category

### User access review (for compliance sign-off)

The **Access Review** page lets any logged-in user review the full user list across all connected systems and formally approve or flag each person for removal. This produces a documented, timestamped audit trail.

1. Go to **Access Review** in the top navigation
2. Filter by application or review status (Pending / Flagged / Approved)
3. Click **Flag** to mark a user for removal (add a note explaining why)
4. Click **Approve** to confirm access is appropriate
5. Flagged users appear in the **Audit Log** tab with the reviewer's name and timestamp
6. Click **Export CSV** to download the full review record for your auditor

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

### User roles

| Role | What they can do |
|---|---|
| **Admin** | Add/edit/delete connectors, manage schedules, view all data, flag/approve users, manage RETINA user roles |
| **Reviewer** | View all connected system data, flag and approve users in access reviews, export review reports |

The first user to log in becomes an admin. Admins can promote or demote other users.

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

RETINA produces two types of export.

**Connector snapshot export (raw data)**
1. Click **History** on any connector
2. Select the snapshot date
3. Click **Export CSV**

The export includes all user attributes (name, email, role, last login, MFA status).

**Access review export (compliance evidence)**
1. Go to **Access Review**
2. Click **Export CSV**

This export contains every review decision — who was flagged, who approved, who the reviewer was, and when. This is the artifact you give to an auditor to demonstrate that a formal access review was conducted.

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

**Authentication required.** RETINA uses Okta or Google OAuth for login. No one can access the application without authenticating through one of the configured providers. Access is controlled at the IdP level — deprovisioning a user in Okta or Google immediately blocks their login.

**Credentials are encrypted at rest.** RETINA generates a Fernet encryption key on first startup and uses it to encrypt all API credentials before writing them to the database. The key is stored at `{RETINA_DATA_DIR}/encryption.key` with restricted file permissions.

**Session cookies are signed.** Login sessions use HMAC-SHA256 signed cookies. The signing key is auto-generated and stored at `{RETINA_DATA_DIR}/session.key`. You can set `SESSION_SECRET` as an environment variable instead if you prefer to manage it yourself.

**Back up your data directory.** The `encryption.key` and `session.key` files must be backed up separately from the database. If you lose `encryption.key`, you cannot decrypt saved credentials and will need to re-enter them all.

**Credentials are masked in the UI.** Once saved, API keys and secrets are shown only as `***` — they cannot be retrieved through the interface.

**Audit log.** Every login, flag, and approval decision is recorded in an immutable audit log with the actor's email and timestamp. The log is included in the access review CSV export.

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

### Login redirects back to the login page with no error

The `OKTA_DOMAIN`, `OKTA_CLIENT_ID`, or `OKTA_CLIENT_SECRET` env vars are not set, or the redirect URI in Okta/Google doesn't match `APP_BASE_URL`. Confirm the callback URI in your OAuth app settings exactly matches `{APP_BASE_URL}/auth/callback` (Okta) or `{APP_BASE_URL}/auth/google/callback` (Google).

### "Invalid state parameter" error after login

The login flow was interrupted (browser back button, expired cookie, etc.). Go back to `/login` and try again. If it happens consistently, make sure `APP_BASE_URL` is set to the actual hostname users access — mismatched URLs cause the OAuth state cookie to fail.

### A connector shows "Auth failed" after saving credentials

The credentials are correct in format but rejected by the API. Common causes:
- **Okta connector:** The API token needs Read Only Admin or Super Admin role; tokens expire after 30 days
- **GitHub:** Personal access tokens expire — check [github.com/settings/tokens](https://github.com/settings/tokens)
- **AWS:** Verify the access key is active in IAM and has appropriate read permissions

### Sync is showing 0 users

The connector authenticated but found no users — either the credentials don't have permission to list users, or the organization/tenant ID is wrong. Check the specific credential requirements for that connector type.

### "Encryption key not found" error

The Docker volume was removed. RETINA cannot decrypt saved credentials without the key. Options:
1. Restore the key from your backup to `{RETINA_DATA_DIR}/encryption.key`
2. If no backup exists, delete the database and re-enter credentials: `docker volume rm retina-data && docker compose up -d`

### Cross-reference shows everyone as orphaned

The Okta connector hasn't synced yet. Click **Pull Access** on your Okta connector first, then run Cross-Reference again.

---

## 12. For developers

### Adding a new connector

1. Create `connectors/my_system.py` extending `BaseConnector`
2. Implement `fetch_users()` returning a list of standardized user dicts
3. Register it in `connectors/__init__.py`

### Tech stack
- **Python 3.9+** with FastAPI
- **SQLAlchemy** ORM + SQLite
- **Cryptography (Fernet)** for credential encryption
- **APScheduler** for background sync jobs
- **Jinja2** templates + vanilla JS frontend

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `RETINA_DATA_DIR` | `.` | Directory for database, encryption key, and session key |
| `APP_BASE_URL` | `http://localhost:8000` | Public base URL — must match OAuth redirect URIs |
| `OKTA_DOMAIN` | — | Your Okta org domain, e.g. `yourorg.okta.com` |
| `OKTA_CLIENT_ID` | — | Okta OAuth app client ID |
| `OKTA_CLIENT_SECRET` | — | Okta OAuth app client secret |
| `GOOGLE_CLIENT_ID` | — | Google OAuth app client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth app client secret |
| `SESSION_SECRET` | auto-generated | HMAC key for signing session cookies; auto-saved to `session.key` if not set |

### API endpoints

All API endpoints require authentication. Endpoints that modify data (create/update/delete connectors, change schedules) require the **admin** role.

**Auth**
- `GET /auth/login` — redirect to Okta
- `GET /auth/callback` — Okta OAuth callback
- `GET /auth/google/login` — redirect to Google
- `GET /auth/google/callback` — Google OAuth callback
- `GET /auth/logout` — clear session
- `GET /auth/me` — current user info

**Access Review**
- `GET /api/review/users` — all latest-snapshot users with review status
- `POST /api/review/action` — flag, approve, or resolve a user
- `GET /api/review/audit-log` — full audit log
- `GET /api/review/export` — CSV export of all review decisions

**RETINA Users (admin only)**
- `GET /api/users` — list RETINA users
- `PUT /api/users/{id}` — update role or active status

---

## License

| What | License |
|---|---|
| Source code | [Elastic License 2.0](LICENSE) |
| Documentation & templates | [CC BY-NC 4.0](LICENSE-docs) |

Free for anyone to use, fork, and build on — including commercially within your own organization. The one restriction: you cannot offer this software as a paid hosted or managed service. See [LICENSE](LICENSE) for full terms.

Copyright 2026 Adam Duman