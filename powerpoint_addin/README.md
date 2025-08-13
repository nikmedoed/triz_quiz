# PowerPoint Add-in Prototype

This folder contains a minimal Office.js add-in that embeds the TRIZ quiz interface inside a task pane. It connects to the existing WebSocket endpoint, fetches the scenario, and renders questions with navigation controls.

## Development

1. Start the quiz server (FastAPI).
2. Host these files via a local HTTPS server, e.g., `python -m http.server 3000` with TLS.
3. Sideload `manifest.xml` into PowerPoint.
4. Open the task pane to see quiz questions and navigate using **Prev** and **Next**.

The add-in reloads the scenario whenever the quiz server broadcasts a `reload` message.
