from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from ...config import Config
from ...utils.logger import get_logger
from ..options_store import OptionsStore
from .daily_insights import OptionsDailyInsightService
from .dealer_inference import build_dealer_inference
from .exposures import aggregate_exposures, compute_option_exposures
from .gamma_flip_history import build_gamma_flip_history
from .input_preparation import prepare_option_inputs
from .market_context import build_market_context
from .outputs import build_operational_output
from .pressure import analyze_pressure_curve
from .range_projection import build_range_projection
from .signal_inference import infer_signal
from .spot_grid import reprice_grid
from .strike_profiles import build_strike_profiles
from .types import ModelRunConfig

logger = get_logger("aquiles.options_modeling.service")


class OptionsModelingService:
    def __init__(
        self,
        store: OptionsStore | None = None,
        bloomberg: Any | None = None,
    ):
        self.store = store or OptionsStore()
        if bloomberg is None:
            from ..options_data_provider import get_options_data_provider  # noqa: PLC0415
            bloomberg = get_options_data_provider()
        self.bloomberg = bloomberg
        self.daily_insights = OptionsDailyInsightService(store=self.store)

    def build_run_config(self, sign_convention: str | None = None) -> ModelRunConfig:
        return ModelRunConfig(
            sign_convention=(sign_convention or Config.OPTIONS_MODEL_SIGN_CONVENTION).strip().lower(),
            grid_range_pct=Config.OPTIONS_MODEL_GRID_RANGE_PCT,
            grid_points=Config.OPTIONS_MODEL_GRID_POINTS,
            gex_weight=Config.OPTIONS_MODEL_GEX_WEIGHT,
            vex_weight=Config.OPTIONS_MODEL_VEX_WEIGHT,
            cex_weight=Config.OPTIONS_MODEL_CEX_WEIGHT,
            option_multiplier=Config.OPTIONS_MODEL_CONTRACT_POINT_VALUE,
            win_point_value=Config.OPTIONS_MODEL_WIN_POINT_VALUE,
            min_time_years=Config.OPTIONS_MODEL_MIN_TIME_YEARS,
            vol_epsilon=Config.OPTIONS_MODEL_VOL_EPS,
            time_epsilon_days=Config.OPTIONS_MODEL_TIME_EPS_DAYS,
        )

    def run_latest(
        self,
        underlying_security: str,
        universe_tier: str | None = None,
        sign_convention: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        tier = universe_tier or Config.OPTIONS_MODEL_DEFAULT_TIER
        source = self.store.read_latest_snapshot(tier, underlying_security=underlying_security, limit=5000)
        if not source:
            raise ValueError(f"No snapshot available for {underlying_security} in tier {tier}")
        return self.run_from_snapshot_payload(source, sign_convention=sign_convention, persist=persist)

    def run_for_batch(
        self,
        underlying_security: str,
        universe_tier: str,
        session_date: str,
        batch_key: str,
        sign_convention: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        source = self.store.read_snapshot_batch(universe_tier, session_date, batch_key)
        if not source:
            raise ValueError(f"Snapshot batch not found: {universe_tier}/{session_date}/{batch_key}")
        batch = source.get("batch") or {}
        if underlying_security and batch.get("underlying_security") and batch.get("underlying_security") != underlying_security:
            raise ValueError("Requested underlying_security does not match snapshot batch")
        return self.run_from_snapshot_payload(source, sign_convention=sign_convention, persist=persist)

    def run_from_snapshot_payload(
        self,
        source_payload: dict[str, Any],
        sign_convention: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        batch = source_payload.get("batch") or {}
        snapshot_rows = source_payload.get("rows") or []
        underlying_security = str(batch.get("underlying_security") or (snapshot_rows[0].get("underlying_security") if snapshot_rows else "")).strip()
        if not underlying_security:
            raise ValueError("Unable to determine underlying_security for modeling run")

        run_config = self.build_run_config(sign_convention)
        market_context = build_market_context(
            underlying_security=underlying_security,
            snapshot_rows=snapshot_rows,
            snapshot_batch=batch,
            bloomberg_service=self.bloomberg,
        )

        # ── Enriquece OI das snapshot_rows com dados B3 frescos ──────────────
        # O snapshot captura OI no momento da coleta (pode ser nulo se coletado
        # antes do fechamento B3). No run-time do modelo, tentamos carregar OI
        # B3 atual (hoje e D-1) e preencher lacunas nas rows antes da preparacao.
        session_date_for_oi = str(batch.get("session_date") or "")[:10]
        self._enrich_snapshot_rows_with_b3_oi(snapshot_rows, session_date_for_oi)

        option_ids = [str(row.get("option_id") or "").strip() for row in snapshot_rows if row.get("option_id")]
        latest_oi_map = self.store.load_latest_oi_map(option_ids, trade_date=batch.get("session_date"))
        signal_payload_by_option = {
            option_id: infer_signal(
                {
                    "distance_to_atm_ratio": row.get("distance_to_atm"),
                    "liquidity_weight": (float(row.get("liquidity_score") or 0.0) / 100.0),
                    "reliability_weight": 1.0 if not row.get("stale_flag") else 0.25,
                    "px_volume": row.get("PX_VOLUME") or row.get("VOLUME"),
                    "spread_pct": row.get("spread_pct"),
                    "days_to_expiry_business": row.get("days_to_expiry_business"),
                    "oi_change_pct": (latest_oi_map.get(option_id) or {}).get("oi_change_pct"),
                },
                run_config.sign_convention,
                Config.OPTIONS_MODEL_SIGNAL_THRESHOLD,
            )
            for option_id, row in (
                (str(row.get("option_id") or "").strip(), row)
                for row in snapshot_rows
                if row.get("option_id")
            )
        }

        prepared_options, preparation_diagnostics = prepare_option_inputs(
            snapshot_rows=snapshot_rows,
            market_context=market_context,
            latest_oi_map=latest_oi_map,
            run_config=run_config,
            signal_payload_by_option=signal_payload_by_option,
        )
        if not prepared_options:
            raise ValueError("No eligible options available for modeling after preparation")

        option_exposures = [compute_option_exposures(option, run_config) for option in prepared_options]
        exposure_aggregates = aggregate_exposures(option_exposures)
        strike_profiles = build_strike_profiles(option_exposures)
        grid_result = reprice_grid(prepared_options, run_config)
        pressure = analyze_pressure_curve(grid_result, run_config, market_context.spot_price)
        summary = build_operational_output(
            underlying_security=underlying_security,
            market_context=market_context,
            run_config=run_config,
            exposures=exposure_aggregates,
            pressure=pressure,
            option_exposures=option_exposures,
        )
        dealer_inference = build_dealer_inference(option_exposures, summary, pressure)
        session_date_text = str(batch.get("session_date") or "").strip()
        oi_history_rows: list[dict[str, Any]] = []
        if session_date_text:
            try:
                session_date_dt = datetime.fromisoformat(session_date_text[:10])
                start_date = (session_date_dt - timedelta(days=Config.OPTIONS_MODEL_GAMMA_FLIP_LOOKBACK_DAYS)).date().isoformat()
                oi_history_rows = self.store.list_oi_history(
                    underlying_security=underlying_security,
                    start_date=start_date,
                    end_date=session_date_text[:10],
                    limit=max(len(prepared_options) * max(Config.OPTIONS_MODEL_GAMMA_FLIP_LOOKBACK_DAYS, 1) * 2, 5000),
                )
            except Exception:
                logger.exception("Failed to load options OI history for gamma flip analytics")
        gamma_flip_history = build_gamma_flip_history(
            option_exposures,
            oi_history_rows,
            max_dates=Config.OPTIONS_MODEL_GAMMA_FLIP_MAX_DATES,
        )
        summary = build_operational_output(
            underlying_security=underlying_security,
            market_context=market_context,
            run_config=run_config,
            exposures=exposure_aggregates,
            pressure=pressure,
            option_exposures=option_exposures,
            dealer_inference=dealer_inference,
        )
        range_projection = build_range_projection(
            underlying_security=underlying_security,
            market_context=market_context,
            prepared_options=[asdict(option) for option in prepared_options],
            option_exposures=option_exposures,
            summary=summary,
            dealer_inference=dealer_inference,
            pressure=pressure,
        )

        captured_at = datetime.now(timezone.utc).isoformat()
        run_id = hashlib.sha1(
            f"{underlying_security}|{batch.get('batch_key')}|{captured_at}|{run_config.sign_convention}".encode("utf-8")
        ).hexdigest()
        payload = {
            "run_id": run_id,
            "captured_at": captured_at,
            "session_date": str(batch.get("session_date") or captured_at[:10]),
            "underlying_security": underlying_security,
            "source": {
                "universe_tier": batch.get("universe_tier"),
                "batch_id": batch.get("batch_id"),
                "batch_key": batch.get("batch_key"),
                "captured_at": batch.get("captured_at"),
                "row_count": len(snapshot_rows),
            },
            "config": {
                "sign_convention": run_config.sign_convention,
                "grid_range_pct": run_config.grid_range_pct,
                "grid_points": run_config.grid_points,
                "gex_weight": run_config.gex_weight,
                "vex_weight": run_config.vex_weight,
                "cex_weight": run_config.cex_weight,
                "option_multiplier": run_config.option_multiplier,
                "win_point_value": run_config.win_point_value,
                "min_time_years": run_config.min_time_years,
                "vol_epsilon": run_config.vol_epsilon,
                "time_epsilon_days": run_config.time_epsilon_days,
            },
            "market_context": {
                "spot_price": market_context.spot_price,
                "spot_security": market_context.spot_security,
                "forward_price": market_context.forward_price,
                "forward_security": market_context.forward_security,
                "future_basis_points": market_context.future_basis_points,
                "future_basis_pct": market_context.future_basis_pct,
                "dividend_proxy_level": market_context.dividend_proxy_level,
                "dividend_security": market_context.dividend_security,
                "rate_curve_points": market_context.rate_curve_points,
                "sources": market_context.sources,
            },
            "diagnostics": {
                **preparation_diagnostics,
                "prepared_count": len(prepared_options),
                "option_exposure_count": len(option_exposures),
            },
            "summary": summary,
            "aggregates": exposure_aggregates,
            "strike_profiles": strike_profiles,
            "gamma_flip_history": gamma_flip_history,
            "dealer_inference": dealer_inference,
            "range_projection": range_projection,
            "prepared_options": [asdict(option) for option in prepared_options],
            "option_exposures": option_exposures,
            "grid": grid_result,
            "pressure": pressure,
        }
        payload["daily_insights"] = self.daily_insights.get_or_create(
            underlying_security=underlying_security,
            trade_date=payload["session_date"],
            sign_convention=run_config.sign_convention,
            summary=summary,
            pressure=pressure,
            dealer_inference=dealer_inference,
            strike_profiles=strike_profiles,
            gamma_flip_history=gamma_flip_history,
        )
        if persist:
            persisted = self.store.write_model_run(payload)
            payload["persisted"] = persisted
        return payload

    def _enrich_snapshot_rows_with_b3_oi(
        self,
        snapshot_rows: list[dict[str, Any]],
        session_date: str,
    ) -> None:
        """
        Preenche campos OPEN_INT / OPT_OPEN_INTEREST nas snapshot_rows que
        ainda estao nulos, usando dados B3 carregados em tempo de execucao.

        O OI B3 e coletado apos o fechamento do mercado; snapshots capturados
        durante o pregao nao terao OI. Ao rodar o modelo depois do fechamento,
        este metodo garante que OI atual (ou D-1) seja usado.

        Parametros
        ----------
        snapshot_rows : list[dict]
            Linhas de snapshot a serem modificadas IN-PLACE.
        session_date : str
            Data de sessao ('YYYY-MM-DD'). Usada como referencia para busca de OI.
        """
        if not snapshot_rows:
            return

        # Verifica se alguma row realmente precisa de OI
        missing_oi = [
            row for row in snapshot_rows
            if row.get("OPEN_INT") is None and row.get("OPT_OPEN_INTEREST") is None
        ]
        if not missing_oi:
            return

        # Tenta carregar OI B3 para session_date e, se vazio, para D-1
        b3_oi_map: dict[str, float] = {}
        dates_to_try: list[str] = []
        if session_date:
            dates_to_try.append(session_date)
            try:
                from datetime import date as _date  # noqa: PLC0415
                from datetime import timedelta as _td
                d = _date.fromisoformat(session_date)
                # Volta ate 5 dias uteis para encontrar dados B3 disponiveis
                for _ in range(5):
                    d -= _td(days=1)
                    while d.weekday() >= 5:   # pula fins de semana
                        d -= _td(days=1)
                    dates_to_try.append(d.isoformat())
            except Exception:
                pass

        for dt in dates_to_try:
            rows = self.store.load_b3_oi_rows(dt)
            if rows:
                for b3row in rows:
                    sym = str(b3row.get("symbol") or "").strip()
                    oi_val = b3row.get("oi_total")
                    if sym and oi_val is not None:
                        b3_oi_map[sym] = float(oi_val)
                        # Normaliza para uppercase para comparacao case-insensitive
                        b3_oi_map[sym.upper()] = float(oi_val)
                logger.debug(
                    "Enrich OI B3: %d simbolos carregados de %s para preencher %d rows sem OI",
                    len(rows), dt, len(missing_oi),
                )
                break  # usa apenas a data mais recente disponivel

        if not b3_oi_map:
            logger.debug(
                "Enrich OI B3: sem dados B3 disponiveis para %s (tentei %d datas); OI permanece nulo.",
                session_date, len(dates_to_try),
            )
            return

        # Injeta OI nas rows com campo nulo, usando bloomberg_ticker como chave
        patched = 0
        for row in missing_oi:
            bticker = str(row.get("bloomberg_ticker") or "").strip()
            if not bticker:
                continue
            oi_val = b3_oi_map.get(bticker) or b3_oi_map.get(bticker.upper())
            if oi_val is not None:
                row["OPEN_INT"] = oi_val
                row["OPT_OPEN_INTEREST"] = oi_val
                patched += 1

        if patched:
            logger.info(
                "Enrich OI B3: %d/%d rows sem OI preenchidas com dados B3.",
                patched, len(missing_oi),
            )

    def read_latest_run(
        self,
        underlying_security: str,
        universe_tier: str | None = None,
    ) -> dict[str, Any] | None:
        return self.store.read_latest_model_run(underlying_security, universe_tier=universe_tier)

    def read_run(self, run_id: str) -> dict[str, Any] | None:
        return self.store.read_model_run(run_id)
