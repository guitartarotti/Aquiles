'use strict';

const { execFile } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DEFAULT_TARGETS = [
  ['aquiles-backend', 6144],
  ['aquiles-market-capture', 4096],
  ['aquiles-discovery-service', 4096],
  ['aquiles-vol-analytics-service', 4096],
  ['aquiles-options-model-service', 4096],
  ['aquiles-options-volume-tracker-service', 3072],
  ['aquiles-options-collector-service', 3072],
  ['aquiles-fair-value-markov-service', 4096],
  ['aquiles-cvm-cda-graph-service', 4096],
  ['aquiles-etf-daily-flow-service', 4096],
  ['aquiles-atemporal-chart-service', 3072],
  ['aquiles-flow-replicator-service', 3072],
];

const MB = 1024 * 1024;
const intervalMs = parseIntEnv('AQUILES_MEMORY_WATCHDOG_INTERVAL_MS', 60_000);
const consecutiveLimit = parseIntEnv('AQUILES_MEMORY_WATCHDOG_CONSECUTIVE_BREACHES', 3);
const restartCooldownMs = parseIntEnv('AQUILES_MEMORY_WATCHDOG_RESTART_COOLDOWN_MS', 10 * 60_000);
const minUptimeMs = parseIntEnv('AQUILES_MEMORY_WATCHDOG_MIN_UPTIME_MS', 5 * 60_000);
const metric = String(process.env.AQUILES_MEMORY_WATCHDOG_METRIC || 'private').toLowerCase();
const dryRun = truthy(process.env.AQUILES_MEMORY_WATCHDOG_DRY_RUN);
const runOnce = truthy(process.env.AQUILES_MEMORY_WATCHDOG_RUN_ONCE);
const enabled = !truthy(process.env.AQUILES_MEMORY_WATCHDOG_DISABLED);
const targets = parseTargets(process.env.AQUILES_MEMORY_WATCHDOG_TARGETS);

const breachCounts = new Map();
const lastRestartAt = new Map();
let running = false;

function parseIntEnv(name, fallback) {
  const parsed = Number.parseInt(process.env[name] || '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function truthy(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').trim().toLowerCase());
}

function parseTargets(spec) {
  if (!spec || !String(spec).trim()) {
    return new Map(DEFAULT_TARGETS);
  }
  const parsed = new Map();
  for (const item of String(spec).split(',')) {
    const text = item.trim();
    if (!text) {
      continue;
    }
    const match = text.match(/^([^:=]+)\s*[:=]\s*(\d+(?:\.\d+)?)$/);
    if (!match) {
      console.error(`[memory-watchdog] ignoring invalid target spec: ${text}`);
      continue;
    }
    parsed.set(match[1].trim(), Number.parseFloat(match[2]));
  }
  return parsed.size ? parsed : new Map(DEFAULT_TARGETS);
}

function pm2Command() {
  const executable = os.platform() === 'win32' ? 'pm2.cmd' : 'pm2';
  const localExecutable = path.resolve(__dirname, '..', 'node_modules', '.bin', executable);
  return fs.existsSync(localExecutable) ? localExecutable : executable;
}

function stripBom(text) {
  return String(text || '').replace(/^\uFEFF/, '').trim();
}

function parseJsonArrayOutput(output) {
  const text = stripBom(output);
  try {
    return JSON.parse(text);
  } catch (initialError) {
    const start = text.indexOf('[{');
    const emptyStart = text.indexOf('[]');
    const arrayStart = start >= 0 ? start : emptyStart;
    const arrayEnd = text.lastIndexOf(']');
    if (arrayStart >= 0 && arrayEnd >= arrayStart) {
      return JSON.parse(text.slice(arrayStart, arrayEnd + 1));
    }
    throw new Error(`PM2 returned invalid JSON: ${initialError.message}`);
  }
}

