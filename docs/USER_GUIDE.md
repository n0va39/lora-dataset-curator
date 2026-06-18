# User Guide

## 목적

LoRA Dataset Curator는 이미 준비된 이미지 데이터셋을 검수하고, 학습에 사용할 파일만 출력 폴더로 이동하기 위한 로컬 GUI 도구입니다.

프로그램은 다운로드, API 호출, 자동 영구 삭제를 수행하지 않습니다.

## 데이터셋 구조

지원하는 기본 구조:

```text
dataset/
  image_001.png
  image_001.txt
  image_001.json
```

분리 구조:

```text
dataset/
  images/
    image_001.png
  captions/
    image_001.txt
  metadata/
    image_001.json
```

이미지와 `.txt`, `.json`은 같은 stem을 기준으로 연결됩니다.

## 실행

exe 배포본:

```text
LoRA-Dataset-Curator.exe
```

개발 환경:

```powershell
uv run lora-dataset-curator
```

CLI 경로 확인:

```powershell
uv run lora-dataset-curator paths
```

## 기본 검수

1. `입력 폴더`를 선택한다.
2. `출력 폴더`를 선택한다.
3. `스캔`을 누른다.
4. 표에서 이미지를 선택한다.
5. 오른쪽 패널에서 미리보기, caption, 크기, 파일 정보를 확인한다.
6. 아래 결정 중 하나를 지정한다.

결정:

- `A 이동 결정`: 출력 폴더 바로 아래로 이미지와 sidecar를 이동한다.
- `D 삭제 예정`: 앱 data 휴지통으로 이미지와 sidecar를 이동한다.
- `S 보류`: 실행 대상에서 제외한다.

단축키:

- `A`: 이동 결정
- `D`: 삭제 예정
- `S`: 보류
- `Left/Right`: 이전/다음 이미지

## 중복 그룹

`중복 그룹` 탭에서 `분석`을 누르면 중복/유사 이미지 후보를 그룹으로 표시합니다.

분석 기준:

- SHA256/MD5
- metadata의 post id, source, md5
- pHash/dHash

`pHash/dHash 사용`은 기본으로 켜져 있습니다. 이미지가 많은 데이터셋은 최초 분석 시간이 걸릴 수 있습니다. 이후에는 `data/cache`에 저장된 해시와 그룹 캐시를 사용합니다.

## Anima LoRA PE 유사도 분석

Anima LoRA가 별도로 설치되어 있으면 PE-Spatial grid matching 기반 유사 이미지 분석을 사용할 수 있습니다. 이 방식은 전체 이미지 해시만 비교하는 pHash/dHash보다 crop, 부분 편집, 작은 영역 차이에 더 강합니다.

전제 조건:

- Anima LoRA가 로컬에 설치되어 있어야 한다.
- Anima LoRA의 `.venv`가 유효해야 한다.
- Anima LoRA 쪽 PE-Spatial 모델/의존성이 준비되어 있어야 한다.

예시 `.venv` 경로:

```text
D:\ComfyUI\Anima_Lora_work\anima_lora_gui\.venv
```

사용 순서:

1. `스캔`을 먼저 실행한다.
2. `중복 그룹` 탭에서 `Anima venv`를 누른다.
3. Anima LoRA 설치 폴더 안의 `.venv` 폴더를 선택한다.
4. 경로가 유효하면 `Anima 임베딩 분석` 버튼이 활성화된다.
5. 필요하면 기준값을 조정한다.
6. `Anima 임베딩 분석`을 누른다.

기준값:

- `cell`: grid cell 하나가 매칭되었다고 볼 cosine 기준. 기본값은 `0.93`이며, 높을수록 엄격하다.
- `match`: 전체 grid cell 중 매칭되어야 하는 비율. 기본값은 `0.25`이며, 높을수록 엄격하다.
- `device`: Anima LoRA 실행 장치. 일반적으로 `cuda`, 테스트나 GPU가 없는 환경에서는 `cpu`.

동작 방식:

- LoRA Dataset Curator는 Anima LoRA를 포함하지 않는다.
- 지정된 `.venv`의 Python으로 Anima LoRA의 `scripts/curate/build_groups.py`를 외부 프로세스로 실행한다.
- 결과 JSON을 읽어 현재 중복 그룹 탭에 `E0001` 형식의 그룹으로 표시한다.
- PE-Spatial feature cache는 앱 data의 `cache/anima_near_twin/` 아래에 저장된다.

