/**
 * aquiles-frontend.js
 * Wrapper Node.js para o servidor de desenvolvimento Vite sob o PM2.
 * Necessário no Windows porque PM2 não executa npm.cmd diretamente.
 */
'use strict';

const path  = require('node:path');
const { spawn } = require('node:child_process');

const ROOT_DIR    = path.resolve(__dirname, '..');
const FRONTEND_DIR = path.join(ROOT_DIR, 'frontend');

console.log(`[aquiles-frontend] Iniciando Vite dev server em: ${FRONTEND_DIR}`);

// No Windows, .cmd precisa de shell:true para ser executado via spawn
const isWin  = process.platform === 'win32';
const npmCmd = isWin ? 'npm.cmd' : 'npm';

const child = spawn(npmCmd, ['run', 'dev'], {
  cwd: FRONTEND_DIR,
  stdio: 'inherit',
  shell: isWin,   // necessário para .cmd no Windows
  env: { ...process.env, FORCE_COLOR: '1' },
  windowsHide: true,
});

process.on('SIGTERM', () => {
  console.log('[aquiles-frontend] Recebido SIGTERM, encerrando Vite...');
  if (!child.killed) child.kill('SIGTERM');
});

process.on('SIGINT', () => {
  console.log('[aquiles-frontend] Recebido SIGINT, encerrando Vite...');
  if (!child.killed) child.kill('SIGINT');
});

child.on('exit', (code, signal) => {
  console.log(`[aquiles-frontend] Vite saiu — código: ${code}, sinal: ${signal}`);
  process.exit(code ?? 0);
});

child.on('error', (err) => {
  console.error(`[aquiles-frontend] Erro ao iniciar Vite: ${err.message}`);
  process.exit(1);
});
