const { app, BrowserWindow, dialog, ipcMain, screen } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { execFile, spawn } = require("node:child_process");

const PROJECT_ROOT = app.isPackaged
    ? path.join(process.resourcesPath, "python")
    : path.resolve(__dirname, "..");

function resolvePythonExe() {
  if (!app.isPackaged) {
    return process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
  }

  const packagedPython = process.platform === "win32"
    ? path.join(PROJECT_ROOT, "python.exe")
    : path.join(PROJECT_ROOT, "bin", "python3");
  if (fs.existsSync(packagedPython)) {
    return packagedPython;
  }

  const venvFallback = process.platform === "win32"
    ? path.join(PROJECT_ROOT, "Scripts", "python.exe")
    : path.join(PROJECT_ROOT, "bin", "python3");
  return venvFallback;
}

const PYTHON_EXE = resolvePythonExe();
const JXL_MODES = ["rec2020-pq", "linear-srgb"];
const FIDELITY_MODES = ["master", "display", "compat"];
const GAINMAP_HEADROOM_MODES = ["source-peak", "auto"];
const DEFAULT_NAME_PATTERN = "{name}";
const INVALID_FILENAME_RE = /[<>:"/\\|?*\x00-\x1f]/g;
const WINDOW_MARGIN = 80;
const MIN_CONTENT_WIDTH = 1180;
const MIN_CONTENT_HEIGHT = 780;
const INPUT_EXTENSIONS = [
  "jxr",
  "wdp",
  "hdp",
  "jxl",
  "exr",
  "avif",
  "heic",
  "heif",
  "hdr",
  "jpg",
  "jpeg",
  "png",
  "tif",
  "tiff",
];

let mainWindow = null;
let currentProcess = null;
let cancelRequested = false;
let cancelForceTimer = null;
let cancelForceUsed = false;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

async function resizeWindowToContent(win) {
  if (!win || win.isDestroyed()) {
    return;
  }

  const contentSize = await win.webContents.executeJavaScript(`
    (() => {
      const doc = document.documentElement;
      const body = document.body;
      return {
        width: Math.ceil(Math.max(doc.scrollWidth, body ? body.scrollWidth : 0)),
        height: Math.ceil(Math.max(doc.scrollHeight, body ? body.scrollHeight : 0))
      };
    })()
  `);

  const display = screen.getDisplayMatching(win.getBounds());
  const maxWidth = Math.max(MIN_CONTENT_WIDTH, display.workArea.width - WINDOW_MARGIN);
  const maxHeight = Math.max(MIN_CONTENT_HEIGHT, display.workArea.height - WINDOW_MARGIN);
  const width = clamp(contentSize.width, MIN_CONTENT_WIDTH, maxWidth);
  const height = clamp(contentSize.height, MIN_CONTENT_HEIGHT, maxHeight);

  win.setContentSize(width, height);
  win.center();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 1040,
    minHeight: 760,
    backgroundColor: "#f5f6f8",
    title: "HDR Image Transcoder",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.webContents.once("did-finish-load", () => {
    resizeWindowToContent(mainWindow).catch((error) => {
      console.error("Failed to resize window to content:", error);
    });
  });
}

function sendToRenderer(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

function runtimeFailure(error, extra = {}) {
  return {
    ok: false,
    missingTools: [],
    pythonVersion: {
      executable: PYTHON_EXE,
      version: null,
      prefix: null,
    },
    dependencyErrors: [{ package: "python", module: "python", error: error.message || String(error) }],
    ...extra,
  };
}

function clearCancelForceTimer() {
  if (cancelForceTimer) {
    clearTimeout(cancelForceTimer);
    cancelForceTimer = null;
  }
}

function forceKillProcess(child) {
  if (!child || child.exitCode !== null) {
    return;
  }

  cancelForceUsed = true;
  if (process.platform === "win32" && child.pid) {
    execFile(
      "taskkill",
      ["/PID", String(child.pid), "/T", "/F"],
      { windowsHide: true },
      (error) => {
        if (error && currentProcess === child) {
          sendToRenderer("conversion:output", {
            stream: "stderr",
            text: `taskkill failed: ${error.message}\n`,
          });
        }
      },
    );
    return;
  }

  child.kill("SIGKILL");
}

function requestProcessCancel(child) {
  if (!child || child.exitCode !== null) {
    return false;
  }

  cancelRequested = true;
  child.kill();
  clearCancelForceTimer();
  cancelForceTimer = setTimeout(() => {
    if (currentProcess === child) {
      forceKillProcess(child);
    }
    cancelForceTimer = null;
  }, 3000);
  return true;
}

function getOutputExtension(format) {
  switch (format) {
    case "jxl":
      return ".jxl";
    case "ultrahdr":
      return ".jpg";
    case "heif":
      return ".heic";
    case "avif":
    case "gainmap":
    default:
      return ".avif";
  }
}

function isSamePath(left, right) {
  const resolvedLeft = path.resolve(left);
  const resolvedRight = path.resolve(right);

  if (process.platform === "win32") {
    return resolvedLeft.toLowerCase() === resolvedRight.toLowerCase();
  }

  return resolvedLeft === resolvedRight;
}

function resolveOutputPath(inputPath, outputDir, format, inputMode) {
  if (!outputDir) {
    return null;
  }

  if (inputMode === "directory") {
    return null;
  }

  const parsed = path.parse(inputPath);
  const outputPath = path.join(outputDir, `${parsed.name}${getOutputExtension(format)}`);

  if (isSamePath(inputPath, outputPath)) {
    return path.join(outputDir, `${parsed.name}_converted${parsed.ext}`);
  }

  return outputPath;
}

function numberToken(index, start = 1, padding = 3) {
  const number = start + index - 1;
  const text = String(number);
  return padding > 0 ? text.padStart(padding, "0") : text;
}

function sanitizeOutputStem(stem) {
  return String(stem).replace(INVALID_FILENAME_RE, "_").trim().replace(/^\.+|\.+$/g, "");
}

function applyNameTemplate(stem, index, options) {
  let name = stem;
  if (options.nameFind) {
    name = name.split(options.nameFind).join(options.nameReplace || "");
  }

  const number = numberToken(index, options.nameStart ?? 1, options.namePadding ?? 3);
  const pattern = options.namePattern || DEFAULT_NAME_PATTERN;
  if (pattern !== DEFAULT_NAME_PATTERN) {
    name = pattern.replaceAll("{name}", name).replaceAll("{n}", number);
  }

  name = `${options.namePrefix || ""}${name}${options.nameSuffix || ""}`;
  name = sanitizeOutputStem(name);
  return name || `output_${number}`;
}

function appendInfoJsonPaths(paths, options) {
  if (!options.infoJson) {
    return paths;
  }
  const sidecars = paths.map((outputPath) => {
    const parsed = path.parse(outputPath);
    return path.join(parsed.dir, `${parsed.name}.info.json`);
  });
  return [...paths, ...sidecars];
}

function appendNamingArgs(args, options) {
  args.push("--name-prefix", options.namePrefix || "");
  args.push("--name-suffix", options.nameSuffix || "");
  args.push("--name-find", options.nameFind || "");
  args.push("--name-replace", options.nameReplace || "");
  args.push("--name-pattern", options.namePattern || DEFAULT_NAME_PATTERN);
  args.push("--name-start", String(options.nameStart ?? 1));
  args.push("--name-padding", String(options.namePadding ?? 3));
}

function runPythonJson(args) {
  return new Promise((resolve, reject) => {
    execFile(
      PYTHON_EXE,
      args,
      {
        cwd: PROJECT_ROOT,
        env: { ...process.env, PYTHONNOUSERSITE: "1" },
        windowsHide: true,
        maxBuffer: 20 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        if (error) {
          const detail = stderr && stderr.trim() ? `${error.message}\n${stderr.trim()}` : error.message;
          reject(new Error(detail));
          return;
        }
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error(`Unable to parse Python JSON output: ${parseError.message}`));
        }
      },
    );
  });
}

