import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import { existsSync } from "fs";
import app from "./app";

const CURRENT_DIR = typeof __dirname !== "undefined"
  ? __dirname
  : path.dirname(fileURLToPath(import.meta.url));

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

function startPythonBackend() {
  const scriptPath = path.resolve(CURRENT_DIR, "../../nba-vault-backend/server.py");
  if (!existsSync(scriptPath)) {
    console.error(`Python backend not found at ${scriptPath}`);
  }
  const python = process.env["PYTHON_BIN"] || "python3";

  console.log(`Starting Python backend: ${python} ${scriptPath}`);

  const pythonEnv = { ...process.env };
  delete pythonEnv["PORT"];
  pythonEnv["PYTHON_PORT"] = "8000";

  const proc = spawn(python, [scriptPath], {
    stdio: "inherit",
    env: pythonEnv,
    cwd: process.cwd(),
  });

  proc.on("error", (err) => {
    console.error("Python backend failed to start:", err.message);
  });

  proc.on("exit", (code, signal) => {
    console.error(`Python backend exited (code=${code} signal=${signal}), restarting in 2s...`);
    setTimeout(startPythonBackend, 2000);
  });
}

startPythonBackend();

app.listen(port, () => {
  console.log(`Server listening on port ${port}`);
});
