from __future__ import annotations

import re
import unicodedata
from collections import Counter
from html import unescape
from typing import Any, Dict, List

THEME_DIRECTIONAL_PRIORS = {
    "ormuz_blockade": "sell",
    "iran_negotiation": "buy",
    "iran_negotiation_setback": "sell",
}

IRAN_PROGRESS_TERMS = {
    "progress",
    "progresso",
    "dialog",
    "dialogue",
    "deal",
    "agreement",
    "acordo",
    "ceasefire",
    "cessar fogo",
    "cessar-fogo",
    "de-escalation",
    "desescalada",
    "risk relief",
    "alivio",
    "alivio de sancoes",
    "sanctions relief",
}

IRAN_SETBACK_TERMS = {
    "renuncia",
    "renunciou",
    "renuncia a lideranca",
    "renuncia a liderança",
    "resign",
    "resigns",
    "resigned",
    "resignation",
    "stepped down",
    "quit",
    "withdrew",
    "walked away",
    "impasse",
    "deadlock",
    "setback",
    "retrocesso",
    "colapso",
    "collapse",
    "suspens",
    "breakdown",
    "desistiu",
}

HARDLINER_TERMS = {
    "linha dura",
    "hardliner",
    "hard line",
    "hard-line",
    "hawk faction",
    "faccao dura",
    "facção dura",
    "pressure from hardliners",
    "pressao da linha dura",
    "pressão da linha dura",
}

MODERATE_EXIT_TERMS = {
    "moderate",
    "moderado",
    "moderada",
    "moderate negotiator",
    "negociador moderado",
    "ponta moderada",
    "ghalibaf",
}

SUCCESSOR_UNCERTAINTY_TERMS = {
    "uncertainty",
    "incerteza",
    "unknown successor",
    "nao se sabe quem entra",
    "não se sabe quem entra",
    "replacement unclear",
    "sem substituto",
    "sem sucessor",
    "successor",
}

DIPLOMACY_TERMS = {
    "talks",
    "negotiations",
    "negociacoes",
    "negociações",
    "dialogue",
    "dialogo",
    "diálogo",
    "diplomacy",
    "diplomacia",
}

TRANSMISSION_MAP = {
    "index": "equity_index",
    "dollar": "fx_defensive_bid",
    "curve_long": "long_end_risk_premium",
    "curve_short": "front_end_policy_repricing",
}


def _normalize_text(value: Any) -> str:
    text = unescape(str(value or "")).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def _contains(text: str, term: str) -> bool:
    token = _normalize_text(term)
    if not token:
        return False
    if " " in token:
        return token in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text))


def _collect_hits(text: str, terms: set[str]) -> list[str]:
    hits = [term for term in sorted(terms) if _contains(text, term)]
    return hits


