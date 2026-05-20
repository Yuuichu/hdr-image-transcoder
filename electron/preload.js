const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hdrTranscoder", {
  selectInputFiles: () => ipcRenderer.invoke("dialog:selectInputFiles"),
  selectInputDirectory: () => ipcRenderer.invoke("dialog:selectInputDirectory"),
  selectOutputDirectory: () => ipcRenderer.invoke("dialog:selectOutputDirectory"),
  scanDirectory: (dirPath) => ipcRenderer.invoke("dialog:scanDirectory", dirPath),
  checkRuntime: () => ipcRenderer.invoke("runtime:check"),
  inspectImages: (filePaths) => ipcRenderer.invoke("image:inspect", filePaths),
  startConversion: (options) => ipcRenderer.invoke("conversion:start", options),
  checkOverwrite: (options) => ipcRenderer.invoke("conversion:checkOverwrite", options),
  cancelConversion: () => ipcRenderer.invoke("conversion:cancel"),
  onConversionOutput: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on("conversion:output", handler);
    return () => ipcRenderer.removeListener("conversion:output", handler);
  },
  onConversionDone: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on("conversion:done", handler);
    return () => ipcRenderer.removeListener("conversion:done", handler);
  },
  onRuntimeStatus: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on("runtime:status", handler);
    return () => ipcRenderer.removeListener("runtime:status", handler);
  },
});
