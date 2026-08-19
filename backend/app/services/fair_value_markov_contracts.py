from __future__ import annotations

from typing import Any

MARKOV_REGIME_MODEL_VERSION = 8
DEFAULT_STATE_COUNT = 4
MIN_OBSERVATIONS = 24
STUDENT_T_NU = 5.0
FULL_MEMORY_CACHE_TTL_SECONDS = 60.0
SNAPSHOT_STALE_SECONDS = 90.0


STATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": 0,
        "key": "risk_on",
        "name": "Risk-on",
        "color": "#22c55e",
        "description": "XB1 follows supportive fair-value legs with positive/benign pressure.",
        "nu": 7.0,
    },
    {
        "id": 1,
        "key": "risk_off",
        "name": "Risk-off",
        "color": "#f59e0b",
        "description": "Defensive tape: fair-value legs or RPC pressure lean against the index.",
        "nu": 6.0,
    },
    {
        "id": 2,
        "key": "local_stress",
        "name": "Local stress",
        "color": "#f97316",
        "description": "Externo ainda sustenta, mas DI/FX/equity local passam a piorar o tape brasileiro.",
        "nu": 5.0,
    },
    {
        "id": 3,
        "key": "local_relief",
        "name": "Alivio local",
        "color": "#14b8a6",
        "description": "Local ainda fragilizado, mas inclinacao, vol e pressao marginal comecam a melhorar.",
        "nu": 5.5,
    },
    {
        "id": 4,
        "key": "stress",
        "name": "Stress",
        "color": "#ef4444",
        "description": "Fat-tail move, negative pressure or volatility shock.",
        "nu": 4.0,
    },
    {
        "id": 5,
        "key": "dislocation",
        "name": "Dislocation",
        "color": "#8b5cf6",
        "description": "XB1 detaches from fair-value legs; residual and FV gap dominate.",
        "nu": 4.0,
    },
]

TAPE_STATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": 0,
        "key": "expansion",
        "name": "Expansao",
        "color": "#38bdf8",
        "description": "Range e volatilidade intraday expandem sem colapso direcional extremo.",
        "nu": 5.0,
    },
    {
        "id": 1,
        "key": "lateral",
        "name": "Lateralidade",
        "color": "#94a3b8",
        "description": "Baixa eficiencia direcional; preco oscila em faixa com pouco deslocamento liquido.",
        "nu": 8.0,
    },
    {
        "id": 2,
        "key": "stop_hunt",
        "name": "Stop hunt",
        "color": "#f59e0b",
        "description": "Pavio/sweep, reversao intrabar e fechamento de volta para dentro da faixa.",
        "nu": 4.5,
    },
    {
        "id": 3,
        "key": "trend",
        "name": "Tendencia clara",
        "color": "#22c55e",
        "description": "Alta eficiencia direcional e persistencia de movimento no XB1.",
        "nu": 6.0,
    },
    {
        "id": 4,
        "key": "panic",
        "name": "Panico",
        "color": "#ef4444",
        "description": "Queda com range, residuo, pressao ou dislocation extremos.",
        "nu": 3.5,
    },
]

CORR_STATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": 0,
        "key": "aligned",
        "name": "Alinhado",
        "color": "#22c55e",
        "description": "Local e externo andam com coerencia semelhante para o XB1.",
        "nu": 7.5,
    },
    {
        "id": 1,
        "key": "external_dominance",
        "name": "Dominancia externa",
        "color": "#38bdf8",
        "description": "O XB1 esta mais acoplado ao bloco externo do que ao bloco local.",
        "nu": 6.5,
    },
    {
        "id": 2,
        "key": "local_dominance",
        "name": "Dominancia local",
        "color": "#f97316",
        "description": "O XB1 passa a responder mais fortemente ao bloco local Brasil.",
        "nu": 6.0,
    },
    {
        "id": 3,
        "key": "corr_break",
        "name": "Quebra de correlacao",
        "color": "#8b5cf6",
        "description": "A coerencia entre os blocos se rompe e a transmissao muda de forma instavel.",
        "nu": 4.5,
    },
]

