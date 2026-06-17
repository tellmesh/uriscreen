# UriPack: uriscreen

Self-contained Markpact — definitions, full source, run config. Unpack & run: `urisys markpact run uriscreen/uriscreen.markpact.md --as service` (writes `.markpact/`).

```yaml markpact:pack
apiVersion: urisys.io/v1
kind: UriPack
metadata:
  id: uriscreen-pack
  version: 1.0.0
  language: python
description: Screen capture — frame query, single capture, capture loop.
schemes:
- screen
capabilities:
- id: screen.frame
  uri: screen://{target}/monitor/{monitor}/query/frame
  kind: query
  operation: screen.frame
  handler: python://uriscreen.handlers:frame
  side_effects: false
  approval: not_required
- id: screen.capture
  uri: screen://{target}/monitor/{monitor}/command/capture
  kind: command
  operation: screen.capture
  handler: python://uriscreen.handlers:capture
  side_effects: true
  approval: required
- id: screen.capture_loop
  uri: screen://{target}/capture/command/loop
  kind: command
  operation: screen.capture_loop
  handler: python://uriscreen.handlers:capture_loop
  side_effects: true
  approval: required
policy:
  default: deny_mutations_without_approval
runtime:
  default_environment: mock
  supports:
  - mock
  - local
  - docker
```

```yaml markpact:run
modes:
- pack
- service
- flow
- interface
- adapter
default: service
scheme: screen
service:
  port: 8790
  wire: POST /uri/call
flow:
  ids: []
adapter:
  wire: POST /uri/call
  events: GET /events
```

```python markpact:module path=uriscreen/__init__.py
from __future__ import annotations

from .routes import register

__version__ = "0.1.0"
__all__ = ["register", "__version__"]
```

```python markpact:module path=uriscreen/backends.py
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
```

```python markpact:module path=uriscreen/handlers.py
from __future__ import annotations

import base64
import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def _screen_cfg(context: dict[str, Any]) -> dict[str, Any]:
    return context.get("config", {}).get("screen", {})


def _backend(context: dict[str, Any], payload: dict[str, Any]) -> str:
    return payload.get("backend") or _screen_cfg(context).get("default_backend", "mss")


def _output_dir(payload: dict[str, Any], context: dict[str, Any]) -> Path:
    raw = payload.get("output") or _screen_cfg(context).get("output_dir", "/tmp/urisys-screens")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _monitor_index(payload: dict[str, Any], context: dict[str, Any], monitor_param: str | None) -> int:
    if payload.get("monitor") is not None:
        return int(payload["monitor"])
    monitors = _screen_cfg(context).get("monitors") or {}
    if monitor_param == "primary":
        return int(monitors.get("primary", {}).get("index", 1))
    if monitor_param and monitor_param.isdigit():
        return int(monitor_param)
    return 1


def _store_latest(context: dict[str, Any], entry: dict[str, Any]) -> None:
    context.setdefault("state", {})["latest_screen"] = entry


def _mock_png(label: str) -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )


def capture(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    from uriscreen.backends import capture_with_fallback, resolve_backend

    monitor = _monitor_index(payload, context, context.get("params", {}).get("monitor"))
    out_dir = _output_dir(payload, context)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = out_dir / f"screen_{monitor}_{ts}.png"

    if context.get("dry_run"):
        path.write_bytes(_mock_png("mock"))
        entry = {"path": str(path), "monitor": monitor, "mime": "image/png", "backend": "mock", "dry_run": True}
        _store_latest(context, entry)
        return entry

    backend = resolve_backend(context, payload)
    if backend == "mock":
        path.write_bytes(_mock_png("mock"))
        entry = {"path": str(path), "monitor": monitor, "mime": "image/png", "backend": "mock"}
        _store_latest(context, entry)
        return entry

    if not (context.get("allow_real") or os.environ.get("URISYS_ALLOW_REAL") == "1"):
        raise PermissionError("screen capture requires allow_real=true or URISYS_ALLOW_REAL=1")

    entry = capture_with_fallback(path, monitor, context, payload)
    _store_latest(context, entry)
    return entry


def frame(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    entry = capture(payload, context)
    raw = Path(entry["path"]).read_bytes()
    entry["base64"] = base64.b64encode(raw).decode("ascii")
    return entry


def capture_loop(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    from uriscreen.backends import resolve_backend

    count = int(payload.get("count", 3))
    interval = float(payload.get("interval", 1.0))
    shots = []
    for i in range(count):
        shots.append(capture({**payload, "index": i}, context))
        if interval > 0 and i < count - 1:
            time.sleep(interval)
    return {"count": len(shots), "shots": shots, "backend": resolve_backend(context, payload)}
```

