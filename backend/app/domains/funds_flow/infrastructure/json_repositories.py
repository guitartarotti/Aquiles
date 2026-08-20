"""Filesystem implementations of Funds Flow persistence ports."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from ....utils.atomic_io import atomic_json_dump
from ..contracts import FundFlowCollectorState, FundFlowSnapshot, FundFlowSnapshotSummary


def _upgrade_legacy_snapshot(payload: dict[str, Any], path: str) -> dict[str, Any]:
    """Fill fields absent from pre-contract snapshots at the filesystem boundary."""
    upgraded = dict(payload)
    report = upgraded.get("report")
    report = dict(report) if isinstance(report, dict) else {}
    upgraded["report"] = report
    upgraded.setdefault("kpis", {})

    generated_at = upgraded.get("generated_at") or report.get("last_updated_at")
    if not generated_at:
        modified_at = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        generated_at = modified_at.isoformat()
    upgraded["generated_at"] = generated_at
    return upgraded


class JsonFundsFlowSnapshotRepository:
    def __init__(self, root_dir: str) -> None:
        self.latest_path = os.path.join(root_dir, "latest.json")
        self.snapshots_path = os.path.join(root_dir, "snapshots.jsonl")

    def load_latest(self) -> FundFlowSnapshot | None:
        try:
            with open(self.latest_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return None
        if not isinstance(payload, dict):
            return None
        return FundFlowSnapshot.model_validate(_upgrade_legacy_snapshot(payload, self.latest_path))

    def save_latest(self, payload: FundFlowSnapshot) -> None:
        atomic_json_dump(self.latest_path, payload.model_dump(mode="json"), indent=2)

    def append_summary(self, summary: FundFlowSnapshotSummary) -> None:
        os.makedirs(os.path.dirname(self.snapshots_path), exist_ok=True)
        with open(self.snapshots_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False) + "\n")


class JsonFundsFlowCollectorStateRepository:
    def __init__(self, state_path: str) -> None:
        self.state_path = state_path

    def load(self) -> FundFlowCollectorState:
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return FundFlowCollectorState()
        return FundFlowCollectorState.model_validate(payload if isinstance(payload, dict) else {})

    def save(self, state: FundFlowCollectorState) -> None:
        atomic_json_dump(self.state_path, state.model_dump(mode="json"), indent=2)
