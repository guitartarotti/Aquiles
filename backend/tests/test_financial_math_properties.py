from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.domains.funds_flow.domain.rules import (
    period_to_window,
    pressure_regime,
    safe_divide,
)
from app.services.fair_value_legs_math import (
    _bias_label,
    _clamp,
    _mean,
    _median,
    _pearson_corr,
    _rpc_regime,
    _sentiment_regime,
    _sign,
)
from app.services.fair_value_markov_math import (
    _delta_from_history,
    _fisher_z,
    _mad,
    _normalize_probabilities,
    _rolling_corr,
    _weighted_average,
    _weighted_sigma,
)
from app.services.funds_flow_local_service import FundsFlowLocalService
from app.services.macro_participant_math import (
    _clamp as _participant_clamp,
)
from app.services.macro_participant_math import (
    _normalize_broker_name,
    _parse_iso,
    _safe_float,
)
from app.utils.funds_flow_source_values import _normalize_cnpj, _normalize_text

finite_numbers = st.floats(
    min_value=-1_000_000,
    max_value=1_000_000,
    allow_nan=False,
    allow_infinity=False,
    width=32,
)
positive_numbers = st.integers(min_value=1, max_value=1_000_000).map(float)


@settings(max_examples=100, deadline=None)
@given(numerator=finite_numbers, denominator=positive_numbers, scale=positive_numbers)
def test_safe_division_is_scale_invariant(
    numerator: float,
    denominator: float,
    scale: float,
) -> None:
    original = safe_divide(numerator, denominator)
    scaled = safe_divide(numerator * scale, denominator * scale)

    assert original is not None
    assert scaled == pytest.approx(original, rel=1e-5, abs=1e-6)
    assert original * denominator == pytest.approx(numerator, rel=1e-5, abs=1e-4)


@given(days=st.integers(min_value=-10_000, max_value=10_000))
def test_custom_periods_are_always_bounded(days: int) -> None:
    assert period_to_window(f"{days}d") == (max(1, min(days, 252)) if days >= 0 else 21)


@given(value=finite_numbers)
def test_pressure_regimes_are_directionally_symmetric(value: float) -> None:
    positive = pressure_regime(abs(value))
    negative = pressure_regime(-abs(value))

    assert positive in {"neutral", "entrada", "entrada_forte"}
    assert negative in {"neutral", "resgate", "stress"}
    if abs(value) >= 2:
        assert (positive, negative) == ("entrada_forte", "stress")


@settings(max_examples=80, deadline=None)
@given(
    flows=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=10_000_000),
            st.integers(min_value=0, max_value=10_000_000),
        ),
        min_size=1,
        max_size=25,
    )
)
def test_funds_flow_aggregation_conserves_subscriptions_and_redemptions(
    flows: list[tuple[int, int]],
) -> None:
    service = FundsFlowLocalService.__new__(FundsFlowLocalService)
    timestamp = pd.Timestamp("2026-08-20")
    informe = pd.DataFrame(
        [
            {
                "cnpj_fundo": f"{index:014d}",
                "id_subclasse": "",
                "dt": timestamp,
                "vl_total": 1_000_000.0,
                "vl_quota": 1.0,
                "pl": 1_000_000.0,
                "captacao": float(subscription),
                "resgate": float(redemption),
                "cotistas": 100,
            }
            for index, (subscription, redemption) in enumerate(flows, start=1)
        ]
    )

    fund_daily = service._build_fund_daily(informe, pd.DataFrame())
    industry = service._build_industry_daily(fund_daily)
    latest = industry.iloc[-1]
    subscriptions = sum(item[0] for item in flows)
    redemptions = sum(item[1] for item in flows)

    assert latest["captacao_total"] == subscriptions
    assert latest["resgate_total"] == redemptions
    assert latest["captacao_liquida_total"] == subscriptions - redemptions
    assert fund_daily["captacao_liquida"].sum() == subscriptions - redemptions


@settings(max_examples=60, deadline=None)
@given(
    net_flows=st.lists(
        st.integers(min_value=-1_000_000, max_value=1_000_000),
        min_size=1,
        max_size=40,
    )
)
def test_rolling_funds_flow_periods_equal_their_component_sums(
    net_flows: list[int],
) -> None:
    service = FundsFlowLocalService.__new__(FundsFlowLocalService)
    start = date(2026, 1, 1)
    informe = pd.DataFrame(
        [
            {
                "cnpj_fundo": "00000000000001",
                "id_subclasse": "",
                "dt": pd.Timestamp(start + timedelta(days=index)),
                "vl_total": 1_000_000.0,
                "vl_quota": 1.0 + index * 0.001,
                "pl": 1_000_000.0,
                "captacao": float(max(net_flow, 0)),
                "resgate": float(max(-net_flow, 0)),
                "cotistas": 100,
            }
            for index, net_flow in enumerate(net_flows)
        ]
    )

    industry = service._build_industry_daily(service._build_fund_daily(informe, pd.DataFrame()))
    latest = industry.iloc[-1]

    assert latest["rolling_flow_5d"] == sum(net_flows[-5:])
    assert latest["rolling_flow_21d"] == sum(net_flows[-21:])
    assert latest["rolling_flow_63d"] == sum(net_flows[-63:])


