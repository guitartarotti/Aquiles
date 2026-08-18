/**
 * ecosystem.config.js — PM2 Ecosystem: Projeto Aquiles
 *
 * Processos gerenciados:
 *   aquiles-neo4j   → banco de grafos Neo4j (porta 7687)
 *   aquiles-backend → Flask API             (porta 5001)
 *   aquiles-frontend→ Vite dev server       (porta 3000)
 *
 * Uso rápido:
 *   pm2 start ecosystem.config.js     ← sobe tudo
 *   pm2 stop all                      ← para tudo
 *   pm2 restart all                   ← reinicia tudo
 *   pm2 status                        ← saúde dos processos
 *   pm2 logs                          ← logs ao vivo
 *   pm2 save                          ← persiste lista para resurrect no boot
 */

'use strict';

const path = require('node:path');
const ROOT = __dirname;

module.exports = {
  apps: [
    // ─── 1. Neo4j ────────────────────────────────────────────────────────────
    {
      name: 'aquiles-neo4j',
      script: path.join(ROOT, 'scripts', 'aquiles-neo4j.js'),
      cwd: ROOT,

      // Reinicia automaticamente se cair
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,          // aguarda 5 s antes de cada tentativa
      min_uptime: '30s',            // considera estável após 30 s em execução
      kill_timeout: 30000,          // permite checkpoint e shutdown limpo do banco

      // Logs
      out_file: path.join(ROOT, '.codex-run', 'neo4j.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'neo4j.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',

      // Não define NODE_APP_INSTANCE para evitar conflito
      instance_var: 'INSTANCE_ID',
    },

    // ─── 2. Backend Flask ─────────────────────────────────────────────────────
    {
      name: 'aquiles-backend',
      script: path.join(ROOT, 'scripts', 'run-backend.js'),
      cwd: ROOT,

      // Backend depende do Neo4j → atrasa 15 s após o Neo4j subir
      // PM2 não tem "depends_on" nativo; usamos restart_delay no start
      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      // Variáveis de ambiente herdadas do sistema + extras
      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR: '1',
        AQUILES_DISABLE_OPTIONS_VOLUME_TRACKER: '1',
        AQUILES_DISABLE_OPTIONS_COLLECTOR: '1',
      },

      // Logs
      out_file: path.join(ROOT, '.codex-run', 'backend.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'backend.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    // ─── 3. Frontend Vite ─────────────────────────────────────────────────────
    {
      name: 'aquiles-market-capture',
      script: path.join(ROOT, 'scripts', 'run-market-screen-collector.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },

      out_file: path.join(ROOT, '.codex-run', 'market-capture.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'market-capture.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-discovery-service',
      script: path.join(ROOT, 'scripts', 'run-discovery-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR: '1',
        DISCOVERY_SERVICE_PORT: '5012',
      },

      out_file: path.join(ROOT, '.codex-run', 'discovery-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'discovery-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-vol-analytics-service',
      script: path.join(ROOT, 'scripts', 'run-vol-analytics-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        VOL_ANALYTICS_SERVICE_PORT: '5013',
      },

      out_file: path.join(ROOT, '.codex-run', 'vol-analytics-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'vol-analytics-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-options-model-service',
      script: path.join(ROOT, 'scripts', 'run-options-model-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        OPTIONS_MODEL_SERVICE_PORT: '5014',
      },

      out_file: path.join(ROOT, '.codex-run', 'options-model-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'options-model-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-options-volume-tracker-service',
      script: path.join(ROOT, 'scripts', 'run-options-volume-tracker-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        OPTIONS_VOLUME_TRACKER_SERVICE_PORT: '5015',
      },

      out_file: path.join(ROOT, '.codex-run', 'options-volume-tracker-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'options-volume-tracker-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-options-collector-service',
      script: path.join(ROOT, 'scripts', 'run-options-collector-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        OPTIONS_COLLECTOR_SERVICE_PORT: '5021',
      },

      out_file: path.join(ROOT, '.codex-run', 'options-collector-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'options-collector-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-fair-value-markov-service',
      script: path.join(ROOT, 'scripts', 'run-fair-value-markov-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR: '1',
        FAIR_VALUE_MARKOV_SERVICE_PORT: '5016',
      },

      out_file: path.join(ROOT, '.codex-run', 'fair-value-markov-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'fair-value-markov-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-cvm-cda-graph-service',
      script: path.join(ROOT, 'scripts', 'run-cvm-cda-graph-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        CVM_CDA_GRAPH_SERVICE_PORT: '5017',
      },

      out_file: path.join(ROOT, '.codex-run', 'cvm-cda-graph-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'cvm-cda-graph-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-etf-daily-flow-service',
      script: path.join(ROOT, 'scripts', 'run-etf-daily-flow-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        ETF_DAILY_FLOW_SERVICE_PORT: '5018',
        ETF_DAILY_FLOW_AUTO_START: 'True',
      },

      out_file: path.join(ROOT, '.codex-run', 'etf-daily-flow-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'etf-daily-flow-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-atemporal-chart-service',
      script: path.join(ROOT, 'scripts', 'run-atemporal-chart-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR: '1',
        ATEMPORAL_CHART_SERVICE_PORT: '5019',
      },

      out_file: path.join(ROOT, '.codex-run', 'atemporal-chart-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'atemporal-chart-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-flow-replicator-service',
      script: path.join(ROOT, 'scripts', 'run-flow-replicator-service.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 20,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        FLOW_REPLICATOR_SERVICE_PORT: '5020',
        FLOW_REPLICATOR_AUTO_START: 'True',
      },

      out_file: path.join(ROOT, '.codex-run', 'flow-replicator-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'flow-replicator-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-legacy-heatmap-service',
      script: path.join(ROOT, 'scripts', 'run-legacy-heatmap-service.js'),
      cwd: ROOT,

      // Old Heatmap/options-context lab. Keep stopped unless explicitly needed.
      autostart: false,
      autorestart: false,
      watch: false,
      max_restarts: 3,
      restart_delay: 3000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        LEGACY_HEATMAP_SERVICE_PORT: '5022',
        LEGACY_PARTICIPANT_HEATMAP_AUTO_START: 'False',
        LEGACY_OPTIONS_HEATMAP_CONTEXT_AUTO_START: 'False',
        LEGACY_INTRADAY_CORRELATION_CONTINUOUS_ENABLE: 'False',
        LEGACY_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS: '300',
        LEGACY_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS: '60',
        LEGACY_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS: '60',
      },

      out_file: path.join(ROOT, '.codex-run', 'legacy-heatmap-service.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'legacy-heatmap-service.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-frontend',
      // Usa wrapper Node para compatibilidade com Windows (npm.cmd não pode
      // ser executado diretamente pelo PM2 no Windows)
      script: path.join(ROOT, 'scripts', 'aquiles-frontend.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,
      min_uptime: '15s',

      env: {
        NODE_ENV: 'development',
        FORCE_COLOR: '1',
      },

      // Logs
      out_file: path.join(ROOT, '.codex-run', 'frontend.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'frontend.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },

    {
      name: 'aquiles-memory-watchdog',
      script: path.join(ROOT, 'scripts', 'memory-watchdog.js'),
      cwd: ROOT,

      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: '20s',

      env: {
        NODE_ENV: 'production',
        AQUILES_MEMORY_WATCHDOG_INTERVAL_MS: '60000',
        AQUILES_MEMORY_WATCHDOG_CONSECUTIVE_BREACHES: '3',
        AQUILES_MEMORY_WATCHDOG_RESTART_COOLDOWN_MS: '600000',
        AQUILES_MEMORY_WATCHDOG_MIN_UPTIME_MS: '300000',
        AQUILES_MEMORY_WATCHDOG_METRIC: 'private',
        AQUILES_MEMORY_WATCHDOG_TARGETS: [
          'aquiles-backend=6144',
          'aquiles-market-capture=4096',
          'aquiles-discovery-service=4096',
          'aquiles-vol-analytics-service=4096',
          'aquiles-options-model-service=4096',
          'aquiles-options-volume-tracker-service=3072',
          'aquiles-options-collector-service=3072',
          'aquiles-fair-value-markov-service=4096',
          'aquiles-cvm-cda-graph-service=4096',
          'aquiles-etf-daily-flow-service=4096',
          'aquiles-atemporal-chart-service=3072',
          'aquiles-flow-replicator-service=3072',
        ].join(','),
      },

      out_file: path.join(ROOT, '.codex-run', 'memory-watchdog.out.log'),
      error_file: path.join(ROOT, '.codex-run', 'memory-watchdog.err.log'),
      merge_logs: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
};
