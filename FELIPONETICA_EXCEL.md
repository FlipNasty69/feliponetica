# Local Feliponetica Excel converter

The Excel worksheet macro sends edited column C values as UTF-8 plain text to
`http://127.0.0.1:8765/convert`. This local service uses the Pollito converter
from this checkout and does not use the hosted Word API or its bearer key.

Start the converter from this project directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m features.feliponetica_local_api
```

Keep its window open while using Excel. If an older converter is already
running on port 8765, stop it in its existing PowerShell window with
**Ctrl+C** first, then start the command above from this checkout. Starting it
from a different project copy can leave Excel using older transcription rules.

To check the local service, send a plain-text POST to
`http://127.0.0.1:8765/convert`; for example, `excited` should return
`ek-sai-ted`. The service listens only on `127.0.0.1`.
