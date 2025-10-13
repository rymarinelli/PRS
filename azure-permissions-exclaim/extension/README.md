# Azure Permissions Exclamation Helper – Extension

This folder contains the Chrome/Edge extension that surfaces permission recommendations while you browse the Azure Portal.

## Load the extension locally
1. Build and run the mock backend from `../backend` (defaults to `http://localhost:5001`).
2. In Chrome or Edge, open `chrome://extensions` (or `edge://extensions`).
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select the `azure-permissions-exclaim/extension` directory.
5. Navigate to `https://portal.azure.com/` (or open `../tools/portal-sim.html` in a local file tab for development).

When the backend reports an issue for the blade’s `resourceId`, the pulsing exclamation icon appears in the lower-right corner. Click it to open the recommendation panel, copy the suggested az CLI fix, or jump to the details view.

## Developing against the simulator
The `tools/portal-sim.html` file can be opened directly in the browser to simulate Azure Portal hash changes. Open the page, click one of the sample links, and the extension will parse the mock `resourceId` and call the backend.
