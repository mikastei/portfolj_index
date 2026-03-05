## Debug logging

Enable portfolio debug logs:

```powershell
$env:PORTFOLIO_DEBUG="1"
py -m src.main
```

Optional strict valuation mode (raise on missing active prices):

```powershell
$env:PORTFOLIO_STRICT="1"
py -m src.main
```
