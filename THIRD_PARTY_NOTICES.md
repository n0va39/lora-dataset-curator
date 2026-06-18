# Third-Party Notices

## Optional Anima LoRA Integration

LoRA Dataset Curator can optionally call an existing local Anima LoRA
installation for PE-Spatial visual similarity grouping.

This project does not bundle, redistribute, or relicense Anima LoRA source code,
dependencies, model weights, or generated artifacts. The integration launches
the Python interpreter from a user-selected Anima LoRA `.venv` and calls the
installed Anima LoRA grouping script as an external process.

Upstream project:

- Repository: https://github.com/sorryhyun/anima_lora
- License for Anima LoRA toolkit source code: MIT License
- Copyright: Copyright (c) 2026 Seunghyun Ji

Anima LoRA's upstream NOTICE states that:

- the toolkit source code is MIT licensed;
- portions are derived from `kohya-ss/sd-scripts`, which is licensed under the
  Apache License 2.0;
- CircleStone / Anima base model weights are not covered by the MIT toolkit
  license and remain subject to the CircleStone Labs Non-Commercial License
  v1.0;
- adapters, fine-tuned checkpoints, merged checkpoints, and other artifacts
  derived from CircleStone / Anima weights may inherit the non-commercial terms
  of that model-weight license.

Users who enable the optional Anima LoRA integration are responsible for
installing Anima LoRA separately and complying with its source-code licenses,
third-party notices, model-weight licenses, and any license terms that apply to
their own trained artifacts or generated outputs.

Relevant upstream files:

- https://github.com/sorryhyun/anima_lora/blob/main/LICENSE
- https://github.com/sorryhyun/anima_lora/blob/main/NOTICE
- https://github.com/sorryhyun/anima_lora/blob/main/LICENSE-APACHE
