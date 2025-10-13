# Azure Permissions Exclamation Helper

Minimal yet production-ready starter that surfaces permission risk recommendations inside the Azure Portal. It consists of a Manifest v3 browser extension and a mock Flask backend that emits alert-informed guidance keyed by `resourceId`.

## Quick start
1. **Start the backend**
   ```bash
   cd backend
   pip install -r requirements.txt
   python server.py
   ```
   The API will listen on `http://localhost:5001`.
2. **Load the extension**
   - Open `chrome://extensions` (or `edge://extensions`).
   - Enable *Developer mode* and select **Load unpacked**.
   - Choose the `azure-permissions-exclaim/extension` directory.
3. **Simulate portal navigation**
   - Navigate to `https://portal.azure.com/#view/...` using the provided hashes in `tools/portal-sim.html` (copy the hash portion to the portal URL bar or trigger navigation buttons there).
   - When the backend reports an issue for the active blade’s `resourceId`, a pulsing exclamation badge appears in the bottom-right of the portal. Click it to see the recommendation, copy the `az` fix, or jump to a mock details page.

### Can I render the UI without Azure access?
Yes. You do **not** need your own Azure subscription or resource instances. The helper only requires a valid Azure Portal session (even a free account works) plus the local tooling in this repo:

1. Start the Flask backend as described above so `POST /recommend` is available at `http://localhost:5001`.
2. Open `tools/portal-sim.html` in a separate tab. The buttons there produce realistic Azure blade hashes with URL-encoded `resourceId` values.
3. Copy one of those hashes (for example, the storage account sample) and paste it after `https://portal.azure.com/` in any portal tab.
4. The extension’s content script will parse the hash, call the backend, and render the pulsing exclamation + recommendation panel directly in the live portal UI.

Because the backend returns mock recommendations, you can iterate entirely locally—the Azure Portal simply provides the layout that hosts the overlay.

## Validation steps
Follow this flow to confirm the end-to-end experience without real Azure access:

1. In a normal Chrome/Edge tab, open `tools/portal-sim.html` from this repo (via `file://` or a simple `python -m http.server`).
2. Click **Storage account with issue** to set the hash to a resource that exists in the backend `MOCK_ALERTS` map.
3. Switch to an actual `https://portal.azure.com` tab (signed in to any account) and paste the copied hash after the base URL. The page will reload to the simulated blade.
4. Wait for the backend POST in the browser’s devtools network panel: you should see a `POST http://localhost:5001/recommend` returning `hasIssue: true`.
5. Verify that the pulsing exclamation badge appears in the lower-right corner of the portal UI. Clicking it should open the panel populated with the mocked recommendation data. Use the **Copy az CLI fix** button to confirm clipboard feedback, and **Open details** to ensure a new tab opens with `rid` and `issue` query params.
6. Repeat with the **Resource without issue** option in the simulator. The backend will respond with `hasIssue: false`, and the badge should stay hidden—confirming the negative path works.

## Architecture overview
```
azure-permissions-exclaim/
├── backend/        # Flask API serving mock recommendations at POST /recommend
├── extension/      # Manifest v3 extension with content script + isolated overlay UI
├── tools/          # Local helpers (e.g., Azure portal hash simulator)
├── README.md       # You are here
├── LICENSE         # MIT license
└── .gitignore
```
- **Content script** observes Azure Portal hash changes, extracts the `resourceId`, and POSTs it to the backend. When `hasIssue=true`, it renders a shadow-DOM overlay with a pulsing icon and actionable panel.
- **Backend** keeps an in-memory `MOCK_ALERTS` dictionary and returns deterministic payloads. CORS headers allow the extension to call it from the Azure Portal origin.
- **Simulator** offers ready-made hashes so you can exercise the parsing logic without Azure credentials.

## Acceptance criteria checklist
- [x] Manifest v3 extension scoped to `https://portal.azure.com/*` with pulsing exclamation badge and recommendation panel.
- [x] Hash parsing extracts `resourceId` patterns like `#view/.../resourceId/%2Fsubscriptions%2F...`.
- [x] Backend `POST /recommend` returns mock data keyed by `resourceId`, including `panelUrl` and `azFix` fields.
- [x] Copy-to-clipboard and “Open details” actions wired to backend response.
- [x] Local simulator to flip between portal-style hashes without Azure access.
