import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

const root = resolve(import.meta.dirname, "..");
const isWindows = process.platform === "win32";

const python = resolve(
  root,
  ".venv",
  isWindows ? "Scripts/python.exe" : "bin/python"
);

const viteEntry = resolve(
  root,
  "node_modules",
  "vite",
  "bin",
  "vite.js"
);

if (!existsSync(python)) {
  console.error("");
  console.error("No existe .venv.");
  console.error("Ejecuta primero:");
  console.error(
    "  powershell -ExecutionPolicy Bypass -File .\\scripts\\setup-windows.ps1"
  );
  console.error("");
  process.exit(1);
}

if (!existsSync(viteEntry)) {
  console.error("");
  console.error("No encuentro Vite en node_modules.");
  console.error("Ejecuta primero:");
  console.error("  npm install");
  console.error("");
  process.exit(1);
}

console.log("");
console.log("Iniciando motor Qwen local...");

const engine = spawn(
  python,
  [resolve(root, "engine/server.py")],
  {
    cwd: root,
    stdio: "inherit",
    env: {
      ...process.env,
      QWEN_STUDIO_ROOT: root,
      QWEN_ENGINE_PORT: "8765"
    }
  }
);

let vite = null;
let shuttingDown = false;

function shutdown(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;

  if (vite && !vite.killed) {
    try {
      vite.kill();
    } catch {}
  }

  if (engine && !engine.killed) {
    try {
      engine.kill();
    } catch {}
  }

  setTimeout(() => process.exit(exitCode), 150);
}

engine.on("error", error => {
  console.error("");
  console.error("No se pudo iniciar el motor Python:");
  console.error(error);
  shutdown(1);
});

engine.on("exit", code => {
  if (!shuttingDown && code && code !== 0) {
    console.error(`El motor Qwen terminó con código ${code}.`);
  }
});

function startVite() {
  console.log("Iniciando interfaz...");

  // Usamos el ejecutable actual de Node para abrir vite.js directamente.
  // Esto evita spawn EINVAL con npx.cmd en algunas versiones de Node/Windows.
  vite = spawn(
    process.execPath,
    [
      viteEntry,
      "--host",
      "127.0.0.1",
      "--port",
      "5173",
      "--strictPort"
    ],
    {
      cwd: root,
      stdio: "inherit",
      env: process.env
    }
  );

  vite.on("error", error => {
    console.error("");
    console.error("No se pudo iniciar Vite:");
    console.error(error);
    shutdown(1);
  });

  vite.on("exit", code => {
    if (!shuttingDown && code && code !== 0) {
      console.error(`Vite terminó con código ${code}.`);
      shutdown(code);
    }
  });
}

// Le damos un instante al servidor Python antes de abrir la interfaz.
setTimeout(startVite, 1200);

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

if (isWindows) {
  process.on("SIGHUP", () => shutdown(0));
}
