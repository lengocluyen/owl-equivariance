from pathlib import Path

from owl_equivariance import budgeting


MANIFEST = Path(__file__).parents[1] / "configs" / "publication_experiment.yaml"


def test_frozen_confirmatory_budget_stays_under_cap_even_at_output_ceiling():
    report = budgeting.estimate(MANIFEST, "confirmatory", ceiling=True)
    assert report.total_calls == 110_880
    assert report.total_cost_usd <= report.hard_cap_usd
    assert len(report.rows) == 6


def test_smoke_stage_selects_complete_orbits_not_arbitrary_rows():
    report = budgeting.estimate(MANIFEST, "smoke", ceiling=False)
    # Four base-item orbits from each of two nine-condition pilot datasets.
    assert report.total_calls == 4 * 2 * 9 * 6


def test_discovery_repeat_budget_rounds_each_dataset_like_subset_builder():
    manifest = Path(__file__).parents[1] / "configs" / "open_weight_experiment_v2.yaml"
    report = budgeting.estimate(manifest, "discovery", ceiling=False)
    # Primary: (114 + 90) * 9. Repeats: two extra responses for
    # (round(114*.2) + round(90*.2)) complete nine-condition orbits.
    per_model = (114 + 90) * 9 + 2 * (23 + 18) * 9
    assert report.total_calls == per_model * 6