@given(value=st.text(alphabet="0123456789./-() ", max_size=40))
def test_cnpj_normalization_is_idempotent_and_numeric(value: str) -> None:
    normalized = _normalize_cnpj(value)

    assert _normalize_cnpj(normalized) == normalized
    assert normalized == "" or normalized.isdigit()
    assert normalized == "" or len(normalized) >= 14


@given(value=st.text(max_size=80))
def test_text_normalization_is_idempotent(value: str) -> None:
    normalized = _normalize_text(value)

    assert _normalize_text(normalized) == normalized
    assert "  " not in normalized


@given(values=st.lists(finite_numbers, min_size=1, max_size=30))
def test_location_statistics_stay_inside_observed_range(values: list[float]) -> None:
    assert _mean(values) is not None
    assert min(values) <= (_mean(values) or 0.0) <= max(values)
    assert min(values) <= (_median(values) or 0.0) <= max(values)
    assert _mad(values) >= 1e-9


@given(
    values=st.lists(finite_numbers, min_size=1, max_size=30),
    weights=st.lists(
        st.floats(
            min_value=0,
            max_value=1000,
            allow_nan=False,
            allow_infinity=False,
            width=32,
        ),
        min_size=1,
        max_size=30,
    ),
)
def test_weighted_statistics_are_finite_and_bounded(
    values: list[float], weights: list[float]
) -> None:
    size = min(len(values), len(weights))
    value_array = np.asarray(values[:size], dtype=float)
    weight_array = np.asarray(weights[:size], dtype=float)
    average = _weighted_average(value_array, weight_array)
    sigma = _weighted_sigma(value_array, weight_array)

    assert math.isfinite(average)
    assert math.isfinite(sigma)
    assert sigma >= 1e-6
    if weight_array.sum() > 1e-12:
        lower = float(value_array.min())
        upper = float(value_array.max())
        assert average >= lower or math.isclose(average, lower, rel_tol=1e-12, abs_tol=1e-12)
        assert average <= upper or math.isclose(average, upper, rel_tol=1e-12, abs_tol=1e-12)


@given(values=st.lists(finite_numbers, min_size=1, max_size=40))
def test_probability_normalization_is_finite_and_conservative(values: list[float]) -> None:
    probabilities = _normalize_probabilities(np.abs(np.asarray(values, dtype=float)))

    assert np.all(np.isfinite(probabilities))
    assert np.all(probabilities >= 0)
    assert float(probabilities.sum()) == pytest.approx(1.0)


@given(value=finite_numbers, lower=finite_numbers, upper=finite_numbers)
def test_clamps_never_escape_their_bounds(value: float, lower: float, upper: float) -> None:
    low, high = sorted((lower, upper))

    assert low <= _clamp(value, low, high) <= high
    assert low <= _participant_clamp(value, low, high) <= high


@given(values=st.lists(finite_numbers, min_size=4, max_size=30))
def test_perfect_linear_series_have_unit_correlation(values: list[float]) -> None:
    transformed = [(3.0 * value) + 7.0 for value in values]
    if np.std(values) <= 1e-9 or np.std(transformed) <= 1e-9:
        return

    assert _pearson_corr(values, transformed) == pytest.approx(1.0, abs=1e-6)
    assert _rolling_corr(values, transformed, len(values)) == pytest.approx(0.995, abs=1e-6)


@given(value=st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False))
def test_fisher_transform_is_odd(value: float) -> None:
    assert _fisher_z(-value) == pytest.approx(-_fisher_z(value))


def test_financial_labels_cover_all_threshold_boundaries() -> None:
    assert [_sign(value) for value in (-1.0, 0.0, 1.0)] == [-1, 0, 1]
    assert {_sentiment_regime(value) for value in (-70, -30, -15, 0, 15, 30, 70)} == {
        "Bear regime",
        "Bear impulse",
        "Bear watch",
        "Transition",
        "Bull watch",
        "Bull impulse",
        "Bull regime",
    }
    assert _bias_label(70, 1) == "Long edge"
    assert _bias_label(-70, -1) == "Short edge"
    assert _rpc_regime(-70, -5, -1) == "Stress impulse"
    assert _rpc_regime(70, 5, 1) == "Risk-on impulse"


def test_participant_and_history_normalizers_are_defensive() -> None:
    assert _safe_float(None) is None
    assert _safe_float("12.5") == 12.5
    assert _normalize_broker_name("  Ação  Çorretora ") == "ACAO CORRETORA"
    assert _normalize_broker_name(_normalize_broker_name("Ágora")) == "AGORA"
    assert _parse_iso("2026-08-20T12:00:00Z") is not None
    assert _parse_iso("invalid") is None
    assert _delta_from_history([10.0, 13.0, 18.0], 2, 1) == 5.0
