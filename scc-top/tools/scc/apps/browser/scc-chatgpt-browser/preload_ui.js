const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("scc", {
  getSettings: () => ipcRenderer.invoke("scc:getSettings"),
  setSettings: (partial) => ipcRenderer.invoke("scc:setSettings", partial),
  sendNow: () => ipcRenderer.invoke("scc:sendNow"),
  copyPayload: () => ipcRenderer.invoke("scc:copyPayload"),
  webgptSyncNow: () => ipcRenderer.invoke("scc:webgptSyncNow"),
  webgptExportNow: () => ipcRenderer.invoke("scc:webgptExportNow"),
  webgptBackfillStart: (opts) => ipcRenderer.invoke("scc:webgptBackfillStart", opts),
  webgptBackfillStop: () => ipcRenderer.invoke("scc:webgptBackfillStop"),
  setToolbarHeight: (height) => ipcRenderer.send("scc:uiHeight", height),
  nav: (action) => ipcRenderer.send("scc:navigate", action),
  openUrl: (url) => ipcRenderer.send("scc:openUrl", url),
  onSnapshot: (cb) => ipcRenderer.on("scc:snapshot", (_e, data) => cb(data)),
  onPostResult: (cb) => ipcRenderer.on("scc:postResult", (_e, data) => cb(data)),
  onWebGPTResult: (cb) => ipcRenderer.on("scc:webgptResult", (_e, data) => cb(data)),
  onWebGPTBackfillProgress: (cb) => ipcRenderer.on("scc:webgptBackfillProgress", (_e, data) => cb(data)),
  onWebGPTBackfillState: (cb) => ipcRenderer.on("scc:webgptBackfillState", (_e, data) => cb(data)),
  onNavigate: (cb) => ipcRenderer.on("scc:navigate", (_e, data) => cb(data))
});
