# Upstream template

This app is based on a locally downloaded copy of an Electron quick-start project:

- Upstream project: `haloislet/electron-quick-start` (folder name on disk: `electron-quick-start-master`)
- License: MIT (see `LICENSE`)

Notes:
- The environment running this agent blocks direct `git clone` to the public internet, so upstream was provided locally under `<ABS_PATH>/shoucuo cursor/electron-quick-start-master`.
- We modernize the app (newer Electron, preload + contextIsolation + BrowserView) and add SCC-specific ChatGPT directive forwarding on top.
