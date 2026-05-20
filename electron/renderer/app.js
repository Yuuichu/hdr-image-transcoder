const state = {
  inputPath: "",
  inputPaths: [],
  inputMode: "files",
  outputDir: "",
  inspectRequestId: 0,
  running: false,
  runtimeOk: true,
};

const elements = {
  form: document.getElementById("convertForm"),
  pickFilesButton: document.getElementById("pickFilesButton"),
  pickDirectoryButton: document.getElementById("pickDirectoryButton"),
  pickOutputButton: document.getElementById("pickOutputButton"),
  clearOutputButton: document.getElementById("clearOutputButton"),
  startButton: document.getElementById("startButton"),
  cancelButton: document.getElementById("cancelButton"),
  clearLogButton: document.getElementById("clearLogButton"),
  inputPath: document.getElementById("inputPath"),
  outputPath: document.getElementById("outputPath"),
  formatSelect: document.getElementById("formatSelect"),
  fidelityBadge: document.getElementById("fidelityBadge"),
  jxlModeSelect: document.getElementById("jxlModeSelect"),
  qualityInput: document.getElementById("qualityInput"),
  speedInput: document.getElementById("speedInput"),
  gainmapHeadroomModeSelect: document.getElementById("gainmapHeadroomModeSelect"),
  headroomSdrInput: document.getElementById("headroomSdrInput"),
  losslessInput: document.getElementById("losslessInput"),
  debugOverlayInput: document.getElementById("debugOverlayInput"),
  infoJsonInput: document.getElementById("infoJsonInput"),
  namePrefixInput: document.getElementById("namePrefixInput"),
  nameSuffixInput: document.getElementById("nameSuffixInput"),
  nameFindInput: document.getElementById("nameFindInput"),
  nameReplaceInput: document.getElementById("nameReplaceInput"),
  namePatternInput: document.getElementById("namePatternInput"),
  nameStartInput: document.getElementById("nameStartInput"),
  namePaddingInput: document.getElementById("namePaddingInput"),
  logOutput: document.getElementById("logOutput"),
  imageInfoContent: document.getElementById("imageInfoContent"),
  runtimeStatus: document.getElementById("runtimeStatus"),
  statusBadge: document.getElementById("statusBadge"),
  summary: document.getElementById("summary"),
};

function setStatus(label, className) {
  elements.statusBadge.textContent = label;
  elements.statusBadge.className = `status-badge ${className}`;
}

function setSummary(text) {
  elements.summary.textContent = text;
}

