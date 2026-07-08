"""Regression guard for the PiAPI model catalog seeded in app/db/seed.py (Task 8).

No live Postgres is available in CI/sandbox for this repo, so this does not run
`python -m app.db.seed` against a real database. Instead it statically inspects
MODEL_CONFIGS to make sure the new PiAPI rows are structurally sound and that none
of them still carry an unresolved "<confirmed in Step 1>"-style placeholder.

NOTE on row count: the task-8 brief's interface line claims "11 new rows (5 image,
6 video)", but the brief's own Step 2 code block lists 7 distinct video dicts
(veo3-fast, wan26, sora2, hailuo, kling3-omni, seedance2-fast, luma) alongside the
5 image dicts -- 12 rows total, not 11. Each of the 7 video rows is a distinct,
legitimately-priced product (no duplicates), so dropping one to force the headcount
to match the summary line would be an arbitrary, unjustified guess about which
sellable model to cut. This test asserts the actual, larger set (5 image + 7 video
= 12) and this discrepancy is flagged in the Task 8 report for reconciliation.
"""

from app.db.enums import ModelProvider
from app.db.seed import MODEL_CONFIGS

PIAPI_ROWS = [row for row in MODEL_CONFIGS if row["provider"] == ModelProvider.piapi]


def test_twelve_piapi_rows_split_five_image_seven_video():
    assert len(PIAPI_ROWS) == 12

    image_rows = [row for row in PIAPI_ROWS if row["category"].value == "image"]
    video_rows = [row for row in PIAPI_ROWS if row["category"].value == "video"]
    assert len(image_rows) == 5
    assert len(video_rows) == 7


def test_every_piapi_row_has_non_null_model_and_task_type():
    for row in PIAPI_ROWS:
        assert row.get("piapi_model"), f"{row['model_code']} missing piapi_model"
        assert row.get("piapi_task_type"), f"{row['model_code']} missing piapi_task_type"


def test_no_seed_dict_contains_unresolved_placeholder():
    for row in MODEL_CONFIGS:
        for value in row.values():
            assert "<confirmed" not in str(value), (
                f"{row.get('model_code')} still has an unresolved placeholder: {value!r}"
            )


def test_unverified_gpt_image_1_5_row_is_inactive():
    # GPT Image 1.5's exact create-task shape could not be verbatim-confirmed against
    # PiAPI's docs (conflicting/ambiguous sources: unified /task endpoint with
    # task_type="gpt-image-generation" vs a separate OpenAI-compatible
    # /images/generations/async endpoint). Per the safer-default rule, this row must
    # stay inactive until verified against a real PiAPI account/API call.
    row = next(r for r in PIAPI_ROWS if r["model_code"] == "piapi-gpt-image-1-5")
    assert row["is_active"] is False


def test_all_other_piapi_rows_are_active():
    inactive = [row["model_code"] for row in PIAPI_ROWS if not row["is_active"]]
    assert inactive == ["piapi-gpt-image-1-5"]