라이선스:

- Anima LoRA source code는 upstream 기준 MIT License이다.
- Anima LoRA는 일부 Apache License 2.0 코드 유래 사항과 별도 NOTICE를 포함한다.
- Anima/CircleStone 모델 가중치와 그 파생물에는 별도의 non-commercial 모델 라이선스가 적용될 수 있다.
- 자세한 내용은 `THIRD_PARTY_NOTICES.md`를 확인한다.

## 추천 점수

그룹 안에서는 보존 우선순위가 높은 이미지가 먼저 표시됩니다.

현재 점수는 아래 요소를 기반으로 계산됩니다.

- 해상도
- 파일 크기
- caption/tag 수
- metadata 연결 여부

점수는 자동 결정을 의미하지 않습니다. 최종 판단은 사용자가 지정합니다.

## 큰 미리보기

`큰 미리보기` 버튼을 누르면 별도 창에서 이미지를 크게 확인할 수 있습니다.

기능:

- 왼쪽 썸네일 목록
- 방향키 이동
- `A`, `D`, `S` 단축키
- `항상 위` 토글
- crop 프레임 조정

## Crop

이미지별 crop:

- `자르기 적용`을 켠다.
- 왼쪽, 위, 오른쪽, 아래에서 잘라낼 픽셀 수를 입력한다.
- 큰 미리보기에서 사각형 프레임의 모서리나 변을 드래그해 조절할 수 있다.
- 프레임이 전체 이미지 크기이면 crop 설정은 저장되지 않고 실행되지 않는다.

일괄 비율 crop:

- `일괄 비율`에서 방향별 비율을 입력한다.
- `비율 일괄 적용`을 누르면 스캔된 모든 이미지에 이미지 크기 기준으로 crop 설정을 저장한다.
- 모든 값이 0%이면 기존 crop 설정을 해제한다.

crop은 `실행` 단계에서 이동 결정 파일에 적용됩니다. 원본 파일이 사라진 경우 해당 crop/이동 작업은 건너뜁니다.

## 실행

`실행` 버튼은 `이동 결정` 또는 `삭제 예정` 상태인 항목만 처리합니다.

처리 결과:

- 이동 결정: 출력 폴더 바로 아래로 이동
- 삭제 예정: 앱 data 휴지통으로 이동
- 보류: 처리하지 않음

이미지와 같은 stem의 `.txt`, `.json` sidecar도 함께 처리됩니다.

## 휴지통

삭제 예정 파일은 영구 삭제하지 않고 앱 data 휴지통으로 이동합니다.

메뉴:

- `파일 > 휴지통 복구`: 원래 경로로 복구
- `파일 > 휴지통 비우기`: 확인 후 영구 삭제

복구 시 원래 위치에 같은 파일이 있으면 덮어쓰지 않고 건너뜁니다.

## 캐시 관리

메뉴:

- `파일 > 데이터 폴더 열기`
- `파일 > 캐시 폴더 열기`
- `파일 > 캐시 삭제`

`캐시 삭제`는 아래만 삭제합니다.

- 해시 캐시
- 중복 그룹 캐시

아래 데이터는 유지됩니다.

- 설정
- 결정 상태
- crop 설정
- 휴지통
- 로그

## 저장 위치

exe 배포 실행 시 기본 저장 위치:

```text
<exe folder>/data/
```

쓰기 권한이 없으면 Windows의 `%LOCALAPPDATA%\lora-dataset-curator`를 사용합니다.

개발 환경에서는 환경변수로 지정할 수 있습니다.

```powershell
$env:LORA_DATASET_CURATOR_HOME="D:\path\to\data"
```

## 문제 해결

스캔 후 파일을 수동으로 이동한 경우:

- 실행 시 사라진 파일은 건너뜁니다.
- 필요하면 다시 `스캔`을 눌러 목록을 갱신합니다.

중복 분석이 오래 걸리는 경우:

- 첫 분석은 pHash/dHash 계산 때문에 시간이 걸릴 수 있습니다.
- 이후 분석은 캐시를 사용합니다.
- 캐시가 꼬였다고 판단되면 `파일 > 캐시 삭제` 후 다시 분석합니다.

복구가 일부만 되는 경우:

- 원래 위치에 같은 파일이 있으면 복구하지 않습니다.
- 해당 파일은 휴지통에 남습니다.
