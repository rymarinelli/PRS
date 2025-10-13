# Mock recommendation backend

This lightweight Flask service powers the Azure Permissions Exclamation Helper extension with mock recommendations.

## Setup
1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Run the server
```bash
python server.py
```

The API listens on `http://localhost:5001`. The `/recommend` endpoint accepts a JSON body containing a `resourceId` and returns a deterministic mock payload whenever that identifier has sample alerts in `MOCK_ALERTS`.

CORS is enabled so that the extension can call this endpoint directly from the Azure Portal origin.
