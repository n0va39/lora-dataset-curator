# Build and Distribution

최종 목표는 Windows에서 실행 가능한 `.exe` 파일로 배포하는 것이다.

초기 빌드 도구는 PyInstaller를 사용한다.

## 1. 개발 환경 준비

```powershell
uv sync --extra gui --extra image --extra build --extra dev
```

## 2. 테스트

```powershell
uv run pytest
```

## 3. CLI 실행 확인

```powershell
uv run lora-dataset-curator scan "D:\path\to\dataset"
```

또는 JSON 출력:

```powershell
uv run lora-dataset-curator scan "D:\path\to\dataset" --json
```

GUI 실행:

```powershell
uv run lora-dataset-curator gui "D:\path\to\dataset"
```

중복/유사 그룹 분석:

```powershell
uv run lora-dataset-curator duplicates "D:\path\to\dataset"
uv run lora-dataset-curator duplicates "D:\path\to\dataset" --perceptual
```

인자 없이 실행하면 GUI를 기본으로 연다.

```powershell
uv run lora-dataset-curator
```

## 4. Windows EXE 빌드

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

출력 파일:

```text
dist/LoRA-Dataset-Curator.exe
```

## 5. PyInstaller 기본 방침

초기에는 console one-file exe를 목표로 한다. 같은 exe에서 `scan`, `plan`, `gui` 명령을 실행한다.
인자 없이 실행하면 GUI를 연다.

```powershell
uv run pyinstaller --noconfirm --clean --onefile --name "LoRA-Dataset-Curator" --specpath "build" --paths "src" "scripts/entrypoint.py"
```

GUI 전용 exe로 분리하는 단계에서는 콘솔 창을 숨기기 위해 `--windowed` 옵션을 검토한다.

```powershell
uv run pyinstaller --noconfirm --clean --onefile --windowed --name "LoRA-Dataset-Curator" --specpath "build" --paths "src" "scripts/entrypoint.py"
```

## 6. 주의사항

- CLI와 GUI를 같은 exe에서 제공하는 동안은 `--windowed`를 기본값으로 쓰지 않는다.
- 빌드 전 반드시 `pytest`를 통과해야 한다.
- 파일 삭제 기능은 exe 배포 전까지 기본 비활성화한다.
- 배포용 exe는 샘플 데이터셋으로 scan, plan, duplicates, gui 실행을 확인한 뒤 릴리스한다.
- PySide6, OpenCV, FAISS 같은 의존성이 추가되면 PyInstaller hidden import 또는 spec 파일 수정이 필요할 수 있다.

## 7. 향후 배포 계획

1. PySide6 GUI MVP 개선
2. GUI 전용 windowed exe 분리 검토
3. 샘플 데이터셋으로 smoke test
4. GitHub Releases에 exe 업로드
5. README에 다운로드/실행 방법 추가