def tokenize_macro_event_context(event: Dict[str, Any]) -> Dict[str, Any]:
    text = _normalize_text(
        " ".join(
            [
                str(event.get("headline") or ""),
                str(event.get("scenario_reason") or ""),
                " ".join(event.get("themes") or []),
                " ".join(event.get("market_relevance_terms") or []),
                " ".join(event.get("high_conviction_macro_terms") or []),
            ]
        )
    )
    theme_set = {
        _normalize_text(theme)
        for theme in (event.get("themes") or [])
        if str(theme or "").strip()
    }
    buckets = [
        _normalize_text(bucket)
        for bucket in (event.get("linked_buckets") or [])
        if str(bucket or "").strip()
    ]
    scenario = _normalize_text(event.get("scenario_classification") or "")
    signal_strength = _normalize_text(event.get("signal_strength") or "")
    macro_scope = _normalize_text(event.get("macro_scope") or "")
    transmission_score = float(event.get("macro_transmission_score") or 0.0)
    impact_score = float(event.get("impact_score") or 0.0)

    progress_hits = _collect_hits(text, IRAN_PROGRESS_TERMS)
    setback_hits = _collect_hits(text, IRAN_SETBACK_TERMS)
    hardliner_hits = _collect_hits(text, HARDLINER_TERMS)
    moderate_exit_hits = _collect_hits(text, MODERATE_EXIT_TERMS)
    successor_hits = _collect_hits(text, SUCCESSOR_UNCERTAINTY_TERMS)
    diplomacy_hits = _collect_hits(text, DIPLOMACY_TERMS)

    buy_score = 0.0
    sell_score = 0.0
    risk_vectors: list[str] = []
    tokens: list[str] = []

    if "ormuz_blockade" in theme_set:
        sell_score += 55.0
        tokens.extend(["theme:ormuz_blockade", "signal:energy_supply_risk", "signal:shipping_disruption"])
        risk_vectors.extend(["energy_supply_risk", "shipping_disruption", "inflation_tail_risk"])

    if "iran_negotiation_setback" in theme_set:
        sell_score += 42.0
        tokens.extend(["theme:iran_negotiation_setback", "signal:diplomatic_setback"])
        risk_vectors.extend(["diplomatic_breakdown", "geopolitical_uncertainty"])

    if "iran_negotiation" in theme_set and progress_hits and not setback_hits:
        buy_score += 34.0
        tokens.extend(["theme:iran_negotiation", "signal:diplomatic_relief"])
        risk_vectors.extend(["risk_relief", "deescalation_option"])

    if setback_hits:
        sell_score += 24.0
        tokens.append("state:talks_setback")
        risk_vectors.append("diplomatic_breakdown")

    if hardliner_hits:
        sell_score += 18.0
        tokens.append("state:hardliner_pressure")
        risk_vectors.append("ideological_hardening")

    if moderate_exit_hits and (setback_hits or hardliner_hits or diplomacy_hits):
        sell_score += 16.0
        tokens.append("state:moderate_exit")
        risk_vectors.append("negotiation_continuity_risk")

    if successor_hits:
        sell_score += 12.0
        tokens.append("state:successor_uncertainty")
        risk_vectors.append("leadership_uncertainty")

    if diplomacy_hits:
        tokens.append("domain:diplomacy")

    if scenario == "regime_shift":
        if sell_score >= buy_score:
            sell_score += 10.0
        else:
            buy_score += 10.0
        tokens.append("scenario:regime_shift")
    elif scenario == "tradable_catalyst":
        if sell_score >= buy_score:
            sell_score += 6.0
        else:
            buy_score += 6.0
        tokens.append("scenario:tradable_catalyst")

    if signal_strength == "high":
        if sell_score >= buy_score:
            sell_score += 8.0
        elif buy_score > 0:
            buy_score += 8.0
        tokens.append("signal_strength:high")
    elif signal_strength == "medium":
        if sell_score >= buy_score:
            sell_score += 4.0
        elif buy_score > 0:
            buy_score += 4.0
        tokens.append("signal_strength:medium")

    for bucket in buckets:
        mapped = TRANSMISSION_MAP.get(bucket)
        if mapped:
            tokens.append(f"transmission:{mapped}")
            risk_vectors.append(mapped)

    if macro_scope == "macro":
        tokens.append("scope:macro")
    elif macro_scope:
        tokens.append(f"scope:{macro_scope}")

    if transmission_score >= 6.0:
        tokens.append("transmission:high")
    elif transmission_score >= 4.0:
        tokens.append("transmission:medium")

    theme_prior = next((THEME_DIRECTIONAL_PRIORS[theme] for theme in theme_set if theme in THEME_DIRECTIONAL_PRIORS), "watch")
    if theme_prior == "sell" and sell_score == 0 and ("iran_negotiation_setback" in theme_set or "ormuz_blockade" in theme_set):
        sell_score += 20.0
    if theme_prior == "buy" and buy_score == 0 and "iran_negotiation" in theme_set and not setback_hits:
        buy_score += 14.0

    score_margin = sell_score - buy_score
    if score_margin >= 8.0:
        bias = "sell"
        confidence = min(100, int(round(sell_score + min(impact_score * 3.0, 18.0) + min(transmission_score * 2.2, 14.0))))
    elif score_margin <= -8.0:
        bias = "buy"
        confidence = min(100, int(round(buy_score + min(impact_score * 3.0, 18.0) + min(transmission_score * 2.2, 14.0))))
    else:
        bias = "watch"
        confidence = min(100, int(round(max(buy_score, sell_score) * 0.7)))

    if bias == "sell" and {"state:hardliner_pressure", "state:moderate_exit"} & set(tokens):
        regime_hint = "risk-off diplomatic setback"
    elif bias == "sell" and "theme:ormuz_blockade" in tokens:
        regime_hint = "risk-off oil shock"
    elif bias == "buy" and "signal:diplomatic_relief" in tokens:
        regime_hint = "risk-on diplomatic relief"
    else:
        regime_hint = "mixed macro tape"

    if bias == "sell" and "state:moderate_exit" in tokens:
        summary = (
            "Moderate negotiation leadership exited under hardliner pressure, which reduces the odds of near-term diplomatic relief "
            "and raises uncertainty about the next negotiation node."
        )
    elif bias == "sell" and "state:hardliner_pressure" in tokens:
        summary = (
            "The headline points to a hardliner shift in the negotiation channel, which is a negative macro signal because it raises "
            "the probability of diplomatic delay, renewed geopolitical risk premium and a less benign risk backdrop."
        )
    elif bias == "buy":
        summary = (
            "The headline improves the diplomatic path and supports a relief regime, lowering geopolitical premium and helping risk appetite."
        )
    else:
        summary = "The headline carries mixed signals and still needs broader cross-asset confirmation."

    prompt_tokens = list(dict.fromkeys(tokens + [f"bias:{bias}", f"regime:{regime_hint.replace(' ', '_')}"]))

    return {
        "bias": bias,
        "confidence": confidence,
        "regime_hint": regime_hint,
        "summary": summary,
        "prompt_tokens": prompt_tokens[:18],
        "risk_vectors": list(dict.fromkeys(risk_vectors))[:8],
        "hits": {
            "progress": progress_hits,
            "setback": setback_hits,
            "hardliner": hardliner_hits,
            "moderate_exit": moderate_exit_hits,
            "successor_uncertainty": successor_hits,
        },
        "scores": {
            "buy": round(buy_score, 2),
            "sell": round(sell_score, 2),
            "margin": round(abs(score_margin), 2),
        },
    }


