const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hdrTranscoder", {
  selectInputFile: () => ipcRenderer.invoke("dialog:selectInputFile"),
  selectInputFiles: () => ipcRenderer.invoke("dialog:selectInputFiles"),
  selectInputDirectory: () => ipcRenderer.invoke("dialog:selectInputDirectory"),
  selectOutputDirectory: () => ipcRenderer.invoke("dialog:selectOutputDirectory"),
  scanDirectory: (dirPath) => ipcRenderer.invoke("dialog:scanDirectory", dirPath),
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
});
