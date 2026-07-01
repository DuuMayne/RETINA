# RETINA — Review of Entitlements, Tokens, Identities and Networked Access

A self-hosted access review tool that connects to your SaaS applications, pulls a snapshot of every user and their permissions, and cross-references it against your identity provider to surface accounts that shouldn't exist — orphaned users, stale access, and people who were offboarded but still have active logins.

Instead of manually exporting users from 15 different apps every quarter, RETINA syncs them on a schedule, stores historical snapshots, and shows you the drift between review periods. Everything stays in your environment — no data leaves your network.

**What it finds:**
- **Orphaned accounts** — users active in an app but no longer in Okta (potential ex-employees)
- **Inactive users** — suspended in Okta but still enabled in other systems
- **Stale access** — no login activity in 90+ days
- **MFA gaps** — users without MFA enrolled

**What it automates:** quarterly access review campaigns. Group applications into business **Products** (optionally scoped to a sub-resource within one connector, e.g. just the "payments-team" Okta group), assign reviewers per product, and run time-boxed **Review Cycles** that generate a scoped review, track progress against a due date, and nag reviewers on Slack as the deadline approaches.

**Supports 51 SaaS connectors** including Okta, AWS, GitHub, Google Workspace, Slack, Jira, Salesforce, Snowflake, CrowdStrike, Kandji, Zendesk, and more. See the [full list](#11-supported-connectors).

---

## Table of Contents

1. [What you need before starting](#1-what-you-need-before-starting)
2. [Setup: Docker (recommended)](#2-setup-docker-recommended)
3. [Setup: Local development](#3-setup-local-development)
4. [Adding your first connector](#4-adding-your-first-connector)
5. [Products: scoping reviews by team or service](#5-products-scoping-reviews-by-team-or-service)
6. [Running a quarterly review cycle](#6-running-a-quarterly-review-cycle)
7. [Ad-hoc access review](#7-ad-hoc-access-review)
8. [Understanding the analysis](#8-understanding-the-analysis)
9. [Scheduling automatic syncs](#9-scheduling-automatic-syncs)
10. [Exporting for audits](#10-exporting-for-audits)
11. [Supported connectors](#11-supported-connectors)
12. [Security notes](#12-security-notes)
13. [Troubleshooting](#13-troubleshooting)
14. [For developers](#14-for-developers)

---

## 1. What you need before starting

**For Docker setup (recommended):**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

**For local development:**
- Python 3.9 or later
- `uv` package manager (faster than pip — install with `pip install uv`)

**Login:** RETINA does not have its own login screen — it trusts an authenticating reverse proxy in front of it (Cloudflare Access, oauth2-proxy, nginx + `auth_request`, a corporate VPN gateway, etc.) that has already verified the user against Okta/Google and forwards their email in an HTTP header. If you don't already have one of these in front of your internal tools, see [Step 2a](#step-2a--put-an-authenticating-proxy-in-front-of-retina) below for the simplest option.

**Credentials:** You'll add API credentials for each connected system through RETINA's web interface — not in a configuration file. RETINA encrypts all credentials immediately when you save them.

**Slack (optional):** if you want reminder/escalation notifications for review cycles, have a Slack incoming webhook URL ready — either one global fallback, or one per product.

---

## 2. Setup: Docker (recommended)

### Step 1 — Install Docker Desktop

Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/). Confirm it's running (whale icon in menu bar/system tray).

### Step 2 — Clone RETINA

```bash
git clone https://github.com/DuuMayne/RETINA.git
cd RETINA
```

### Step 2a — Put an authenticating proxy in front of RETINA

RETINA has no login page of its own. It reads the logged-in user's email from an HTTP header and trusts whatever set that header — so it must only ever be reachable through something that has already authenticated the user against Okta or Google.

If you already put internal tools behind a VPN or an access proxy (Cloudflare Access, oauth2-proxy, Tailscale, an nginx `auth_request` gateway, etc.), just add RETINA to that same setup and configure it to forward the authenticated email as a header — e.g. Cloudflare Access sends `Cf-Access-Authenticated-User-Email` by default, which is what RETINA expects out of the box.

If you don't have one yet, the fastest path is [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/) in front of `http://localhost:8000` (or your host), with Okta or Google configured as the identity provider in the Cloudflare Zero Trust dashboard. No changes to RETINA itself are required — it already reads Cloudflare's header by default.

**Never expose port 8000 directly to the internet or an untrusted network.** Without a proxy in front, anyone can set the identity header themselves and impersonate any user.

### Step 3 — Set environment variables

Edit `docker-compose.yml`:

```yaml
environment:
  - RETINA_DATA_DIR=/app/data
  - AUTH_EMAIL_HEADER=Cf-Access-Authenticated-User-Email   # change if your proxy uses a different header name
  - AUTH_NAME_HEADER=                                       # optional — header carrying a display name, if your proxy sends one
  - RETINA_ADMIN_EMAILS=                                     # optional — comma-separated list; first user becomes admin if left blank
  - RETINA_SLACK_WEBHOOK_URL=                                 # optional — global fallback webhook for cycle reminders
  - RETINA_REMINDER_INTERVAL_HOURS=6                          # how often the reminder job checks for due/overdue cycles
```

### Step 4 — Start RETINA

```bash
docker compose up -d --build
```

- **`--build`** — builds the image the first time (takes 2–3 minutes)
- **`-d`** — runs in the background

### Step 5 — Open RETINA through your proxy

Go to whatever URL your proxy exposes for RETINA (not `http://host:8000` directly, unless your proxy *is* on that host/port). The first person to access it is automatically made an **admin**. Everyone after that gets the **reviewer** role, unless you set `RETINA_ADMIN_EMAILS`.

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

> **Important:** Before updating, back up the data volume containing your encryption key. Without it, saved credentials cannot be decrypted. See [Security notes](#12-security-notes).

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

### Step 3 — Set a dev identity

Locally you won't have a proxy in front of RETINA, so set `DEV_USER_EMAIL` to simulate a logged-in user. **This variable must never be set in production** — it bypasses the identity header check entirely.

```bash
export DEV_USER_EMAIL=you@company.com
```

`RETINA_DATA_DIR` defaults to `./data` (created automatically) if you don't set it.

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

## 5. Products: scoping reviews by team or service

A **Product** groups one or more connected applications into a business-level unit — e.g. "Payments Platform" might be your Okta group plus a specific AWS account plus a GitHub org. Products are what a review cycle actually gets scoped to, and each one carries its own reviewer list and (optionally) its own Slack webhook.

This page is admin-only, at **Products** in the top navigation.

### Step 1 — Create a product

Click **+ Add Product**, give it a name and optional description, and optionally paste a Slack incoming webhook URL for that product's reminders.

### Step 2 — Scope it to one or more applications

Click **+ Add Scope** and pick a connected application. To include *every* user synced from that application, leave the filter blank. To narrow it to a sub-resource — a specific Okta group, GitHub org, AWS account, etc. — set a **Field**, **Match** (Contains/Equals), and **Value**, then click **Preview Match Count** before saving.

The filter is evaluated against whatever fields that connector actually returns (commonly `roles`, which is often a list like `["Group: payments-team", "Super Administrator"]`). This is deliberately simple — one field/match/value per scope — and it's checked live so you can see exactly how many users it matches (and a sample of who) before it's used in a real review. **If a filter matches 0 users, RETINA warns you immediately** rather than silently generating an empty review months later. If you need two different sub-resource slices of the same application, add the application to the product twice with two different filters.

### Step 3 — Assign reviewers

Click **Manage Reviewers** and list the emails (one per line) who should review this product's access. When a cycle is generated, every item in that product is assigned to this reviewer list.

---

## 6. Running a quarterly review cycle

A **Review Cycle** is a time-boxed campaign — e.g. "Q3 2026 SOC 2 Review" — with a due date and a scope (either every connected application, or a specific set of Products). Creating one triggers fresh syncs of everything in scope and generates the review items reviewers will work through.

### Step 1 — Create a cycle

Go to **Review Cycles** → **+ New Cycle**. Give it a name and due date, then choose **All applications** or check specific **Products**.

### Step 2 — Let it generate

RETINA syncs every in-scope application (a few at a time, so it doesn't hammer several connectors simultaneously) and creates one review item per matching user. This can take a little while for a large scope — the cycle shows "Generating…" until it's done. If a connector's sync fails, RETINA falls back to the most recent snapshot it already has and flags it with a warning banner rather than blocking the whole cycle.

### Step 3 — Reviewers work their assigned items

Each reviewer sees **My Assignments** by default on a cycle's detail page — only the items belonging to a product they're listed as a reviewer for. They can **Flag**, **Approve**, or (once flagged) **Resolve** each item with a note. Admins can always see and act on everything via the **All Items** toggle.

Trying to act on an item you're not assigned to returns a permission error — this is stricter than the [ad-hoc review](#7-ad-hoc-access-review) flow, which any authenticated user can act on.

### Step 4 — Track progress and close it out

The cycle list shows a progress bar (resolved vs. pending). The **Audit Log** tab on a cycle's detail page shows every decision and every reminder/escalation sent. When everything's resolved (or you're satisfied with where it landed), click **Close Cycle** — this stops further Slack reminders for it. Cycles are never auto-closed by their due date; an overdue-and-still-open cycle keeps escalating on purpose.

### Reminders and escalation

If a product has pending items, RETINA posts a Slack reminder to that product's webhook (or the global `RETINA_SLACK_WEBHOOK_URL` fallback) at 7, 3, and 1 days before the due date — once each. Past the due date, it posts a repeating `@here` escalation (at most once per product per day) for as long as the cycle stays open with pending items. **RETINA never takes action in the source system itself** — it only records decisions and nags humans. Actually disabling or removing access stays a manual step wherever that access lives.

---

## 7. Ad-hoc access review

Outside of formal cycles, the **Access Review** page lets any logged-in user review the full current user list across all connected systems and flag or approve people on the spot — no cycle, no due date, no reviewer assignment. This is unchanged from before Review Cycles existed and stays fully open to any authenticated user.

1. Go to **Access Review** in the top navigation
2. Filter by application or review status (Pending / Flagged / Approved)
3. Click **Flag** to mark a user for removal (add a note explaining why)
4. Click **Approve** to confirm access is appropriate
5. Decisions appear in the **Audit Log** tab with the reviewer's name and timestamp
6. Click **Export CSV** to download the full ad-hoc review record

### What to do with flagged accounts

RETINA identifies issues — it doesn't take action in external systems, in either the ad-hoc flow or review cycles. For each flagged account:
- **Orphaned account:** Log into the relevant system and disable or delete the account
- **Stale access:** Check with the user's manager, then remove if no longer needed
- **Inactive user:** Confirm offboarding completed in all systems
- **MFA gap:** Contact the user or their manager to enroll

---

## 8. Understanding the analysis

### Cross-reference flags

Available from **Cross-Reference** in the top navigation — runs automatically across all connected systems using Okta as the baseline.

| Flag | What it means | What to do |
|---|---|---|
| **Orphaned** | User is active in the app but doesn't exist in Okta | Likely an ex-employee or service account — verify and disable if unneeded |
| **Inactive** | User is suspended in Okta but still active elsewhere | Check if offboarding was completed across all systems |
| **Stale** | No login in 90+ days | Confirm with the user's team — may indicate role change or unused account |
| **MFA gap** | User doesn't have MFA enrolled | Remediate before the next audit |

### User roles

| Role | What they can do |
|---|---|
| **Admin** | Add/edit/delete connectors, manage Products and reviewers, create/close cycles, view and act on everything, manage RETINA user roles |
| **Reviewer** | View connected system data, flag/approve users in ad-hoc review, flag/approve/resolve items assigned to them in review cycles, export reports |

The first person to access RETINA becomes an admin (unless `RETINA_ADMIN_EMAILS` is set). Admins can promote or demote other users via `PUT /api/users/{id}`.

### Snapshots

Every sync creates a timestamped snapshot. The **History** view shows historical point-in-time snapshots of the user list for any application. This is the evidence you need for audit questions like "what did access look like on date X?"

---

## 9. Scheduling automatic syncs

Set each connector to sync automatically so your data — and your snapshot history — stays current between reviews.

Click **Schedule** on any connector card and choose a frequency: **Hourly, Every 6 hours, Daily, Weekly, Monthly**, or turn it off for manual-only syncs. Each scheduled run creates a new snapshot, which is what gives you point-in-time history in the **History** view — and it's also what a review cycle syncs against when it's generated.

For a custom cron expression instead of a preset, use the API directly: `PUT /api/applications/{app_id}/schedule` with `{"schedule": "0 3 * * *", "enabled": true}`.

**Recommended schedules:**
- Identity providers (Okta, Google Workspace): Daily
- High-risk systems (AWS, GitHub, Snowflake): Daily or twice daily
- Lower-risk collaboration tools (Zoom, Slack): Weekly

---

## 10. Exporting for audits

RETINA produces three types of export.

**Connector snapshot export (raw data)**
1. Click **History** on any connector
2. Select the snapshot date
3. Click **Export CSV**

The export includes all user attributes (name, email, role, last login, MFA status).

**Review cycle export (formal quarterly evidence)**
1. Open a cycle under **Review Cycles**
2. Click **Export CSV**

Contains every item in that cycle — product, application, reviewer, decision, and notes. This is the primary artifact for a SOC 2 / ISO 27001 auditor asking for evidence that a specific quarter's access review happened, who ran it, and who reviewed what.

**Ad-hoc review export**
1. Go to **Access Review**
2. Click **Export CSV**

Contains every ad-hoc review decision — who was flagged, who approved, who the reviewer was, and when.

---

## 11. Supported connectors

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

## 12. Security notes

**RETINA has no login of its own — it trusts your proxy.** It reads the authenticated user's email from an HTTP header (`Cf-Access-Authenticated-User-Email` by default) and never verifies who set that header. This means RETINA is only as secure as the reverse proxy or VPN in front of it. **Never expose it directly to the internet or an untrusted network** — anyone who can reach it directly could set that header themselves and impersonate any user, including an admin.

**Deprovisioning is enforced upstream.** Because auth happens at the proxy, removing someone's access to RETINA is a matter of removing them from the Okta/Google group your proxy checks — RETINA doesn't need to be told separately. You can additionally deactivate a user inside RETINA (`PUT /api/users/{id}` with `is_active: false`) if you want a second layer of control.

**Cycle items enforce their own permission boundary.** Only a product's assigned reviewers (or an admin) can act on that product's items within a cycle — this is checked server-side, not just hidden in the UI. Ad-hoc review has no such restriction and stays open to any authenticated user, by design.

**Credentials and Slack webhook URLs are encrypted at rest.** RETINA generates a Fernet encryption key on first startup and uses it to encrypt all API credentials and product Slack webhook URLs before writing them to the database. The key is stored at `{RETINA_DATA_DIR}/encryption.key` with restricted file permissions.

**Back up your data directory.** `encryption.key` and `retina.db` should be backed up together, ideally to a location separate from where they normally live. If you lose `encryption.key`, you cannot decrypt saved credentials or webhook URLs and will need to re-enter them all.

**Credentials are masked in the UI.** Once saved, API keys and secrets are shown only as `***` — they cannot be retrieved through the interface.

**Audit log.** Every ad-hoc decision, cycle decision, cycle generation run, and Slack reminder/escalation is recorded in an immutable audit log with the actor's email and timestamp (system-triggered entries like reminders use `actor_email: "system"`). Cycle-scoped entries are included in that cycle's CSV export and visible in its Audit Log tab.

---

## 13. Troubleshooting

### "This site can't be reached" at localhost:8000

The container isn't running:
```bash
docker compose ps
```
If `retina` isn't listed as `Up`:
```bash
docker compose up -d
```

### "No identity header found" error (401)

RETINA didn't see the header it expects from your proxy. Check:
- You're accessing RETINA *through* your proxy's URL, not hitting `host:8000` directly
- `AUTH_EMAIL_HEADER` matches exactly what your proxy actually sends (check your proxy's docs/logs — header names are case-insensitive but must match)
- The proxy is actually configured to protect this specific route/hostname

### Everyone is getting the reviewer role, or the wrong person is admin

Set `RETINA_ADMIN_EMAILS` explicitly rather than relying on "first user becomes admin" — if multiple people accessed RETINA before you set this, the wrong person may have claimed the admin slot. Set the env var and restart; existing users' roles update automatically on their next request.

### A connector shows "Auth failed" after saving credentials

The credentials are correct in format but rejected by the API. Common causes:
- **Okta connector:** The API token needs Read Only Admin or Super Admin role; tokens expire after 30 days
- **GitHub:** Personal access tokens expire — check [github.com/settings/tokens](https://github.com/settings/tokens)
- **AWS:** Verify the access key is active in IAM and has appropriate read permissions

### Sync is showing 0 users

The connector authenticated but found no users — either the credentials don't have permission to list users, or the organization/tenant ID is wrong. Check the specific credential requirements for that connector type.

### A product's scope filter matches 0 users

Use **Preview Match Count** on the scope before saving — this is exactly what it's for. Common causes: the field name doesn't match what that connector actually returns (check a raw snapshot via **History**), the value's spelling/case doesn't match, or the source group/role was renamed since the filter was set up. If a filter starts matching 0 users after previously working, the underlying group/org/account was probably renamed — update the filter value to match.

### A cycle shows a sync warning banner but still has items

This is expected, not a bug — if a connector's live sync fails during cycle generation, RETINA falls back to the most recent snapshot it already has rather than generating an empty cycle. The warning tells you which application used stale data; re-sync that connector manually and click **Regenerate** on the cycle once it's fixed.

### "Encryption key not found" error

The Docker volume was removed. RETINA cannot decrypt saved credentials without the key. Options:
1. Restore the key from your backup to `{RETINA_DATA_DIR}/encryption.key`
2. If no backup exists, delete the database and re-enter credentials: `docker volume rm retina-data && docker compose up -d`

### Cross-reference shows everyone as orphaned

The Okta connector hasn't synced yet. Click **Pull Access** on your Okta connector first, then run Cross-Reference again.

### Not getting Slack reminders

Check that a webhook URL is set — either on the product (Products → Edit) or as the `RETINA_SLACK_WEBHOOK_URL` fallback. Reminders only fire at exactly 7/3/1 days before the due date (once each) plus a repeating daily escalation once overdue — there's no reminder at other points, and a product with zero pending items never gets nagged.

---

## 14. For developers

### Adding a new connector

1. Create `connectors/my_system.py` extending `BaseConnector`
2. Implement `fetch_users()` returning a list of standardized user dicts
3. Register it in `connectors/__init__.py`

### Tech stack
- **Python 3.9+** with FastAPI
- **SQLAlchemy** ORM + SQLite
- **Cryptography (Fernet)** for credential and webhook URL encryption
- **APScheduler** for background sync jobs and the cycle reminder job
- **Jinja2** templates + vanilla JS frontend

### Architecture notes

- `products.py` and `cycles.py` are `APIRouter`s mounted onto the main `app` in `main.py` — everything else lives directly on `app`.
- `scoping.py` holds the generic sub-resource filter (field/match/value) shared by the Products preview endpoint and cycle generation.
- `review_common.py` holds the shared "apply a flag/approve/resolve decision + write the audit log" logic used by both the ad-hoc review endpoint and the cycle item action endpoint.
- Ad-hoc `ReviewItem`/`AuditLog` rows have `cycle_id IS NULL`; cycle-scoped rows always have it set. The two domains never mix.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `RETINA_DATA_DIR` | `./data` | Directory for the SQLite database and encryption key |
| `AUTH_EMAIL_HEADER` | `Cf-Access-Authenticated-User-Email` | HTTP header your proxy uses to forward the authenticated user's email |
| `AUTH_NAME_HEADER` | — | Optional header for the user's display name, if your proxy sends one |
| `RETINA_ADMIN_EMAILS` | — | Comma-separated emails that get the admin role; first user becomes admin if unset |
| `DEV_USER_EMAIL` | — | **Local dev only.** Bypasses the identity header check — never set in production |
| `RETINA_SLACK_WEBHOOK_URL` | — | Global fallback Slack webhook for cycle reminders, used when a product has no webhook of its own |
| `RETINA_REMINDER_INTERVAL_HOURS` | `6` | How often the reminder job checks active cycles for due/overdue items |

### API endpoints

All API endpoints require an identity header (or `DEV_USER_EMAIL` locally). Endpoints that modify data (create/update/delete connectors, schedules, products) require the **admin** role.

**Auth**
- `GET /auth/me` — current user info, as resolved from the identity header

**Products** (admin only)
- `GET/POST /api/products`, `GET/PUT/DELETE /api/products/{id}`
- `POST /api/products/{id}/scopes`, `DELETE /api/products/{id}/scopes/{scope_id}`
- `GET /api/products/{id}/preview-scope` — dry-run a filter against the latest snapshot
- `PUT /api/products/{id}/reviewers`

**Review Cycles**
- `GET/POST /api/cycles` (create is admin only), `GET /api/cycles/{id}`
- `POST /api/cycles/{id}/regenerate`, `POST /api/cycles/{id}/close` (admin only)
- `GET /api/cycles/{id}/items?scope=mine|all`
- `POST /api/cycles/{id}/items/{item_id}/action` — flag/approve/resolve; restricted to the item's assigned reviewer(s) or an admin
- `GET /api/cycles/{id}/audit-log`, `GET /api/cycles/{id}/export`

**Ad-hoc Access Review**
- `GET /api/review/users` — all latest-snapshot users with review status (cycle-agnostic)
- `POST /api/review/action` — flag, approve, or resolve a user
- `GET /api/review/audit-log`, `GET /api/review/export`

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