from __future__ import annotations

import httpx

from .base import BaseConnector


class FigmaConnector(BaseConnector):
    """Connector for Figma team member access review.

    Uses the Figma REST API to retrieve team members and their project
    access.  Auth is via a personal access token passed in the
    ``X-FIGMA-TOKEN`` header (OAuth2 Bearer tokens are also accepted).

    Primary endpoint:
        GET /v1/teams/{team_id}/members

    The team-members endpoint returns all members of the given team with
    their role (``owner``, ``editor``, ``viewer``).  Pagination is not
    documented for this endpoint as of the current API version, but the
    connector handles it defensively in case Figma adds cursor-based
    pagination in the future.

    To enrich results the connector also fetches the project list for the
    team (GET /v1/teams/{team_id}/projects) and, for each project, the
    files (GET /v1/projects/{project_id}/files) so that per-user project
    and file counts can be reported.
    """

    DEFAULT_BASE_URL = "https://api.figma.com"

    @staticmethod
    def credential_fields() -> list[dict]:
        return [
            {
                "name": "api_token",
                "label": "Personal Access Token or OAuth Token",
                "type": "password",
            },
            {
                "name": "team_id",
                "label": "Team ID",
                "type": "text",
            },
        ]

    @staticmethod
    def default_base_url() -> str | None:
        return FigmaConnector.DEFAULT_BASE_URL

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        token = self.credentials["api_token"].strip()
        return {
            "X-FIGMA-TOKEN": token,
            "Accept": "application/json",
        }

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict | None = None,
    ) -> dict:
        resp = await client.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Fetch users
    # ------------------------------------------------------------------

    async def fetch_users(self) -> list[dict]:
        base = (self.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        team_id = self.credentials["team_id"].strip()

        async with httpx.AsyncClient(timeout=30) as client:
            # ----- 1. Get team members --------------------------------
            members_url = f"{base}/v1/teams/{team_id}/members"
            members_data = await self._get_json(client, members_url)

            raw_members: list[dict] = members_data.get("members", [])

            # Defensive cursor-based pagination (in case Figma adds it).
            cursor = members_data.get("cursor")
            while cursor:
                page = await self._get_json(
                    client,
                    members_url,
                    params={"cursor": cursor},
                )
                raw_members.extend(page.get("members", []))
                cursor = page.get("cursor")

            # ----- 2. Enrich: count projects per member ---------------
            # Build a map of member_id -> set of project ids they appear in.
            member_projects: dict[str, set[str]] = {
                str(m.get("id", "")): set() for m in raw_members
            }

            try:
                projects_data = await self._get_json(
                    client,
                    f"{base}/v1/teams/{team_id}/projects",
                )
                projects = projects_data.get("projects", [])

                for project in projects:
                    project_id = project.get("id")
                    if not project_id:
                        continue

                    # Fetch files in each project to discover collaborators.
                    try:
                        files_data = await self._get_json(
                            client,
                            f"{base}/v1/projects/{project_id}/files",
                        )
                        for f in files_data.get("files", []):
                            last_mod_by = f.get("last_modified_by", {})
                            uid = str(last_mod_by.get("id", ""))
                            if uid in member_projects:
                                member_projects[uid].add(str(project_id))
                    except httpx.HTTPStatusError:
                        # Permissions may restrict some projects; skip.
                        continue

            except httpx.HTTPStatusError:
                # Project enrichment is best-effort; proceed with member
                # data alone if the endpoint is inaccessible.
                pass

            # ----- 3. Build result list -------------------------------
            results: list[dict] = []
            for member in raw_members:
                member_id = str(member.get("id", ""))

                # The API returns ``role`` as one of: owner, editor, viewer.
                role = member.get("role", "viewer")
                roles = [role]

                # Determine admin status from role.
                is_admin = role == "owner"

                results.append({
                    "id": member_id,
                    "email": member.get("email", ""),
                    "name": member.get("handle", ""),
                    "roles": roles,
                    "status": "active",
                    "last_login": "",
                    "created_at": "",
                    "img_url": member.get("img_url", ""),
                    "is_admin": str(is_admin),
                    "project_count": len(member_projects.get(member_id, set())),
                })

        return results
