const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packageRoot = path.join(root, "python");

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
    if (entry.name === "__pycache__" || entry.name.endsWith(".pyc")) {
      continue;
    }
    if (entry.isDirectory()) {
      copyDirectory(child);
    } else if (entry.isFile()) {
      copyFile(child);
    }
  }
}

fs.rmSync(packageRoot, { recursive: true, force: true });

for (const file of ["hdr2avif.py", "jxr2avif.py", "requirements.txt"]) {
  copyFile(file);
}

copyDirectory("src");
copyDirectory(path.join("tools", "libavif"));