def aggregate_macro_event_tokens(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    packets = []
    token_counter: Counter[str] = Counter()
    vector_counter: Counter[str] = Counter()
    buy_score = 0.0
    sell_score = 0.0

    for event in events:
        packet = tokenize_macro_event_context(event)
        weight = 1.0 + min(float(event.get("impact_score") or 0.0), 8.0) / 4.0 + min(float(event.get("macro_transmission_score") or 0.0), 8.0) / 6.0
        if packet["bias"] == "buy":
            buy_score += packet["confidence"] * weight
        elif packet["bias"] == "sell":
            sell_score += packet["confidence"] * weight
        token_counter.update(packet["prompt_tokens"])
        vector_counter.update(packet["risk_vectors"])
        packets.append(
            {
                "event_id": event.get("event_id"),
                "headline": event.get("headline"),
                "bias": packet["bias"],
                "confidence": packet["confidence"],
                "regime_hint": packet["regime_hint"],
                "summary": packet["summary"],
                "prompt_tokens": packet["prompt_tokens"][:8],
                "risk_vectors": packet["risk_vectors"][:6],
            }
        )

    if sell_score >= buy_score + 18.0:
        aggregate_bias = "sell"
        aggregate_confidence = min(100, int(round(sell_score / max(len(events), 1))))
    elif buy_score >= sell_score + 18.0:
        aggregate_bias = "buy"
        aggregate_confidence = min(100, int(round(buy_score / max(len(events), 1))))
    else:
        aggregate_bias = "watch"
        aggregate_confidence = min(100, int(round(max(buy_score, sell_score) / max(len(events), 1) * 0.75)))

    if aggregate_bias == "sell" and vector_counter.get("negotiation_continuity_risk"):
        regime_hint = "risk-off diplomatic setback"
    elif aggregate_bias == "sell" and vector_counter.get("energy_supply_risk"):
        regime_hint = "risk-off oil shock"
    elif aggregate_bias == "buy":
        regime_hint = "risk-on diplomatic relief"
    else:
        regime_hint = "mixed macro tape"

    if packets:
        summaries = [packet["summary"] for packet in packets[:2] if packet.get("summary")]
        aggregate_summary = " ".join(dict.fromkeys(summaries))
    else:
        aggregate_summary = "No semantic macro context extracted."

    return {
        "aggregate_bias": aggregate_bias,
        "aggregate_confidence": aggregate_confidence,
        "aggregate_regime": regime_hint,
        "aggregate_summary": aggregate_summary,
        "top_tokens": [token for token, _count in token_counter.most_common(12)],
        "top_risk_vectors": [token for token, _count in vector_counter.most_common(8)],
        "event_contexts": packets[:6],
        "scores": {
            "buy": round(buy_score, 2),
            "sell": round(sell_score, 2),
            "margin": round(abs(sell_score - buy_score), 2),
        },
    }


def build_driver_llm_context_packet(
    *,
    events: List[Dict[str, Any]],
    primary_asset: str | None,
    focus_contracts: List[str],
    focus_securities: List[str],
    focus_buckets: List[str],
    themes: List[str],
    asset_asymmetry: List[Dict[str, Any]],
    participant_reactions: List[Dict[str, Any]],
    day_context: Dict[str, Any],
    directional_consensus: Dict[str, Any],
    expected_impact_fallback: Dict[str, Any],
    importance_score: int,
    technical_driver: bool,
) -> Dict[str, Any]:
    semantic = aggregate_macro_event_tokens(events)
    day_meta = (day_context or {}).get("meta") or {}
    narrative_memory = (day_context or {}).get("narrative_memory") or {}
    narrative_titles = [
        str(item.get("title") or "")
        for item in (narrative_memory.get("related_drivers") or [])[:3]
        if str(item.get("title") or "").strip()
    ]
    top_day_drivers = narrative_titles or [
        str(item.get("title") or "")
        for item in ((day_context or {}).get("top_drivers") or [])[:3]
        if str(item.get("title") or "").strip()
    ]
    fragile_titles = [
        str(item.get("title") or "")
        for item in ((day_context or {}).get("fragile_drivers") or [])[:2]
        if str(item.get("title") or "").strip()
    ]

    contradiction_flags: list[str] = []
    consensus_bias = str(directional_consensus.get("bias") or "watch")
    if consensus_bias in {"buy", "sell"} and semantic.get("aggregate_bias") in {"buy", "sell"} and semantic.get("aggregate_bias") != consensus_bias:
        contradiction_flags.append("semantic_vs_consensus_divergence")
    if "iran_negotiation" in {str(theme).strip().lower() for theme in themes} and semantic.get("aggregate_bias") == "sell":
        contradiction_flags.append("iran_relief_theme_overridden_by_setback_tokens")
    narrative_verdict = str(narrative_memory.get("contextual_verdict") or "mixed_context").strip().lower()
    if narrative_verdict == "dissolving_sequence" and semantic.get("aggregate_bias") in {"buy", "sell"}:
        contradiction_flags.append("narrative_dissolution_warning")
    if narrative_verdict == "headline_repetition_without_followthrough":
        contradiction_flags.append("repeat_headline_without_followthrough")
    narrative_tokens = list(
        dict.fromkeys(
            [
                f"narrative_verdict:{narrative_verdict}",
                *(f"narrative_flag:{flag}" for flag in (narrative_memory.get("contextual_flags") or [])[:4]),
                *(
                    f"related_driver:{str(item.get('title') or '').strip().replace(' ', '_')[:48]}"
                    for item in (narrative_memory.get("related_drivers") or [])[:3]
                    if str(item.get("title") or "").strip()
                ),
            ]
        )
    )

    prompt_tokens = list(
        dict.fromkeys(
            [
                *(semantic.get("top_tokens") or []),
                f"aggregate_bias:{semantic.get('aggregate_bias')}",
                f"aggregate_regime:{str(semantic.get('aggregate_regime') or '').replace(' ', '_')}",
                *(f"focus_bucket:{bucket}" for bucket in focus_buckets[:4]),
                *(f"theme:{theme}" for theme in themes[:4]),
                *(f"contract:{ticker}" for ticker in focus_contracts[:3]),
                *(f"security:{ticker}" for ticker in focus_securities[:3]),
                *narrative_tokens,
            ]
        )
    )[:24]

    return {
        "version": "macro-context-tokenizer-v2",
        "primary_asset": primary_asset or "macro basket",
        "technical_driver": technical_driver,
        "importance_score": importance_score,
        "expected_impact_fallback": {
            "score": expected_impact_fallback.get("score"),
            "band": expected_impact_fallback.get("band"),
            "scenario_classification": expected_impact_fallback.get("scenario_classification"),
        },
        "semantic": semantic,
        "focus": {
            "contracts": focus_contracts[:5],
            "securities": focus_securities[:5],
            "buckets": focus_buckets[:5],
            "themes": themes[:5],
        },
        "asset_asymmetry_top": asset_asymmetry[:4],
        "participant_reactions_top": participant_reactions[:4],
        "day_context_tokens": {
            "top_drivers": top_day_drivers,
            "fragile_drivers": fragile_titles,
            "comparison_driver_count": day_meta.get("comparison_driver_count"),
            "headline_count": day_meta.get("headline_count"),
            "narrative_match_count": day_meta.get("narrative_match_count"),
        },
        "narrative_memory": {
            "contextual_verdict": narrative_memory.get("contextual_verdict") or "mixed_context",
            "contextual_flags": narrative_memory.get("contextual_flags") or [],
            "contextual_summary": narrative_memory.get("contextual_summary") or "",
            "related_drivers": [
                {
                    "title": item.get("title"),
                    "recommended_action": item.get("recommended_action"),
                    "narrative_role": item.get("narrative_role"),
                    "overlap_score": item.get("overlap_score"),
                    "semantic_summary": item.get("semantic_summary"),
                    "realized_impact": item.get("realized_impact"),
                }
                for item in (narrative_memory.get("related_drivers") or [])[:4]
            ],
        },
        "directional_consensus": {
            "bias": directional_consensus.get("bias"),
            "confidence": directional_consensus.get("confidence"),
            "market_regime": directional_consensus.get("market_regime"),
            "reason": directional_consensus.get("reason"),
        },
        "contradiction_flags": contradiction_flags,
        "prompt_tokens": prompt_tokens,
    }
