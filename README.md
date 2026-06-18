# LoRA Dataset Curator

LoRA 학습용 이미지, caption, metadata 데이터셋을 로컬에서 검수하고 정리하는 Windows GUI 도구입니다.

이미지 다운로드나 Danbooru/Gelbooru API 호출은 포함하지 않습니다. 이미 준비된 이미지 폴더를 스캔하고, 유사 이미지 그룹을 확인한 뒤 사람이 이동/삭제 예정/보류 결정을 내리는 큐레이션 프로그램입니다.

## 주요 기능

- 이미지와 같은 stem의 `.txt`, `.json` sidecar 연결
- `images/`, `captions/`, `metadata/` 분리 구조 스캔
- SHA256, MD5, pHash, dHash 기반 중복/유사 이미지 그룹 분석
- 선택적 Anima LoRA PE-Spatial 임베딩 기반 유사 이미지 그룹 분석
- 그룹별 추천 keep 이미지 점수 표시
- 이미지 미리보기, 큰 미리보기, 방향키 이동
- `A` 이동 결정, `D` 삭제 예정, `S` 보류 단축키
- 이미지별 crop 설정 및 일괄 비율 crop 설정
- 결정 상태와 crop 설정 자동 저장
- 해시/중복 분석 캐시 저장
- 앱 data 휴지통 기반 삭제 예정 파일 보관, 복구, 비우기
- Windows `.exe` 배포 빌드

## 빠른 실행

개발 환경:

```powershell
uv sync --extra gui --extra image --extra build --extra dev
uv run lora-dataset-curator
```

Windows exe 빌드:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

릴리즈 zip 생성:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_release.ps1
```

빌드 결과:

```text
dist/
  LoRA-Dataset-Curator.exe
  LoRA-Dataset-Curator-0.1.0.zip
```

## 기본 사용 흐름

1. `입력 폴더`에 검수할 데이터셋 폴더를 지정한다.
2. `출력 폴더`에 이동 결정 파일을 저장할 폴더를 지정한다.
3. `스캔`을 눌러 이미지, caption, metadata 연결 상태를 확인한다.
4. `중복 그룹` 탭에서 `분석`을 눌러 유사 이미지 그룹을 만든다.
5. 큰 미리보기 또는 표에서 이미지를 확인한다.
6. `A`, `D`, `S` 또는 버튼으로 결정을 지정한다.
7. 필요한 경우 crop 설정을 지정한다.
8. `실행`을 눌러 결정된 작업을 수행한다.

이동 결정 파일은 출력 폴더 바로 아래에 저장됩니다. 삭제 예정 파일은 영구 삭제하지 않고 앱 data 휴지통으로 이동합니다.

## Anima LoRA PE 유사도 분석

기본 pHash/dHash 분석은 전체 이미지 해시를 비교하므로, 한쪽이 크게 crop된 이미지는 놓칠 수 있습니다. 이미 로컬에 Anima LoRA가 설치되어 있다면 `중복 그룹` 탭의 `Anima 임베딩 분석`을 사용해 PE-Spatial grid matching 기반 그룹을 만들 수 있습니다.

이 기능은 Anima LoRA를 앱에 포함하지 않습니다. 사용자가 지정한 Anima LoRA `.venv`의 Python으로 Anima LoRA의 grouping script를 외부 프로세스로 실행하고, 생성된 JSON 결과만 읽어 현재 그룹 탭에 표시합니다.

사용 순서:

1. Anima LoRA가 설치된 폴더의 `.venv` 경로를 확인한다.
   예: `D:\ComfyUI\Anima_Lora_work\anima_lora_gui\.venv`
2. LoRA Dataset Curator에서 `스캔`을 먼저 실행한다.
3. `중복 그룹` 탭에서 `Anima venv` 버튼을 누르고 해당 `.venv` 폴더를 선택한다.
4. `.venv`가 유효하면 `Anima 임베딩 분석` 버튼이 활성화된다.
5. 필요하면 `cell`, `match`, `device` 값을 조정한다.
6. `Anima 임베딩 분석`을 실행한다.

기준값:

- `cell`: grid cell 하나가 매칭되었다고 볼 cosine 기준입니다. 기본값은 `0.93`입니다. 높을수록 엄격합니다.
- `match`: 전체 grid cell 중 매칭되어야 하는 비율입니다. 기본값은 `0.25`입니다. 높을수록 엄격합니다.
- `device`: Anima LoRA가 사용할 장치입니다. 일반적으로 `cuda`를 사용하고, GPU가 없거나 테스트 목적이면 `cpu`를 사용할 수 있습니다.

주의:

- 이 기능은 Anima LoRA 설치, 해당 `.venv`, 필요한 모델/의존성이 준비되어 있어야 동작합니다.
- Anima LoRA 실행 실패 시 오류 로그에 외부 프로세스 출력이 기록됩니다.
- PE-Spatial feature cache는 앱 data의 `cache/anima_near_twin/` 아래에 저장됩니다.
- Anima LoRA와 Anima/CircleStone 모델 가중치의 라이선스는 별도로 적용됩니다. 자세한 내용은 [Third-Party Notices](THIRD_PARTY_NOTICES.md)를 확인하세요.

## 저장 위치

exe 배포 실행 시 앱 데이터는 기본적으로 exe 옆 `data/` 폴더에 저장됩니다. 해당 위치에 쓸 수 없으면 Windows의 `%LOCALAPPDATA%\lora-dataset-curator`를 사용합니다.

개발 또는 테스트에서는 `LORA_DATASET_CURATOR_HOME` 환경변수로 저장 위치를 지정할 수 있습니다.

```text
data/
  config/
    settings.json
  profiles/
    default.json
  cache/
    hashes.sqlite
    datasets/
      <dataset-id>/
        duplicate_groups.json
  state/
    decisions/
      <output-id>.json
    crops/
      <output-id>.json
  trash/
    <trash-item>/
      manifest.json
      image/caption/metadata files
  logs/
```

현재 저장 경로는 CLI에서 확인할 수 있습니다.

```powershell
uv run lora-dataset-curator paths
```

## 문서

- [User Guide](docs/USER_GUIDE.md)
- [Release Notes](RELEASE.md)
- [Build and Distribution](docs/BUILD_DISTRIBUTION.md)
- [Project Plan](docs/PROJECT_PLAN.md)
- [Third-Party Notices](THIRD_PARTY_NOTICES.md)

## 주의 사항

- 다운로드 기능은 제공하지 않습니다.
- API 호출 기능은 제공하지 않습니다.
- 삭제 예정 파일은 앱 휴지통으로 이동됩니다.
- `파일 > 휴지통 비우기`는 확인 후 휴지통 파일을 영구 삭제합니다.
- 실행 전 수동으로 파일을 옮긴 경우 해당 파일은 건너뜁니다.

## License

MIT License.

Optional Anima LoRA integration is an external-process integration with a
separately installed Anima LoRA environment. LoRA Dataset Curator does not bundle
Anima LoRA source code, dependencies, or model weights. See
[Third-Party Notices](THIRD_PARTY_NOTICES.md).
