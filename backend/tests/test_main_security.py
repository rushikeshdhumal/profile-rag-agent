from __future__ import annotations

from pathlib import Path

from app.main import resolve_static_path


def test_resolve_static_path_serves_file_inside_static(tmp_path: Path):
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    resolved = resolve_static_path(tmp_path, "app.js")
    assert resolved == (tmp_path / "app.js").resolve()


def test_resolve_static_path_rejects_parent_traversal(tmp_path: Path):
    static = tmp_path / "dist"
    static.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("do not serve me", encoding="utf-8")

    assert resolve_static_path(static, "../secret.txt") is None
    assert resolve_static_path(static, "../../../../etc/passwd") is None


def test_resolve_static_path_allows_nested_subpaths(tmp_path: Path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "assets" / "logo.png").write_bytes(b"\x89PNG")

    resolved = resolve_static_path(static, "assets/logo.png")
    assert resolved == (static / "assets" / "logo.png").resolve()


def test_resolve_static_path_root_itself_is_allowed(tmp_path: Path):
    static = tmp_path / "dist"
    static.mkdir()
    assert resolve_static_path(static, "") == static.resolve()
