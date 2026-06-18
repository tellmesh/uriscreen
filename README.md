# uriscreen

`screen://` URI capability pack — monitor frame query, capture, and capture loop.

Backends: `mss` (X11), `portal` / `vdisplay` (Wayland), `mock` (dry-run).

Used by `urisys-node` (`pip install uriscreen`) and desktop automation pipelines.

Licensed under Apache-2.0.

## Ekosystem TellMesh

Orchestrator: **[urisys](https://github.com/tellmesh/urisys)** · Mapa: **[MESH.md](https://github.com/tellmesh/urisys/blob/main/docs/MESH.md)** · Model: **[ECOSYSTEM.md](https://github.com/tellmesh/urisys/blob/main/../docs/ECOSYSTEM.md)**

| Pole | Wartość |
|------|---------|
| **Warstwa** | Capability pack |
| **Scheme** | `screen://` |
| **Zależność** | `uricore>=0.1.8` |
| **Edge** | urisys-node |

Runtime edge: **`uri_control.edge`** w pakiecie **`uricore`** (legacy `urisysedge` usunięty 2026-06).
Router intencji: **`urirouter`** (`uri_router`) — resolve + HTTP/MQTT delegate.

<!-- end-ecosystem -->
