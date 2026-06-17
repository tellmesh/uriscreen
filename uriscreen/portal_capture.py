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
