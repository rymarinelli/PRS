# Mock recommendation backend

This lightweight Flask service powers the Microsoft Defender for Cloud RBAC Advisor extension with AI-backed recommendations. A small PyTorch logistic-regression model scores each incoming Azure resource for excess-permission risk and combines the result with a remediation knowledge base for demo-friendly payloads inspired by Defender for Cloud.

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
- `modelTraining` – metadata (dataset size, accuracy, positive ratio, last training timestamp) describing the on-device model.

CORS is enabled so that the extension can call this endpoint directly from the Azure Portal origin.

## How the model is trained
- At import time the service synthesizes 720 alert observations across Contoso, Fabrikam, Northwind, AdventureWorks, and other fictional tenants. Each record encodes the `resourceId`, portal hash context, incident counts, and environment risk signals the real portal would produce.
- A logistic regression head (`torch.nn.Linear`) is then optimized against that dataset using Adam for 600 epochs. This takes well under a second on CPU.
- The resulting weights, bias, and training telemetry are frozen and used for inference. Every response echoes the training metadata so demos can speak to the model provenance without digging into code.
