from __future__ import annotations

from app.github_fetch import _format_repos, _iso_date


def test_iso_date_extracts_date_part():
    assert _iso_date("2026-08-20T12:00:00Z") == "2026-08-20"


def test_iso_date_handles_missing_and_malformed():
    assert _iso_date(None) == ""
    assert _iso_date("") == ""
    assert _iso_date("not-a-date") == ""
    assert _iso_date(2026) == ""


def test_format_repos_heading_states_recency_order():
    body = _format_repos([])
    assert body.startswith("# Recent public repositories (most recently updated first)")


def test_format_repos_includes_dates_when_present():
    repos = [
        {
            "name": "rag-toolkit",
            "description": "Hybrid retrieval toolkit.",
            "language": "Python",
            "stargazers_count": 142,
            "updated_at": "2026-08-20T12:00:00Z",
            "pushed_at": "2026-08-19T09:30:00Z",
            "html_url": "https://github.com/ada-example/rag-toolkit",
        }
    ]
    body = _format_repos(repos)
    assert "updated=2026-08-20" in body
    assert "pushed=2026-08-19" in body
    assert "rag-toolkit" in body


def test_format_repos_omits_date_fields_when_absent():
    repos = [
        {
            "name": "no-dates-repo",
            "description": "",
            "language": "",
            "stargazers_count": 0,
            "html_url": "https://github.com/ada-example/no-dates-repo",
        }
    ]
    body = _format_repos(repos)
    assert "updated=" not in body
    assert "pushed=" not in body
    assert "no-dates-repo" in body


def test_format_repos_empty_list_notes_no_repos():
    body = _format_repos([])
    assert "no non-fork public repos found" in body
