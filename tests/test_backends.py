"""Auto screen backend selection."""

from __future__ import annotations

from uriscreen.backends import is_black_png, resolve_backend


def test_resolve_backend_auto_x11(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    ctx = {"config": {"screen": {}}}
    assert resolve_backend(ctx, {}) == "mss"


def test_resolve_backend_auto_wayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    ctx = {"config": {"screen": {}}}
    assert resolve_backend(ctx, {}) == "portal"


def test_is_black_png(tmp_path):
    import pytest

    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")

    p = tmp_path / "black.png"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(p)
    assert is_black_png(p) is True
    p2 = tmp_path / "white.png"
    Image.new("RGB", (10, 10), (255, 255, 255)).save(p2)
    assert is_black_png(p2) is False
