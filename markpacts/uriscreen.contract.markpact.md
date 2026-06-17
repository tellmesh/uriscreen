# uriscreen contract v0.1

Scheme: `screen://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: uriscreen.contract
  version: 0.1.0
scheme: screen
queries:
  - id: screen.frame
    pattern: screen://{node}/monitor/{monitor}/query/frame
commands:
  - id: screen.capture
    pattern: screen://{node}/monitor/{monitor}/command/capture
    side_effects: true
    requires_approval: true
  - id: screen.capture_loop
    pattern: screen://{node}/capture/command/loop
    side_effects: true
    requires_approval: true
```

Routes:

```txt
screen://{node}/monitor/{monitor}/query/frame
screen://{node}/monitor/{monitor}/command/capture
screen://{node}/capture/command/loop
```

Backends: `mss`, `mock` (MVP).

Side effects require `approved: true` and `allow_real` for mss capture.
