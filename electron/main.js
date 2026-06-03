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
const UHDR_BACKENDS = ["auto", "imagecodecs", "libultrahdr"];
const DEFAULT_NAME_PATTERN = "{name}";
const INVALID_FILENAME_RE = /[<>:"/\\|?*\x00-\x1f]/g;
const WINDOW_MARGIN = 80;
const MIN_CONTENT_WIDTH = 1180;
const MIN_CONTENT_HEIGHT = 780;
const MAX_INFO_JSON_BYTES = 4 * 1024 * 1024;
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
let allowedInfoJsonSidecars = new Map();

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

function convertedName(filePath) {
  const parsed = path.parse(filePath);
  return path.join(parsed.dir, `${parsed.name}_converted${parsed.ext}`);
}

function outputPathFor(inputPath, outputDir, ext, index, options, useNaming = true) {
  const parsed = path.parse(inputPath);
  const stem = useNaming ? applyNameTemplate(parsed.name, index, options) : parsed.name;
  const outputPath = path.join(outputDir, `${stem}${ext}`);
  return isSamePath(inputPath, outputPath) ? convertedName(outputPath) : outputPath;
}

function resolveOutputPath(inputPath, outputDir, format, inputMode) {
  if (!outputDir) {
    return null;
  }

  if (inputMode === "directory") {
    return null;
  }

  return outputPathFor(inputPath, outputDir, getOutputExtension(format), 1, {}, false);
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
  if (!options.infoJson && !options.verifyLayers && !options.dumpValidationLayers) {
    return paths;
  }
  const sidecars = paths.map((outputPath) => {
    const parsed = path.parse(outputPath);
    return path.join(parsed.dir, `${parsed.name}.info.json`);
  });
  return [...paths, ...sidecars];
}

function clearAllowedInfoJsonSidecars() {
  allowedInfoJsonSidecars = new Map();
}

function collectInfoJsonPathFromLine(line, collector) {
  const match = String(line).match(/^\s*Info JSON:\s*(.+?)\s*$/);
  if (match) {
    collector.add(path.resolve(match[1]));
  }
}

function scanInfoJsonLogChunk(text, collector, carry = "") {
  const combined = `${carry}${text}`;
  const lines = combined.split(/\r?\n/);
  const remainder = lines.pop() || "";
  for (const line of lines) {
    collectInfoJsonPathFromLine(line, collector);
  }
  return remainder;
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
  if (["gainmap", "ultrahdr"].includes(options.format) && options.headroom != null && typeof options.headroom === "number") {
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
  if (options.infoJson || options.verifyLayers || options.dumpValidationLayers) {
    args.push("--info-json");
  }
  if (options.verifyFidelity) {
    args.push("--verify-fidelity");
  }
  if (options.verifyLayers) {
    args.push("--verify-layers", "--validation-report");
  }
  if (options.dumpValidationLayers) {
    args.push("--dump-validation-layers");
  }
  if (options.format === "ultrahdr" && options.bt2020PqTiff) {
    args.push("--bt2020-pq-tiff");
  }
  if (options.format === "ultrahdr") {
    args.push("--uhdr-backend", options.uhdrBackend || "auto");
    args.push("--gainmap-scale", String(options.uhdrGainmapScale ?? 2));
    args.push("--target-peak-nits", String(options.uhdrTargetPeakNits ?? 1000));
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
  if (options.format === "gainmap" && !GAINMAP_HEADROOM_MODES.includes(options.gainmapHeadroomMode || "source-peak")) {
    throw new Error("Unknown gainmap headroom mode.");
  }
  if (options.format === "ultrahdr" && !UHDR_BACKENDS.includes(options.uhdrBackend || "auto")) {
    throw new Error("Unknown Ultra HDR backend.");
  }
  if (options.debugOverlay != null && typeof options.debugOverlay !== "boolean") {
    throw new Error("Debug overlay must be true or false.");
  }
  if (options.infoJson != null && typeof options.infoJson !== "boolean") {
    throw new Error("Info JSON must be true or false.");
  }
  if (options.verifyFidelity != null && typeof options.verifyFidelity !== "boolean") {
    throw new Error("Verify fidelity must be true or false.");
  }
  if (options.verifyLayers != null && typeof options.verifyLayers !== "boolean") {
    throw new Error("Layer validation must be true or false.");
  }
  if (options.dumpValidationLayers != null && typeof options.dumpValidationLayers !== "boolean") {
    throw new Error("Dump validation layers must be true or false.");
  }
  if (options.bt2020PqTiff != null && typeof options.bt2020PqTiff !== "boolean") {
    throw new Error("BT.2020 PQ TIFF mode must be true or false.");
  }
  if (!Number.isInteger(options.quality) || options.quality < 0 || options.quality > 100) {
    throw new Error("Quality must be between 0 and 100.");
  }
  if (!Number.isInteger(options.speed) || options.speed < 0 || options.speed > 10) {
    throw new Error("Speed must be between 0 and 10.");
  }
  const uhdrGainmapScale = options.uhdrGainmapScale ?? 2;
  if (options.format === "ultrahdr" && (!Number.isInteger(uhdrGainmapScale) || uhdrGainmapScale < 1 || uhdrGainmapScale > 128)) {
    throw new Error("Ultra HDR gainmap scale must be between 1 and 128.");
  }
  const uhdrTargetPeakNits = options.uhdrTargetPeakNits ?? 1000;
  if (
    options.format === "ultrahdr" &&
    (typeof uhdrTargetPeakNits !== "number" || !Number.isFinite(uhdrTargetPeakNits) ||
      uhdrTargetPeakNits < 203 || uhdrTargetPeakNits > 10000)
  ) {
    throw new Error("Ultra HDR target peak must be between 203 and 10000 nits.");
  }
  if (
    ["gainmap", "ultrahdr"].includes(options.format) &&
    (typeof options.headroom !== "number" || !Number.isFinite(options.headroom) || options.headroom <= 0)
  ) {
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
      .map((e) => ({ name: e.name, path: path.join(directoryPath, e.name) }))
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
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
  let outputDir = options.outputDir ? path.resolve(options.outputDir) : null;

  if (options.inputMode === "files" && Array.isArray(options.inputPaths)) {
    outputDir = outputDir || path.dirname(path.resolve(options.inputPaths[0] || ""));
    const paths = options.inputPaths.map((p, index) => {
      return outputPathFor(p, outputDir, ext, index + 1, options);
    });
    return appendInfoJsonPaths(paths, options);
  }

  if (options.inputMode === "directory") {
    const dirPath = path.resolve(options.inputPath);
    outputDir = outputDir || dirPath;
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
      return outputPathFor(path.join(dirPath, name), outputDir, ext, index + 1, options);
    });
    return appendInfoJsonPaths(paths, options);
  }

  // Single file mode
  const outputPath = resolveOutputPath(options.inputPath, outputDir, options.format, options.inputMode);
  if (outputPath) {
    return appendInfoJsonPaths([outputPath], options);
  }

  const parsed = path.parse(options.inputPath);
  return appendInfoJsonPaths([outputPathFor(options.inputPath, parsed.dir, ext, 1, options)], options);
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

function infoJsonPathForOutput(outputPath) {
  if (path.extname(outputPath).toLowerCase() === ".json") {
    return path.resolve(outputPath);
  }
  const parsed = path.parse(outputPath);
  return path.resolve(parsed.dir, `${parsed.name}.info.json`);
}

function rememberAllowedInfoJsonSidecars(outputPaths, options, conversionStartedAtMs, writtenInfoJsonPaths) {
  clearAllowedInfoJsonSidecars();
  if (
    (!options.infoJson && !options.verifyLayers && !options.dumpValidationLayers) ||
    !Array.isArray(outputPaths) ||
    !(writtenInfoJsonPaths instanceof Set)
  ) {
    return;
  }

  const minMtimeMs = Math.max(0, conversionStartedAtMs - 5000);
  const expectedSidecars = new Set(outputPaths
    .filter((p) => typeof p === "string" && p)
    .map(infoJsonPathForOutput));
  const sidecars = [...writtenInfoJsonPaths].filter((sidecar) => expectedSidecars.has(sidecar));

  for (const sidecar of sidecars) {
    try {
      const stat = fs.lstatSync(sidecar);
      if (!stat.isFile() || stat.size > MAX_INFO_JSON_BYTES || stat.mtimeMs < minMtimeMs) {
        continue;
      }
      allowedInfoJsonSidecars.set(sidecar, { minMtimeMs });
    } catch {
      // Only sidecars actually written by the completed conversion become readable.
    }
  }
}

ipcMain.handle("conversion:readInfoJson", async (_event, outputPaths) => {
  if (!Array.isArray(outputPaths)) {
    return [];
  }
  const sidecars = [...new Set(outputPaths
    .filter((p) => typeof p === "string" && p)
    .map(infoJsonPathForOutput))]
    .filter((sidecar) => allowedInfoJsonSidecars.has(sidecar));
  const reports = [];
  for (const sidecar of sidecars) {
    const allowed = allowedInfoJsonSidecars.get(sidecar);
    try {
      const stat = fs.lstatSync(sidecar);
      if (!stat.isFile()) {
        continue;
      }
      if (stat.size > MAX_INFO_JSON_BYTES) {
        throw new Error(`Info JSON exceeds ${MAX_INFO_JSON_BYTES} bytes`);
      }
      if (allowed && stat.mtimeMs < allowed.minMtimeMs) {
        continue;
      }
      reports.push(JSON.parse(fs.readFileSync(sidecar, "utf8")));
    } catch (error) {
      reports.push({
        path: sidecar,
        format: "info-json",
        verify: { requested: false, ok: false },
        error: error && error.message ? error.message : String(error),
      });
    }
  }
  return reports;
});

ipcMain.handle("conversion:start", async (_event, options) => {
  validateOptions(options);

  if (currentProcess) {
    throw new Error("A conversion is already running.");
  }

  clearAllowedInfoJsonSidecars();
  const conversionStartedAtMs = Date.now();
  const writtenInfoJsonPaths = new Set();
  let infoJsonLogCarry = "";
  const { args, outputPath } = buildArgs(options);
  const outputPaths = computeOutputPaths(options);
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
    const text = chunk.toString();
    infoJsonLogCarry = scanInfoJsonLogChunk(text, writtenInfoJsonPaths, infoJsonLogCarry);
    sendToRenderer("conversion:output", {
      stream: "stdout",
      text,
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
    clearAllowedInfoJsonSidecars();
    clearCancelForceTimer();
    sendToRenderer("conversion:done", {
      ok: false,
      canceled: false,
      exitCode: null,
      outputPath,
      outputPaths,
      message,
    });
  });

  currentProcess.on("close", (exitCode, signal) => {
    const canceled = (cancelRequested && exitCode !== 0) || cancelForceUsed || signal === "SIGTERM";
    if (infoJsonLogCarry) {
      collectInfoJsonPathFromLine(infoJsonLogCarry, writtenInfoJsonPaths);
      infoJsonLogCarry = "";
    }
    currentProcess = null;
    cancelRequested = false;
    cancelForceUsed = false;
    if (!canceled && (options.infoJson || options.verifyLayers || options.dumpValidationLayers)) {
      rememberAllowedInfoJsonSidecars(outputPaths, options, conversionStartedAtMs, writtenInfoJsonPaths);
    } else {
      clearAllowedInfoJsonSidecars();
    }
    clearCancelForceTimer();
    sendToRenderer("conversion:done", {
      ok: exitCode === 0 && !canceled,
      canceled,
      exitCode,
      outputPath,
      outputPaths,
      message: canceled ? "Conversion canceled." : exitCode === 0 ? "Conversion finished." : `Conversion failed with exit code ${exitCode}.`,
    });
  });

  return { started: true, outputPath, outputPaths };
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