async function checkRuntimeEnvironment() {
  if (app.isPackaged && !fs.existsSync(PYTHON_EXE)) {
    return runtimeFailure(new Error(`Bundled Python not found: ${PYTHON_EXE}`));
  }

  try {
    return await runPythonJson(["-m", "hdr_transcoder.tools_check"]);
  } catch (error) {
    return runtimeFailure(error);
  }
}

function buildArgs(options) {
  let args;
  let outputPath = null;

  if (options.inputMode === "files" && Array.isArray(options.inputPaths)) {
    args = ["hdr2avif.py", ...options.inputPaths];
    const outputDir = options.outputDir || path.dirname(path.resolve(options.inputPaths[0]));
    if (outputDir) {
      args.push("--output-dir", outputDir);
    }
  } else {
    args = ["hdr2avif.py", options.inputPath];
    outputPath = resolveOutputPath(
      options.inputPath,
      options.outputDir,
      options.format,
      options.inputMode,
    );

    if (outputPath) {
      args.push(outputPath);
    }

    if (options.inputMode === "directory" && options.outputDir) {
      args.push("--output-dir", options.outputDir);
    }
  }

  if (options.format && options.format !== "gainmap") {
    args.push("--format", options.format);
  } else if (options.format === "gainmap") {
    args.push("--format", "gainmap");
  }

  args.push("--fidelity", options.fidelity || "master");
  args.push("--quality", String(options.quality));
  args.push("--speed", String(options.speed));
  if (options.headroom != null && typeof options.headroom === "number") {
    args.push("--headroom", String(options.headroom));
  }
  if (options.format === "gainmap") {
    args.push("--gainmap-headroom-mode", options.gainmapHeadroomMode || "source-peak");
  }

  if (options.lossless && options.format === "jxl") {
    args.push("--lossless");
  }

  if (options.format === "jxl") {
    args.push("--jxl-mode", options.jxlMode || "rec2020-pq");
  }

  if (options.debugOverlay) {
    args.push("--debug-overlay");
  }
  if (options.infoJson) {
    args.push("--info-json");
  }

  appendNamingArgs(args, options);

  return { args, outputPath };
}

