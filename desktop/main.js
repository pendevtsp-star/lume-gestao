const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { autoUpdater } = require("electron-updater");

const PORT = process.env.LUME_PORT || "18780";
const HOST = "127.0.0.1";
const APP_URL = `http://${HOST}:${PORT}`;
const HEALTH_URL = `${APP_URL}/health/`;

let backendProcess;
let mainWindow;

function repoRoot() {
  return path.resolve(__dirname, "..");
}

function backendDataDir() {
  return path.join(app.getPath("userData"), "backend-data");
}

function appIconPath() {
  const resourcesRoot = process.resourcesPath || repoRoot();
  const candidates = app.isPackaged
    ? [path.join(resourcesRoot, "icon.png"), path.join(__dirname, "build", "icon.png")]
    : [path.join(__dirname, "build", "icon.png")];

  return candidates.find((candidate) => fs.existsSync(candidate));
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

function copyIfExists(source, destination) {
  if (!fs.existsSync(source)) {
    return false;
  }

  fs.cpSync(source, destination, { recursive: true });
  return true;
}

function createDesktopDataBackup(reason, versionLabel = app.getVersion()) {
  const dataDir = backendDataDir();
  const databasePath = path.join(dataDir, "db.sqlite3");
  const mediaPath = path.join(dataDir, "media");

  if (!fs.existsSync(databasePath) && !fs.existsSync(mediaPath)) {
    return null;
  }

  const safeVersion = String(versionLabel).replace(/[^a-zA-Z0-9._-]/g, "-");
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupDir = path.join(dataDir, "backups", `${reason}-${safeVersion}-${timestamp}`);
  fs.mkdirSync(backupDir, { recursive: true });

  const copied = {
    database: copyIfExists(databasePath, path.join(backupDir, "db.sqlite3")),
    media: copyIfExists(mediaPath, path.join(backupDir, "media")),
  };

  fs.writeFileSync(
    path.join(backupDir, "manifest.json"),
    JSON.stringify(
      {
        createdAt: new Date().toISOString(),
        appVersion: app.getVersion(),
        reason,
        copied,
      },
      null,
      2
    )
  );

  console.log(`[backup] Dados locais salvos em ${backupDir}`);
  return backupDir;
}

function createStartupBackupBeforeMigrations() {
  if (!app.isPackaged) {
    return;
  }

  try {
    const dataDir = backendDataDir();
    const markerPath = path.join(dataDir, "backups", ".last-startup-backup-version");
    const currentVersion = app.getVersion();
    const previousMarker = fs.existsSync(markerPath) ? fs.readFileSync(markerPath, "utf8").trim() : "";

    if (previousMarker === currentVersion) {
      return;
    }

    const backupDir = createDesktopDataBackup("before-migrations", currentVersion);
    fs.mkdirSync(path.dirname(markerPath), { recursive: true });
    fs.writeFileSync(markerPath, currentVersion);

    if (backupDir) {
      dialog.showMessageBox({
        type: "info",
        title: "Backup local criado",
        message: "Criamos um backup dos dados locais antes de abrir esta versao.",
        detail: backupDir,
      });
    }
  } catch (error) {
    console.error(`[backup] ${error.message}`);
    dialog.showErrorBox(
      "Falha ao criar backup local",
      "Nao foi possivel criar o backup antes de abrir esta versao. Verifique espaco em disco e permissoes da pasta de dados."
    );
  }
}

function startBackend() {
  const dataDir = backendDataDir();
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
      const response = await fetch(HEALTH_URL, { redirect: "manual" });
      if (response.status < 500) {
        return;
      }
    } catch (_error) {
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }

  throw new Error("Backend local nao respondeu dentro do tempo esperado.");
}

function configureAutoUpdates() {
  if (!app.isPackaged || process.env.LUME_DISABLE_UPDATES === "True") {
    return;
  }

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("error", (error) => {
    console.error(`[updater] ${error.message}`);
  });

  autoUpdater.on("update-available", (info) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      dialog.showMessageBox(mainWindow, {
        type: "info",
        title: "Atualizacao disponivel",
        message: `Uma nova versao (${info.version}) do Lume Gestao esta sendo baixada em segundo plano.`,
      });
    }
  });

  autoUpdater.on("update-downloaded", async (info) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      try {
        createDesktopDataBackup("before-update-install", info.version);
      } catch (error) {
        console.error(`[backup] ${error.message}`);
      }
      autoUpdater.quitAndInstall();
      return;
    }

    const result = await dialog.showMessageBox(mainWindow, {
      type: "question",
      buttons: ["Atualizar agora", "Depois"],
      defaultId: 0,
      cancelId: 1,
      title: "Atualizacao pronta",
      message: `A versao ${info.version} ja esta pronta para instalar.`,
      detail: "O aplicativo sera reiniciado para concluir a atualizacao.",
    });

    if (result.response === 0) {
      try {
        createDesktopDataBackup("before-update-install", info.version);
      } catch (error) {
        dialog.showErrorBox(
          "Falha ao criar backup local",
          "A atualizacao nao sera instalada agora porque nao foi possivel criar o backup dos dados locais."
        );
        console.error(`[backup] ${error.message}`);
        return;
      }
      autoUpdater.quitAndInstall();
    }
  });

  autoUpdater.checkForUpdatesAndNotify().catch((error) => {
    console.error(`[updater] ${error.message}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    title: "Lume Gestao",
    icon: appIconPath(),
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

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(APP_URL)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.loadURL(APP_URL);
}

const singleInstanceLock = app.requestSingleInstanceLock();

if (!singleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore();
      }
      mainWindow.focus();
    }
  });
}

if (singleInstanceLock) {
  app.whenReady().then(async () => {
    createStartupBackupBeforeMigrations();
    startBackend();

    try {
      await waitForBackend();
      createWindow();
      configureAutoUpdates();
    } catch (error) {
      dialog.showErrorBox("Lume Gestao", error.message);
      app.quit();
    }
  });
}

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

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
