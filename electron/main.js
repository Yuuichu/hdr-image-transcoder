const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const PROJECT_ROOT = app.isPackaged
    ? path.join(process.resourcesPath, "python")
    : path.resolve(__dirname, "..");

const PYTHON_EXE = process.platform === "win32" ? "python" : "python3";
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

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1120,
    height: 780,
    minWidth: 920,
    minHeight: 640,
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
}

function sendToRenderer(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
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
  }

  args.push("--quality", String(options.quality));
  args.push("--speed", String(options.speed));
  if (options.headroom != null && typeof options.headroom === "number") {
    args.push("--headroom", String(options.headroom));
  }
  args.push("--max-headroom", String(options.maxHeadroom));

  if (options.lossless && options.format === "jxl") {
    args.push("--lossless");
  }

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
  if (!Number.isInteger(options.quality) || options.quality < 0 || options.quality > 100) {
    throw new Error("Quality must be between 0 and 100.");
  }
  if (!Number.isInteger(options.speed) || options.speed < 0 || options.speed > 10) {
    throw new Error("Speed must be between 0 and 10.");
  }
  if (typeof options.maxHeadroom !== "number" || options.maxHeadroom < 0) {
    throw new Error("Max headroom must be a non-negative number.");
  }
  if (typeof options.headroom !== "number" || options.headroom <= 0) {
    throw new Error("Base headroom must be greater than 0.");
  }
}

ipcMain.handle("dialog:selectInputFile", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select HDR image",
    properties: ["openFile"],
    filters: [
      { name: "HDR images", extensions: INPUT_EXTENSIONS },
      { name: "All files", extensions: ["*"] },
    ],
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  return result.filePaths[0];
});

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

function computeOutputPaths(options) {
  const ext = getOutputExtension(options.format);
  const outputDir = options.outputDir
    ? path.resolve(options.outputDir)
    : path.dirname(path.resolve(options.inputPath || options.inputPaths?.[0] || ""));

  if (options.inputMode === "files" && Array.isArray(options.inputPaths)) {
    return options.inputPaths.map((p) => {
      const parsed = path.parse(p);
      const outPath = path.join(outputDir, `${parsed.name}${ext}`);
      return isSamePath(p, outPath) ? path.join(outputDir, `${parsed.name}_converted${ext}`) : outPath;
    });
  }

  if (options.inputMode === "directory") {
    const dirPath = path.resolve(options.inputPath);
    let entries = [];
    try {
      entries = fs.readdirSync(dirPath, { withFileTypes: true })
        .filter((e) => e.isFile() && INPUT_EXTENSIONS.includes(path.extname(e.name).toLowerCase().replace(".", "")))
        .map((e) => e.name);
    } catch {
      return [];
    }
    return entries.map((name) => {
      const parsed = path.parse(name);
      return path.join(outputDir, `${parsed.name}${ext}`);
    });
  }

  // Single file mode
  const outputPath = resolveOutputPath(options.inputPath, options.outputDir, options.format, options.inputMode);
  return outputPath ? [outputPath] : [];
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
  sendToRenderer("conversion:output", {
    stream: "system",
    text: `python ${args.map((arg) => (arg.includes(" ") ? `"${arg}"` : arg)).join(" ")}\n`,
  });

  currentProcess = spawn(PYTHON_EXE, args, {
    cwd: PROJECT_ROOT,
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
    sendToRenderer("conversion:done", {
      ok: false,
      canceled: false,
      exitCode: null,
      outputPath,
      message,
    });
  });

  currentProcess.on("close", (exitCode, signal) => {
    const canceled = cancelRequested || signal === "SIGTERM";
    currentProcess = null;
    cancelRequested = false;
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

  cancelRequested = true;
  currentProcess.kill();
  const pid = currentProcess.pid;
  setTimeout(() => {
    if (currentProcess && currentProcess.pid === pid) {
      currentProcess.kill('SIGKILL');
    }
  }, 3000);
  return { canceled: true };
});

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (currentProcess) {
    cancelRequested = true;
    currentProcess.kill();
    currentProcess = null;
  }

  if (process.platform !== "darwin") {
    app.quit();
  }
});