```python markpact:module path=uriscreen/portal_capture.py
"""XDG Desktop Portal screenshot (Wayland) — no mss dependency."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path


class PortalCaptureError(RuntimeError):
    pass


_INLINE_SCRIPT = r"""
import sys
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
token = "urisys_portal"
sender = bus.get_unique_name()[1:].replace(".", "_")
request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
state = {"uri": None, "error": None}

def _on_response(response, results):
    if int(response) != 0:
        state["error"] = f"portal response code {response}"
    elif "uri" in results:
        state["uri"] = str(results["uri"])
    else:
        state["error"] = "portal response missing uri"
    loop.quit()

bus.add_signal_receiver(
    _on_response,
    dbus_interface="org.freedesktop.portal.Request",
    path=request_path,
    signal_name="Response",
)
proxy = bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
iface = dbus.Interface(proxy, "org.freedesktop.portal.Screenshot")
iface.Screenshot("", {"handle_token": token, "interactive": False})

loop = GLib.MainLoop()
GLib.timeout_add(12000, lambda: (loop.quit(), False)[1])
loop.run()

if state["error"]:
    print(state["error"], file=sys.stderr)
    sys.exit(2)
if not state["uri"]:
    print("portal screenshot timed out", file=sys.stderr)
    sys.exit(3)
print(state["uri"])
"""


def _portal_python() -> str:
    override = os.environ.get("URISYS_PORTAL_PYTHON", os.environ.get("KORU_PORTAL_PYTHON", "")).strip()
    if override:
        return override
    for candidate in ("/usr/bin/python3", shutil.which("python3"), sys.executable):
        if not candidate:
            continue
        try:
            proc = subprocess.run(
                [candidate, "-c", "import dbus; import gi"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            return candidate
    return sys.executable


def capture_portal_png(*, timeout_seconds: float = 15.0) -> bytes:
    python = _portal_python()
    env = os.environ.copy()
    uid = os.getuid()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    try:
        proc = subprocess.run(
            [python, "-c", _INLINE_SCRIPT],
            capture_output=True,
            timeout=timeout_seconds,
            text=True,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PortalCaptureError(f"portal subprocess failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"exit code {proc.returncode}"
        raise PortalCaptureError(f"portal capture failed: {detail}")
    uri = (proc.stdout or "").strip()
    if not uri:
        raise PortalCaptureError("portal returned empty URI")
    path = Path(urllib.parse.urlparse(uri).path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PortalCaptureError(f"cannot read portal screenshot at {path}") from exc
```

```python markpact:module path=uriscreen/routes.py
from __future__ import annotations

from importlib.resources import files

from urisysedge.manifest import register_manifest_file


def register(runtime):
    register_manifest_file(runtime, files(__package__).joinpath("manifest.yaml"))
```

```markdown markpact:docs
# uriscreen

`screen://` URI capability pack — monitor frame query, capture, and capture loop.

Backends: `mss` (X11), `portal` / `vdisplay` (Wayland), `mock` (dry-run).

Used by `urisys-node` (`pip install uriscreen`) and desktop automation pipelines.

Licensed under Apache-2.0.
```

