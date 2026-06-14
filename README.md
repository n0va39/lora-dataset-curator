# LoRA Dataset Curator

LoRA 학습용 이미지·캡션 데이터셋을 검수하고 정리하기 위한 로컬 GUI 프로그램입니다.

이 프로젝트는 이미지와 캡션을 직접 다운로드하지 않습니다. 이미 다운로드된 이미지, caption, metadata를 불러와서 중복·유사 이미지 후보를 묶고, 사람이 keep/move/delete/quarantine을 빠르게 판단할 수 있게 하는 큐레이션 도구입니다.

## 목표

- 이미지와 연결된 `.txt`, `.json` 메타데이터를 함께 관리
- Danbooru post id, md5, source, tag 정보를 검수에 활용
- 거의 동일하거나 유사한 이미지를 그룹화
- 그룹 안에서 보존 우선순위가 높은 이미지를 먼저 표시
- 최종 판단은 사람이 수행
- 선택한 출력 디렉토리로 이미지와 캡션을 함께 이동하거나 격리

## 실행

개발 환경을 준비합니다.

```powershell
uv sync --extra gui --extra image --extra build --extra dev
```

CLI로 데이터셋을 스캔합니다.

```powershell
uv run lora-dataset-curator scan sample/000_raw
```

중복/유사 그룹 후보를 분석합니다.

```powershell
uv run lora-dataset-curator duplicates sample/000_raw
```

pHash/dHash 기반 유사 이미지 후보까지 보려면 아래처럼 실행합니다. 큰 데이터셋에서는 시간이 걸릴 수 있습니다.

```powershell
uv run lora-dataset-curator duplicates sample/000_raw --perceptual
```

GUI를 실행합니다.

```powershell
uv run lora-dataset-curator gui sample/000_raw
```

인자 없이 실행해도 GUI가 열립니다.

```powershell
uv run lora-dataset-curator
```

현재 GUI의 action 버튼은 dry-run 이동 계획만 표시합니다. 실제 파일 이동이나 삭제는 수행하지 않습니다.
GUI의 `Duplicate Groups` 탭에서 `Analyze`를 누르면 SHA256/metadata 기준 그룹을 볼 수 있습니다.
`Use pHash/dHash`를 켜면 perceptual hash 기반 유사 후보도 함께 계산합니다.

## GUI 기본 사용 방법

1. `입력 폴더`에 검수할 데이터셋 폴더를 지정합니다.
2. `출력 폴더`에 keep/quarantine 계획을 만들 기준 폴더를 지정합니다.
3. `스캔`을 누르면 이미지, caption, metadata 연결 상태를 읽습니다.
4. 왼쪽 목록에서 이미지를 선택하면 오른쪽에서 미리보기, 캡션, 메타데이터를 확인합니다.
5. `보관`, `이동`, `격리`, `건너뛰기` 버튼은 실제 파일을 옮기지 않고 dry-run 이동 계획만 보여줍니다.
6. `중복 그룹` 탭에서 `분석`을 누르면 중복 후보 그룹을 계산합니다.
7. `pHash/dHash 사용`을 켜면 리사이즈나 압축 차이가 있는 유사 이미지 후보도 찾습니다. 이미지가 많으면 시간이 오래 걸릴 수 있습니다.

스캔과 중복 분석 중에는 하단 진행률이 갱신됩니다. 작업은 백그라운드에서 실행되어 창이 멈춘 것처럼 보이는 현상을 줄입니다.

Windows 실행 파일을 빌드합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

빌드된 exe는 더블클릭하거나 인자 없이 실행하면 GUI가 열립니다.

## 관련 프로젝트

이미지와 태그 다운로드는 별도 도구에서 수행합니다.

- <https://github.com/n0va39/danbooru-downloader>

## 개발 문서

상세한 구현 계획과 Codex 작업 지침은 아래 문서에 정리합니다.

- [Project Plan](docs/PROJECT_PLAN.md)
- [Build and Distribution](docs/BUILD_DISTRIBUTION.md)

## License

MIT License.
