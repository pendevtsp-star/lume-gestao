const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const PORT = process.env.LUME_PORT || "18780";
const HOST = "127.0.0.1";
const APP_URL = `http://${HOST}:${PORT}`;

let backendProcess;
let mainWindow;

function repoRoot() {
  return path.resolve(__dirname, "..");
}

function backendExecutablePath() {
  const resourcesRoot = process.resourcesPath || repoRoot();
  const executable = process.platform === "win32" ? "lume-backend.exe" : "lume-backend";
  const candidates = [
    path.join(resourcesRoot, "backend", executable),
    path.join(resourcesRoot, "backend", "lume-backend", executable),
  ];

  return candidates.find((candidate) => fs.existsSync(candidate)) || candidates[0];
}

function devPythonPath() {
  const root = repoRoot();
  const candidates =
    process.platform === "win32"
      ? [
          path.join(root, ".venv", "Scripts", "python.exe"),
          "python",
          "py",
        ]
      : [
          path.join(root, ".venv", "bin", "python"),
          "python3",
          "python",
        ];

  return candidates.find((candidate) => {
    if (candidate === "python" || candidate === "python3" || candidate === "py") {
      return true;
    }
    return fs.existsSync(candidate);
  });
}

function backendCommand() {
  const packagedBackend = backendExecutablePath();

  if (app.isPackaged && fs.existsSync(packagedBackend)) {
    return {
      command: packagedBackend,
      args: [],
      cwd: path.dirname(packagedBackend),
    };
  }

  return {
    command: devPythonPath(),
    args: [path.join(repoRoot(), "desktop", "backend_entry.py")],
    cwd: repoRoot(),
  };
}

function startBackend() {
  const dataDir = path.join(app.getPath("userData"), "backend-data");
  fs.mkdirSync(dataDir, { recursive: true });

  const backend = backendCommand();
  backendProcess = spawn(backend.command, backend.args, {
    cwd: backend.cwd,
    env: {
      ...process.env,
      DB_ENGINE: "sqlite",
      LUME_DESKTOP: "True",
      LUME_DATA_DIR: dataDir,
      LUME_HOST: HOST,
      LUME_PORT: PORT,
      LUME_SEED_DEMO: process.env.LUME_SEED_DEMO || "False",
      ALLOWED_HOSTS: `${HOST},localhost,127.0.0.1`,
    },
    stdio: "pipe",
    windowsHide: true,
  });

  backendProcess.stdout.on("data", (chunk) => {
    console.log(`[backend] ${chunk.toString().trim()}`);
  });

  backendProcess.stderr.on("data", (chunk) => {
    console.error(`[backend] ${chunk.toString().trim()}`);
  });

  backendProcess.on("exit", (code) => {
    backendProcess = undefined;
    if (code !== 0 && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox(
        "Lume Gestao",
        "O backend local foi encerrado inesperadamente. Feche e abra o app novamente."
      );
    }
  });
}

async function waitForBackend(timeoutMs = 45000) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(APP_URL, { redirect: "manual" });
      if (response.status < 500) {
        return;
      }
    } catch (_error) {
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  }

  throw new Error("Backend local nao respondeu dentro do tempo esperado.");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    title: "Lume Gestao",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.loadURL(APP_URL);
}

app.whenReady().then(async () => {
  startBackend();

  try {
    await waitForBackend();
    createWindow();
  } catch (error) {
    dialog.showErrorBox("Lume Gestao", error.message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});