META_REGIME_DEFINITIONS: list[dict[str, str]] = [
    {
        "key": "defensive_rally",
        "name": "Rali defensivo",
        "color": "#f59e0b",
        "description": "Preco sobe, mas com DI/fluxo/estrutura ainda defensivos e distancia do fair value elevada.",
    },
    {
        "key": "fragile_risk_on",
        "name": "Risk-on fragil",
        "color": "#14b8a6",
        "description": "Melhora direcional existe, mas ainda sem confirmacao estrutural ampla entre pernas e correlacoes.",
    },
    {
        "key": "clean_risk_on",
        "name": "Risk-on limpo",
        "color": "#22c55e",
        "description": "Direcao, fair value, correlacao e pernas andam juntos em favor do XB1.",
    },
    {
        "key": "capitulation",
        "name": "Capitulacao",
        "color": "#ef4444",
        "description": "Stress/panico e cauda dominam a leitura, com pressao e deslocamento extremos.",
    },
    {
        "key": "defensive_balance",
        "name": "Balanceamento defensivo",
        "color": "#f97316",
        "description": "Mercado defensivo, sem rali limpo, sustentado por confirmacao parcial e pouca expansao saudavel.",
    },
    {
        "key": "balanced",
        "name": "Balanceado",
        "color": "#94a3b8",
        "description": "Sinais mistos e sem vies estatistico forte para regime derivado especifico.",
    },
]

META_HMM_STATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": 0,
        "key": "defensive_rally",
        "name": "Rali defensivo",
        "color": "#f59e0b",
        "description": "Rali com suporte incompleto e estrutura ainda defensiva.",
        "nu": 5.0,
    },
    {
        "id": 1,
        "key": "fragile_risk_on",
        "name": "Risk-on fragil",
        "color": "#14b8a6",
        "description": "Melhora direcional com confirmacao parcial.",
        "nu": 5.5,
    },
    {
        "id": 2,
        "key": "clean_risk_on",
        "name": "Risk-on limpo",
        "color": "#22c55e",
        "description": "Pernas, correlacao e fluxo sustentam a alta.",
        "nu": 6.0,
    },
    {
        "id": 3,
        "key": "capitulation",
        "name": "Capitulacao",
        "color": "#ef4444",
        "description": "Cauda, stress e pressao dominam a leitura.",
        "nu": 4.2,
    },
    {
        "id": 4,
        "key": "defensive_balance",
        "name": "Balanceamento defensivo",
        "color": "#f97316",
        "description": "Mercado mais defensivo e sem direcao limpa.",
        "nu": 5.0,
    },
]


EXTRA_FEATURE_DEFINITIONS: list[dict[str, str]] = [
    {"key": "rpc_pressure", "label": "RPC pressure"},
    {"key": "rpc_slope", "label": "RPC slope"},
    {"key": "rpc_acceleration", "label": "RPC acceleration"},
    {"key": "fair_value_gap_z", "label": "FV gap z"},
    {"key": "core_shadow_gap", "label": "Core-shadow gap"},
    {"key": "edge_bias", "label": "Edge bias"},
    {"key": "local_block", "label": "Local block"},
    {"key": "external_block", "label": "External block"},
    {"key": "block_consensus", "label": "Block consensus"},
    {"key": "block_gap", "label": "External-local gap"},
    {"key": "block_agreement", "label": "Block agreement"},
    {"key": "di_curve_slope_change", "label": "DI curve slope change"},
    {"key": "di_curve_level_change", "label": "DI curve level change"},
    {"key": "vixbr_rpc_score", "label": "VIXBR RPC score"},
    {"key": "di_curve_shape_relief", "label": "DI curve shape relief"},
    {"key": "vixbr_relief_impulse", "label": "VIXBR relief impulse"},
    {"key": "local_relief_impulse", "label": "Local relief impulse"},
    {"key": "local_stress_impulse", "label": "Local stress impulse"},
    {"key": "broad_risk_off_pressure", "label": "Broad risk-off pressure"},
    {"key": "corr_local_short", "label": "Corr local short"},
    {"key": "corr_local_medium", "label": "Corr local medium"},
    {"key": "corr_external_short", "label": "Corr external short"},
    {"key": "corr_external_medium", "label": "Corr external medium"},
    {"key": "corr_gain_local", "label": "Corr gain local"},
    {"key": "corr_gain_external", "label": "Corr gain external"},
    {"key": "corr_gain_gap", "label": "Corr gain gap"},
    {"key": "corr_break_score", "label": "Corr break score"},
    {"key": "dislocation_pressure", "label": "Dislocation pressure"},
    {"key": "corr_state_aligned", "label": "Corr aligned prob"},
    {"key": "corr_state_external_dominance", "label": "Corr external prob"},
    {"key": "corr_state_local_dominance", "label": "Corr local prob"},
    {"key": "corr_state_corr_break", "label": "Corr break prob"},
]
