#Requires -Version 5.1
<#
.SYNOPSIS
    Aquiles — Gerenciador de processos da plataforma Aquiles.

.DESCRIPTION
    Controla todos os processos do projeto via PM2:
      Neo4j, Backend Flask e Frontend Vite.
    Suporta instalação de auto-start no boot do Windows via Task Scheduler.

.PARAMETER Command
    start      Sobe todos os processos
    stop       Para todos os processos
    restart    Reinicia todos os processos
    status     Mostra status e health de cada processo
    logs       Exibe logs ao vivo (Ctrl+C para sair)
    logs-neo4j Exibe logs apenas do Neo4j
    logs-back  Exibe logs apenas do backend
    logs-front Exibe logs apenas do frontend
    install    Instala PM2, registra no boot e sobe o projeto
    uninstall  Remove do boot e para todos os processos
    flush      Limpa todos os logs de todos os processos

.EXAMPLE
    .\aquiles.ps1 install
    .\aquiles.ps1 start
    .\aquiles.ps1 status
    .\aquiles.ps1 logs
    .\aquiles.ps1 restart
    .\aquiles.ps1 stop
    .\aquiles.ps1 uninstall
#>

param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('start','stop','restart','status','logs','logs-neo4j','logs-back','logs-front','install','uninstall','flush')]
    [string]$Command
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ─── Caminhos ─────────────────────────────────────────────────────────────────
$ScriptDir   = $PSScriptRoot
$EcoConfig   = Join-Path $ScriptDir 'ecosystem.config.js'
$LogDir      = Join-Path $ScriptDir '.codex-run'

# ─── Helpers ──────────────────────────────────────────────────────────────────
function Write-Header([string]$Text) {
    Write-Host "`n═══════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════`n" -ForegroundColor Cyan
}

function Write-Step([string]$Text) {
    Write-Host "  ► $Text" -ForegroundColor Yellow
}

function Write-OK([string]$Text) {
    Write-Host "  ✔ $Text" -ForegroundColor Green
}

function Write-Fail([string]$Text) {
    Write-Host "  ✘ $Text" -ForegroundColor Red
}

function Assert-PM2 {
    $pm2Path = (Get-Command pm2 -ErrorAction SilentlyContinue)?.Source
    if (-not $pm2Path) {
        Write-Fail "PM2 não encontrado. Execute: .\aquiles.ps1 install"
        exit 1
    }
    return $pm2Path
}

function Invoke-PM2([string[]]$Args) {
    $pm2 = Assert-PM2
    & $pm2 @Args
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Comando PM2 falhou (código $LASTEXITCODE): pm2 $($Args -join ' ')"
        exit $LASTEXITCODE
    }
}

function Assert-EcoConfig {
    if (-not (Test-Path $EcoConfig)) {
        Write-Fail "ecosystem.config.js não encontrado em: $EcoConfig"
        exit 1
    }
}

# ─── Comandos ─────────────────────────────────────────────────────────────────

function Command-Install {
    Write-Header "Instalando Aquiles — configuração de auto-start"

    # 1. Verifica Node.js
    Write-Step "Verificando Node.js..."
    try {
        $nodeVer = node --version 2>&1
        Write-OK "Node.js $nodeVer"
    } catch {
        Write-Fail "Node.js não encontrado. Instale Node.js 18+ e tente novamente."
        exit 1
    }

    # 2. Instala PM2 globalmente
    Write-Step "Instalando PM2 globalmente (npm install -g pm2)..."
    npm install -g pm2
    if ($LASTEXITCODE -ne 0) { Write-Fail "Falha ao instalar PM2"; exit 1 }
    Write-OK "PM2 instalado"

    # 3. Instala pm2-windows-startup (integra PM2 ao Task Scheduler)
    Write-Step "Instalando pm2-windows-startup..."
    npm install -g pm2-windows-startup
    if ($LASTEXITCODE -ne 0) { Write-Fail "Falha ao instalar pm2-windows-startup"; exit 1 }
    Write-OK "pm2-windows-startup instalado"

    # 4. Registra PM2 no Task Scheduler do Windows
    Write-Step "Registrando PM2 no Task Scheduler (requer privilégio de Admin)..."
    try {
        pm2-startup install
        Write-OK "PM2 registrado no boot do Windows"
    } catch {
        Write-Fail "Falha ao registrar no Task Scheduler. Execute como Administrador."
        Write-Host "    Dica: clique com botão direito no PowerShell → 'Executar como administrador'" -ForegroundColor DarkYellow
        exit 1
    }

    # 5. Sobe os processos
    Write-Step "Subindo todos os processos Aquiles..."
    Assert-EcoConfig
    pm2 start $EcoConfig
    if ($LASTEXITCODE -ne 0) { Write-Fail "Falha ao iniciar processos"; exit 1 }

    # 6. Salva lista de processos para ressurreição no boot
    Write-Step "Salvando lista de processos (pm2 save)..."
    pm2 save --force
    Write-OK "Lista salva — processos voltarão automaticamente após reinicialização"

    Write-Header "Instalação concluída!"
    Write-Host "  Comandos úteis:" -ForegroundColor White
    Write-Host "    .\aquiles.ps1 status    → saúde dos processos" -ForegroundColor Gray
    Write-Host "    .\aquiles.ps1 logs      → logs ao vivo" -ForegroundColor Gray
    Write-Host "    .\aquiles.ps1 restart   → reiniciar tudo" -ForegroundColor Gray
    Write-Host "    .\aquiles.ps1 stop      → parar tudo" -ForegroundColor Gray
    Write-Host ""
}

