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
  console.error("  npm ci");
  console.error("");
  process.exit(1);
}

console.log("");
console.log("Iniciando motor Qwen local...");

let engine = null;
let vite = null;
let shuttingDown = false;
let engineExited = false;

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

function probePython() {
  return new Promise(resolve => {
    const probe = spawn(
      python,
      ["-c", "import sys; print(sys.version)"],
      { cwd: root, stdio: ["ignore", "pipe", "pipe"] }
    );
    let stderr = "";
    probe.stderr.on("data", chunk => {
      stderr += chunk.toString();
    });
    probe.on("error", error => resolve({ ok: false, detail: error.message }));
    probe.on("exit", code =>
      resolve({
        ok: code === 0,
        detail: stderr.trim() || `código de salida ${code}`
      })
    );
  });
}

async function waitForEngine(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (engineExited) {
      throw new Error("El motor Python terminó antes de publicar su API.");
    }
    try {
      const response = await fetch("http://127.0.0.1:8765/api/health", {
        signal: AbortSignal.timeout(1200)
      });
      if (response.ok) return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(
    "El motor Python no respondió en 30 segundos. Revisa el diagnóstico del entorno."
  );
}

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

async function boot() {
  const probe = await probePython();
  if (!probe.ok) {
    throw new Error(
      `El entorno Python no puede iniciarse (${python}). ${probe.detail}\n` +
        "Recréalo con scripts/setup-windows.ps1 o instala Python 3.12."
    );
  }

  engine = spawn(
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

  engine.on("error", error => {
    engineExited = true;
    console.error("\nNo se pudo iniciar el motor Python:");
    console.error(error);
  });

  engine.on("exit", code => {
    engineExited = true;
    if (!shuttingDown && code && code !== 0) {
      console.error(`El motor Qwen terminó con código ${code}.`);
    }
  });

  await waitForEngine();
  startVite();
}

boot().catch(error => {
  console.error("\nNo se pudo preparar la prueba local:");
  console.error(error.message || error);
  shutdown(1);
});

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

if (isWindows) {
  process.on("SIGHUP", () => shutdown(0));
}
