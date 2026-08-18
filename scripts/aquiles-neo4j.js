/**
 * aquiles-neo4j.js
 * Wrapper Node.js para gerenciar o processo Neo4j sob o PM2.
 * Lança neo4j.bat console com JAVA_HOME correto e repassa sinais de término.
 */
'use strict';

const path  = require('node:path');
const fs    = require('node:fs');
const { spawn } = require('node:child_process');

const ROOT_DIR  = path.resolve(__dirname, '..');
const NEO4J_DIR = path.join(ROOT_DIR, '.codex-run', 'neo4j-community-5.26.24');
const NEO4J_BAT = path.join(NEO4J_DIR, 'bin', 'neo4j.bat');

// ─── Localiza JAVA_HOME (Java 21+) ───────────────────────────────────────────
function findJavaHome() {
  // 1. Variável de ambiente já definida
  if (process.env.JAVA_HOME) return process.env.JAVA_HOME;

  // 2. Caminhos comuns no Windows
  const candidates = [
    path.join(ROOT_DIR, '.codex-run', 'jdk-21'),
    'C:\\Program Files\\Java\\jdk-21',
    'C:\\Program Files\\Java\\jdk-21.0.1',
    'C:\\Program Files\\Java\\jdk-21.0.2',
    'C:\\Program Files\\Java\\jdk-21.0.3',
    'C:\\Program Files\\Java\\jdk-21.0.4',
    'C:\\Program Files\\Eclipse Adoptium\\jdk-21.0.1.12-hotspot',
    'C:\\Program Files\\Eclipse Adoptium\\jdk-21.0.2.13-hotspot',
    'C:\\Program Files\\Eclipse Adoptium\\jdk-21.0.3.9-hotspot',
    'C:\\Program Files\\Eclipse Adoptium\\jdk-21.0.4.7-hotspot',
    'C:\\Program Files\\Microsoft\\jdk-21.0.1.12-hotspot',
    'C:\\Program Files\\Microsoft\\jdk-21.0.3.9-hotspot',
    'C:\\Program Files\\Amazon Corretto\\jdk21.0.1_12',
  ];
  for (const c of candidates) {
    if (fs.existsSync(path.join(c, 'bin', 'java.exe'))) return c;
  }

  // 3. Tenta localizar via `where java`
  try {
    const { execFileSync } = require('node:child_process');
    const javaPath = execFileSync('where', ['java'], { encoding: 'utf8' }).trim().split('\n')[0].trim();
    if (javaPath) {
      // onde/bin/java.exe → onde
      return path.resolve(javaPath, '..', '..');
    }
  } catch (_) { /* ignora */ }

  return null;
}

// ─── Validações ──────────────────────────────────────────────────────────────
if (!fs.existsSync(NEO4J_BAT)) {
  console.error(`[aquiles-neo4j] neo4j.bat não encontrado em: ${NEO4J_BAT}`);
  process.exit(1);
}

const javaHome = findJavaHome();
if (!javaHome) {
  console.error('[aquiles-neo4j] Java 21+ não encontrado. Defina JAVA_HOME manualmente.');
  process.exit(1);
}

console.log(`[aquiles-neo4j] JAVA_HOME: ${javaHome}`);
console.log(`[aquiles-neo4j] Neo4j BAT: ${NEO4J_BAT}`);
console.log(`[aquiles-neo4j] Iniciando Neo4j...`);

// ─── Lança o processo ────────────────────────────────────────────────────────
const env = {
  ...process.env,
  JAVA_HOME: javaHome,
  PATH: `${path.join(javaHome, 'bin')};${process.env.PATH}`,
};

const child = spawn('cmd.exe', ['/c', NEO4J_BAT, 'console'], {
  cwd: NEO4J_DIR,
  env,
  stdio: 'inherit',
  windowsHide: true,
});

// Repassa sinais do PM2 → Neo4j
function shutdown(signal) {
  console.log(`[aquiles-neo4j] Recebido ${signal}, encerrando Neo4j...`);
  if (!child.killed) {
    // Tenta parada limpa; se demorar 15 s, força
    const killer = spawn('cmd.exe', ['/c', NEO4J_BAT, 'stop'], {
      cwd: NEO4J_DIR, env, stdio: 'inherit', windowsHide: true,
    });
    killer.on('close', () => {
      if (!child.killed) child.kill('SIGTERM');
    });
    setTimeout(() => {
      if (!child.killed) child.kill('SIGKILL');
    }, 15_000);
  }
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT',  () => shutdown('SIGINT'));

child.on('exit', (code, signal) => {
  console.log(`[aquiles-neo4j] Neo4j saiu — código: ${code}, sinal: ${signal}`);
  process.exit(code ?? 0);
});

child.on('error', (err) => {
  console.error(`[aquiles-neo4j] Erro ao iniciar Neo4j: ${err.message}`);
  process.exit(1);
});
