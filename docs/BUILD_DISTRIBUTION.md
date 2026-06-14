# Build and Distribution

Windows에서 실행 가능한 GUI exe와 릴리즈 zip을 만드는 절차입니다.

## 요구 사항

- Windows
- PowerShell
- uv

## 개발 환경 준비

```powershell
uv sync --extra gui --extra image --extra build --extra dev
```

## 검증

```powershell
uv run ruff check
uv run pytest
uv run lora-dataset-curator --help
uv run lora-dataset-curator
```

샘플 데이터셋이 있으면 아래도 확인합니다.

```powershell
uv run lora-dataset-curator scan "sample\000_raw"
uv run lora-dataset-curator duplicates "sample\000_raw" --perceptual
```

## exe 빌드

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

이 스크립트는 아래 작업을 수행합니다.

1. `uv sync --extra gui --extra image --extra build --extra dev`
2. `uv run pytest`
3. PyInstaller one-file windowed exe 빌드

출력:

```text
dist/
  LoRA-Dataset-Curator.exe
```

PyInstaller 옵션:

```powershell
uv run pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "LoRA-Dataset-Curator" `
  --specpath "build" `
  --paths "src" `
  "scripts/entrypoint.py"
```

`--windowed`를 사용하므로 exe 실행 시 cmd 창이 뜨지 않습니다.

## 릴리즈 zip 생성

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_release.ps1
```

이 스크립트는 `build_windows.ps1`을 먼저 실행한 뒤 릴리즈 폴더와 zip을 만듭니다.

출력:

```text
dist/
  LoRA-Dataset-Curator.exe
  LoRA-Dataset-Curator-0.1.0/
    LoRA-Dataset-Curator.exe
    README.md
    RELEASE.md
    docs/
      USER_GUIDE.md
      BUILD_DISTRIBUTION.md
  LoRA-Dataset-Curator-0.1.0.zip
```

## 배포 전 체크리스트

- `uv run ruff check` 통과
- `uv run pytest` 통과
- `scripts\build_windows.ps1` 성공
- `scripts\package_release.ps1` 성공
- exe 더블클릭 시 GUI 실행
- 입력/출력 폴더가 이전 실행값으로 복원되는지 확인
- 샘플 데이터셋 스캔 성공
- 중복 그룹 분석 성공
- 이동 결정 실행 시 출력 폴더 바로 아래에 파일 저장
- 삭제 예정 실행 시 `data\trash`로 이동
- `파일 > 휴지통 복구` 동작 확인
- `파일 > 캐시 삭제` 후 중복 분석 재실행 확인

## 앱 데이터

exe 배포 실행 시 기본 저장 위치:

```text
<exe folder>\data\
```

쓰기 권한이 없으면 Windows의 `%LOCALAPPDATA%\lora-dataset-curator`를 사용합니다.

주요 하위 폴더:

```text
data\
  config\
  profiles\
  cache\
  state\
  trash\
  logs\
```

## GitHub Release 업로드

업로드 대상:

```text
dist\LoRA-Dataset-Curator-0.1.0.zip
```

릴리즈 설명은 `RELEASE.md`의 해당 버전 항목을 사용합니다.

## 주의 사항

- `sample/`은 로컬 검증용이며 커밋/릴리즈 대상이 아닙니다.
- `data/`는 실행 중 생성되는 사용자 데이터이며 릴리즈 zip에 포함하지 않습니다.
- 자동 영구 삭제 기능은 제공하지 않습니다.
- `파일 > 휴지통 비우기`는 확인창 이후 휴지통 파일을 영구 삭제합니다.
