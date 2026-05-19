from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from logs.structured_logger import StructuredLogger


class StructuredLoggerTests(unittest.TestCase):
    def test_logger_writes_jsonl_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            logger = StructuredLogger(temp)
            logger.error("job_failed", job_id="job_1", error="boom")
            log_path = Path(temp) / "error.log"
            record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(record["level"], "ERROR")
        self.assertEqual(record["event"], "job_failed")
        self.assertEqual(record["job_id"], "job_1")
        self.assertEqual(record["error"], "boom")
        self.assertIn("ts", record)


if __name__ == "__main__":
    unittest.main()
