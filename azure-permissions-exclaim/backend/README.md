# Mock recommendation backend

This lightweight Flask service powers the Azure Permissions Exclamation Helper extension with AI-backed recommendations. A small PyTorch logistic-regression model scores each incoming Azure resource for excess-permission risk and combines the result with a remediation knowledge base for demo-friendly payloads.

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

The API listens on `http://localhost:5001`. The `/recommend` endpoint accepts a JSON body containing a `resourceId` and returns an AI-generated payload whenever the PyTorch risk score crosses the configured threshold. Responses include:

- `modelScore` – the normalized risk produced by the PyTorch model.
- `topFactors` – the dominant engineered features contributing to the score.
- Alert-driven summaries and CLI fixes tailored to the requested resource.

CORS is enabled so that the extension can call this endpoint directly from the Azure Portal origin.
