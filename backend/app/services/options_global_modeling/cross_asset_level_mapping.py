from __future__ import annotations

from typing import Any

from .types import GlobalTriangulationConfig


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _build_local_reference_zones(local_state: dict[str, Any], tolerance_points: float) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    dealer_core = _safe_float(local_state.get("dealer_core"), 0.0)
    zero_pressure = _safe_float(local_state.get("zero_pressure"), 0.0)
    acceleration = _safe_float(local_state.get("acceleration_level"), 0.0)
    pin_low = _safe_float(local_state.get("pinning_band_low"), 0.0)
    pin_high = _safe_float(local_state.get("pinning_band_high"), 0.0)

    if dealer_core > 0:
        zones.append({
            "label": "dealer_core",
            "kind": "point",
            "center": dealer_core,
            "low": dealer_core - tolerance_points,
            "high": dealer_core + tolerance_points,
        })
    if zero_pressure > 0:
        zones.append({
            "label": "zero_pressure",
            "kind": "point",
            "center": zero_pressure,
            "low": zero_pressure - tolerance_points,
            "high": zero_pressure + tolerance_points,
        })
    if acceleration > 0:
        accel_tol = tolerance_points * 1.15
        zones.append({
            "label": "acceleration",
            "kind": "point",
            "center": acceleration,
            "low": acceleration - accel_tol,
            "high": acceleration + accel_tol,
        })
    if pin_low > 0 and pin_high > 0 and pin_high >= pin_low:
        zones.append({
            "label": "pinning_band",
            "kind": "band",
            "center": (pin_low + pin_high) / 2.0,
            "low": pin_low,
            "high": pin_high,
        })
    return zones


def _nearest_zone_match(projected_level: float, zones: list[dict[str, Any]]) -> dict[str, Any]:
    if projected_level <= 0 or not zones:
        return {
            "matches_local_zone": False,
            "match_label": None,
            "match_distance_points": None,
            "match_score": 0.0,
        }

    best: dict[str, Any] | None = None
    for zone in zones:
        low = _safe_float(zone.get("low"), 0.0)
        high = _safe_float(zone.get("high"), 0.0)
        center = _safe_float(zone.get("center"), 0.0)
        if low <= projected_level <= high:
            distance = 0.0
        else:
            distance = min(abs(projected_level - low), abs(projected_level - high)) if low > 0 and high > 0 else abs(projected_level - center)
        if best is None or distance < best["match_distance_points"]:
            tolerance = max((high - low) / 2.0, 1.0)
            best = {
                "matches_local_zone": distance <= tolerance,
                "match_label": zone.get("label"),
                "match_distance_points": distance,
                "match_score": _clamp(1.0 - (distance / max(tolerance, 1.0)), 0.0, 1.0),
            }
    return best or {
        "matches_local_zone": False,
        "match_label": None,
        "match_distance_points": None,
        "match_score": 0.0,
    }