function exec(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    let executable = command;
    let executableArgs = args;
    if (os.platform() === 'win32' && /\.cmd$/i.test(command)) {
      executable = 'cmd.exe';
      executableArgs = ['/d', '/s', '/c', [command, ...args].map(quoteCmdArg).join(' ')];
    }
    execFile(executable, executableArgs, { windowsHide: true, maxBuffer: 64 * MB, ...options }, (error, stdout, stderr) => {
      if (error) {
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

function quoteCmdArg(value) {
  const text = String(value);
  if (!/[\s"]/g.test(text)) {
    return text;
  }
  return `"${text.replace(/"/g, '\\"')}"`;
}

async function readPm2List() {
  const { stdout } = await exec(pm2Command(), ['jlist']);
  const processList = parseJsonArrayOutput(stdout);
  if (!Array.isArray(processList)) {
    throw new TypeError('PM2 process list must be a JSON array');
  }
  return processList;
}

async function readProcessTrees(rootApps) {
  if (os.platform() !== 'win32') {
    return readProcessTreesWithPs(rootApps);
  }
  return readProcessTreesWithPowerShell(rootApps);
}

async function readProcessTreesWithPowerShell(rootApps) {
  const rootsJson = JSON.stringify(rootApps.map((app) => ({ name: app.name, pid: Number(app.pid) })));
  const script = `
$rootsJson = @'
${rootsJson}
'@
$roots = ConvertFrom-Json $rootsJson
$all = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name, CommandLine
$results = @()
foreach ($root in $roots) {
  $ids = New-Object 'System.Collections.Generic.HashSet[int]'
  [void]$ids.Add([int]$root.pid)
  $changed = $true
  while ($changed) {
    $changed = $false
    foreach ($p in $all) {
      if ($ids.Contains([int]$p.ParentProcessId) -and -not $ids.Contains([int]$p.ProcessId)) {
        [void]$ids.Add([int]$p.ProcessId)
        $changed = $true
      }
    }
  }
  [Int64]$privateTotal = 0
  [Int64]$workingSetTotal = 0
  $processRows = @()
  foreach ($id in $ids) {
    try {
      $proc = Get-Process -Id $id -ErrorAction Stop
      $privateTotal += [Int64]$proc.PrivateMemorySize64
      $workingSetTotal += [Int64]$proc.WorkingSet64
      $processRows += [pscustomobject]@{
        pid = [int]$id
        name = [string]$proc.ProcessName
        privateBytes = [Int64]$proc.PrivateMemorySize64
        workingSetBytes = [Int64]$proc.WorkingSet64
      }
    } catch {}
  }
  $results += [pscustomobject]@{
    name = [string]$root.name
    rootPid = [int]$root.pid
    totalPrivateBytes = [Int64]$privateTotal
    totalWorkingSetBytes = [Int64]$workingSetTotal
    processes = $processRows
  }
}
@($results) | ConvertTo-Json -Depth 6 -Compress
`;
  const encoded = Buffer.from(script, 'utf16le').toString('base64');
  const { stdout } = await exec('powershell.exe', [
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-EncodedCommand',
    encoded,
  ]);
  const parsed = JSON.parse(stripBom(stdout) || '[]');
  return Array.isArray(parsed) ? parsed : [parsed];
}

async function readProcessTreesWithPs(rootApps) {
  const result = [];
  for (const app of rootApps) {
    const { stdout } = await exec('ps', ['-o', 'pid=,ppid=,rss=,comm=', '-e']);
    const rows = stripBom(stdout)
      .split(/\r?\n/)
      .map((line) => {
        const match = line.trim().match(/^(\d+)\s+(\d+)\s+(\d+)\s+(.+)$/);
        return match
          ? { pid: Number(match[1]), ppid: Number(match[2]), rssBytes: Number(match[3]) * 1024, name: match[4] }
          : null;
      })
      .filter(Boolean);
    const ids = new Set([Number(app.pid)]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const row of rows) {
        if (ids.has(row.ppid) && !ids.has(row.pid)) {
          ids.add(row.pid);
          changed = true;
        }
      }
    }
    const processes = rows
      .filter((row) => ids.has(row.pid))
      .map((row) => ({
        pid: row.pid,
        name: row.name,
        privateBytes: row.rssBytes,
        workingSetBytes: row.rssBytes,
      }));
    const total = processes.reduce((sum, row) => sum + row.workingSetBytes, 0);
    result.push({
      name: app.name,
      rootPid: Number(app.pid),
      totalPrivateBytes: total,
      totalWorkingSetBytes: total,
      processes,
    });
  }
  return result;
}

function bytesToMb(bytes) {
  return Math.round((Number(bytes || 0) / MB) * 10) / 10;
}

function appUptimeMs(app) {
  const startedAt = Number(app.pm2_env?.pm_uptime || 0);
  return startedAt > 0 ? Date.now() - startedAt : 0;
}

function topProcesses(tree) {
  return [...(tree.processes || [])]
    .sort((a, b) => Number(b.privateBytes || 0) - Number(a.privateBytes || 0))
    .slice(0, 5)
    .map((item) => ({
      pid: item.pid,
      name: item.name,
      privateMb: bytesToMb(item.privateBytes),
      workingSetMb: bytesToMb(item.workingSetBytes),
    }));
}

async function restartApp(name, tree, limitMb, observedMb) {
  const last = lastRestartAt.get(name) || 0;
  if (Date.now() - last < restartCooldownMs) {
    log('restart_suppressed_cooldown', { name, observedMb, limitMb, cooldownMs: restartCooldownMs });
    return;
  }
  lastRestartAt.set(name, Date.now());
  log(dryRun ? 'restart_dry_run' : 'restart', {
    name,
    observedMb,
    limitMb,
    metric,
    topProcesses: topProcesses(tree),
  });
  if (!dryRun) {
    await exec(pm2Command(), ['restart', name]);
  }
  breachCounts.set(name, 0);
}

function log(event, payload = {}) {
  console.log(JSON.stringify({ ts: new Date().toISOString(), event, ...payload }));
}

async function cycle() {
  if (!enabled) {
    log('disabled');
    return;
  }
  if (running) {
    log('cycle_skipped_still_running');
    return;
  }
  running = true;
  try {
    const processList = await readPm2List();
    const watchedApps = processList
      .filter((app) => targets.has(app.name))
      .filter((app) => app.pm2_env?.status === 'online')
      .filter((app) => Number(app.pid || 0) > 0);
    const trees = await readProcessTrees(watchedApps);
    const byName = new Map(trees.map((tree) => [tree.name, tree]));
    const samples = [];

    for (const app of watchedApps) {
      const name = app.name;
      const tree = byName.get(name);
      if (!tree) {
        continue;
      }
      const limitMb = targets.get(name);
      const observedBytes = metric === 'working_set' ? tree.totalWorkingSetBytes : tree.totalPrivateBytes;
      const observedMb = bytesToMb(observedBytes);
      const uptimeMs = appUptimeMs(app);
      const sample = {
        name,
        pid: app.pid,
        privateMb: bytesToMb(tree.totalPrivateBytes),
        workingSetMb: bytesToMb(tree.totalWorkingSetBytes),
        limitMb,
        uptimeMs,
        processCount: (tree.processes || []).length,
      };
      samples.push(sample);

      if (uptimeMs < minUptimeMs) {
        breachCounts.set(name, 0);
        continue;
      }
      if (observedMb > limitMb) {
        const count = (breachCounts.get(name) || 0) + 1;
        breachCounts.set(name, count);
        log('breach', { ...sample, consecutiveBreaches: count, requiredBreaches: consecutiveLimit, topProcesses: topProcesses(tree) });
        if (count >= consecutiveLimit) {
          await restartApp(name, tree, limitMb, observedMb);
        }
      } else {
        breachCounts.set(name, 0);
      }
    }
    log('sample', { metric, samples });
  } catch (error) {
    log('error', {
      message: error.message,
      stderr: stripBom(error.stderr),
      stdout: stripBom(error.stdout),
    });
  } finally {
    running = false;
    if (runOnce) {
      process.exit(0);
    }
  }
}

log('started', {
  intervalMs,
  consecutiveLimit,
  restartCooldownMs,
  minUptimeMs,
  metric,
  dryRun,
  targets: Object.fromEntries(targets),
});

cycle();
if (!runOnce) {
  setInterval(cycle, intervalMs);
}
