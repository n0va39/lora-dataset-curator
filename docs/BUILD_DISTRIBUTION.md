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

## 4. Windows EXE 빌드

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

출력 파일:

```text
dist/LoRA-Dataset-Curator.exe
```

## 5. PyInstaller 기본 방침

초기에는 one-file exe를 목표로 한다.

```powershell
uv run pyinstaller --noconfirm --clean --onefile --name "LoRA-Dataset-Curator" --paths "src" "scripts/entrypoint.py"
```

GUI가 붙은 뒤에는 콘솔 창을 숨기기 위해 `--windowed` 옵션을 검토한다.

```powershell
uv run pyinstaller --noconfirm --clean --onefile --windowed --name "LoRA-Dataset-Curator" --paths "src" "scripts/entrypoint.py"
```

## 6. 주의사항

- 실제 GUI가 붙기 전까지는 `--windowed`를 기본값으로 쓰지 않는다.
- 빌드 전 반드시 `pytest`를 통과해야 한다.
- 파일 삭제 기능은 exe 배포 전까지 기본 비활성화한다.
- 배포용 exe는 샘플 데이터셋으로 scan, plan, quarantine 동작을 확인한 뒤 릴리스한다.
- PySide6, OpenCV, FAISS 같은 의존성이 추가되면 PyInstaller hidden import 또는 spec 파일 수정이 필요할 수 있다.

## 7. 향후 배포 계획

1. CLI 기반 MVP exe 생성
2. PySide6 GUI 추가
3. GUI exe 빌드 확인
4. 샘플 데이터셋으로 smoke test
5. GitHub Releases에 exe 업로드
6. README에 다운로드/실행 방법 추가
