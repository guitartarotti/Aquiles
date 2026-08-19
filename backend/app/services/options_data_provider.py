"""
options_data_provider
=====================
Factory que retorna o provedor de dados de opcoes correto conforme a configuracao.

Logica de selecao (em ordem de prioridade):
  1. OPLAB_ENABLE=True                 → OpLabOptionsService  (API REST OpLab)
  2. OPTIONS_BLOOMBERG_ENABLE=True     → OptionsBloombergService (Bloomberg Desktop, legado)
  3. Nenhum habilitado                 → OpLabOptionsService com aviso (fail-safe)

A interface publica e identica nos dois providers:
  .status()
  .fetch_option_chain(underlying_security)
  .fetch_option_snapshots(securities, fields)
  .fetch_option_history(security, start_date, end_date, fields)

Os campos retornados em fetch_option_snapshots sao um superconjunto do Bloomberg:
  - Campos Bloomberg padrao: PX_LAST, BID, ASK, OPT_DELTA, OPT_GAMMA, IVOL_MID, ...
  - Campos proprietarios (OpLab only): MODEL_IV, MODEL_DELTA, MODEL_GAMMA_POINT,
      MODEL_GAMMA_1PCT, MODEL_VEGA_1PCTVOL, MODEL_THETA_BD252, MODEL_VANNA,
      MODEL_CHARM_BD252, MODEL_SOURCE, EFF_DELTA, EFF_GAMMA_PT, EFF_GAMMA_1PCT,
      EFF_IV, EFF_VEGA, EFF_THETA, EFF_VANNA, EFF_CHARM

Quando o provider e Bloomberg, os campos MODEL_* e EFF_* nao sao preenchidos
(ficam como None), mantendo compatibilidade total com o restante do modulo.

Uso:
    from .options_data_provider import get_options_data_provider

    provider = get_options_data_provider()
    chain = provider.fetch_option_chain("IBOVE Index")
    snapshots = provider.fetch_option_snapshots(["IBOVQ178A3"], fields=None)
    # snapshots["rows"][0]["fields"]["EFF_DELTA"]  ← disponivel com OpLab
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("aquiles.options_data_provider")


def get_options_data_provider(config: Any = None) -> Any:
    """
    Retorna a instancia correta do provedor de dados de opcoes.

    Parametros
    ----------
    config : Any, opcional
        Objeto de configuracao. Padrao: Config do modulo config.py.

    Retorno
    -------
    OpLabOptionsService | OptionsBloombergService
    """
    from ..config import Config as _Config  # noqa: PLC0415

    cfg = config or _Config

    oplab_enabled     = getattr(cfg, "OPLAB_ENABLE", False)
    bloomberg_enabled = getattr(cfg, "OPTIONS_BLOOMBERG_ENABLE", True)

    if oplab_enabled:
        from .oplab_options_service import OpLabOptionsService  # noqa: PLC0415
        logger.debug("Options provider: OpLab (OPLAB_ENABLE=True)")
        return OpLabOptionsService(config=cfg)

    if bloomberg_enabled:
        from .options_bloomberg_service import OptionsBloombergService  # noqa: PLC0415
        logger.debug("Options provider: Bloomberg (OPTIONS_BLOOMBERG_ENABLE=True)")
        return OptionsBloombergService()

    # Nenhum habilitado — fail-safe: retorna OpLab (nao conectado, mas nao quebra o modulo)
    logger.warning(
        "Nenhum provider de opcoes habilitado (OPLAB_ENABLE=False, "
        "OPTIONS_BLOOMBERG_ENABLE=False). Usando OpLab como fail-safe."
    )
    from .oplab_options_service import OpLabOptionsService  # noqa: PLC0415
    return OpLabOptionsService(config=cfg)
