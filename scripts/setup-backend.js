const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const requirementsPath = path.join(backendDir, 'requirements.txt');
const isWin = process.platform === 'win32';
const venvPython = isWin
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python');

function fail(message) {
  console.error(message);
  process.exit(1);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: backendDir,
    stdio: 'inherit',
    shell: options.shell ?? false,
    env: process.env,
  });

  if (result.error) {
    fail(result.error.message);
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function capture(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: options.shell ?? false,
    env: process.env,
    encoding: 'utf8',
  });

  if (result.error || result.status !== 0) {
    return null;
  }

  return `${result.stdout || ''}${result.stderr || ''}`.trim();
}

function parsePythonVersion(text) {
  const match = text.match(/Python\s+(\d+)\.(\d+)\.(\d+)/i);
  if (!match) {
    return null;
  }

  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
  };
}

function isSupportedPython(version) {
  return version && version.major === 3 && version.minor >= 11 && version.minor <= 12;
}

function compareVersions(left, right) {
  if (left.major !== right.major) return left.major - right.major;
  if (left.minor !== right.minor) return left.minor - right.minor;
  return left.patch - right.patch;
}

function getPyenvWindowsCandidates() {
  if (!isWin) {
    return [];
  }

  const userHome = process.env.USERPROFILE || process.env.HOME;
  if (!userHome) {
    return [];
  }

  const versionsDir = path.join(userHome, '.pyenv', 'pyenv-win', 'versions');
  if (!fs.existsSync(versionsDir)) {
    return [];
  }

  return fs.readdirSync(versionsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({
      command: path.join(versionsDir, entry.name, 'python.exe'),
      shell: false,
      source: `pyenv-win ${entry.name}`,
    }))
    .filter((candidate) => fs.existsSync(candidate.command));
}

function getCommandCandidates() {
  const candidates = [];
  const seen = new Set();

  function addCandidate(command, shell, source) {
    if (!command || seen.has(`${command}|${shell}`)) {
      return;
    }
    seen.add(`${command}|${shell}`);
    candidates.push({ command, shell, source });
  }

  if (process.env.BACKEND_PYTHON) {
    addCandidate(process.env.BACKEND_PYTHON, false, 'BACKEND_PYTHON');
  }

  if (process.env.PYTHON) {
    addCandidate(process.env.PYTHON, false, 'PYTHON');
  }

  for (const candidate of getPyenvWindowsCandidates()) {
    addCandidate(candidate.command, candidate.shell, candidate.source);
  }

  addCandidate('python3', true, 'python3');
  addCandidate('python', true, 'python');

  return candidates;
}

function detectPython() {
  let best = null;

  for (const candidate of getCommandCandidates()) {
    const versionOutput = capture(candidate.command, ['--version'], { shell: candidate.shell });
    const version = parsePythonVersion(versionOutput || '');

    if (!isSupportedPython(version)) {
      continue;
    }

    if (!best || compareVersions(version, best.version) > 0) {
      best = { ...candidate, version };
    }
  }

  return best;
}

if (!fs.existsSync(requirementsPath)) {
  fail('requirements.txt not found in backend/');
}

if (!fs.existsSync(venvPython)) {
  const detectedPython = detectPython();

  if (!detectedPython) {
    fail(
      'No supported Python interpreter found. Install Python 3.11 or 3.12, or set BACKEND_PYTHON to a compatible executable.'
    );
  }

  console.log(
    `Creating backend virtual environment with Python ${detectedPython.version.major}.${detectedPython.version.minor}.${detectedPython.version.patch} (${detectedPython.source})`
  );
  run(detectedPython.command, ['-m', 'venv', '.venv'], { shell: detectedPython.shell });
}

console.log('Installing backend dependencies into backend/.venv');
run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip']);
run(venvPython, ['-m', 'pip', 'install', '-r', 'requirements.txt']);
