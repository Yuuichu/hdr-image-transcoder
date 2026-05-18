const state = {
  inputPath: "",
  inputMode: "file",
  outputDir: "",
  running: false,
};

const elements = {
  form: document.getElementById("convertForm"),
  pickFileButton: document.getElementById("pickFileButton"),
  pickDirectoryButton: document.getElementById("pickDirectoryButton"),
  pickOutputButton: document.getElementById("pickOutputButton"),
  clearOutputButton: document.getElementById("clearOutputButton"),
  startButton: document.getElementById("startButton"),
  cancelButton: document.getElementById("cancelButton"),
  clearLogButton: document.getElementById("clearLogButton"),
  inputPath: document.getElementById("inputPath"),
  outputPath: document.getElementById("outputPath"),
  formatSelect: document.getElementById("formatSelect"),
  qualityInput: document.getElementById("qualityInput"),
  speedInput: document.getElementById("speedInput"),
  headroomInput: document.getElementById("headroomInput"),
  losslessInput: document.getElementById("losslessInput"),
  logOutput: document.getElementById("logOutput"),
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

function appendLog(text, stream = "stdout") {
  if (!text) {
    return;
  }

  const prefix = stream === "stderr" ? "[stderr] " : stream === "system" ? "[cmd] " : "";
  elements.logOutput.textContent += `${prefix}${text}`;
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
}

function getNumberValue(input, fallback) {
  const value = Number(input.value);
  return Number.isFinite(value) ? value : fallback;
}

function getOptions() {
  return {
    inputPath: state.inputPath,
    inputMode: state.inputMode,
    outputDir: state.outputDir,
    format: elements.formatSelect.value,
    quality: Math.trunc(getNumberValue(elements.qualityInput, 95)),
    speed: Math.trunc(getNumberValue(elements.speedInput, 6)),
    maxHeadroom: getNumberValue(elements.headroomInput, 0),
    lossless: elements.losslessInput.checked,
  };
}

function validateOptions(options) {
  if (!options.inputPath) {
    return "Select an input file or folder first.";
  }
  if (options.quality < 0 || options.quality > 100) {
    return "Quality must be between 0 and 100.";
  }
  if (options.speed < 0 || options.speed > 10) {
    return "Speed must be between 0 and 10.";
  }
  if (options.maxHeadroom < 0) {
    return "Max headroom must be 0 or higher.";
  }
  return "";
}

function updateFormatState() {
  const isJxl = elements.formatSelect.value === "jxl";
  const isGainmap = elements.formatSelect.value === "gainmap";
  elements.losslessInput.disabled = !isJxl || state.running;
  elements.headroomInput.disabled = !isGainmap || state.running;

  if (!isJxl) {
    elements.losslessInput.checked = false;
  }
}

function updateBusyState(running) {
  state.running = running;
  elements.pickFileButton.disabled = running;
  elements.pickDirectoryButton.disabled = running;
  elements.pickOutputButton.disabled = running;
  elements.clearOutputButton.disabled = running;
  elements.startButton.disabled = running;
  elements.cancelButton.disabled = !running;
  elements.formatSelect.disabled = running;
  elements.qualityInput.disabled = running;
  elements.speedInput.disabled = running;
  updateFormatState();
}

async function chooseInputFile() {
  const filePath = await window.hdrTranscoder.selectInputFile();
  if (!filePath) {
    return;
  }

  state.inputPath = filePath;
  state.inputMode = "file";
  setPathDisplay(elements.inputPath, filePath, "No input selected");
  setSummary("Input file selected.");
}

async function chooseInputDirectory() {
  const directoryPath = await window.hdrTranscoder.selectInputDirectory();
  if (!directoryPath) {
    return;
  }

  state.inputPath = directoryPath;
  state.inputMode = "directory";
  setPathDisplay(elements.inputPath, directoryPath, "No input selected");
  setSummary("Input folder selected. Default output is the same folder.");
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

updateFormatState();
setPathDisplay(elements.inputPath, "", "No input selected");
setPathDisplay(elements.outputPath, "", "Default output location");

if (!window.hdrTranscoder) {
  updateBusyState(true);
  elements.cancelButton.disabled = true;
  elements.clearLogButton.disabled = false;
  setStatus("Unavailable", "error");
  setSummary("Electron preload API is unavailable. Start this UI with npm start.");
  appendLog("Electron preload API is unavailable. Start this UI with npm start.\n", "stderr");
} else {
  elements.pickFileButton.addEventListener("click", chooseInputFile);
  elements.pickDirectoryButton.addEventListener("click", chooseInputDirectory);
  elements.pickOutputButton.addEventListener("click", chooseOutputDirectory);
  elements.clearOutputButton.addEventListener("click", clearOutputDirectory);
  elements.form.addEventListener("submit", startConversion);
  elements.cancelButton.addEventListener("click", cancelConversion);

  window.hdrTranscoder.onConversionOutput((payload) => {
    appendLog(payload.text, payload.stream);
  });

  window.hdrTranscoder.onConversionDone(handleConversionDone);
}
