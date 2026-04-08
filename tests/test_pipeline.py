from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from app.pipeline import ClassifyResult, DigestResult, FetchResult, run_full_pipeline


class RunFullPipelineTests(unittest.TestCase):
    def test_run_full_pipeline_orchestrates_steps_and_returns_summary(self) -> None:
        fake_db = object()
        digest_result = DigestResult(
            sent_count=2,
            text="digest",
            sent_ids=[11, 12],
            window_start=object(),  # type: ignore[arg-type]
            window_end=object(),  # type: ignore[arg-type]
            digest_date=date(2026, 4, 7),
        )

        with patch("app.pipeline.settings.validate_runtime") as validate_runtime, patch(
            "app.pipeline.run_fetch_step",
            return_value=FetchResult(created=5, existed=3, source_errors=1),
        ) as run_fetch_step, patch(
            "app.pipeline.run_classify_step",
            return_value=ClassifyResult(processed=4, kept=2, rejected=2, errors=1),
        ) as run_classify_step, patch(
            "app.pipeline.build_digest_step",
            return_value=digest_result,
        ) as build_digest_step, patch(
            "app.pipeline.send_digest_step",
            return_value=2,
        ) as send_digest_step:
            summary = run_full_pipeline(fake_db)  # type: ignore[arg-type]

        validate_runtime.assert_called_once_with()
        run_fetch_step.assert_called_once()
        run_classify_step.assert_called_once()
        build_digest_step.assert_called_once_with(fake_db)
        send_digest_step.assert_called_once_with(fake_db, digest_result)
        self.assertEqual(
            summary,
            {
                "created": 5,
                "existed": 3,
                "source_errors": 1,
                "processed": 4,
                "kept": 2,
                "rejected": 2,
                "classify_errors": 1,
                "sent": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
