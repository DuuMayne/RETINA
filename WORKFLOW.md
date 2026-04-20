# Building an Access Review Application with a Coding Assistant

This document captures the end-to-end workflow used to build a locally hosted access review application for compliance obligations using Claude Code as a coding assistant. It is intended as a reference for teams adopting AI-assisted development.

---

## Project Overview

**Goal:** Build a self-hosted web application that connects to SaaS applications via their APIs, pulls user access data (users, roles, permissions), and displays it for compliance access reviews.

**Final result:** A FastAPI application with 27 SaaS connectors, encrypted credential storage, snapshot history, search, and CSV export.

**Time:** Single session.

---

## Phase 1: Requirements and Architecture

### What we did

Started with a high-level description of the problem:

> "I need a locally hosted application I can use for access reviews for compliance obligations. We have a few dozen SaaS Applications that we need reviewed."

The assistant asked three clarifying questions before writing any code:

1. **Which SaaS apps?** — Determines which API connectors to build first.
2. **Tech preferences?** — Proposed a stack (Python/FastAPI, SQLite, Fernet encryption) and asked for confirmation.
3. **Workflow needs?** — Asked whether approval flows, scheduling, or just on-demand pulls were needed.

### Why this matters

Scoping up front avoided rework. The decision to start with a single connector (CrowdStrike) kept the first iteration small and testable. The assistant proposed a plugin architecture that would scale to dozens of connectors later without refactoring.

### Takeaway

> **Start with the smallest useful version.** Give the assistant your end goal, but agree on a minimal first milestone. Let it propose the architecture — it will optimize for extensibility patterns it has seen work across many projects.

---

## Phase 2: Initial Build (Single Connector)

### What we did

The assistant generated the full project structure in one pass:

```
access-review-app/
├── main.py                  # FastAPI routes
├── database.py              # SQLAlchemy models (SQLite)
├── crypto.py                # Fernet encryption for credentials
├── connectors/
│   ├── base.py              # Abstract base class
│   └── crowdstrike.py       # First connector
├── templates/index.html     # Single-page UI
├── static/
│   ├── style.css
│   └── app.js
└── requirements.txt
```

It created all files in parallel, set up a virtual environment, installed dependencies, and started the server — all without manual intervention.

### What went wrong

1. **Python version incompatibility.** The assistant used `str | None` type syntax (Python 3.10+), but the local machine had Python 3.9. The error surfaced on first import. Fix: added `from __future__ import annotations` and `Optional` imports.

2. **Server port conflict.** The first server process didn't fully terminate before a restart was attempted, causing an `Address already in use` error. Fix: kill the process on the port before restarting.

### Takeaway

> **Expect environment-specific issues.** The assistant writes correct code for modern defaults, but your local Python version, OS, or network config may differ. These are fast fixes — the important thing is that the assistant can read the error and adapt immediately.

---

## Phase 3: Iterative Debugging with a Live API

### What we did

Connected the app to CrowdStrike Falcon using real API credentials. Hit three issues in sequence:

1. **403 Forbidden on `/oauth2/token`** — Turned out to be incorrect credentials (copy/paste issue with whitespace). The assistant improved error handling to surface CrowdStrike's actual error message instead of a generic HTTP error, and added `.strip()` to credential values.

2. **201 "error"** — CrowdStrike returns HTTP 201 (Created) on successful token creation. The original code only accepted 200. One-line fix.

3. **404 on user endpoints** — The assistant had used legacy CrowdStrike API paths (`/users/queries/users/v1`). After consulting CrowdStrike's API documentation via FalconPy reference docs, updated to the current paths (`/user-management/queries/users/v1`).

### The debugging loop

Each issue followed the same pattern:
1. User reports error message from the UI
2. Assistant reads the error, identifies the cause
3. Assistant makes a targeted fix (usually 1-5 lines)
4. Server auto-reloads, user tests again

### Takeaway

> **Real API integration is where most time goes.** Documentation can be outdated, error messages can be vague, and auth flows have quirks. The assistant's value here is speed of iteration: it can read an error, hypothesize a fix, and apply it in seconds. Surfacing detailed error messages early (rather than generic "request failed") pays off immediately.

---

## Phase 4: Feature Addition (Edit Functionality)

### What we did

After the initial build worked, we added the ability to edit existing application configurations (name, base URL, credentials). This required:

- A new `GET /api/applications/{id}` endpoint that returns masked credentials
- A new `PUT /api/applications/{id}` endpoint with credential merge logic (only updates fields the user actually changed)
- An edit modal in the frontend
- An "Edit" button on each application card

### How the assistant handled it

It read the existing `main.py` and `app.js` files first, then made surgical additions — inserting the new endpoints between existing ones and adding the modal HTML before the script tag. No existing code was modified unnecessarily.

### Takeaway

> **Read before writing.** The assistant reads existing files before modifying them, which prevents it from breaking working code. When adding features, it extends rather than rewrites.

---

## Phase 5: Scaling to 27 Connectors

### What we did

Provided a list of 26 additional SaaS applications to support. The assistant:

1. **Parallelized research.** Launched 4 background research agents simultaneously, each investigating 4 APIs it was less certain about (Cisco Umbrella, Kandji, Lacework, files.com, HackerOne, HelloSign, Looker, NameCheap, Segment, UniFi, Atlassian, NPM, Docker Hub, Snowflake, Experian, Airflow).

2. **Built known connectors immediately.** While research agents ran in the background, it wrote connectors for well-known APIs it was confident about: GitHub, Okta, Slack, Google Workspace, Cloudflare, Zendesk, SendGrid, New Relic, Splunk, AWS.

3. **Built remaining connectors from research.** Once research completed, it wrote the remaining connectors and validated that the research matched its implementations.

4. **Registered all connectors.** Updated `__init__.py` with all 27 imports and verified clean imports.

### How the work was organized

The assistant wrote connectors in batches of 6-10 files at a time, using parallel file writes. Each connector follows the same pattern:
- Extends `BaseConnector`
- Implements `credential_fields()`, `default_base_url()`, and `fetch_users()`
- Returns normalized user records: `{id, email, name, roles, status, last_login, created_at}`

### What the research agents found

- **Experian** has no public user management API — the connector is a best-effort implementation.
- **NameCheap** has no team/user API — the connector pulls account contacts as a proxy.
- **UniFi** uses an unofficial API — the connector tries both classic and UDM-Pro URL patterns.
- **Cisco Umbrella** endpoint paths differed from initial assumptions — fixed based on research.

### Takeaway

> **Parallelize independent work.** The assistant can research and build simultaneously. For large-scale tasks, it delegates research to background agents while doing productive work on what it already knows. This is the biggest time multiplier — 27 connectors were built in minutes, not hours.

---

## What Worked Well

| Practice | Why it helped |
|---|---|
| Starting with one connector | Validated the architecture before scaling |
| Detailed error messages | Made API debugging a fast loop instead of guesswork |
| Plugin architecture | Adding 26 connectors required zero changes to the core app |
| Parallel research agents | Cut research time by 4x |
| Normalized data model | Every connector returns the same shape, so the UI works for all |
| Encrypted credential storage | Security built in from the start, not bolted on later |

## What to Watch For

| Issue | Mitigation |
|---|---|
| Python version mismatches | Specify your Python version up front, or let the assistant discover it |
| API documentation can be wrong or outdated | Always test with real credentials; the assistant can consult live docs |
| Port conflicts on restart | The assistant learned to kill existing processes before restarting |
| API auth quirks (201 vs 200, SigV4, etc.) | Detailed error surfacing catches these fast |
| Unofficial APIs (UniFi) | Flag these as potentially unstable; document the risk |

---

## Reproducing This Workflow

1. **Describe the problem, not the solution.** Let the assistant propose the architecture.
2. **Agree on a minimal first milestone.** One working connector, one working page.
3. **Test with real credentials early.** Mock data hides integration issues.
4. **Report exact error messages.** Copy-paste the full error — the assistant parses them.
5. **Request features incrementally.** Edit support, then bulk connectors, not everything at once.
6. **Let the assistant parallelize.** When you have a list of independent tasks, give them all at once.

---

## Tech Stack

- **Backend:** Python 3.9+, FastAPI, SQLAlchemy, SQLite
- **Credentials:** Fernet symmetric encryption (key file with 0600 permissions)
- **HTTP client:** httpx (async)
- **Frontend:** Vanilla HTML/CSS/JS (no framework)
- **Server:** Uvicorn with auto-reload

## Running the Application

```bash
cd ~/access-review-app
uv run python main.py
# Open http://127.0.0.1:8000
```