function Command-Uninstall {
    Write-Header "Desinstalando auto-start do Aquiles"

    $pm2 = (Get-Command pm2 -ErrorAction SilentlyContinue)?.Source
    if ($pm2) {
        Write-Step "Parando todos os processos..."
        & $pm2 stop all 2>$null
        Write-OK "Processos parados"

        Write-Step "Deletando processos do PM2..."
        & $pm2 delete all 2>$null
        Write-OK "Processos removidos da lista do PM2"

        Write-Step "Removendo PM2 do Task Scheduler..."
        try {
            pm2-startup uninstall 2>$null
            Write-OK "Removido do boot do Windows"
        } catch {
            Write-Host "  (pm2-startup não disponível ou já removido)" -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  PM2 não encontrado — nada a fazer." -ForegroundColor DarkYellow
    }

    Write-OK "Desinstalação concluída"
}

function Command-Start {
    Write-Header "Iniciando Aquiles"
    Assert-EcoConfig

    # Verifica se já está rodando
    $pm2 = (Get-Command pm2 -ErrorAction SilentlyContinue)?.Source
    if ($pm2) {
        $runningList = & $pm2 list --no-color 2>&1
        if ($runningList -match 'aquiles-neo4j') {
            Write-Step "Processos já em execução — reiniciando..."
            Invoke-PM2 @('restart', 'all')
        } else {
            Invoke-PM2 @('start', $EcoConfig)
        }
    } else {
        Write-Fail "PM2 não instalado. Execute: .\aquiles.ps1 install"
        exit 1
    }

    Start-Sleep -Seconds 3
    Write-OK "Aquiles iniciado"
    Invoke-PM2 @('status')
}

function Command-Stop {
    Write-Header "Parando Aquiles"
    Invoke-PM2 @('stop', 'all')
    Write-OK "Todos os processos parados"
}

function Command-Restart {
    Write-Header "Reiniciando Aquiles"
    Invoke-PM2 @('restart', 'all')
    Start-Sleep -Seconds 3
    Write-OK "Reinicialização concluída"
    Invoke-PM2 @('status')
}

function Command-Status {
    Write-Header "Status do Aquiles"
    Invoke-PM2 @('status')
    Write-Host ""
    Write-Host "  Portas esperadas:" -ForegroundColor White
    Write-Host "    Neo4j    → bolt://localhost:7687  |  http://localhost:7474" -ForegroundColor Gray
    Write-Host "    Backend  → http://localhost:5001" -ForegroundColor Gray
    Write-Host "    Frontend → http://localhost:3000  (ou 5173)" -ForegroundColor Gray
    Write-Host ""

    # Teste rápido de conectividade
    Write-Step "Verificando portas..."
    @(
        @{ Name = 'Neo4j Bolt';  Port = 7687 },
        @{ Name = 'Backend';     Port = 5001 },
        @{ Name = 'Frontend';    Port = 3000 }
    ) | ForEach-Object {
        $conn = Test-NetConnection -ComputerName localhost -Port $_.Port -WarningAction SilentlyContinue -InformationLevel Quiet 2>$null
        if ($conn) {
            Write-OK "$($_.Name) (porta $($_.Port)) — ONLINE"
        } else {
            Write-Host "  ○ $($_.Name) (porta $($_.Port)) — aguardando" -ForegroundColor DarkYellow
        }
    }
    Write-Host ""
}

function Command-Logs([string]$Filter = '') {
    if ($Filter) {
        Invoke-PM2 @('logs', $Filter, '--lines', '50')
    } else {
        Invoke-PM2 @('logs', '--lines', '50')
    }
}

function Command-Flush {
    Write-Header "Limpando logs do Aquiles"
    Invoke-PM2 @('flush')
    Write-OK "Logs limpos"
}

# ─── Dispatcher ───────────────────────────────────────────────────────────────
switch ($Command) {
    'install'     { Command-Install }
    'uninstall'   { Command-Uninstall }
    'start'       { Command-Start }
    'stop'        { Command-Stop }
    'restart'     { Command-Restart }
    'status'      { Command-Status }
    'logs'        { Command-Logs }
    'logs-neo4j'  { Command-Logs 'aquiles-neo4j' }
    'logs-back'   { Command-Logs 'aquiles-backend' }
    'logs-front'  { Command-Logs 'aquiles-frontend' }
    'flush'       { Command-Flush }
}