function validateOptions(options) {
  if (!options || typeof options !== "object") {
    throw new Error("Missing conversion options.");
  }
  if (options.inputMode === "files") {
    if (!Array.isArray(options.inputPaths) || options.inputPaths.length === 0) {
      throw new Error("Select at least one input file first.");
    }
  } else {
    if (!options.inputPath || typeof options.inputPath !== "string") {
      throw new Error("Select an input file or directory first.");
    }
  }
  if (!["file", "directory", "files"].includes(options.inputMode)) {
    throw new Error("Input mode must be file, files, or directory.");
  }
  if (!["gainmap", "jxl", "ultrahdr", "avif", "heif"].includes(options.format)) {
    throw new Error("Unknown output format.");
  }
  if (options.format === "jxl" && !JXL_MODES.includes(options.jxlMode || "rec2020-pq")) {
    throw new Error("Unknown JPEG XL mode.");
  }
  if (!FIDELITY_MODES.includes(options.fidelity || "master")) {
    throw new Error("Unknown fidelity mode.");
  }
  if (!GAINMAP_HEADROOM_MODES.includes(options.gainmapHeadroomMode || "source-peak")) {
    throw new Error("Unknown gainmap headroom mode.");
  }
  if (options.debugOverlay != null && typeof options.debugOverlay !== "boolean") {
    throw new Error("Debug overlay must be true or false.");
  }
  if (options.infoJson != null && typeof options.infoJson !== "boolean") {
    throw new Error("Info JSON must be true or false.");
  }
  if (!Number.isInteger(options.quality) || options.quality < 0 || options.quality > 100) {
    throw new Error("Quality must be between 0 and 100.");
  }
  if (!Number.isInteger(options.speed) || options.speed < 0 || options.speed > 10) {
    throw new Error("Speed must be between 0 and 10.");
  }
  if (typeof options.headroom !== "number" || options.headroom <= 0) {
    throw new Error("Base headroom must be greater than 0.");
  }
  const nameStart = options.nameStart ?? 1;
  const namePadding = options.namePadding ?? 3;
  if (!Number.isInteger(nameStart) || nameStart < 0) {
    throw new Error("Name start must be a non-negative integer.");
  }
  if (!Number.isInteger(namePadding) || namePadding < 0) {
    throw new Error("Name padding must be a non-negative integer.");
  }
}

ipcMain.handle("dialog:selectInputFiles", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select HDR images",
    properties: ["openFile", "multiSelections"],
    filters: [
      { name: "HDR images", extensions: INPUT_EXTENSIONS },
      { name: "All files", extensions: ["*"] },
    ],
  });

  if (result.canceled || result.filePaths.length === 0) {
    return [];
  }

  return result.filePaths;
});

ipcMain.handle("dialog:selectInputDirectory", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select input directory",
    properties: ["openDirectory"],
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  return result.filePaths[0];
});

ipcMain.handle("dialog:selectOutputDirectory", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select output directory",
    properties: ["openDirectory", "createDirectory"],
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  return result.filePaths[0];
});

ipcMain.handle("dialog:scanDirectory", async (_event, directoryPath) => {
  try {
    const entries = fs.readdirSync(directoryPath, { withFileTypes: true });
    const files = entries
      .filter((e) => e.isFile() && INPUT_EXTENSIONS.includes(path.extname(e.name).toLowerCase().replace(".", "")))
      .map((e) => e.name);
    return { count: files.length, files };
  } catch {
    return { count: 0, files: [], error: "Unable to scan directory." };
  }
});

ipcMain.handle("image:inspect", async (_event, filePaths) => {
  if (!Array.isArray(filePaths) || filePaths.length === 0) {
    return [];
  }
  const paths = filePaths.filter((p) => typeof p === "string" && p);
  if (paths.length === 0) {
    return [];
  }
  return runPythonJson(["-m", "hdr_transcoder.inspector", ...paths]);
});

ipcMain.handle("runtime:check", async () => checkRuntimeEnvironment());

