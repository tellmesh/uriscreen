"""Auto screen backends: vdisplay agent, portal (Wayland), mss (X11)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .portal_capture import PortalCaptureError, capture_portal_png


def session_type() -> str:
    return (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()


def is_wayland() -> bool:
    return session_type() == "wayland"


def vdisplay_agent_url() -> str:
    return os.environ.get("VDISPLAY_AGENT_URL", "http://127.0.0.1:8765").rstrip("/")


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, timeout: float = 5.0) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def vdisplay_agent_up() -> bool:
    try:
        out = _http_json(f"{vdisplay_agent_url()}/health", timeout=1.5)
        return bool(out.get("ok", True))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def vdisplay_screencast_ready() -> bool:
    try:
        out = _http_json(f"{vdisplay_agent_url()}/session/screencast/status", timeout=2.0)
        data = out.get("result") or out
        return bool(data.get("ready") or data.get("capture_ready"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, KeyError):
        return False


def resolve_backend(context: dict[str, Any], payload: dict[str, Any]) -> str:
    cfg = context.get("config", {}).get("screen", {})
    backend = payload.get("backend") or cfg.get("default_backend") or os.environ.get("URISYS_SCREEN_BACKEND", "auto")
    if backend != "auto":
        return str(backend)
    if is_wayland():
        if vdisplay_agent_up() and vdisplay_screencast_ready():
            return "vdisplay"
        return "portal"
    return "mss"


def is_black_png(path: Path, *, threshold: float = 0.98) -> bool:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return False
    im = Image.open(path).convert("L")
    pixels = list(im.getdata())
    if not pixels:
        return True
    black = sum(1 for p in pixels if p < 8)
    return (black / len(pixels)) >= threshold


def capture_vdisplay(path: Path, monitor: int, source: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"output": str(path), "monitor": monitor}
    if source:
        body["source"] = source
    out = _http_json(f"{vdisplay_agent_url()}/capture/frame", method="POST", body=body, timeout=130.0)
    data = out.get("result") or out
    if not out.get("ok", True) and not data.get("path"):
        raise RuntimeError(data.get("error") or out.get("error") or "vdisplay capture failed")
    return {
        "path": str(data.get("path") or path),
        "mime": "image/png",
        "backend": "vdisplay",
        "method": data.get("method"),
        "width": data.get("width"),
        "height": data.get("height"),
        "source": data.get("source"),
    }


def capture_portal(path: Path) -> dict[str, Any]:
    raw = capture_portal_png()
    path.write_bytes(raw)
    width = height = None
    try:
        from PIL import Image  # type: ignore

        im = Image.open(path)
        width, height = im.size
    except Exception:
        pass
    return {
        "path": str(path),
        "mime": "image/png",
        "backend": "portal",
        "width": width,
        "height": height,
    }


def capture_with_fallback(
    path: Path,
    monitor: int,
    context: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Try resolved backend; on Wayland retry portal/vdisplay when mss is black."""
    primary = resolve_backend(context, payload)
    chain = [primary]
    if is_wayland():
        for alt in ("vdisplay", "portal", "mss"):
            if alt not in chain:
                chain.append(alt)
    elif "mss" not in chain:
        chain.append("mss")

    last_exc: Exception | None = None
    for backend in chain:
        try:
            if backend == "vdisplay":
                entry = capture_vdisplay(path, monitor, payload.get("source"))
            elif backend == "portal":
                entry = capture_portal(path)
            elif backend == "mss":
                entry = _capture_mss(path, monitor)
            else:
                continue
            if backend == "mss" and is_black_png(path) and is_wayland():
                last_exc = RuntimeError("mss returned black frame on Wayland")
                continue
            entry["monitor"] = monitor
            entry["backend_chain"] = chain
            entry["backend_used"] = backend
            return entry
        except (PortalCaptureError, RuntimeError, OSError, urllib.error.URLError) as exc:
            last_exc = exc
            continue
    raise RuntimeError(f"all capture backends failed: {last_exc}")


def _capture_mss(path: Path, monitor: int) -> dict[str, Any]:
    import mss  # type: ignore
    from PIL import Image  # type: ignore

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[monitor])
        img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
        img.save(path, format="PNG")
    return {
        "path": str(path),
        "mime": "image/png",
        "backend": "mss",
        "width": shot.width,
        "height": shot.height,
    }
