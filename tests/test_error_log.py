from __future__ import annotations

from lora_dataset_curator.error_log import (
    append_error_log,
    clear_error_log,
    error_log_path,
    read_error_log,
)


def test_error_log_can_be_written_read_and_cleared():
    append_error_log("sample error")

    assert error_log_path().exists()
    assert "sample error" in read_error_log()

    clear_error_log()

    assert read_error_log() == ""
