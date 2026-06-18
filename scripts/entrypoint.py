from __future__ import annotations

from lora_dataset_curator.app import main
from lora_dataset_curator.error_log import install_runtime_error_logging

install_runtime_error_logging()

if __name__ == "__main__":
    raise SystemExit(main())
