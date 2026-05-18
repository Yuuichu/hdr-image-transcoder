const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const path = require("node:path");
const { spawn } = require("node:child_process");

const PROJECT_ROOT = path.resolve(__dirname, "..");
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
      sandbox: false,
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
  const args = ["hdr2avif.py", options.inputPath];
  const outputPath = resolveOutputPath(
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

  if (options.format && options.format !== "gainmap") {
    args.push("--format", options.format);
  }

  args.push("--quality", String(options.quality));
  args.push("--speed", String(options.speed));
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
  if (!options.inputPath || typeof options.inputPath !== "string") {
    throw new Error("Select an input file or directory first.");
  }
  if (!["file", "directory"].includes(options.inputMode)) {
    throw new Error("Input mode must be file or directory.");
  }
  if (!["gainmap", "jxl", "ultrahdr", "avif"].includes(options.format)) {
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

  currentProcess = spawn("python", args, {
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