def _add_candidate(
    rows: list[dict[str, Any]],
    *,
    asset_state: dict[str, Any],
    relationship: dict[str, Any],
    local_future_spot: float,
    asset_spot: float,
    source_type: str,
    source_label: str,
    source_family: str,
    source_level: float,
    local_zones: list[dict[str, Any]],
    zone_strength: float,
    support_strength: float,
    run_config: GlobalTriangulationConfig,
) -> None:
    beta = _safe_float(relationship.get("beta"), 0.0)
    corr_smoothed = _safe_float(relationship.get("corr_smoothed"), 0.0)
    corr_short = _safe_float(relationship.get("corr_short"), 0.0)
    effective_corr = max(abs(corr_smoothed), abs(corr_short))
    if asset_spot <= 0 or source_level <= 0 or local_future_spot <= 0:
        return
    relative_move = (source_level / asset_spot) - 1.0
    mapped_move_pct = beta * relative_move
    if abs(mapped_move_pct) > 0.08:
        return

    projected_level = local_future_spot * (1.0 + mapped_move_pct)
    match = _nearest_zone_match(projected_level, local_zones)
    quality = _safe_float(asset_state.get("state_quality_score"), 0.0)
    dealer_conf = _safe_float(asset_state.get("dealer_regime_confidence"), 0.0)
    corr_score = _clamp((effective_corr - run_config.min_corr_for_mapping) / max(1.0 - run_config.min_corr_for_mapping, 1e-6), 0.0, 1.0)
    beta_score = _clamp(min(abs(beta), 1.5) / 1.5, 0.0, 1.0)
    quality_score = _clamp((0.45 * quality) + (0.25 * dealer_conf) + (0.30 * support_strength), 0.0, 1.0)
    confluence_score = 100.0 * _clamp(
        (0.30 * corr_score)
        + (0.20 * beta_score)
        + (0.20 * quality_score)
        + (0.20 * zone_strength)
        + (0.10 * match.get("match_score", 0.0)),
        0.0,
        1.0,
    )

    rows.append(
        {
            "asset": asset_state.get("asset"),
            "label": asset_state.get("label"),
            "security": asset_state.get("security"),
            "dealer_zone_source_underlying": asset_state.get("dealer_zone_source_underlying"),
            "dealer_zone_source_security": asset_state.get("dealer_zone_source_security"),
            "dealer_zone_source_mode": asset_state.get("dealer_zone_source_mode"),
            "support_level": asset_state.get("support_level"),
            "direction": "upside" if projected_level >= local_future_spot else "downside",
            "source_type": source_type,
            "source_label": source_label,
            "source_family": source_family,
            "source_level": source_level,
            "source_distance_pct": relative_move,
            "mapped_local_future": projected_level,
            "mapped_move_pct": mapped_move_pct,
            "distance_from_local_future_points": projected_level - local_future_spot,
            "distance_from_local_future_pct": mapped_move_pct,
            "beta_dynamic": beta,
            "corr_short": corr_short,
            "corr_smoothed": corr_smoothed,
            "effective_corr": effective_corr,
            "zone_strength": zone_strength,
            "support_strength": support_strength,
            "vol_deviation_score": _safe_float(asset_state.get("vol_deviation_score"), 0.0),
            "iv_skew_numeric": _safe_float(asset_state.get("iv_skew_numeric"), 0.0),
            "matches_local_zone": match.get("matches_local_zone"),
            "match_label": match.get("match_label"),
            "match_distance_points": match.get("match_distance_points"),
            "confluence_score": confluence_score,
        }
    )


