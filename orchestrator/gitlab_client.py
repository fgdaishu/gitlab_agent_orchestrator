from __future__ import annotations

import json
import time
from typing import Any
from urllib import error, parse, request


class GitLabError(RuntimeError):
    pass


class GitLabClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v4"
        self.token = token
        self.opener = request.build_opener(request.ProxyHandler({}))

    def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {"PRIVATE-TOKEN": self.token}
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(f"{self.api_url}{path}", data=body, headers=headers, method=method)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=30) as resp:
                    content = resp.read()
                    if not content:
                        return None
                    return json.loads(content.decode("utf-8"))
            except error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                raise GitLabError(f"GitLab API {method} {path} failed: {exc.code} {details}") from exc
            except error.URLError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
        raise GitLabError(f"GitLab API {method} {path} failed: {last_error}") from last_error

    def update_issue_labels(self, project_id: int, issue_iid: int, labels: list[str]) -> Any:
        path = f"/projects/{project_id}/issues/{issue_iid}"
        return self._request("PUT", path, {"labels": ",".join(labels)})

    def get_issue(self, project_id: int, issue_iid: int) -> dict[str, Any]:
        return self._request("GET", f"/projects/{project_id}/issues/{issue_iid}")

    def add_issue_note(self, project_id: int, issue_iid: int, body: str) -> Any:
        return self._request("POST", f"/projects/{project_id}/issues/{issue_iid}/notes", {"body": body})

    def get_issue_notes(self, project_id: int, issue_iid: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/projects/{project_id}/issues/{issue_iid}/notes?sort=asc&per_page=100") or []

    def find_open_merge_request(self, project_id: int, source_branch: str) -> dict[str, Any] | None:
        branch = parse.quote(source_branch, safe="")
        result = self._request(
            "GET",
            f"/projects/{project_id}/merge_requests?state=opened&source_branch={branch}&per_page=1",
        )
        if isinstance(result, list) and result:
            return result[0]
        return None

    def create_merge_request(
        self,
        project_id: int,
        *,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{project_id}/merge_requests",
            {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
                "remove_source_branch": False,
            },
        )

    def create_or_get_merge_request(
        self,
        project_id: int,
        *,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        existing = self.find_open_merge_request(project_id, source_branch)
        if existing:
            return existing
        return self.create_merge_request(
            project_id,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=description,
        )

    def authenticated_repo_url(self, repo_http_url: str) -> str:
        if not self.token:
            return repo_http_url
        parsed = parse.urlsplit(repo_http_url)
        netloc = f"oauth2:{parse.quote(self.token, safe='')}@{parsed.netloc}"
        return parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
