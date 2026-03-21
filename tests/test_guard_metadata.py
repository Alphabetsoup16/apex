from __future__ import annotations

from apex.config.constants import ENSEMBLE_RUNS_MAX_EFFECTIVE, ENSEMBLE_RUNS_MIN_EFFECTIVE
from apex.models import Mode
from apex.pipeline.guard_metadata import blocked_run_base_metadata, clamp_ensemble_runs


def test_clamp_ensemble_runs() -> None:
    assert clamp_ensemble_runs(1) == (1, ENSEMBLE_RUNS_MIN_EFFECTIVE)
    assert clamp_ensemble_runs(3) == (3, 3)
    assert clamp_ensemble_runs(99) == (99, ENSEMBLE_RUNS_MAX_EFFECTIVE)


def test_blocked_run_base_metadata_shape() -> None:
    mode: Mode = "auto"
    md = blocked_run_base_metadata(
        run_id="r1",
        actual_mode="text",
        mode=mode,
        inferred="text",
        ensemble_runs_requested=5,
        ensemble_runs_effective=3,
        max_tokens=100,
        output_mode="candidate",
        code_ground_truth=False,
        timings_total_ms=12,
    )
    assert md["run_id"] == "r1"
    assert md["mode"] == "text"
    assert md["mode_request"] == "auto"
    assert md["mode_inferred"] == "text"
    assert md["ensemble_runs_requested"] == 5
    assert md["ensemble_runs_effective"] == 3
    assert md["pipeline_steps"] == []
    assert md["timings_ms"] == {"total": 12}
