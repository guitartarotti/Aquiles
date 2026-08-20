from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

from .flow_replicator_store import FlowReplicatorStore, _safe_float

SESSION_TIMEZONE = ZoneInfo("America/Sao_Paulo")
SESSION_START = dt_time(hour=9, minute=0)
SESSION_END = dt_time(hour=18, minute=30)


STYLE_META = {
    "aggressive_taker": {
        "label": "CTA agressivo",
        "description": "montagem dominante na agressao, com urgencia de execucao e pouca paciencia para absorcao",
    },
    "passive_builder": {
        "label": "Builder passivo",
        "description": "montagem sustentada por maker flow, sugerindo paciencia e defesa de preco",
    },
    "rlp_recycler": {
        "label": "RLP recycler",
        "description": "parcela relevante da execucao via RLP, com footprint menos exposto na agressao direta",
    },
    "steady_inventory_builder": {
        "label": "Inventory builder",
        "description": "curva limpa e consistente de posicao, com cara de robo de montagem programada",
    },
    "mixed_executor": {
        "label": "Execucao mista",
        "description": "atividade relevante, mas com assinatura menos uniforme entre agressao, maker e cadence",
    },
}


@dataclass(slots=True)
class DetectionThresholds:
    noise_floor: float
    continuation_threshold: float
    start_threshold: float
    reversal_threshold: float
    min_total_qty: float
    max_idle_buckets: int


