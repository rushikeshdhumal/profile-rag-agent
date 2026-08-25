from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

PROFILE_README_MAX = 4000
REPO_README_MAX = 2000
REPO_DESC_MAX = 160
MAX_REPO_LIST = 10
MAX_REPO_READMES = 5


def fetch_github_documents(username: str) -> list[tuple[str, str]]:
    """Fetch public GitHub data as separate corpus documents (partial-failure tolerant)."""
    username = username.strip().lstrip("@")
    if not username or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", username):
        raise ValueError("Invalid GitHub username")

    settings = get_settings()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-rag-agent",
    }
    if settings.github_token.strip():
        headers["Authorization"] = f"Bearer {settings.github_token.strip()}"

    docs: list[tuple[str, str]] = []
    repos: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0, headers=headers) as client:
        try:
            user_resp = client.get(f"https://api.github.com/users/{username}")
            if user_resp.status_code == 404:
                raise ValueError(f"GitHub user not found: {username}")
            user_resp.raise_for_status()
            docs.append(("github_identity.md", _format_user(user_resp.json())))
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("GitHub identity fetch failed for %s: %s", username, exc)
            docs.append(
                (
                    "github_identity.md",
                    f"# GitHub profile\n\nLogin: {username}\n\n(Identity fetch failed: {exc})\n",
                )
            )

        try:
            repos_resp = client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"sort": "updated", "per_page": 30, "type": "owner"},
            )
            repos_resp.raise_for_status()
            repos = [r for r in repos_resp.json() if not r.get("fork")]
            docs.append(("github_repos.md", _format_repos(repos[:MAX_REPO_LIST])))
        except Exception as exc:
            logger.warning("GitHub repos fetch failed for %s: %s", username, exc)
            docs.append(
                (
                    "github_repos.md",
                    f"# Recent public repositories\n\n(Fetch failed: {exc})\n",
                )
            )

        try:
            readme = _fetch_raw_readme(client, username, username)
            if readme:
                docs.append(
                    (
                        "github_readme.md",
                        "# GitHub profile README\n\n" + readme[:PROFILE_README_MAX],
                    )
                )
        except Exception as exc:
            logger.warning("GitHub profile README fetch failed for %s: %s", username, exc)

        for repo in _top_repos(repos)[:MAX_REPO_READMES]:
            name = str(repo.get("name") or "").strip()
            if not name:
                continue
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:60]
            try:
                body = _fetch_raw_readme(client, username, name)
                if not body:
                    continue
                header_lines = [
                    f"# Repository: {name}\n",
                    f"URL: {repo.get('html_url') or ''}",
                    f"Language: {repo.get('language') or ''}",
                    f"Stars: {repo.get('stargazers_count', 0)}",
                ]
                updated = _iso_date(repo.get("updated_at"))
                pushed = _iso_date(repo.get("pushed_at"))
                if updated:
                    header_lines.append(f"Updated: {updated}")
                if pushed:
                    header_lines.append(f"Pushed: {pushed}")
                header_lines.append(
                    f"Description: {_truncate(repo.get('description') or '', REPO_DESC_MAX)}\n"
                )
                header = "\n".join(header_lines) + "\n"
                docs.append(
                    (f"github_repo_{safe}.md", header + body[:REPO_README_MAX])
                )
            except Exception as exc:
                logger.warning("GitHub README fetch failed for %s/%s: %s", username, name, exc)

    return docs


def fetch_github_profile(username: str) -> str:
    """Backward-compatible single-string fetch (joined documents)."""
    docs = fetch_github_documents(username)
    return "\n\n".join(text for _, text in docs)


def _iso_date(value: Any) -> str:
    """Reduce a GitHub timestamp ("2026-08-20T12:00:00Z") to its date part.

    Returns "" for missing/malformed input so callers can omit the field
    rather than print a confusing empty date.
    """
    if not value or not isinstance(value, str):
        return ""
    return value[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", value) else ""


def _truncate(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_user(user: dict[str, Any]) -> str:
    lines = [
        "# GitHub profile",
        f"Login: {user.get('login', '')}",
        f"Name: {user.get('name') or ''}",
        f"Bio: {user.get('bio') or ''}",
        f"Company: {user.get('company') or ''}",
        f"Location: {user.get('location') or ''}",
        f"Blog: {user.get('blog') or ''}",
        f"Public repos: {user.get('public_repos', 0)}",
        f"Followers: {user.get('followers', 0)}",
        f"Profile URL: {user.get('html_url', '')}",
    ]
    return "\n".join(lines)


def _format_repos(repos: list[dict[str, Any]]) -> str:
    # Fetched with sort=updated (see fetch_github_documents), so this order
    # is meaningful for "most recent project" questions -- state that plainly
    # rather than relying on the model to infer list order as recency.
    lines = ["# Recent public repositories (most recently updated first)"]
    for repo in repos:
        desc = _truncate(repo.get("description") or "", REPO_DESC_MAX)
        lang = repo.get("language") or ""
        stars = repo.get("stargazers_count", 0)
        fields = [f"language={lang}", f"stars={stars}"]
        updated = _iso_date(repo.get("updated_at"))
        pushed = _iso_date(repo.get("pushed_at"))
        if updated:
            fields.append(f"updated={updated}")
        if pushed:
            fields.append(f"pushed={pushed}")
        fields.append(f"url={repo.get('html_url')}")
        lines.append(f"- {repo.get('name')}: {desc} ({', '.join(fields)})")
    if len(lines) == 1:
        lines.append("- (no non-fork public repos found)")
    return "\n".join(lines)


def _top_repos(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer highest stars; fall back to API order (recently updated)."""
    if not repos:
        return []
    ranked = sorted(
        repos,
        key=lambda r: (int(r.get("stargazers_count") or 0), r.get("pushed_at") or ""),
        reverse=True,
    )
    return ranked


def _fetch_raw_readme(client: httpx.Client, owner: str, repo: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    resp = client.get(url, headers={"Accept": "application/vnd.github.raw"})
    if resp.status_code == 404:
        return ""
    if resp.status_code >= 400:
        logger.warning("Could not fetch README for %s/%s: %s", owner, repo, resp.status_code)
        return ""
    return resp.text.strip()