function setPathDisplay(node, value, emptyText) {
  node.textContent = value || emptyText;
  node.classList.toggle("empty", !value);
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function setImageInfoMessage(text, className = "empty") {
  clearNode(elements.imageInfoContent);
  elements.imageInfoContent.textContent = text;
  elements.imageInfoContent.className = `image-info-content ${className}`.trim();
}

function appendLog(text, stream = "stdout") {
  if (!text) {
    return;
  }

  const prefix = stream === "stderr" ? "[stderr] " : stream === "system" ? "[cmd] " : "";
  elements.logOutput.textContent += `${prefix}${text}`;
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;

  const progressMatch = text.match(/\[(\d+)\/(\d+)\]/);
  if (progressMatch) {
    elements.statusBadge.textContent = `Running ${progressMatch[1]}/${progressMatch[2]}`;
  }
}

function formatRuntimeIssue(result) {
  const missing = (result.missingTools || []).map((tool) => tool.name || tool.path);
  const deps = (result.dependencyErrors || []).map((item) => item.package || item.module || item.error);
  const issues = [...missing, ...deps];
  return issues.length > 0 ? issues.join(", ") : "Runtime check failed.";
}

function renderRuntimeStatus(result) {
  state.runtimeOk = !!(result && result.ok);
  if (state.runtimeOk) {
    const version = result.pythonVersion && result.pythonVersion.version ? result.pythonVersion.version : "unknown";
    elements.runtimeStatus.textContent = `Runtime ready. Python ${version}; bundled tools found.`;
    elements.runtimeStatus.className = "runtime-status ok";
    if (!state.running) {
      setStatus("Idle", "idle");
    }
  } else {
    const issue = formatRuntimeIssue(result || {});
    elements.runtimeStatus.textContent = `Runtime error: ${issue}`;
    elements.runtimeStatus.className = "runtime-status error";
    setStatus("Runtime Error", "error");
    setSummary(`Runtime self-check failed: ${issue}`);
    appendLog(`Runtime self-check failed: ${issue}\n`, "stderr");
  }
  updateBusyState(state.running);
}

function formatBytes(bytes) {
  if (typeof bytes !== "number") {
    return "Unknown";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatFloat(value, digits = 3) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "Unknown";
}

function addInfoRow(container, label, value, className = "") {
  const row = document.createElement("div");
  row.className = `info-row ${className}`.trim();

  const labelNode = document.createElement("span");
  labelNode.className = "info-label";
  labelNode.textContent = label;

  const valueNode = document.createElement("span");
  valueNode.className = "info-value";
  valueNode.textContent = value == null || value === "" ? "Unknown" : String(value);

  row.appendChild(labelNode);
  row.appendChild(valueNode);
  container.appendChild(row);
}

function createImageInfoCard(info, open) {
  const details = document.createElement("details");
  details.className = "image-info-card";
  details.open = open;

  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.textContent = info.filename || "Unknown file";
  const badge = document.createElement("span");
  badge.className = info.error ? "mini-badge error" : (info.hdr && info.hdr.is_hdr ? "mini-badge hdr" : "mini-badge");
  badge.textContent = info.error ? "Error" : (info.hdr && info.hdr.is_hdr ? "HDR" : "SDR");
  summary.appendChild(title);
  summary.appendChild(badge);
  details.appendChild(summary);

  const body = document.createElement("div");
  body.className = "image-info-body";
  addInfoRow(body, "Format", `${info.format_name || "Unknown"} (${info.detected_format || "unknown"})`);
  addInfoRow(body, "Dimensions", info.width && info.height ? `${info.width} x ${info.height}` : "Unknown");
  addInfoRow(body, "File Size", formatBytes(info.file_size_bytes));

  const color = info.color || {};
  addInfoRow(
    body,
    "Color",
    `${color.primaries_label || "Unknown"} / ${color.transfer_label || "Unknown"} / ${color.matrix_label || "Unknown"}`,
  );
  if (color.primaries || color.transfer || color.matrix) {
    addInfoRow(body, "CICP/nclx", `${color.primaries || "?"}/${color.transfer || "?"}/${color.matrix || "?"}`);
  }

  const hdr = info.hdr || {};
  addInfoRow(body, "RGB Peak", `${formatFloat(hdr.rgb_max)} scRGB`);
  addInfoRow(body, "Headroom", `${formatFloat(hdr.peak_headroom)} stops`);

  const gainmap = info.gainmap || {};
  addInfoRow(body, "Gain Map", gainmap.present ? "Present" : "Not detected");
  if (gainmap.present) {
    addInfoRow(body, "Base Headroom", `${formatFloat(gainmap.base_headroom)} stops`);
    addInfoRow(body, "Alternate Headroom", `${formatFloat(gainmap.alternate_headroom)} stops`);
    const alternateColor = gainmap.alternate_color || {};
    if (alternateColor.primaries || alternateColor.transfer || alternateColor.matrix) {
      addInfoRow(
        body,
        "Alt Color",
        `${alternateColor.primaries_label || "Unknown"} / ${alternateColor.transfer_label || "Unknown"} / ${alternateColor.matrix_label || "Unknown"}`,
      );
      addInfoRow(
        body,
        "Alt CICP",
        `${alternateColor.primaries || "?"}/${alternateColor.transfer || "?"}/${alternateColor.matrix || "?"}`,
      );
    }
  }

  if (info.error) {
    addInfoRow(body, "Error", info.error, "error");
  }
  for (const warning of info.warnings || []) {
    addInfoRow(body, "Warning", warning, "warning");
  }

  details.appendChild(body);
  return details;
}

function renderImageInfos(payload) {
  const infos = Array.isArray(payload) ? payload : [payload];
  clearNode(elements.imageInfoContent);
  elements.imageInfoContent.className = "image-info-content";
  if (infos.length === 0) {
    setImageInfoMessage("No image information available.");
    return;
  }
  infos.forEach((info) => {
    elements.imageInfoContent.appendChild(createImageInfoCard(info, infos.length === 1));
  });
}

async function loadImageInfo(filePaths) {
  const requestId = ++state.inspectRequestId;
  setImageInfoMessage("Inspecting selected image metadata...", "loading");
  try {
    const result = await window.hdrTranscoder.inspectImages(filePaths);
    if (requestId !== state.inspectRequestId) {
      return;
    }
    renderImageInfos(result);
  } catch (error) {
    if (requestId !== state.inspectRequestId) {
      return;
    }
    setImageInfoMessage(error && error.message ? error.message : String(error), "error");
  }
}

function getNumberValue(input, fallback) {
  const value = Number(input.value);
  return Number.isFinite(value) ? value : fallback;
}

function getFidelityMode() {
  if (
    elements.formatSelect.value === "jxl" &&
    elements.jxlModeSelect.value === "linear-srgb" &&
    elements.losslessInput.checked
  ) {
    return "master";
  }
  if (["jxl", "avif", "heif"].includes(elements.formatSelect.value)) {
    return "display";
  }
  return "compat";
}

function getOptions() {
  return {
    inputPath: state.inputPath,
    inputPaths: state.inputPaths,
    inputMode: state.inputMode,
    outputDir: state.outputDir,
    format: elements.formatSelect.value,
    fidelity: getFidelityMode(),
    jxlMode: elements.jxlModeSelect.value,
    quality: Math.trunc(getNumberValue(elements.qualityInput, 100)),
    speed: Math.trunc(getNumberValue(elements.speedInput, 0)),
    gainmapHeadroomMode: elements.gainmapHeadroomModeSelect.value,
    headroom: getNumberValue(elements.headroomSdrInput, 2.0),
    lossless: elements.losslessInput.checked,
    debugOverlay: elements.debugOverlayInput.checked,
    infoJson: elements.infoJsonInput.checked,
    namePrefix: elements.namePrefixInput.value,
    nameSuffix: elements.nameSuffixInput.value,
    nameFind: elements.nameFindInput.value,
    nameReplace: elements.nameReplaceInput.value,
    namePattern: elements.namePatternInput.value || "{name}",
    nameStart: Math.trunc(getNumberValue(elements.nameStartInput, 1)),
    namePadding: Math.trunc(getNumberValue(elements.namePaddingInput, 3)),
  };
}

function validateOptions(options) {
  if (options.inputMode === "files") {
    if (!Array.isArray(options.inputPaths) || options.inputPaths.length === 0) {
      return "Select at least one image file first.";
    }
  } else if (!options.inputPath) {
    return "Select an input file or folder first.";
  }
  if (options.quality < 0 || options.quality > 100) {
    return "Quality must be between 0 and 100.";
  }
  if (options.speed < 0 || options.speed > 10) {
    return "Speed must be between 0 and 10.";
  }
  if (options.headroom <= 0) {
    return "Base headroom must be greater than 0.";
  }
  if (!["rec2020-pq", "linear-srgb"].includes(options.jxlMode)) {
    return "Unknown JPEG XL mode.";
  }
  if (!["master", "display", "compat"].includes(options.fidelity)) {
    return "Unknown fidelity mode.";
  }
  if (!["source-peak", "auto"].includes(options.gainmapHeadroomMode)) {
    return "Unknown gainmap headroom mode.";
  }
  if (typeof options.debugOverlay !== "boolean") {
    return "Unknown debug overlay mode.";
  }
  if (typeof options.infoJson !== "boolean") {
    return "Unknown info JSON mode.";
  }
  if (options.nameStart < 0) {
    return "Name start must be 0 or higher.";
  }
  if (options.namePadding < 0) {
    return "Name padding must be 0 or higher.";
  }
  return "";
}

function updateFormatState() {
  const isJxl = elements.formatSelect.value === "jxl";
  const isGainmap = elements.formatSelect.value === "gainmap";
  elements.losslessInput.disabled = !isJxl || state.running;
  elements.jxlModeSelect.disabled = !isJxl || state.running;
  const isUltraHdr = elements.formatSelect.value === "ultrahdr";
  elements.gainmapHeadroomModeSelect.disabled = !isGainmap || state.running;
  elements.headroomSdrInput.disabled = !(isGainmap || isUltraHdr) || state.running;

  if (!isJxl) {
    elements.losslessInput.checked = false;
  }

  const fidelity = getFidelityMode();
  elements.fidelityBadge.textContent =
    fidelity === "master" ? "Master" : fidelity === "display" ? "Display HDR" : "Compat";
  elements.fidelityBadge.className = `fidelity-badge ${fidelity}`;
}

function updateBusyState(running) {
  state.running = running;
  elements.pickFilesButton.disabled = running;
  elements.pickDirectoryButton.disabled = running;
  elements.pickOutputButton.disabled = running;
  elements.clearOutputButton.disabled = running;
  elements.startButton.disabled = running || !state.runtimeOk;
  elements.cancelButton.disabled = !running;
  elements.formatSelect.disabled = running;
  elements.qualityInput.disabled = running;
  elements.speedInput.disabled = running;
  elements.jxlModeSelect.disabled = running;
  elements.gainmapHeadroomModeSelect.disabled = running;
  elements.headroomSdrInput.disabled = running;
  elements.debugOverlayInput.disabled = running;
  elements.infoJsonInput.disabled = running;
  elements.namePrefixInput.disabled = running;
  elements.nameSuffixInput.disabled = running;
  elements.nameFindInput.disabled = running;
  elements.nameReplaceInput.disabled = running;
  elements.namePatternInput.disabled = running;
  elements.nameStartInput.disabled = running;
  elements.namePaddingInput.disabled = running;
  updateFormatState();
}

async function chooseInputFiles() {
  const filePaths = await window.hdrTranscoder.selectInputFiles();
  if (!filePaths || filePaths.length === 0) {
    return;
  }

  state.inputPaths = filePaths;
  state.inputPath = "";
  state.inputMode = "files";
  const label = filePaths.length === 1 ? filePaths[0] : `${filePaths.length} images selected`;
  setPathDisplay(elements.inputPath, label, "No images selected");
  setSummary(filePaths.length === 1 ? "1 image selected." : `${filePaths.length} images selected.`);
  loadImageInfo(filePaths);
}

async function chooseInputDirectory() {
  const directoryPath = await window.hdrTranscoder.selectInputDirectory();
  if (!directoryPath) {
    return;
  }

  state.inputPath = directoryPath;
  state.inputPaths = [];
  state.inputMode = "directory";
  setPathDisplay(elements.inputPath, directoryPath, "No images selected");
  ++state.inspectRequestId;
  setImageInfoMessage("Directory mode selected. Image metadata is shown for selected files only.");

  const scan = await window.hdrTranscoder.scanDirectory(directoryPath);
  if (scan.error) {
    setSummary(scan.error);
  } else if (scan.count === 0) {
    setSummary("No supported image files found in this folder.");
    setStatus("No Files", "error");
  } else {
    setSummary(`Folder selected. Found ${scan.count} supported image(s).`);
  }
}

async function chooseOutputDirectory() {
  const directoryPath = await window.hdrTranscoder.selectOutputDirectory();
  if (!directoryPath) {
    return;
  }

  state.outputDir = directoryPath;
  setPathDisplay(elements.outputPath, directoryPath, "Default output location");
  setSummary("Output folder selected.");
}

function clearOutputDirectory() {
  state.outputDir = "";
  setPathDisplay(elements.outputPath, "", "Default output location");
  setSummary("Default output location will be used.");
}

async function startConversion(event) {
  event.preventDefault();

  const options = getOptions();
  const validationError = validateOptions(options);
  if (validationError) {
    setStatus("Needs Input", "error");
    setSummary(validationError);
    return;
  }

  const overwrite = await window.hdrTranscoder.checkOverwrite(options);
  if (overwrite.existing && overwrite.existing.length > 0) {
    const names = overwrite.existing.map((p) => p.split(/[/\\]/).pop()).slice(0, 5).join(", ");
    const extra = overwrite.existing.length > 5 ? ` and ${overwrite.existing.length - 5} more` : "";
    const confirmed = confirm(
      `${overwrite.existing.length} output file(s) already exist:\n\n${names}${extra}\n\nOverwrite?`
    );
    if (!confirmed) {
      setSummary("Conversion canceled.");
      return;
    }
  }

  updateBusyState(true);
  setStatus("Running", "running");
  setSummary("Conversion running.");
  appendLog("\n--- Conversion started ---\n", "system");

  try {
    await window.hdrTranscoder.startConversion(options);
  } catch (error) {
    updateBusyState(false);
    setStatus("Error", "error");
    setSummary(error && error.message ? error.message : String(error));
  }
}

async function cancelConversion() {
  if (!state.running) {
    return;
  }

  setSummary("Cancel requested.");
  await window.hdrTranscoder.cancelConversion();
}

function handleConversionDone(result) {
  updateBusyState(false);

  if (result.ok) {
    setStatus("Done", "success");
    setSummary(result.outputPath ? `Finished. Output: ${result.outputPath}` : "Finished.");
  } else if (result.canceled) {
    setStatus("Canceled", "idle");
    setSummary("Conversion canceled.");
  } else {
    setStatus("Error", "error");
    setSummary(result.message || "Conversion failed.");
  }

  appendLog(`\n--- ${result.message || "Conversion ended."} ---\n`, "system");
}

elements.clearLogButton.addEventListener("click", () => {
  elements.logOutput.textContent = "";
});
elements.formatSelect.addEventListener("change", updateFormatState);
elements.jxlModeSelect.addEventListener("change", updateFormatState);
elements.losslessInput.addEventListener("change", updateFormatState);

updateFormatState();
setPathDisplay(elements.inputPath, "", "No images selected");
setPathDisplay(elements.outputPath, "", "Default output location");

if (!window.hdrTranscoder) {
  updateBusyState(true);
  elements.cancelButton.disabled = true;
  elements.clearLogButton.disabled = false;
  setStatus("Unavailable", "error");
  setSummary("Electron preload API is unavailable. Start this UI with npm start.");
  appendLog("Electron preload API is unavailable. Start this UI with npm start.\n", "stderr");
} else {
  elements.pickFilesButton.addEventListener("click", chooseInputFiles);
  elements.pickDirectoryButton.addEventListener("click", chooseInputDirectory);
  elements.pickOutputButton.addEventListener("click", chooseOutputDirectory);
  elements.clearOutputButton.addEventListener("click", clearOutputDirectory);
  elements.form.addEventListener("submit", startConversion);
  elements.cancelButton.addEventListener("click", cancelConversion);

  window.hdrTranscoder.onConversionOutput((payload) => {
    appendLog(payload.text, payload.stream);
  });

  window.hdrTranscoder.onConversionDone(handleConversionDone);
  if (window.hdrTranscoder.onRuntimeStatus) {
    window.hdrTranscoder.onRuntimeStatus(renderRuntimeStatus);
  }
  if (window.hdrTranscoder.checkRuntime) {
    window.hdrTranscoder.checkRuntime().then(renderRuntimeStatus).catch((error) => {
      renderRuntimeStatus({
        ok: false,
        missingTools: [],
        dependencyErrors: [{ package: "runtime", error: error && error.message ? error.message : String(error) }],
      });
    });
  }
}
