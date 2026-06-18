# uriscreen contract v1.0

Scheme: `screen://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: uriscreen.contract
  version: 1.0.0
scheme: screen
queries:
  - id: screen.frame
    pattern: screen://{target}/monitor/{monitor}/query/frame
commands:
  - id: screen.capture
    pattern: screen://{target}/monitor/{monitor}/command/capture
    side_effects: true
    requires_approval: true
  - id: screen.capture_loop
    pattern: screen://{target}/capture/command/loop
    side_effects: true
    requires_approval: true
```

Routes:

```txt
screen://{target}/monitor/{monitor}/query/frame
screen://{target}/monitor/{monitor}/command/capture
screen://{target}/capture/command/loop
```

Backends: `mss`, `mock` (MVP).

Side effects require `approved: true` and `allow_real` for mss capture.