class FlowActivityRadarService:
    def __init__(self, store: FlowReplicatorStore | None = None) -> None:
        self.store = store or FlowReplicatorStore()

    def build_dashboard(
        self,
        *,
        ticker: str | None = None,
        session_date: str | date | None = None,
        bucket_minutes: int = 1,
        top_runs: int = 24,
    ) -> dict[str, Any]:
        resolved_bucket_minutes = max(1, min(int(bucket_minutes or 1), 15))
        latest_snapshot = self.store.latest_snapshot(ticker) or {}
        resolved_ticker = str(
            ticker
            or latest_snapshot.get("ticker")
            or ""
        ).strip()
        if not resolved_ticker:
            return {
                "ok": False,
                "message": "Flow replicator ainda sem ticker ativo.",
                "ticker": None,
                "session": {},
                "summary": {},
                "reader": {},
                "detections": [],
                "session_flow": [],
            }

        resolved_session_date = self._resolve_session_date(session_date, latest_snapshot)
        session_meta = self._build_session_meta(
            session_date=resolved_session_date,
            bucket_minutes=resolved_bucket_minutes,
        )
        minute_rows = self._load_minute_buckets(
            ticker=resolved_ticker,
            session_meta=session_meta,
        )
        if not minute_rows:
            return {
                "ok": False,
                "message": "Sem buckets de fluxo para a sessao selecionada.",
                "ticker": resolved_ticker,
                "session": session_meta,
                "source": {
                    "latest_snapshot_at": latest_snapshot.get("received_at"),
                    "vwap": latest_snapshot.get("vwap"),
                    "rlp_vwap": latest_snapshot.get("rlp_vwap"),
                    "agent_count": latest_snapshot.get("agent_count"),
                },
                "summary": {
                    "active_runs": 0,
                    "cooling_runs": 0,
                    "inactive_runs": 0,
                    "dominant_side": "neutral",
                },
                "reader": {
                    "headline": "Ainda sem montagem detectada",
                    "summary": "A sessao nao tem dados suficientes de fluxo por participante para montar o radar.",
                    "bullets": [],
                    "tone": "neutral",
                },
                "detections": [],
                "session_flow": [],
            }

        context = self._build_agent_context(
            minute_rows=minute_rows,
            session_meta=session_meta,
        )
        session_meta["latest_bucket_index"] = context["latest_bucket_index"]
        session_meta["latest_capture_at"] = context["latest_capture_at"]
        session_meta["latest_bucket_label"] = self._minute_label(
            session_meta,
            context["latest_bucket_index"],
        )

        thresholds = self._derive_thresholds(
            values=context["impact_distribution"],
            bucket_minutes=resolved_bucket_minutes,
        )
        detections: list[dict[str, Any]] = []
        for agent in context["agents"].values():
            detections.extend(
                self._detect_agent_runs(
                    agent=agent,
                    session_meta=session_meta,
                    thresholds=thresholds,
                )
            )

        detections = self._merge_directional_tracks(detections)
        detections.sort(
            key=lambda item: (
                -(float(item.get("ranking_score") or 0.0) * self._status_weight(item.get("status"))),
                -float(item.get("holding_score") or 0.0),
                -float(item.get("absolute_delta_contracts") or 0.0),
                self._status_rank(item.get("status")),
            )
        )
        detections = detections[: max(1, min(int(top_runs or 24), 60))]

        summary = self._build_summary(
            detections=detections,
            session_meta=session_meta,
        )
        reader = self._build_reader(
            detections=detections,
            summary=summary,
            session_meta=session_meta,
        )
        session_flow = self._build_session_flow(
            detections=detections,
            session_meta=session_meta,
        )
        return {
            "ok": True,
            "ticker": resolved_ticker,
            "generated_at": datetime.now(SESSION_TIMEZONE).isoformat(),
            "session": session_meta,
            "source": {
                "latest_snapshot_at": latest_snapshot.get("received_at"),
                "vwap": latest_snapshot.get("vwap"),
                "rlp_vwap": latest_snapshot.get("rlp_vwap"),
                "agent_count": latest_snapshot.get("agent_count"),
            },
            "thresholds": {
                "noise_floor": thresholds.noise_floor,
                "continuation_threshold": thresholds.continuation_threshold,
                "start_threshold": thresholds.start_threshold,
                "reversal_threshold": thresholds.reversal_threshold,
                "min_total_qty": thresholds.min_total_qty,
                "max_idle_buckets": thresholds.max_idle_buckets,
            },
            "summary": summary,
            "reader": reader,
            "detections": detections,
            "session_flow": session_flow,
        }

    def _merge_directional_tracks(
        self,
        detections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for detection in detections:
            agent_code = str(detection.get("agent_code") or "").strip()
            side = str(detection.get("side") or "").strip()
            if not agent_code or not side:
                continue
            grouped.setdefault((agent_code, side), []).append(detection)

        merged: list[dict[str, Any]] = []
        for runs in grouped.values():
            ordered_runs = sorted(
                runs,
                key=self._directional_track_priority,
                reverse=True,
            )
            primary_source = ordered_runs[0]
            primary = dict(primary_source)
            primary["primary_run_id"] = primary_source.get("run_id")
            primary["run_id"] = f"{primary.get('agent_code')}:{primary.get('side')}"

            historical_runs: list[dict[str, Any]] = []
            for run in ordered_runs[1:]:
                if str(run.get("status") or "") != "inactive":
                    continue
                historical_runs.append(self._build_history_run(run))

            primary["history_runs"] = historical_runs
            primary["history_runs_count"] = len(historical_runs)
            primary["related_runs_count"] = len(ordered_runs)
            primary["has_live_projection"] = str(primary.get("status") or "") != "inactive"
            if not primary["has_live_projection"]:
                primary = self._strip_projection(primary)
            merged.append(primary)
        return merged

    def _resolve_session_date(
        self,
        session_date: str | date | None,
        latest_snapshot: dict[str, Any],
    ) -> date:
        if isinstance(session_date, date):
            return session_date
        if isinstance(session_date, str) and session_date.strip():
            try:
                return date.fromisoformat(session_date.strip())
            except ValueError:
                pass
        latest_iso = str(latest_snapshot.get("received_at") or "").strip()
        if latest_iso:
            try:
                parsed = datetime.fromisoformat(latest_iso.replace("Z", "+00:00"))
                return parsed.astimezone(SESSION_TIMEZONE).date()
            except Exception:
                pass
        return datetime.now(SESSION_TIMEZONE).date()

    def _build_session_meta(
        self,
        *,
        session_date: date,
        bucket_minutes: int,
    ) -> dict[str, Any]:
        start_local = datetime.combine(session_date, SESSION_START, tzinfo=SESSION_TIMEZONE)
        end_local = datetime.combine(session_date, SESSION_END, tzinfo=SESSION_TIMEZONE)
        session_minutes = int((end_local - start_local).total_seconds() // 60)
        total_buckets = (session_minutes // bucket_minutes) + 1
        return {
            "date": session_date.isoformat(),
            "timezone": "America/Sao_Paulo",
            "bucket_minutes": bucket_minutes,
            "start_at": start_local.isoformat(),
            "end_at": end_local.isoformat(),
            "start_epoch": int(start_local.timestamp()),
            "end_epoch": int(end_local.timestamp()),
            "total_buckets": total_buckets,
            "session_minutes": session_minutes,
            "latest_bucket_index": 0,
            "latest_capture_at": None,
            "latest_bucket_label": self._minute_label(
                {
                    "start_at": start_local.isoformat(),
                    "bucket_minutes": bucket_minutes,
                },
                0,
            ),
        }

    def _load_minute_buckets(
        self,
        *,
        ticker: str,
        session_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self.store.ensure_schema()
        bucket_seconds = int(session_meta["bucket_minutes"]) * 60
        with self.store._connect() as conn:  # internal service access on same store
            rows = conn.execute(
                """
                SELECT
                    CAST(received_at_epoch / ? AS INTEGER) * ? AS bucket_epoch,
                    agent_code,
                    broker_name,
                    SUM(COALESCE(delta_qty, 0)) AS delta_qty,
                    SUM(COALESCE(delta_buy_quantity, 0)) AS delta_buy_quantity,
                    SUM(COALESCE(delta_sell_quantity, 0)) AS delta_sell_quantity,
                    SUM(COALESCE(delta_agression_balance, 0)) AS delta_agression_balance,
                    SUM(COALESCE(delta_maker_balance, 0)) AS delta_maker_balance,
                    SUM(COALESCE(delta_rlp_balance, 0)) AS delta_rlp_balance,
                    COUNT(*) AS sample_count,
                    MIN(received_at_epoch) AS first_epoch,
                    MAX(received_at_epoch) AS last_epoch
                FROM flow_agent_deltas
                WHERE ticker = ?
                  AND received_at_epoch >= ?
                  AND received_at_epoch <= ?
                GROUP BY bucket_epoch, agent_code, broker_name
                ORDER BY bucket_epoch, ABS(SUM(COALESCE(delta_qty, 0))) DESC
                """,
                (
                    bucket_seconds,
                    bucket_seconds,
                    ticker,
                    session_meta["start_epoch"],
                    session_meta["end_epoch"],
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def _build_agent_context(
        self,
        *,
        minute_rows: list[dict[str, Any]],
        session_meta: dict[str, Any],
    ) -> dict[str, Any]:
        bucket_minutes = int(session_meta["bucket_minutes"])
        bucket_seconds = bucket_minutes * 60
        agents: dict[str, dict[str, Any]] = {}
        impact_distribution: list[float] = []
        latest_bucket_index = 0
        latest_capture_at = None
        for row in minute_rows:
            bucket_epoch = int(_safe_float(row.get("bucket_epoch")) or 0)
            minute_index = int((bucket_epoch - int(session_meta["start_epoch"])) // bucket_seconds)
            if minute_index < 0 or minute_index >= int(session_meta["total_buckets"]):
                continue
            latest_bucket_index = max(latest_bucket_index, minute_index)
            last_epoch = _safe_float(row.get("last_epoch"))
            if last_epoch is not None:
                candidate = datetime.fromtimestamp(last_epoch, tz=SESSION_TIMEZONE).isoformat()
                if latest_capture_at is None or candidate > latest_capture_at:
                    latest_capture_at = candidate
            agent_code = str(row.get("agent_code") or "").strip()
            if not agent_code:
                continue
            broker_name = str(
                self.store.resolve_broker_name(agent_code, row.get("broker_name"))
                or f"Broker {agent_code}"
            ).strip()
            point = {
                "minute_index": minute_index,
                "label": self._minute_label(session_meta, minute_index),
                "timestamp": self._minute_timestamp(session_meta, minute_index),
                "delta_qty": float(_safe_float(row.get("delta_qty")) or 0.0),
                "delta_buy_quantity": float(_safe_float(row.get("delta_buy_quantity")) or 0.0),
                "delta_sell_quantity": float(_safe_float(row.get("delta_sell_quantity")) or 0.0),
                "delta_agression_balance": float(_safe_float(row.get("delta_agression_balance")) or 0.0),
                "delta_maker_balance": float(_safe_float(row.get("delta_maker_balance")) or 0.0),
                "delta_rlp_balance": float(_safe_float(row.get("delta_rlp_balance")) or 0.0),
                "sample_count": int(_safe_float(row.get("sample_count")) or 0),
            }
            agent = agents.setdefault(
                agent_code,
                {
                    "agent_code": agent_code,
                    "broker_name": broker_name,
                    "points": {},
                    "totals": {
                        "delta_qty": 0.0,
                        "delta_agression_balance": 0.0,
                        "delta_maker_balance": 0.0,
                        "delta_rlp_balance": 0.0,
                    },
                },
            )
            agent["points"][minute_index] = point
            agent["totals"]["delta_qty"] += point["delta_qty"]
            agent["totals"]["delta_agression_balance"] += point["delta_agression_balance"]
            agent["totals"]["delta_maker_balance"] += point["delta_maker_balance"]
            agent["totals"]["delta_rlp_balance"] += point["delta_rlp_balance"]
            if abs(point["delta_qty"]) > 0:
                impact_distribution.append(abs(point["delta_qty"]))
        return {
            "agents": agents,
            "impact_distribution": impact_distribution,
            "latest_bucket_index": latest_bucket_index,
            "latest_capture_at": latest_capture_at,
        }

    def _derive_thresholds(
        self,
        *,
        values: list[float],
        bucket_minutes: int,
    ) -> DetectionThresholds:
        resolved = sorted(value for value in values if math.isfinite(value) and value > 0)
        if not resolved:
            base = 100.0 * bucket_minutes
            return DetectionThresholds(
                noise_floor=max(16.0, base * 0.25),
                continuation_threshold=max(38.0, base * 0.55),
                start_threshold=max(90.0, base),
                reversal_threshold=max(80.0, base * 0.8),
                min_total_qty=max(240.0, base * 2.5),
                max_idle_buckets=4,
            )
        p50 = self._percentile(resolved, 0.50)
        p65 = self._percentile(resolved, 0.65)
        p75 = self._percentile(resolved, 0.75)
        p85 = self._percentile(resolved, 0.85)
        noise_floor = max(12.0 * bucket_minutes, p50 * 0.38)
        continuation_threshold = max(noise_floor * 1.35, p65 * 0.62, 34.0 * bucket_minutes)
        start_threshold = max(continuation_threshold * 1.65, p75 * 0.92, 85.0 * bucket_minutes)
        reversal_threshold = max(start_threshold * 0.82, p85 * 0.72, 72.0 * bucket_minutes)
        min_total_qty = max(start_threshold * 2.15, p75 * 3.2, 220.0 * bucket_minutes)
        return DetectionThresholds(
            noise_floor=noise_floor,
            continuation_threshold=continuation_threshold,
            start_threshold=start_threshold,
            reversal_threshold=reversal_threshold,
            min_total_qty=min_total_qty,
            max_idle_buckets=max(3, min(6, round(4 / bucket_minutes) if bucket_minutes > 1 else 4)),
        )

    def _detect_agent_runs(
        self,
        *,
        agent: dict[str, Any],
        session_meta: dict[str, Any],
        thresholds: DetectionThresholds,
    ) -> list[dict[str, Any]]:
        latest_index = int(session_meta["latest_bucket_index"])
        dense = [
            agent["points"].get(
                index,
                {
                    "minute_index": index,
                    "label": self._minute_label(session_meta, index),
                    "timestamp": self._minute_timestamp(session_meta, index),
                    "delta_qty": 0.0,
                    "delta_buy_quantity": 0.0,
                    "delta_sell_quantity": 0.0,
                    "delta_agression_balance": 0.0,
                    "delta_maker_balance": 0.0,
                    "delta_rlp_balance": 0.0,
                    "sample_count": 0,
                },
            )
            for index in range(latest_index + 1)
        ]
        raw = [float(point.get("delta_qty") or 0.0) for point in dense]
        if not any(abs(value) >= thresholds.noise_floor for value in raw):
            return []
        smoothed = self._ewma(raw, alpha=0.34)
        runs: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        index = 0
        while index < len(dense):
            if current is None:
                current = self._maybe_start_run(
                    dense=dense,
                    raw=raw,
                    smoothed=smoothed,
                    index=index,
                    thresholds=thresholds,
                )
                index += 1
                continue

            raw_value = raw[index]
            side_hint = self._sign(
                smoothed[index] if abs(smoothed[index]) >= thresholds.noise_floor else raw_value
            )
            strength = max(
                abs(raw_value),
                abs(smoothed[index]) * 1.35,
                abs(sum(raw[max(0, index - 2):index + 1])),
            )
            current["end_index"] = index
            if side_hint == current["side"] and strength >= thresholds.continuation_threshold * 0.55:
                current["last_active_index"] = index
                current["opposite_streak"] = 0
                current["peak_strength"] = max(current["peak_strength"], strength)
                index += 1
                continue

            if strength < thresholds.noise_floor:
                if index - int(current["last_active_index"]) > thresholds.max_idle_buckets:
                    run = self._materialize_run(
                        agent=agent,
                        dense=dense,
                        start_index=int(current["start_index"]),
                        last_active_index=int(current["last_active_index"]),
                        original_side=int(current["side"]),
                        session_meta=session_meta,
                        thresholds=thresholds,
                        run_scope="detected_run",
                    )
                    if run:
                        runs.append(run)
                    current = None
                    continue
                index += 1
                continue

            if side_hint == -int(current["side"]) and strength >= thresholds.reversal_threshold:
                run = self._materialize_run(
                    agent=agent,
                    dense=dense,
                    start_index=int(current["start_index"]),
                    last_active_index=int(current["last_active_index"]),
                    original_side=int(current["side"]),
                    session_meta=session_meta,
                    thresholds=thresholds,
                    run_scope="detected_run",
                )
                if run:
                    runs.append(run)
                current = self._maybe_start_run(
                    dense=dense,
                    raw=raw,
                    smoothed=smoothed,
                    index=index,
                    thresholds=thresholds,
                )
                index += 1
                continue

            if side_hint == -int(current["side"]) and strength >= thresholds.noise_floor:
                current["opposite_streak"] += 1
                if current["opposite_streak"] >= 3:
                    run = self._materialize_run(
                        agent=agent,
                        dense=dense,
                        start_index=int(current["start_index"]),
                        last_active_index=int(current["last_active_index"]),
                        original_side=int(current["side"]),
                        session_meta=session_meta,
                        thresholds=thresholds,
                        run_scope="detected_run",
                    )
                    if run:
                        runs.append(run)
                    current = None
                    continue
            else:
                current["opposite_streak"] = 0
            index += 1

        if current is not None:
            run = self._materialize_run(
                agent=agent,
                dense=dense,
                start_index=int(current["start_index"]),
                last_active_index=int(current["last_active_index"]),
                original_side=int(current["side"]),
                session_meta=session_meta,
                thresholds=thresholds,
                run_scope="detected_run",
            )
            if run:
                runs.append(run)
        fallback = self._build_structural_fallback_run(
            agent=agent,
            dense=dense,
            runs=runs,
            session_meta=session_meta,
            thresholds=thresholds,
        )
        if fallback:
            runs.append(fallback)
        existing_sides = {str(run.get("side") or "").strip() for run in runs}
        runs.extend(
            self._detect_directional_shape_runs(
                agent=agent,
                dense=dense,
                session_meta=session_meta,
                thresholds=thresholds,
                existing_sides=existing_sides,
            )
        )
        return runs

    def _build_structural_fallback_run(
        self,
        *,
        agent: dict[str, Any],
        dense: list[dict[str, Any]],
        runs: list[dict[str, Any]],
        session_meta: dict[str, Any],
        thresholds: DetectionThresholds,
    ) -> dict[str, Any] | None:
        total_qty = float(agent.get("totals", {}).get("delta_qty") or 0.0)
        abs_total_qty = abs(total_qty)
        if abs_total_qty < max(thresholds.min_total_qty * 3.5, 4_500.0):
            return None
        side = self._sign(total_qty)
        covered = max(
            (
                abs(float(item.get("delta_contracts") or 0.0))
                for item in runs
                if self._sign(float(item.get("delta_contracts") or 0.0)) == side
            ),
            default=0.0,
        )
        if covered >= abs_total_qty * 0.58:
            return None
        active_indices = [
            index
            for index, point in enumerate(dense)
            if abs(float(point.get("delta_qty") or 0.0)) >= thresholds.noise_floor
        ]
        if len(active_indices) < 6:
            return None
        fallback = self._materialize_run(
            agent=agent,
            dense=dense,
            start_index=active_indices[0],
            last_active_index=active_indices[-1],
            original_side=side,
            session_meta=session_meta,
            thresholds=thresholds,
            run_scope="session_builder",
        )
        if not fallback:
            return None
        fallback["impact_score"] = float(fallback.get("impact_score") or 0.0) * 1.12
        return fallback

    def _detect_directional_shape_runs(
        self,
        *,
        agent: dict[str, Any],
        dense: list[dict[str, Any]],
        session_meta: dict[str, Any],
        thresholds: DetectionThresholds,
        existing_sides: set[str],
    ) -> list[dict[str, Any]]:
        raw = [float(point.get("delta_qty") or 0.0) for point in dense]
        net_total = float(agent.get("totals", {}).get("delta_qty") or 0.0)
        dominant_side = self._sign(net_total)
        if dominant_side == 0 or abs(net_total) < max(thresholds.min_total_qty * 3.5, 4_500.0):
            return []

        shape_runs: list[dict[str, Any]] = []
        for side_name, side in (("buy", 1), ("sell", -1)):
            if side != dominant_side:
                continue
            if side_name in existing_sides:
                continue
            candidate = self._best_directional_shape_window(
                raw=raw,
                side=side,
                thresholds=thresholds,
                bucket_minutes=int(session_meta["bucket_minutes"]),
            )
            if not candidate:
                continue
            extended_end_index = self._extend_directional_shape_tail(
                raw=raw,
                side=side,
                start_index=int(candidate["start_index"]),
                end_index=int(candidate["end_index"]),
                retain_ratio=0.82,
            )
            run = self._materialize_run(
                agent=agent,
                dense=dense,
                start_index=int(candidate["start_index"]),
                last_active_index=extended_end_index,
                original_side=side,
                session_meta=session_meta,
                thresholds=thresholds,
                run_scope="shape_builder",
            )
            if not run:
                continue
            run["shape_window_score"] = float(candidate["score"])
            run["directional_aligned_share"] = float(candidate["aligned_share"])
            run["directional_window_total"] = float(candidate["total"])
            shape_runs.append(run)
        return shape_runs

    def _best_directional_shape_window(
        self,
        *,
        raw: list[float],
        side: int,
        thresholds: DetectionThresholds,
        bucket_minutes: int,
    ) -> dict[str, Any] | None:
        if len(raw) < 12:
            return None
        min_window_bars = max(12, math.ceil(20 / max(bucket_minutes, 1)))
        max_window_bars = max(min_window_bars, min(len(raw), math.ceil(210 / max(bucket_minutes, 1))))
        min_total = max(thresholds.min_total_qty * 2.0, 2_500.0)
        best: dict[str, Any] | None = None
        start_gate = max(thresholds.continuation_threshold * 1.1, thresholds.start_threshold * 0.38)
        candidate_starts = [
            index
            for index, value in enumerate(raw[: max(0, len(raw) - min_window_bars + 1)])
            if (side * value) >= start_gate
        ]
        if not candidate_starts:
            return None

        for start_index in candidate_starts:
            transformed_total = 0.0
            aligned_sum = 0.0
            abs_sum = 0.0
            cumulative: list[float] = []
            max_end_index = min(len(raw), start_index + max_window_bars)
            for end_index in range(start_index, max_end_index):
                value = raw[end_index]
                transformed = side * value
                transformed_total += transformed
                cumulative.append(transformed_total)
                abs_sum += abs(value)
                if transformed > 0:
                    aligned_sum += transformed
                length = end_index - start_index + 1
                if length < min_window_bars or transformed_total < min_total or abs_sum <= 0:
                    continue
                _, fit_r2 = self._linear_fit(cumulative)
                aligned_share = aligned_sum / abs_sum
                if fit_r2 < 0.82 or aligned_share < 0.68:
                    continue
                score = (
                    transformed_total
                    * max(fit_r2, 0.0)
                    * max(aligned_share, 0.0)
                    / (length ** 0.18)
                )
                if best is None or score > float(best["score"]):
                    best = {
                        "start_index": start_index,
                        "end_index": end_index,
                        "score": score,
                        "aligned_share": aligned_share,
                        "total": transformed_total,
                    }
        return best

    @staticmethod
    def _extend_directional_shape_tail(
        *,
        raw: list[float],
        side: int,
        start_index: int,
        end_index: int,
        retain_ratio: float,
    ) -> int:
        if start_index < 0 or end_index < start_index or end_index >= len(raw):
            return end_index
        transformed_running = 0.0
        cumulative_totals: list[float] = []
        for value in raw[start_index:]:
            transformed_running += side * value
            cumulative_totals.append(transformed_running)
        relative_end_index = end_index - start_index
        if relative_end_index < 0 or relative_end_index >= len(cumulative_totals):
            return end_index
        peak_total = cumulative_totals[relative_end_index]
        threshold_total = peak_total * max(min(retain_ratio, 0.98), 0.5)
        furthest_index = end_index
        for offset in range(relative_end_index, len(cumulative_totals)):
            if cumulative_totals[offset] >= threshold_total:
                furthest_index = start_index + offset
        return furthest_index

    def _maybe_start_run(
        self,
        *,
        dense: list[dict[str, Any]],
        raw: list[float],
        smoothed: list[float],
        index: int,
        thresholds: DetectionThresholds,
    ) -> dict[str, Any] | None:
        recent = raw[max(0, index - 2):index + 1]
        recent_sum = sum(recent)
        side = self._sign(smoothed[index] if abs(smoothed[index]) >= thresholds.noise_floor else recent_sum)
        if side == 0:
            return None
        consistency = self._directional_consistency(
            values=recent,
            side=side,
            noise_floor=thresholds.noise_floor,
        )
        strength = max(abs(raw[index]), abs(smoothed[index]) * 1.35, abs(recent_sum))
        if not (
            strength >= thresholds.start_threshold
            or (consistency >= 0.66 and abs(recent_sum) >= thresholds.start_threshold * 0.72)
        ):
            return None
        return {
            "start_index": index,
            "last_active_index": index,
            "end_index": index,
            "side": side,
            "opposite_streak": 0,
            "peak_strength": strength,
        }

    def _materialize_run(
        self,
        *,
        agent: dict[str, Any],
        dense: list[dict[str, Any]],
        start_index: int,
        last_active_index: int,
        original_side: int,
        session_meta: dict[str, Any],
        thresholds: DetectionThresholds,
        run_scope: str = "detected_run",
    ) -> dict[str, Any] | None:
        if last_active_index < start_index:
            return None
        segment = dense[start_index:last_active_index + 1]
        total_qty = sum(float(point.get("delta_qty") or 0.0) for point in segment)
        side = self._sign(total_qty) or original_side
        active_points = [
            point
            for point in segment
            if abs(float(point.get("delta_qty") or 0.0)) >= thresholds.noise_floor
        ]
        abs_total_qty = abs(total_qty)
        if abs_total_qty < thresholds.min_total_qty and len(active_points) < 5:
            return None

        cumulative = 0.0
        cumulative_aggression = 0.0
        cumulative_maker = 0.0
        cumulative_rlp = 0.0
        chart: list[dict[str, Any]] = []
        for point in segment:
            cumulative += float(point.get("delta_qty") or 0.0)
            cumulative_aggression += float(point.get("delta_agression_balance") or 0.0)
            cumulative_maker += float(point.get("delta_maker_balance") or 0.0)
            cumulative_rlp += float(point.get("delta_rlp_balance") or 0.0)
            chart.append(
                {
                    "minute_index": int(point["minute_index"]),
                    "label": point["label"],
                    "timestamp": point["timestamp"],
                    "delta_qty": float(point.get("delta_qty") or 0.0),
                    "delta_agression_balance": float(point.get("delta_agression_balance") or 0.0),
                    "delta_maker_balance": float(point.get("delta_maker_balance") or 0.0),
                    "delta_rlp_balance": float(point.get("delta_rlp_balance") or 0.0),
                    "cumulative_qty": cumulative,
                    "cumulative_aggression": cumulative_aggression,
                }
            )

        cumulative_series = [float(point["cumulative_qty"]) for point in chart]
        full_slope, fit_r2 = self._linear_fit(cumulative_series)
        recent_series = cumulative_series[-min(len(cumulative_series), 8):]
        recent_slope, recent_r2 = self._linear_fit(recent_series)
        bucket_minutes = int(session_meta["bucket_minutes"])
        projected_slope_per_bucket = side * max(0.0, side * ((0.40 * full_slope) + (0.60 * recent_slope)))
        pace_per_minute = projected_slope_per_bucket / max(bucket_minutes, 1)
        pace_per_hour = pace_per_minute * 60.0
        gap_minutes = max(
            0,
            (int(session_meta["latest_bucket_index"]) - int(last_active_index)) * bucket_minutes,
        )
        if gap_minutes <= bucket_minutes * 2 and side * projected_slope_per_bucket > thresholds.continuation_threshold * 0.22:
            status = "active"
        elif gap_minutes <= bucket_minutes * 8:
            status = "cooling"
        else:
            status = "inactive"

        reference_index = int(last_active_index)
        remaining_minutes = max(
            0,
            (int(session_meta["total_buckets"]) - 1 - reference_index) * bucket_minutes,
        )
        projected_remaining_contracts = pace_per_minute * remaining_minutes
        if side * projected_remaining_contracts < 0:
            projected_remaining_contracts = 0.0
        projected_total_contracts = total_qty + projected_remaining_contracts

        active_abs = [abs(float(point.get("delta_qty") or 0.0)) for point in active_points]
        persistence = abs_total_qty / max(sum(active_abs), 1.0)
        regularity = self._regularity_score(active_abs)
        cadence = self._cadence_score([int(point["minute_index"]) for point in active_points])
        max_bar_share = max(active_abs, default=0.0) / max(abs_total_qty, 1.0)
        top3_share = sum(sorted(active_abs, reverse=True)[:3]) / max(abs_total_qty, 1.0)
        sustained_linear_minutes, sustained_linear_r2 = self._best_aligned_streak_metrics(
            chart=chart,
            side=side,
            noise_floor=thresholds.noise_floor,
            bucket_minutes=bucket_minutes,
        )
        linearity_score = self._blended_linearity(
            fit_r2=fit_r2,
            recent_r2=recent_r2,
            active_minutes=len(active_points) * bucket_minutes,
        )
        holding_score = self._holding_score(
            active_minutes=len(active_points) * bucket_minutes,
            fit_r2=fit_r2,
            recent_r2=recent_r2,
            persistence=persistence,
            max_bar_share=max_bar_share,
            top3_share=top3_share,
        )
        robot_score = self._clamp(
            (
                (persistence * 42.0)
                + (regularity * 28.0)
                + (cadence * 18.0)
                + (min(len(active_points) / 16.0, 1.0) * 12.0)
            ),
            8.0,
            99.0,
        )
        confidence = self._clamp(
            (
                min(abs_total_qty / max(thresholds.min_total_qty, 1.0), 2.0) * 28.0
                + persistence * 28.0
                + max(linearity_score, 0.0) * 18.0
                + max(recent_r2, 0.0) * 10.0
                + min(len(active_points) / 12.0, 1.0) * 16.0
            ),
            14.0,
            99.0,
        )

        total_aggression = sum(float(point.get("delta_agression_balance") or 0.0) for point in segment)
        total_maker = sum(float(point.get("delta_maker_balance") or 0.0) for point in segment)
        total_rlp = sum(float(point.get("delta_rlp_balance") or 0.0) for point in segment)
        style_key = self._classify_style(
            total_qty=total_qty,
            total_aggression=total_aggression,
            total_maker=total_maker,
            total_rlp=total_rlp,
            persistence=persistence,
            active_points=len(active_points),
        )
        recent_tail = chart[-min(len(chart), 6):]
        baseline_head = chart[:-6] if len(chart) > 6 else chart
        aggression_pulse = self._pulse_ratio(
            recent=[abs(float(point.get("delta_agression_balance") or 0.0)) for point in recent_tail],
            baseline=[abs(float(point.get("delta_agression_balance") or 0.0)) for point in baseline_head],
        )
        momentum_value = recent_slope - full_slope
        momentum_side = side * momentum_value
        if side * recent_slope <= 0:
            momentum_label = "virando"
        elif momentum_side > thresholds.noise_floor * 0.15:
            momentum_label = "ganhando inclinacao"
        elif momentum_side < -thresholds.noise_floor * 0.15:
            momentum_label = "perdendo inclinacao"
        else:
            momentum_label = "estavel"

        active_minutes = len(active_points) * bucket_minutes
        elapsed_minutes = max(bucket_minutes, ((last_active_index - start_index) + 1) * bucket_minutes)
        if not self._passes_holder_filter(
            run_scope=run_scope,
            active_minutes=active_minutes,
            elapsed_minutes=elapsed_minutes,
            linearity_score=linearity_score,
            sustained_linear_minutes=sustained_linear_minutes,
            sustained_linear_r2=sustained_linear_r2,
            max_bar_share=max_bar_share,
            top3_share=top3_share,
        ):
            return None

        projection_component = min(abs(projected_remaining_contracts), abs_total_qty * 1.35)
        impact_score = (
            abs_total_qty
            + (projection_component * 0.34)
            + (abs(total_aggression) * 0.18)
            + (robot_score * 8.5)
            + (confidence * 4.0)
        )
        ranking_score = impact_score + (holding_score * 1_500.0)
        start_label = chart[0]["label"] if chart else self._minute_label(session_meta, start_index)
        last_label = chart[-1]["label"] if chart else self._minute_label(session_meta, last_active_index)
        run_id = f"{agent['agent_code']}:{start_index}:{last_active_index}:{side}"
        return {
            "run_id": run_id,
            "agent_code": agent["agent_code"],
            "broker_name": agent["broker_name"],
            "display_name": self._short_broker_name(agent["broker_name"]),
            "run_scope": run_scope,
            "run_scope_label": self._run_scope_label(run_scope),
            "side": "buy" if side > 0 else "sell",
            "status": status,
            "status_label": self._status_label(status),
            "style": {
                "key": style_key,
                "label": STYLE_META[style_key]["label"],
                "description": STYLE_META[style_key]["description"],
            },
            "start_time": chart[0]["timestamp"] if chart else self._minute_timestamp(session_meta, start_index),
            "last_active_time": chart[-1]["timestamp"] if chart else self._minute_timestamp(session_meta, last_active_index),
            "start_label": start_label,
            "last_active_label": last_label,
            "elapsed_minutes": elapsed_minutes,
            "active_minutes": active_minutes,
            "inactive_gap_minutes": gap_minutes,
            "delta_contracts": total_qty,
            "absolute_delta_contracts": abs_total_qty,
            "contracts_per_minute": pace_per_minute,
            "contracts_per_hour": pace_per_hour,
            "projected_total_contracts": projected_total_contracts,
            "projected_remaining_contracts": projected_remaining_contracts,
            "aggression_balance": total_aggression,
            "maker_balance": total_maker,
            "rlp_balance": total_rlp,
            "aggression_pulse": aggression_pulse,
            "robot_score": robot_score,
            "holding_score": holding_score,
            "confidence": confidence,
            "directional_persistence": persistence * 100.0,
            "fit_r2": fit_r2,
            "recent_fit_r2": recent_r2,
            "linearity_score": linearity_score,
            "sustained_linear_minutes": sustained_linear_minutes,
            "sustained_linear_r2": sustained_linear_r2,
            "max_bar_share": max_bar_share,
            "top3_share": top3_share,
            "momentum": {
                "label": momentum_label,
                "value": momentum_value / max(bucket_minutes, 1),
            },
            "impact_score": impact_score,
            "ranking_score": ranking_score,
            "chart": chart,
        }

    def _build_summary(
        self,
        *,
        detections: list[dict[str, Any]],
        session_meta: dict[str, Any],
    ) -> dict[str, Any]:
        active = [item for item in detections if item.get("status") == "active"]
        cooling = [item for item in detections if item.get("status") == "cooling"]
        inactive = [item for item in detections if item.get("status") == "inactive"]
        live_focus = active or cooling
        focus = live_focus or detections
        current_net = sum(float(item.get("delta_contracts") or 0.0) for item in focus[:6])
        projected_net = (
            sum(float(item.get("projected_total_contracts") or 0.0) for item in focus[:6])
            if live_focus
            else current_net
        )
        buy_count = sum(1 for item in detections if item.get("side") == "buy")
        sell_count = sum(1 for item in detections if item.get("side") == "sell")
        dominant_side = "neutral"
        if projected_net > 0:
            dominant_side = "buy"
        elif projected_net < 0:
            dominant_side = "sell"
        top_abs = [abs(float(item.get("absolute_delta_contracts") or 0.0)) for item in detections[:3]]
        concentration = 0.0
        total_abs = sum(abs(float(item.get("absolute_delta_contracts") or 0.0)) for item in detections[:8])
        if total_abs > 0:
            concentration = sum(top_abs) / total_abs
        robot_mean = statistics.fmean(
            [float(item.get("robot_score") or 0.0) for item in focus[:6]]
        ) if focus else 0.0
        holding_mean = statistics.fmean(
            [float(item.get("holding_score") or 0.0) for item in focus[:6]]
        ) if focus else 0.0
        confidence_mean = statistics.fmean(
            [float(item.get("confidence") or 0.0) for item in focus[:6]]
        ) if focus else 0.0
        active_projection = sum(float(item.get("projected_remaining_contracts") or 0.0) for item in active[:6])
        return {
            "active_runs": len(active),
            "cooling_runs": len(cooling),
            "inactive_runs": len(inactive),
            "buy_runs": buy_count,
            "sell_runs": sell_count,
            "dominant_side": dominant_side,
            "has_live_projection": bool(live_focus),
            "current_net_contracts": current_net,
            "projected_net_close": projected_net,
            "active_projection_remaining": active_projection,
            "concentration": concentration,
            "robot_score_mean": robot_mean,
            "holding_score_mean": holding_mean,
            "confidence_mean": confidence_mean,
            "latest_bucket_label": session_meta.get("latest_bucket_label"),
            "remaining_minutes_to_close": max(
                0,
                (int(session_meta["total_buckets"]) - 1 - int(session_meta["latest_bucket_index"]))
                * int(session_meta["bucket_minutes"]),
            ),
        }

    def _build_reader(
        self,
        *,
        detections: list[dict[str, Any]],
        summary: dict[str, Any],
        session_meta: dict[str, Any],
    ) -> dict[str, Any]:
        if not detections:
            return {
                "headline": "Ainda sem robos relevantes",
                "summary": "O radar ainda nao encontrou uma curva de montagem com tamanho e persistencia suficientes para entrar no catalogo.",
                "bullets": [],
                "tone": "neutral",
            }
        active = [item for item in detections if item.get("status") == "active"]
        focus = active or detections[:3]
        leader_names = ", ".join(self._unique_display_names(focus, limit=3))
        dominant_side = summary.get("dominant_side") or "neutral"
        tone = dominant_side if dominant_side in {"buy", "sell"} else "mixed"
        if active:
            if dominant_side == "buy":
                headline = f"{leader_names} puxam montagem compradora"
            elif dominant_side == "sell":
                headline = f"{leader_names} puxam desmontagem vendedora"
            else:
                headline = f"{leader_names} dividem a fita"
        else:
            headline = f"{leader_names} deixaram historico relevante"

        concentration = float(summary.get("concentration") or 0.0)
        if concentration >= 0.72:
            concentration_read = "bem concentrado nas primeiras assinaturas"
        elif concentration >= 0.52:
            concentration_read = "concentrado, mas nao monopolizado"
        else:
            concentration_read = "mais distribuido entre varias pontas"
        remaining_minutes = int(summary.get("remaining_minutes_to_close") or 0)
        if active:
            summary_text = (
                f"O fluxo relevante da sessao esta {concentration_read}. "
                f"O bloco principal projeta {self._signed_contracts(summary.get('projected_net_close'))} ate o fechamento, "
                f"com {remaining_minutes}min restantes para a sessao e reader orientado por montagem minuto a minuto."
            )
        else:
            summary_text = (
                f"O fluxo relevante da sessao esta {concentration_read}. "
                f"O bloco principal deixou {self._signed_contracts(summary.get('current_net_contracts'))} no historico, "
                f"sem projecao ativa neste momento."
            )

        bullets: list[str] = []
        top = focus[0]
        if top.get("has_live_projection"):
            bullets.append(
                f"{top['display_name']} esta {self._side_label(top['side'])} "
                f"{self._signed_contracts(top.get('delta_contracts'))} a {self._signed_number(top.get('contracts_per_minute'), 1)}/min, "
                f"com projecao de {self._signed_contracts(top.get('projected_total_contracts'))} ate o fim do pregao."
            )
        else:
            bullets.append(
                f"{top['display_name']} deixou um historico {self._side_label(top['side'])} de "
                f"{self._signed_contracts(top.get('delta_contracts'))}, sem projecao ativa no momento."
            )
        if len(focus) > 1:
            bullets.append(
                f"As duas maiores assinaturas somam {self._signed_contracts(sum(float(item.get('delta_contracts') or 0.0) for item in focus[:2]))} "
                f"e deixam o tape mais {self._bias_word(dominant_side)}."
            )
        if active:
            pulse = statistics.fmean(
                [float(item.get("aggression_pulse") or 0.0) for item in active[:3]]
            )
            bullets.append(
                f"Pulso medio de agressao em {pulse:.2f}x o baseline recente; use isso para separar montagem viva de historico ja desligado."
            )
        styles = {item["style"]["label"] for item in focus[:4]}
        bullets.append(
            f"As assinaturas mais fortes parecem {', '.join(sorted(styles))}, o que ajuda a diferenciar CTA agressivo, builder passivo e execucao mista."
        )
        return {
            "headline": headline,
            "summary": summary_text,
            "bullets": bullets,
            "tone": tone,
        }

    def _build_session_flow(
        self,
        *,
        detections: list[dict[str, Any]],
        session_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        latest_index = int(session_meta["latest_bucket_index"])
        points = [
            {
                "minute_index": index,
                "label": self._minute_label(session_meta, index),
                "timestamp": self._minute_timestamp(session_meta, index),
                "net_flow": 0.0,
                "active_count": 0,
                "aggression": 0.0,
            }
            for index in range(latest_index + 1)
        ]
        for item in detections[:12]:
            for chart_point in item.get("chart") or []:
                index = int(chart_point.get("minute_index") or 0)
                if 0 <= index < len(points):
                    points[index]["net_flow"] += float(chart_point.get("delta_qty") or 0.0)
                    points[index]["aggression"] += float(chart_point.get("delta_agression_balance") or 0.0)
                    points[index]["active_count"] += 1
        return points

    @staticmethod
    def _linear_fit(series: list[float]) -> tuple[float, float]:
        if len(series) < 2:
            return 0.0, 0.0
        x_values = list(range(len(series)))
        x_mean = statistics.fmean(x_values)
        y_mean = statistics.fmean(series)
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        if denominator <= 0:
            return 0.0, 0.0
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, series, strict=False))
        slope = numerator / denominator
        ss_total = sum((y - y_mean) ** 2 for y in series)
        if ss_total <= 0:
            return slope, 0.0
        intercept = y_mean - (slope * x_mean)
        residuals = [y - ((slope * x) + intercept) for x, y in zip(x_values, series, strict=False)]
        ss_res = sum(value * value for value in residuals)
        r2 = 1.0 - (ss_res / ss_total)
        return slope, max(min(r2, 1.0), -1.0)

    def _best_aligned_streak_metrics(
        self,
        *,
        chart: list[dict[str, Any]],
        side: int,
        noise_floor: float,
        bucket_minutes: int,
    ) -> tuple[int, float]:
        best_minutes = 0
        best_r2 = 0.0
        current_streak: list[float] = []
        previous_minute_index: int | None = None

        def flush_streak() -> None:
            nonlocal best_minutes, best_r2, current_streak
            if not current_streak:
                return
            streak_minutes = len(current_streak) * max(bucket_minutes, 1)
            if len(current_streak) >= 2:
                cumulative_series: list[float] = []
                running_total = 0.0
                for value in current_streak:
                    running_total += value
                    cumulative_series.append(running_total)
                _, streak_r2 = self._linear_fit(cumulative_series)
            else:
                streak_r2 = 0.0
            if streak_minutes > best_minutes or (streak_minutes == best_minutes and streak_r2 > best_r2):
                best_minutes = streak_minutes
                best_r2 = streak_r2
            current_streak = []

        for point in chart:
            delta_qty = float(point.get("delta_qty") or 0.0)
            minute_index = int(point.get("minute_index") or 0)
            aligned = abs(delta_qty) >= noise_floor and (1 if delta_qty > 0 else -1) == side
            contiguous = previous_minute_index is not None and minute_index == previous_minute_index + 1
            if aligned and (not current_streak or contiguous):
                current_streak.append(delta_qty)
            elif aligned:
                flush_streak()
                current_streak = [delta_qty]
            else:
                flush_streak()
            previous_minute_index = minute_index

        flush_streak()
        return best_minutes, best_r2

    @staticmethod
    def _regularity_score(values: list[float]) -> float:
        if not values:
            return 0.0
        mean_value = statistics.fmean(values)
        if mean_value <= 0:
            return 0.0
        if len(values) == 1:
            return 1.0
        deviation = statistics.pstdev(values)
        cv = deviation / max(mean_value, 1e-6)
        return max(0.0, 1.0 - min(cv / 1.45, 1.0))

    @staticmethod
    def _cadence_score(indices: list[int]) -> float:
        if len(indices) < 2:
            return 0.4
        gaps = [indices[position] - indices[position - 1] for position in range(1, len(indices))]
        mean_gap = statistics.fmean(gaps)
        if mean_gap <= 0:
            return 1.0
        if len(gaps) == 1:
            return 0.85
        deviation = statistics.pstdev(gaps)
        cv = deviation / max(mean_gap, 1e-6)
        return max(0.0, 1.0 - min(cv / 1.55, 1.0))

    @staticmethod
    def _pulse_ratio(*, recent: list[float], baseline: list[float]) -> float:
        recent_clean = [value for value in recent if value > 0]
        baseline_clean = [value for value in baseline if value > 0]
        if not recent_clean:
            return 0.0
        recent_mean = statistics.fmean(recent_clean)
        if not baseline_clean:
            return 1.0
        baseline_mean = statistics.fmean(baseline_clean)
        if baseline_mean <= 0:
            return 1.0
        return recent_mean / baseline_mean

    @staticmethod
    def _blended_linearity(*, fit_r2: float, recent_r2: float, active_minutes: int) -> float:
        if active_minutes >= 60:
            return max(fit_r2, (fit_r2 * 0.88) + (recent_r2 * 0.12))
        if active_minutes >= 20:
            return max(fit_r2 * 0.92, (fit_r2 * 0.74) + (recent_r2 * 0.26))
        return max(fit_r2 * 0.90, (fit_r2 * 0.66) + (recent_r2 * 0.34))

    @staticmethod
    def _holding_score(
        *,
        active_minutes: int,
        fit_r2: float,
        recent_r2: float,
        persistence: float,
        max_bar_share: float,
        top3_share: float,
    ) -> float:
        duration_component = min(active_minutes / 90.0, 1.0)
        linearity_component = FlowActivityRadarService._blended_linearity(
            fit_r2=fit_r2,
            recent_r2=recent_r2,
            active_minutes=active_minutes,
        )
        dispersion_component = max(0.0, 1.0 - min((max_bar_share * 0.85) + (top3_share * 0.55), 1.0))
        return FlowActivityRadarService._clamp(
            (
                (linearity_component * 42.0)
                + (duration_component * 28.0)
                + (persistence * 14.0)
                + (dispersion_component * 16.0)
            ),
            0.0,
            100.0,
        )

    @staticmethod
    def _passes_holder_filter(
        *,
        run_scope: str,
        active_minutes: int,
        elapsed_minutes: int,
        linearity_score: float,
        sustained_linear_minutes: int,
        sustained_linear_r2: float,
        max_bar_share: float,
        top3_share: float,
    ) -> bool:
        min_active_minutes = 45 if run_scope == "session_builder" else 8
        if active_minutes < min_active_minutes:
            return False
        if sustained_linear_minutes < 5:
            return False
        if run_scope == "session_builder":
            return (
                elapsed_minutes >= 60
                and linearity_score >= 0.78
                and sustained_linear_r2 >= 0.76
                and max_bar_share <= 0.48
                and top3_share <= 0.62
            )
        if active_minutes < 16:
            return (
                linearity_score >= 0.80
                and sustained_linear_r2 >= 0.84
                and max_bar_share <= 0.44
                and top3_share <= 0.68
            )
        return (
            linearity_score >= 0.72
            and sustained_linear_r2 >= 0.78
            and max_bar_share <= 0.52
            and top3_share <= 0.76
        )

    def _classify_style(
        self,
        *,
        total_qty: float,
        total_aggression: float,
        total_maker: float,
        total_rlp: float,
        persistence: float,
        active_points: int,
    ) -> str:
        abs_qty = max(abs(total_qty), 1.0)
        aggr_ratio = abs(total_aggression) / abs_qty
        maker_ratio = abs(total_maker) / abs_qty
        rlp_ratio = abs(total_rlp) / abs_qty
        if aggr_ratio >= 0.75 and abs(total_aggression) > abs(total_maker) * 1.15:
            return "aggressive_taker"
        if maker_ratio >= 0.72 and abs(total_maker) > abs(total_aggression) * 1.1:
            return "passive_builder"
        if rlp_ratio >= 0.35:
            return "rlp_recycler"
        if persistence >= 0.68 and active_points >= 8:
            return "steady_inventory_builder"
        return "mixed_executor"

    @staticmethod
    def _percentile(values: list[float], quantile: float) -> float:
        if not values:
            return 0.0
        index = max(0, min(len(values) - 1, int(round((len(values) - 1) * quantile))))
        return float(values[index])

    @staticmethod
    def _ewma(values: list[float], alpha: float) -> list[float]:
        output: list[float] = []
        previous = 0.0
        for value in values:
            previous = (alpha * value) + ((1.0 - alpha) * previous)
            output.append(previous)
        return output

    @staticmethod
    def _directional_consistency(*, values: list[float], side: int, noise_floor: float) -> float:
        active = [value for value in values if abs(value) >= noise_floor]
        if not active:
            return 0.0
        aligned = sum(1 for value in active if (1 if value > 0 else -1) == side)
        return aligned / len(active)

    @staticmethod
    def _sign(value: float) -> int:
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def _directional_track_priority(self, item: dict[str, Any]) -> tuple[int, float, float, int, str]:
        status = str(item.get("status") or "")
        run_scope = str(item.get("run_scope") or "")
        status_priority = {
            "active": 3,
            "cooling": 2,
            "inactive": 1,
        }.get(status, 0)
        scope_priority = {
            "shape_builder": 3,
            "session_builder": 2,
            "detected_run": 1,
        }.get(run_scope, 0)
        last_active_time = str(item.get("last_active_time") or "")
        ranking_score = float(item.get("ranking_score") or 0.0)
        active_minutes = float(item.get("active_minutes") or 0.0)
        return (
            status_priority,
            ranking_score,
            active_minutes,
            scope_priority,
            last_active_time,
        )

    @staticmethod
    def _build_history_run(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": item.get("run_id"),
            "status": "inactive",
            "status_label": "historico",
            "run_scope": item.get("run_scope"),
            "run_scope_label": item.get("run_scope_label"),
            "start_time": item.get("start_time"),
            "last_active_time": item.get("last_active_time"),
            "start_label": item.get("start_label"),
            "last_active_label": item.get("last_active_label"),
            "elapsed_minutes": item.get("elapsed_minutes"),
            "active_minutes": item.get("active_minutes"),
            "inactive_gap_minutes": item.get("inactive_gap_minutes"),
            "delta_contracts": item.get("delta_contracts"),
            "absolute_delta_contracts": item.get("absolute_delta_contracts"),
            "contracts_per_minute": item.get("contracts_per_minute"),
            "contracts_per_hour": item.get("contracts_per_hour"),
            "aggression_pulse": item.get("aggression_pulse"),
            "holding_score": item.get("holding_score"),
            "confidence": item.get("confidence"),
            "directional_persistence": item.get("directional_persistence"),
            "linearity_score": item.get("linearity_score"),
            "sustained_linear_minutes": item.get("sustained_linear_minutes"),
            "sustained_linear_r2": item.get("sustained_linear_r2"),
            "chart": item.get("chart") or [],
            "has_live_projection": False,
            "projected_total_contracts": None,
            "projected_remaining_contracts": None,
        }

    @staticmethod
    def _strip_projection(item: dict[str, Any]) -> dict[str, Any]:
        item["has_live_projection"] = False
        item["projected_total_contracts"] = None
        item["projected_remaining_contracts"] = None
        return item

    def _minute_label(self, session_meta: dict[str, Any], minute_index: int) -> str:
        start_at = datetime.fromisoformat(str(session_meta["start_at"]))
        instant = start_at + timedelta(minutes=int(session_meta["bucket_minutes"]) * minute_index)
        return instant.strftime("%H:%M")

    def _minute_timestamp(self, session_meta: dict[str, Any], minute_index: int) -> str:
        start_at = datetime.fromisoformat(str(session_meta["start_at"]))
        instant = start_at + timedelta(minutes=int(session_meta["bucket_minutes"]) * minute_index)
        return instant.isoformat()

    @staticmethod
    def _status_rank(status: Any) -> int:
        if status == "active":
            return 0
        if status == "cooling":
            return 1
        return 2

    @staticmethod
    def _status_weight(status: Any) -> float:
        if status == "active":
            return 1.0
        if status == "cooling":
            return 0.93
        return 0.84

    @staticmethod
    def _status_label(status: str) -> str:
        if status == "active":
            return "ativo"
        if status == "cooling":
            return "desacelerando"
        return "inativo"

    @staticmethod
    def _run_scope_label(run_scope: str) -> str:
        if run_scope == "session_builder":
            return "builder do dia"
        if run_scope == "shape_builder":
            return "shape direcional"
        return "janela ativa"

    @staticmethod
    def _unique_display_names(items: list[dict[str, Any]], limit: int = 3) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for item in items:
            name = str(item.get("display_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
            if len(names) >= limit:
                break
        return names

    @staticmethod
    def _short_broker_name(name: str) -> str:
        cleaned = " ".join(str(name or "").strip().split())
        suffixes = [
            " CTVM S/A",
            " CCVM S/A",
            " CCTVM S/A",
            " CTVM SA",
            " DTVM LTDA",
            " DTVM S/A",
            " S.A.",
            " SA",
            " LTDA",
        ]
        for suffix in suffixes:
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip()
        return cleaned.strip() or name

    @staticmethod
    def _side_label(side: str) -> str:
        return "comprando" if side == "buy" else "vendendo" if side == "sell" else "neutro"

    @staticmethod
    def _bias_word(side: str) -> str:
        if side == "buy":
            return "comprador"
        if side == "sell":
            return "vendedor"
        return "misto"

    @staticmethod
    def _signed_contracts(value: Any) -> str:
        numeric = float(_safe_float(value) or 0.0)
        sign = "+" if numeric > 0 else ""
        return f"{sign}{numeric:,.0f}".replace(",", ".")

    @staticmethod
    def _signed_number(value: Any, digits: int = 1) -> str:
        numeric = float(_safe_float(value) or 0.0)
        sign = "+" if numeric > 0 else ""
        return f"{sign}{numeric:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
