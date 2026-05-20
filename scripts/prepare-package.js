const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packageRoot = path.join(root, "python");
const isWin = process.platform === "win32";
const pythonCommand = process.env.PYTHON || (isWin ? "python" : "python3");

function run(command, args, options = {}) {
  execFileSync(command, args, {
    cwd: root,
    stdio: "inherit",
    env: { ...process.env, PYTHONNOUSERSITE: "1" },
    windowsHide: true,
    ...options,
  });
}

function pythonJson(code) {
  const stdout = execFileSync(pythonCommand, ["-c", code], {
    cwd: root,
    encoding: "utf-8",
    windowsHide: true,
  });
  return JSON.parse(stdout);
}

function shouldSkip(entryPath) {
  const name = path.basename(entryPath);
  if (name === "__pycache__" || name === ".pytest_cache") {
    return true;
  }
  return name.endsWith(".pyc") || name.endsWith(".pyo");
}

function copyFile(relativePath) {
  const source = path.join(root, relativePath);
  const target = path.join(packageRoot, relativePath);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
}

function copyDirectory(relativePath) {
  const source = path.join(root, relativePath);
  const target = path.join(packageRoot, relativePath);
  fs.mkdirSync(target, { recursive: true });

  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const child = path.join(relativePath, entry.name);
    if (shouldSkip(child)) {
      continue;
    }
    if (entry.isDirectory()) {
      copyDirectory(child);
    } else if (entry.isFile()) {
      copyFile(child);
    }
  }
}

function copyPythonRuntime() {
  const info = pythonJson(`
import json
import sys
print(json.dumps({
    "executable": sys.executable,
    "prefix": sys.base_prefix or sys.prefix,
    "version": sys.version,
}))
`);
  const sourcePrefix = info.prefix;
  if (!sourcePrefix || !fs.existsSync(sourcePrefix)) {
    throw new Error(`Cannot locate Python runtime prefix from ${pythonCommand}`);
  }

  fs.cpSync(sourcePrefix, packageRoot, {
    recursive: true,
    dereference: true,
    filter: (source) => !shouldSkip(source),
  });

  const packagedPython = isWin
    ? path.join(packageRoot, "python.exe")
    : path.join(packageRoot, "bin", "python3");
  if (!fs.existsSync(packagedPython)) {
    throw new Error(`Packaged Python executable was not created: ${packagedPython}`);
  }

  fs.rmSync(path.join(packageRoot, "Lib", "site-packages"), { recursive: true, force: true });
  fs.rmSync(path.join(packageRoot, "Scripts"), { recursive: true, force: true });

  run(packagedPython, ["-m", "ensurepip", "--upgrade"]);
  run(packagedPython, [
    "-m",
    "pip",
    "install",
    "--upgrade",
    "--no-warn-script-location",
    "-r",
    path.join(root, "requirements.txt"),
  ]);
}

fs.rmSync(packageRoot, { recursive: true, force: true });
fs.mkdirSync(packageRoot, { recursive: true });

for (const file of [
  path.join("tools", "libavif", "avifgainmaputil.exe"),
  path.join("tools", "libavif", "avifgainmaputil_hdr.exe"),
  path.join("tools", "libavif", "avifdec.exe"),
  path.join("tools", "libjxl", "cjxl.exe"),
  path.join("tools", "libjxl", "jxlinfo.exe"),
]) {
  if (!fs.existsSync(path.join(root, file))) {
    throw new Error(`Missing required packaged tool: ${file}`);
  }
}

copyPythonRuntime();

for (const file of ["hdr2avif.py", "jxr2avif.py", "requirements.txt"]) {
  copyFile(file);
}

copyDirectory("hdr_transcoder");
copyDirectory("src");
copyDirectory(path.join("tools", "libavif"));
copyDirectory(path.join("tools", "libjxl"));

run(isWin ? path.join(packageRoot, "python.exe") : path.join(packageRoot, "bin", "python3"), [
  "-m",
  "hdr_transcoder.tools_check",
]);
