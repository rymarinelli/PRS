# Azure RBAC Risk Advisor

Minimal yet production-ready starter that surfaces Azure RBAC risk recommendations inside the Azure Portal. It consists of a Manifest v3 browser extension and an AI-backed Flask backend that scores each `resourceId` with a lightweight PyTorch model trained on synthetic Defender for Cloud telemetry.

## Quick start
1. **Start the backend (Flask + PyTorch inference)**
   ```bash
   cd backend
   pip install -r requirements.txt
   python server.py
   ```
   The API will listen on `http://localhost:5001` and load a small PyTorch model into memory for scoring.
2. **Load the extension**
   - Open `chrome://extensions` (or `edge://extensions`).
   - Enable *Developer mode* and select **Load unpacked**.
   - Choose the `azure-permissions-exclaim/extension` directory.
3. **Simulate portal navigation**
   - Navigate to `https://portal.azure.com/#view/...` using the provided hashes in `tools/portal-sim.html` (copy the hash portion to the portal URL bar or trigger navigation buttons there).
   - When the backend reports an issue for the active blade’s `resourceId`, Azure RBAC Risk Advisor pulses an exclamation badge in the bottom-right of the portal. Click it to see the AI-crafted recommendation, copy the `az` fix, or jump to a mock details page.

### Can I render the UI without Azure access?
Yes. You do **not** need your own Azure subscription or resource instances. The helper only requires a valid Azure Portal session (even a free account works) plus the local tooling in this repo:

1. Start the Flask backend as described above so `POST /recommend` is available at `http://localhost:5001`. The service will spin up an on-device PyTorch model; no outbound network calls occur.
2. Open `tools/portal-sim.html` in a separate tab. The buttons there produce realistic Azure blade hashes (for Contoso storage, Fabrikam Key Vault, and Northwind SQL) with URL-encoded `resourceId` values.
3. Copy one of those hashes (for example, the Contoso storage sample) and paste it after `https://portal.azure.com/` in any portal tab.
4. The extension’s content script will parse the hash, call the backend, and render the pulsing exclamation + recommendation panel directly in the live portal UI.

Because the backend returns deterministic AI-generated recommendations, you can iterate entirely locally—the Azure Portal simply provides the layout that hosts the overlay.

### How the AI recommendation model works
- When `backend/server.py` starts, it synthesizes 720 alert records spanning Contoso, Fabrikam, Northwind, and other fictional tenants. Each sample encodes resource depth, URL context, environment risk, and incident counts just like the real extension would observe.
- The service then trains a logistic-regression head in PyTorch against that dataset. Training completes in under a second on CPU and yields accuracy metrics (size, accuracy, positive ratio, last trained timestamp) that surface in the UI for transparency.
- Every `/recommend` response includes `modelTraining` metadata so reviewers can confirm the model provenance directly inside the portal overlay or the standalone render demo.

### I just want to *see* the overlay — is there a render?
Absolutely. For demos or stakeholder reviews you can load a lightweight Azure Portal facsimile that already has the helper rendered in place:

1. From the repo root run a quick static server so browsers can load the shared CSS: `python -m http.server 8000`.
2. Visit <http://localhost:8000/azure-permissions-exclaim/tools/render-demo.html>.
3. The page recreates an Azure IAM blade and injects the same shadow-DOM overlay the extension uses. The exclamation button animates inside whichever row you select, calling the live backend when available and falling back to demo payloads otherwise. The panel now highlights the PyTorch training metadata so you can discuss the model lineage while demoing.

This render relies purely on local assets—it does **not** require an Azure subscription, portal login, or the Flask backend (though it will consume the backend if it is running).

## Validation steps
Follow this flow to confirm the end-to-end experience without real Azure access:

1. In a normal Chrome/Edge tab, open `tools/portal-sim.html` from this repo (via `file://` or a simple `python -m http.server`).
2. Click **Storage account · contoso-retail-prod** to set the hash to a resource that the backend has historical incident data for.
3. Switch to an actual `https://portal.azure.com` tab (signed in to any account) and paste the copied hash after the base URL. The page will reload to the simulated blade.
4. Wait for the backend POST in the browser’s devtools network panel: you should see a `POST http://localhost:5001/recommend` returning `hasIssue: true` with `modelScore` and `topFactors` fields.
5. Verify that the pulsing exclamation badge appears in the lower-right corner of the portal UI. Clicking it should open the panel populated with the AI recommendation (including alert context injected into the summary). Use the **Copy az CLI fix** button to confirm clipboard feedback, and **Open details** to ensure a new tab opens with `rid` and `issue` query params.
6. Repeat with the **Resource without issue** option in the simulator. The backend will respond with `hasIssue: false` plus a low `modelScore`, and the badge should stay hidden—confirming the negative path works.

## Architecture overview
```
azure-permissions-exclaim/
├── backend/        # Flask API serving PyTorch-scored recommendations at POST /recommend
├── extension/      # Manifest v3 extension with content script + isolated overlay UI
├── tools/          # Local helpers (e.g., Azure portal hash simulator)
├── README.md       # You are here
├── LICENSE         # MIT license
└── .gitignore
```
- **Content script** observes Azure Portal hash changes, extracts the `resourceId`, and POSTs it to the backend. When `hasIssue=true`, it renders a shadow-DOM overlay with a pulsing icon and actionable panel.
- **Backend** embeds a tiny PyTorch logistic-regression model plus a knowledge base of remediation playbooks. CORS headers allow the extension to call it from the Azure Portal origin.
- **Simulator** offers ready-made hashes so you can exercise the parsing logic without Azure credentials.

## Acceptance criteria checklist
- [x] Manifest v3 extension scoped to `https://portal.azure.com/*` with pulsing Azure RBAC Risk Advisor badge and recommendation panel.
- [x] Hash parsing extracts `resourceId` patterns like `#view/.../resourceId/%2Fsubscriptions%2F...`.
- [x] Backend `POST /recommend` returns AI-scored data keyed by `resourceId`, including `panelUrl`, `azFix`, and model transparency fields.
- [x] Copy-to-clipboard and “Open details” actions wired to backend response.
- [x] Local simulator to flip between portal-style hashes without Azure access.