def _build_asset_level_rows(
    asset_state: dict[str, Any],
    asset_meta: dict[str, Any],
    relationship: dict[str, Any],
    local_future_spot: float,
    local_zones: list[dict[str, Any]],
    run_config: GlobalTriangulationConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    asset_spot = _safe_float(asset_state.get("spot"), 0.0)
    if asset_spot <= 0:
        return rows

    dealer_conf = _safe_float(asset_state.get("dealer_regime_confidence"), 0.0)
    absorption = _safe_float(asset_state.get("local_absorption_score"), 0.0)
    breakout = _safe_float(asset_state.get("local_breakout_score"), 0.0)
    support_strength = _clamp((0.50 * _safe_float(asset_state.get("state_quality_score"), 0.0)) + (0.50 * dealer_conf), 0.0, 1.0)
    gamma_source_label = str(
        asset_state.get("dealer_zone_source_underlying")
        or asset_state.get("dealer_zone_source_security")
        or asset_state.get("security")
        or asset_state.get("label")
        or ""
    ).strip()

    gamma_levels = [
        ("dealer_core", "Dealer core", _safe_float(asset_state.get("dealer_core"), 0.0), _clamp(max(absorption, dealer_conf), 0.0, 1.0)),
        ("zero_pressure", "Zero pressure", _safe_float(asset_state.get("zero_pressure"), 0.0), _clamp(max(absorption, breakout), 0.0, 1.0)),
        ("acceleration", "Acceleration", _safe_float(asset_state.get("acceleration_level"), 0.0), _clamp(max(breakout, 0.4 * dealer_conf), 0.0, 1.0)),
        ("pinning_low", "Pinning low", _safe_float(asset_state.get("pinning_band_low"), 0.0), _clamp(absorption * 0.95, 0.0, 1.0)),
        ("pinning_high", "Pinning high", _safe_float(asset_state.get("pinning_band_high"), 0.0), _clamp(absorption * 0.95, 0.0, 1.0)),
    ]
    for source_type, label, level, zone_strength in gamma_levels:
        if level > 0:
            source_label = f"{label} ({gamma_source_label})" if gamma_source_label else label
            _add_candidate(
                rows,
                asset_state=asset_state,
                relationship=relationship,
                local_future_spot=local_future_spot,
                asset_spot=asset_spot,
                source_type=source_type,
                source_label=source_label,
                source_family="gamma_zone",
                source_level=level,
                local_zones=local_zones,
                zone_strength=zone_strength,
                support_strength=support_strength,
                run_config=run_config,
            )

    model_run = asset_meta.get("options_model_run") or {}
    strike_profiles = model_run.get("strike_profiles") or []
    if strike_profiles:
        max_abs_gamma = max(abs(_safe_float(item.get("gamma_net"), 0.0)) for item in strike_profiles) or 1.0
        max_abs_gex = max(abs(_safe_float(item.get("gex_net"), 0.0)) for item in strike_profiles) or 1.0
        max_oi = max(_safe_float(item.get("open_interest_total"), 0.0) for item in strike_profiles) or 1.0
        for item in strike_profiles:
            strike_level = _safe_float(item.get("strike"), 0.0)
            if strike_level <= 0:
                continue
            gamma_net = _safe_float(item.get("gamma_net"), 0.0)
            gex_net = _safe_float(item.get("gex_net"), 0.0)
            oi_total = _safe_float(item.get("open_interest_total"), 0.0)
            if abs(gamma_net) <= 1e-12 and abs(gex_net) <= 1e-12:
                continue
            strike_strength = _clamp(
                (0.45 * (abs(gamma_net) / max_abs_gamma))
                + (0.40 * (abs(gex_net) / max_abs_gex))
                + (0.15 * (oi_total / max_oi)),
                0.0,
                1.0,
            )
            gamma_sign = "+" if gamma_net >= 0 else "-"
            source_label = f"Gamma strike {int(round(strike_level))} ({gamma_sign} {gamma_source_label})" if gamma_source_label else f"Gamma strike {int(round(strike_level))}"
            _add_candidate(
                rows,
                asset_state=asset_state,
                relationship=relationship,
                local_future_spot=local_future_spot,
                asset_spot=asset_spot,
                source_type=f"strike_gamma_{int(round(strike_level))}",
                source_label=source_label,
                source_family="strike_gamma",
                source_level=strike_level,
                local_zones=local_zones,
                zone_strength=strike_strength,
                support_strength=support_strength,
                run_config=run_config,
            )

    range_projection = model_run.get("range_projection") or {}
    range_bands = range_projection.get("bands") or []
    if range_projection.get("enabled") and range_bands:
        upper_key = "adjusted_upper_future" if asset_meta.get("use_future_space") else "adjusted_upper_spot"
        lower_key = "adjusted_lower_future" if asset_meta.get("use_future_space") else "adjusted_lower_spot"
        vol_strength = _clamp(
            (0.55 * _safe_float(asset_state.get("vol_deviation_score"), 0.0))
            + (0.25 * min(abs(_safe_float(asset_state.get("iv_skew_numeric"), 0.0)), 1.0))
            + (0.20 * support_strength),
            0.0,
            1.0,
        )
        for band in range_bands[:3]:
            upper_level = _safe_float(band.get(upper_key), 0.0)
            lower_level = _safe_float(band.get(lower_key), 0.0)
            band_label = str(band.get("label") or band.get("level") or "band").strip()
            if upper_level > 0:
                _add_candidate(
                    rows,
                    asset_state=asset_state,
                    relationship=relationship,
                    local_future_spot=local_future_spot,
                    asset_spot=asset_spot,
                    source_type=f"iv_range_up_{band_label}",
                    source_label=f"{band_label} upper",
                    source_family="vol_deviation",
                    source_level=upper_level,
                    local_zones=local_zones,
                    zone_strength=vol_strength,
                    support_strength=support_strength,
                    run_config=run_config,
                )
            if lower_level > 0:
                _add_candidate(
                    rows,
                    asset_state=asset_state,
                    relationship=relationship,
                    local_future_spot=local_future_spot,
                    asset_spot=asset_spot,
                    source_type=f"iv_range_down_{band_label}",
                    source_label=f"{band_label} lower",
                    source_family="vol_deviation",
                    source_level=lower_level,
                    local_zones=local_zones,
                    zone_strength=vol_strength,
                    support_strength=support_strength,
                    run_config=run_config,
                )
    else:
        sigma_move = max(
            _safe_float(asset_state.get("realized_vol_intraday"), 0.0) * run_config.vol_band_sigma,
            abs(_safe_float(asset_state.get("latest_return"), 0.0)) * 0.75,
            0.0015,
        )
        vol_strength = _clamp(
            (0.65 * _safe_float(asset_state.get("vol_deviation_score"), 0.0))
            + (0.20 * min(abs(_safe_float(asset_state.get("iv_skew_numeric"), 0.0)), 1.0))
            + (0.15 * support_strength),
            0.0,
            1.0,
        )
        for scale in (1.0, 1.8, 2.6):
            scaled_move = sigma_move * scale
            sigma_label = run_config.vol_band_sigma * scale
            _add_candidate(
                rows,
                asset_state=asset_state,
                relationship=relationship,
                local_future_spot=local_future_spot,
                asset_spot=asset_spot,
                source_type=f"vol_proxy_up_{scale:.1f}",
                source_label=f"Vol proxy +{sigma_label:.2f}σ",
                source_family="vol_deviation",
                source_level=asset_spot * (1.0 + scaled_move),
                local_zones=local_zones,
                zone_strength=vol_strength,
                support_strength=support_strength,
                run_config=run_config,
            )
            _add_candidate(
                rows,
                asset_state=asset_state,
                relationship=relationship,
                local_future_spot=local_future_spot,
                asset_spot=asset_spot,
                source_type=f"vol_proxy_down_{scale:.1f}",
                source_label=f"Vol proxy -{sigma_label:.2f}σ",
                source_family="vol_deviation",
                source_level=asset_spot * (1.0 - scaled_move),
                local_zones=local_zones,
                zone_strength=vol_strength,
                support_strength=support_strength,
                run_config=run_config,
            )

    return rows


def _cluster_rows(rows: list[dict[str, Any]], local_future_spot: float, cluster_points: float, local_zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    sorted_rows = sorted(rows, key=lambda item: item.get("mapped_local_future") or 0.0)
    clusters: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush(cluster_rows: list[dict[str, Any]]) -> None:
        if not cluster_rows:
            return
        weight_sum = sum(max(_safe_float(row.get("confluence_score"), 0.0), 1.0) for row in cluster_rows)
        center = sum((_safe_float(row.get("mapped_local_future"), 0.0) * max(_safe_float(row.get("confluence_score"), 0.0), 1.0)) for row in cluster_rows) / max(weight_sum, 1e-6)
        band_low = min(_safe_float(row.get("mapped_local_future"), 0.0) for row in cluster_rows)
        band_high = max(_safe_float(row.get("mapped_local_future"), 0.0) for row in cluster_rows)
        assets = sorted({str(row.get("label") or row.get("asset") or "") for row in cluster_rows if row.get("label") or row.get("asset")})
        source_families = sorted({str(row.get("source_family") or "") for row in cluster_rows if row.get("source_family")})
        source_labels = sorted({str(row.get("source_label") or "") for row in cluster_rows if row.get("source_label")})
        local_match = _nearest_zone_match(center, local_zones)
        diversity_bonus = min(len(assets) / 3.0, 1.0)
        source_bonus = 0.18 if len(source_families) >= 2 else 0.0
        match_bonus = 0.12 if local_match.get("matches_local_zone") else 0.0
        average_score = sum(_safe_float(row.get("confluence_score"), 0.0) for row in cluster_rows) / max(len(cluster_rows), 1)
        cluster_score = 100.0 * _clamp((0.55 * (average_score / 100.0)) + (0.20 * diversity_bonus) + source_bonus + match_bonus, 0.0, 1.0)
        clusters.append(
            {
                "center_future": center,
                "band_low": band_low,
                "band_high": band_high,
                "direction": "upside" if center >= local_future_spot else "downside",
                "asset_count": len(assets),
                "level_count": len(cluster_rows),
                "assets": assets,
                "source_families": source_families,
                "source_labels": source_labels,
                "score": cluster_score,
                "matches_local_zone": local_match.get("matches_local_zone"),
                "match_label": local_match.get("match_label"),
                "match_distance_points": local_match.get("match_distance_points"),
            }
        )

    for row in sorted_rows:
        if not current:
            current = [row]
            continue
        previous = current[-1]
        prev_level = _safe_float(previous.get("mapped_local_future"), 0.0)
        current_level = _safe_float(row.get("mapped_local_future"), 0.0)
        same_direction = str(previous.get("direction") or "") == str(row.get("direction") or "")
        if same_direction and abs(current_level - prev_level) <= cluster_points:
            current.append(row)
        else:
            flush(current)
            current = [row]
    flush(current)
    return sorted(clusters, key=lambda item: (_safe_float(item.get("score"), 0.0), -abs(_safe_float(item.get("center_future"), 0.0) - local_future_spot)), reverse=True)


def build_cross_asset_level_map(
    prepared_inputs: dict[str, Any],
    dynamic_model: dict[str, Any],
    asset_states: list[dict[str, Any]],
    run_config: GlobalTriangulationConfig,
) -> dict[str, Any]:
    local_state = next((item for item in asset_states if item.get("asset") == "local_index"), None) or {}
    local_future_spot = _safe_float(dynamic_model.get("local_current_price"), 0.0)
    if local_future_spot <= 0:
        return {"enabled": False, "mapped_levels": [], "clusters": []}

    local_zones = _build_local_reference_zones(local_state, run_config.level_match_points)
    relationship_map = {
        str(item.get("slug")): item
        for item in (dynamic_model.get("relationships") or [])
        if item.get("slug")
    }
    asset_meta_map = {
        str(item.get("slug")): item
        for item in (prepared_inputs.get("assets") or [])
        if item.get("slug")
    }

    mapped_rows: list[dict[str, Any]] = []
    for asset_state in asset_states:
        slug = str(asset_state.get("asset") or "")
        if slug == "local_index":
            continue
        relationship = relationship_map.get(slug) or {}
        if not relationship.get("active"):
            continue
        asset_meta = asset_meta_map.get(slug) or {}
        mapped_rows.extend(
            _build_asset_level_rows(
                asset_state=asset_state,
                asset_meta=asset_meta,
                relationship=relationship,
                local_future_spot=local_future_spot,
                local_zones=local_zones,
                run_config=run_config,
            )
        )

    mapped_rows = sorted(mapped_rows, key=lambda item: _safe_float(item.get("confluence_score"), 0.0), reverse=True)
    representative_map: dict[str, dict[str, Any]] = {}
    representative_by_direction_map: dict[tuple[str, str], dict[str, Any]] = {}
    for row in mapped_rows:
        asset_key = str(row.get("asset") or "")
        if asset_key and asset_key not in representative_map:
            representative_map[asset_key] = row
        direction_key = str(row.get("direction") or "")
        if asset_key and direction_key:
            current = representative_by_direction_map.get((asset_key, direction_key))
            candidate_distance = abs(_safe_float(row.get("distance_from_local_future_points"), 0.0))
            current_distance = abs(_safe_float((current or {}).get("distance_from_local_future_points"), 0.0))
            if current is None or candidate_distance > current_distance:
                representative_by_direction_map[(asset_key, direction_key)] = row
    representative_levels = sorted(
        representative_map.values(),
        key=lambda item: _safe_float(item.get("confluence_score"), 0.0),
        reverse=True,
    )
    representative_upside_levels = sorted(
        [row for (asset_key, direction_key), row in representative_by_direction_map.items() if direction_key == "upside"],
        key=lambda item: _safe_float(item.get("mapped_local_future"), 0.0),
        reverse=False,
    )
    representative_downside_levels = sorted(
        [row for (asset_key, direction_key), row in representative_by_direction_map.items() if direction_key == "downside"],
        key=lambda item: _safe_float(item.get("mapped_local_future"), 0.0),
        reverse=True,
    )
    filtered_rows = [
        row for row in mapped_rows
        if _safe_float(row.get("effective_corr"), 0.0) >= run_config.min_corr_for_mapping
    ]
    top_rows = filtered_rows[: run_config.top_mapped_levels]
    clusters = _cluster_rows(top_rows, local_future_spot, run_config.level_cluster_points, local_zones)
    upside_clusters = [item for item in clusters if _safe_float(item.get("center_future"), 0.0) >= local_future_spot]
    downside_clusters = [item for item in clusters if _safe_float(item.get("center_future"), 0.0) < local_future_spot]
    strongest_cluster = clusters[0] if clusters else {}

    return {
        "enabled": True,
        "local_future_spot": local_future_spot,
        "local_reference_zones": local_zones,
        "mapped_levels": top_rows,
        "representative_levels": representative_levels,
        "representative_upside_levels": representative_upside_levels,
        "representative_downside_levels": representative_downside_levels,
        "clusters": clusters,
        "nearest_upside_cluster": min(upside_clusters, key=lambda item: abs(_safe_float(item.get("center_future"), 0.0) - local_future_spot)) if upside_clusters else {},
        "nearest_downside_cluster": min(downside_clusters, key=lambda item: abs(_safe_float(item.get("center_future"), 0.0) - local_future_spot)) if downside_clusters else {},
        "strongest_cluster": strongest_cluster,
        "global_confluence_score": _safe_float(strongest_cluster.get("score"), 0.0),
    }