function computeOutputPaths(options) {
  const ext = getOutputExtension(options.format);
  const outputDir = options.outputDir
    ? path.resolve(options.outputDir)
    : path.dirname(path.resolve(options.inputPath || options.inputPaths?.[0] || ""));

  if (options.inputMode === "files" && Array.isArray(options.inputPaths)) {
    const paths = options.inputPaths.map((p, index) => {
      const parsed = path.parse(p);
      const stem = applyNameTemplate(parsed.name, index + 1, options);
      const outPath = path.join(outputDir, `${stem}${ext}`);
      return isSamePath(p, outPath) ? path.join(outputDir, `${parsed.name}_converted${ext}`) : outPath;
    });
    return appendInfoJsonPaths(paths, options);
  }

  if (options.inputMode === "directory") {
    const dirPath = path.resolve(options.inputPath);
    let entries = [];
    try {
      entries = fs.readdirSync(dirPath, { withFileTypes: true })
        .filter((e) => e.isFile() && INPUT_EXTENSIONS.includes(path.extname(e.name).toLowerCase().replace(".", "")))
        .map((e) => e.name)
        .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    } catch {
      return [];
    }
    const paths = entries.map((name, index) => {
      const parsed = path.parse(name);
      const stem = applyNameTemplate(parsed.name, index + 1, options);
      return path.join(outputDir, `${stem}${ext}`);
    });
    return appendInfoJsonPaths(paths, options);
  }

  // Single file mode
  const outputPath = resolveOutputPath(options.inputPath, options.outputDir, options.format, options.inputMode);
  return outputPath ? appendInfoJsonPaths([outputPath], options) : [];
}

ipcMain.handle("conversion:checkOverwrite", async (_event, options) => {
  try {
    validateOptions(options);
  } catch {
    return { existing: [] };
  }

  const paths = computeOutputPaths(options);
  const existing = paths.filter((p) => fs.existsSync(p));
  return { existing };
});

ipcMain.handle("conversion:start", async (_event, options) => {
  validateOptions(options);

  if (currentProcess) {
    throw new Error("A conversion is already running.");
  }

  const { args, outputPath } = buildArgs(options);
  cancelRequested = false;
  cancelForceUsed = false;
  clearCancelForceTimer();
  sendToRenderer("conversion:output", {
    stream: "system",
    text: `python ${args.map((arg) => (arg.includes(" ") ? `"${arg}"` : arg)).join(" ")}\n`,
  });

  currentProcess = spawn(PYTHON_EXE, args, {
    cwd: PROJECT_ROOT,
    env: { ...process.env, PYTHONNOUSERSITE: "1" },
    windowsHide: true,
  });

  currentProcess.stdout.on("data", (chunk) => {
    sendToRenderer("conversion:output", {
      stream: "stdout",
      text: chunk.toString(),
    });
  });

  currentProcess.stderr.on("data", (chunk) => {
    sendToRenderer("conversion:output", {
      stream: "stderr",
      text: chunk.toString(),
    });
  });

  currentProcess.on("error", (error) => {
    const message = error && error.message ? error.message : String(error);
    currentProcess = null;
    cancelRequested = false;
    cancelForceUsed = false;
    clearCancelForceTimer();
    sendToRenderer("conversion:done", {
      ok: false,
      canceled: false,
      exitCode: null,
      outputPath,
      message,
    });
  });

  currentProcess.on("close", (exitCode, signal) => {
    const canceled = (cancelRequested && exitCode !== 0) || cancelForceUsed || signal === "SIGTERM";
    currentProcess = null;
    cancelRequested = false;
    cancelForceUsed = false;
    clearCancelForceTimer();
    sendToRenderer("conversion:done", {
      ok: exitCode === 0 && !canceled,
      canceled,
      exitCode,
      outputPath,
      message: canceled ? "Conversion canceled." : exitCode === 0 ? "Conversion finished." : `Conversion failed with exit code ${exitCode}.`,
    });
  });

  return { started: true, outputPath };
});

ipcMain.handle("conversion:cancel", async () => {
  if (!currentProcess) {
    return { canceled: false };
  }

  if (cancelRequested) {
    return { canceled: true };
  }

  return { canceled: requestProcessCancel(currentProcess) };
});

app.whenReady().then(() => {
  createWindow();
  checkRuntimeEnvironment().then((result) => {
    sendToRenderer("runtime:status", result);
  }).catch((error) => {
    sendToRenderer("runtime:status", runtimeFailure(error));
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (currentProcess) {
    cancelRequested = true;
    forceKillProcess(currentProcess);
    currentProcess = null;
    clearCancelForceTimer();
  }

  if (process.platform !== "darwin") {
    app.quit();
  }
});
