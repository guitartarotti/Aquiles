from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def run_regime_state_machine(
    *,
    regime_scores: dict[str, float],
    previous_state: dict[str, Any] | None,
    captured_at: str,
    switch_threshold: float = 6.0,
    confirmation_snapshots: int = 2,
    min_regime_duration_seconds: int = 120,
    extreme_override_threshold: float = 88.0,
) -> dict[str, Any]:
    previous_state = dict(previous_state or {})
    ordered = sorted((regime_scores or {}).items(), key=lambda item: float(item[1] or 0.0), reverse=True)
    dominant_regime, dominant_score = ordered[0] if ordered else ("neutral", 0.0)
    second_best_regime, second_best_score = ordered[1] if len(ordered) > 1 else ("neutral", 0.0)

    current_regime = str(previous_state.get("current_regime") or dominant_regime)
    current_score = float(previous_state.get("regime_score") or 0.0)
    previous_regime = str(previous_state.get("previous_regime") or "")
    candidate_regime = str(previous_state.get("candidate_regime") or "")
    candidate_count = int(previous_state.get("candidate_count") or 0)
    current_since = _parse_iso(previous_state.get("current_since")) or _parse_iso(captured_at) or datetime.now(timezone.utc)
    captured_dt = _parse_iso(captured_at) or datetime.now(timezone.utc)
    duration_seconds = max((captured_dt - current_since).total_seconds(), 0.0)

    transition_reason = "hold_current_regime"
    should_override = dominant_regime in {"global_funding_stress", "risk_off_confirmed"} and dominant_score >= extreme_override_threshold
    should_switch = (
        dominant_regime != current_regime
        and dominant_score > (current_score + switch_threshold)
        and duration_seconds >= min_regime_duration_seconds
    )

    if dominant_regime != current_regime:
        if candidate_regime == dominant_regime:
            candidate_count += 1
        else:
            candidate_regime = dominant_regime
            candidate_count = 1
    else:
        candidate_regime = ""
        candidate_count = 0

    if should_override:
        previous_regime = current_regime
        current_regime = dominant_regime
        current_score = dominant_score
        current_since = captured_dt
        candidate_regime = ""
        candidate_count = 0
        transition_reason = "extreme_override"
    elif should_switch and candidate_count >= confirmation_snapshots:
        previous_regime = current_regime
        current_regime = dominant_regime
        current_score = dominant_score
        current_since = captured_dt
        candidate_regime = ""
        candidate_count = 0
        transition_reason = "confirmed_switch"
    else:
        current_score = max(current_score, dominant_score if dominant_regime == current_regime else current_score * 0.98)
        if dominant_regime == current_regime:
            transition_reason = "regime_reinforced"
        elif candidate_regime:
            transition_reason = "candidate_waiting_confirmation"

    return {
        "current_regime": current_regime,
        "previous_regime": previous_regime,
        "regime_score": round(float(current_score), 4),
        "second_best_regime": second_best_regime,
        "second_best_score": round(float(second_best_score), 4),
        "duration_seconds": round(max((captured_dt - current_since).total_seconds(), 0.0), 3),
        "candidate_regime": candidate_regime or None,
        "candidate_count": candidate_count,
        "transition_reason": transition_reason,
        "current_since": current_since.isoformat(),
        "switch_threshold": switch_threshold,
        "confirmation_snapshots": confirmation_snapshots,
        "min_regime_duration_seconds": min_regime_duration_seconds,
        "extreme_override_threshold": extreme_override_threshold,
    }
