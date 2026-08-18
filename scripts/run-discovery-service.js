const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const venvPython = process.platform === 'win32'
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python');

function exitWithMessage(message) {
  console.error(message);
  process.exit(1);
}

function forwardExit(child) {
  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  });

  child.on('error', (error) => {
    exitWithMessage(`Failed to start discovery service: ${error.message}`);
  });
}

if (fs.existsSync(venvPython)) {
  const child = spawn(venvPython, ['run_discovery_market_service.py'], {
    cwd: backendDir,
    stdio: 'inherit',
  });
  forwardExit(child);
} else {
  const child = spawn('uv run python run_discovery_market_service.py', {
    cwd: backendDir,
    stdio: 'inherit',
    shell: true,
  });
  forwardExit(child);
}
