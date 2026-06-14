# LoRA Dataset Curator

LoRA 학습용 이미지·캡션 데이터셋을 검수하고 정리하기 위한 로컬 GUI 프로그램입니다.

이 프로젝트는 이미지와 캡션을 직접 다운로드하는 프로그램이 아니라, 이미 다운로드된 이미지·캡션·메타데이터를 불러와서 사람이 빠르게 검수할 수 있도록 돕는 도구입니다.

## 배경

LoRA 학습 데이터셋에서는 단순히 이미지 개수를 늘리는 것보다, 중복·저품질·부정확한 캡션을 줄이고 학습 목적에 맞는 이미지를 선별하는 것이 중요합니다.

특히 Danbooru 계열 이미지 데이터셋에서는 다음 문제가 자주 발생합니다.

- 같은 이미지의 원본, 샘플, 리사이즈 버전이 함께 존재함
- 거의 동일한 이미지가 해상도나 압축 형식만 다르게 저장됨
- 같은 post에서 파생된 이미지 또는 alternate 이미지가 섞임
- 태그는 비슷하지만 실제로는 다른 이미지가 존재함
- 이미지와 caption/txt/json 메타데이터를 함께 이동·삭제해야 함
- 학습에 사용할 이미지와 제외할 이미지를 사람이 직접 판단해야 함

이 프로그램은 자동 삭제 도구가 아니라, **중복·유사 이미지 후보를 묶어서 우선순위를 제시하고, 최종 판단은 사람이 하는 큐레이션 도구**를 목표로 합니다.

## 관련 프로젝트

이미지와 태그 다운로드는 별도 프로그램에서 수행합니다.

기본 입력 데이터는 다음 프로젝트의 출력 구조와 연동하는 것을 우선 고려합니다.

- <https://github.com/n0va39/danbooru-downloader>

`danbooru-downloader`에서 저장하는 post id, source URL, md5, rating, tag 정보 등을 가능하면 보존하고, 검수 과정에서 활용할 수 있게 설계합니다.

## 핵심 목표

1. 원하는 디렉토리의 이미지를 순차적으로 검수한다.
2. 각 이미지에 연결된 caption/txt/json/tag metadata를 함께 표시한다.
3. 거의 동일하거나 유사한 이미지를 자동으로 그룹화한다.
4. 그룹 안에서 어떤 이미지가 더 보존 우선순위가 높은지 추천한다.
5. 사람이 직접 keep, move, delete, split, ignore를 결정한다.
6. 결정 결과에 따라 이미지와 연결된 캡션/메타데이터를 함께 이동하거나 삭제한다.
7. LoRA 학습용으로 정리된 출력 디렉토리를 만든다.

## 비목표

초기 버전에서는 다음 기능을 직접 담당하지 않습니다.

- Danbooru 이미지 다운로드
- Civitai 모델 업로드
- LoRA 학습 실행
- 자동 캡션 생성
- 자동 태그 번역
- 완전 자동 데이터셋 정리

## 기본 사용 흐름

```text
1. danbooru-downloader 등으로 이미지와 태그/메타데이터 다운로드
2. LoRA Dataset Curator에서 입력 디렉토리 선택
3. 이미지, 캡션, 메타데이터 스캔
4. 해시/이미지 유사도/태그 유사도 기반으로 유사 이미지 그룹 생성
5. 그룹 단위 또는 단일 이미지 단위로 검수
6. 사람이 keep / move / delete / split / ignore 결정
7. 이미지와 관련 caption/metadata를 함께 처리
8. 정리된 학습용 디렉토리와 검수 로그 출력
```

## 입력 구조 예시

초기 구현에서는 다음과 같은 구조를 우선 지원합니다.

```text
dataset/
  images/
    1234567.jpg
    1234568.png
  captions/
    1234567.txt
    1234568.txt
  metadata/
    1234567.json
    1234568.json
```

또는 이미지와 caption이 같은 폴더에 있는 구조도 지원 대상으로 둡니다.

```text
dataset/
  1234567.jpg
  1234567.txt
  1234567.json
  1234568.png
  1234568.txt
  1234568.json
```

## 메타데이터 활용 계획

가능하면 이미지마다 다음 정보를 읽어옵니다.

| 필드 | 용도 |
|---|---|
| post_id | 원본 post 추적, 같은 post 파생 파일 확인 |
| md5 | Danbooru 기준 동일 이미지 추적 |
| source | 원본 URL 또는 참조 URL 표시 |
| rating | 필터링/검수 보조 |
| tag_string | 전체 태그 표시 |
| tag_string_artist | 작가 태그 비교 |
| tag_string_character | 캐릭터 태그 비교 |
| tag_string_copyright | 작품 태그 비교 |
| tag_string_general | 일반 태그 비교 |
| tag_string_meta | 품질/해상도/메타 태그 보조 |
| width / height | 보존 우선순위 계산 |
| file_ext | 원본 형식 판단 |
| file_size | 압축/원본성 판단 보조 |

## 유사 이미지 그룹화

유사 이미지 판단은 여러 기준을 조합합니다.

### 1. 파일 해시

완전히 같은 파일을 찾습니다.

- SHA256 또는 BLAKE3
- 같은 파일이면 자동으로 duplicate group 후보에 포함

### 2. 원본 메타데이터 해시

Danbooru에서 제공되는 md5 등을 사용합니다.

- 같은 md5이면 같은 원본 이미지일 가능성이 높음
- post_id가 같으면 같은 post에서 온 파일로 표시

### 3. Perceptual hash

리사이즈, 재압축, 포맷 변경된 거의 동일 이미지를 찾습니다.

- pHash
- dHash
- wHash
- Hamming distance 기반 후보 생성

### 4. 정밀 이미지 비교

perceptual hash로 가까운 후보에 대해 추가 비교합니다.

- SSIM
- resize 후 픽셀 구조 비교
- 크롭/리사이즈 차이에 대한 보조 판단

### 5. 임베딩 기반 유사도

후기 버전에서 추가합니다.

- OpenCLIP 또는 DINOv2 계열 임베딩
- FAISS 기반 top-k 검색
- 단순 중복이 아니라 시각적으로 비슷한 이미지 후보 탐색

주의: 임베딩 유사도는 같은 캐릭터, 같은 작가, 비슷한 구도도 높게 나올 수 있으므로 자동 삭제 기준으로 사용하지 않습니다.

## 유사 그룹 상태 모델

Hydrus식 관계 모델을 참고해 다음 상태를 둡니다.

| 상태 | 의미 |
|---|---|
| pending | 아직 판단하지 않은 후보 |
| duplicate | 사실상 같은 이미지 |
| alternate | 같은 post/주제/구도 계열이지만 별도 이미지 |
| false_positive | 유사 후보였지만 관련 없음 |
| split | 기존 그룹에서 분리됨 |
| keep | 학습용으로 유지 |
| move | 다른 디렉토리로 이동 |
| delete | 삭제 또는 휴지통 이동 |
| quarantine | 바로 삭제하지 않고 격리 |

## 품질 우선순위 추천

유사 이미지 그룹 안에서 어떤 이미지를 먼저 보여줄지 자동으로 계산합니다.

우선순위 후보 기준:

1. 해상도가 높은 이미지
2. 파일 크기가 큰 이미지
3. 원본 post_id/source/md5가 있는 이미지
4. PNG 또는 손실이 적은 형식
5. 워터마크 가능성이 낮은 이미지
6. caption/tag 정보가 더 풍부한 이미지
7. explicit한 sample/resized/compressed 표시가 적은 이미지
8. 사용자가 이전에 선호한 규칙과 일치하는 이미지

단, 학습용 데이터셋에서는 무조건 최대 해상도가 항상 좋은 것은 아니므로, 추천은 자동 판단이 아니라 사람이 확인할 기준으로만 사용합니다.

## 단일 이미지 검수

유사 이미지가 없는 경우에도 이미지를 그냥 통과시키지 않고 단일 이미지 검수 화면을 제공합니다.

표시 정보:

- 이미지 미리보기
- 파일명
- 해상도
- 파일 크기
- caption 내용
- 태그 목록
- artist / character / copyright 태그
- post id
- source URL
- rating
- 검수 상태

가능한 액션:

- keep
- move to selected directory
- delete
- quarantine
- edit caption
- open source URL
- open file location
- skip

## GUI 요구사항

### 메인 검수 화면

- 왼쪽: 현재 이미지 또는 유사 이미지 그룹
- 오른쪽: caption, tag, metadata, score 정보
- 하단: 액션 버튼
- 상단: 진행률, 필터, 정렬 옵션

### 유사 이미지 그룹 화면

그룹 내부 이미지를 품질 추천 순으로 보여줍니다.

각 이미지 카드에 표시할 정보:

- 미리보기
- 해상도
- 파일 크기
- 확장자
- post_id
- md5
- source 유무
- pHash/dHash distance
- SSIM score
- tag similarity
- 추천 순위

지원 액션:

- 이 이미지를 keep
- 나머지를 quarantine
- 이 이미지를 delete
- 그룹에서 split
- 두 이미지를 duplicate로 확정
- alternate로 표시
- false positive로 표시
- caption 병합 또는 복사

## 파일 처리 원칙

삭제는 기본적으로 즉시 영구 삭제하지 않습니다.

초기 기본 동작:

```text
output/
  keep/
  rejected/
  duplicate_quarantine/
  logs/
```

이미지를 이동할 때 관련 파일도 함께 처리합니다.

예시:

```text
1234567.jpg
1234567.txt
1234567.json
```

`1234567.jpg`를 이동하면 `.txt`, `.json`도 같이 이동합니다.

## 검수 로그

모든 판단은 나중에 되돌릴 수 있도록 로그로 남깁니다.

예시:

```csv
image_path,action,target_path,group_id,reason,timestamp
images/1234567.jpg,keep,output/keep/1234567.jpg,G0001,best_resolution,2026-06-14T12:00:00+09:00
images/1234568.jpg,quarantine,output/duplicate_quarantine/1234568.jpg,G0001,duplicate_candidate,2026-06-14T12:00:03+09:00
```

## 데이터베이스

초기 버전에서는 SQLite를 사용합니다.

주요 테이블 후보:

- images
- captions
- metadata
- hashes
- similarity_pairs
- duplicate_groups
- review_actions
- settings

## 권장 기술 스택

초기 구현:

- Python 3.11+
- PySide6 또는 Gradio
- Pillow
- OpenCV
- imagehash
- scikit-image
- pandas
- SQLite

후기 구현:

- OpenCLIP
- FAISS
- DuckDB
- ONNX Runtime 또는 PyTorch

## MVP 범위

첫 구현 목표는 너무 넓히지 않습니다.

### MVP 1

- 입력 디렉토리 스캔
- 이미지와 같은 stem의 txt/json 연결
- 이미지 미리보기
- caption/tag/metadata 표시
- keep/move/delete/quarantine 처리
- 처리 로그 저장

### MVP 2

- SHA256 기반 완전 중복 탐지
- pHash/dHash 기반 near-duplicate 후보 생성
- 유사 이미지 그룹 UI
- 그룹 안에서 우선순위 추천
- split / false positive 처리

### MVP 3

- SSIM 정밀 비교
- Danbooru metadata 필드 활용
- artist/character/copyright 태그 유사도 점수
- caption 병합/수정

### MVP 4

- OpenCLIP/DINO 임베딩 기반 유사 이미지 검색
- FAISS index
- outlier 이미지 탐지
- blur/dark/bright 품질 검사

## Codex 작업 지침

이 프로젝트를 Codex에서 진행할 때는 다음 원칙을 따른다.

1. 먼저 로컬에서 실행 가능한 최소 GUI를 만든다.
2. 다운로드 기능은 구현하지 않는다.
3. 파일 이동/삭제는 항상 dry-run 또는 quarantine을 먼저 지원한다.
4. 이미지와 연결된 txt/json 파일을 절대 누락하지 않는다.
5. 자동 삭제보다 사람이 판단할 수 있는 후보 정렬과 정보 표시를 우선한다.
6. 기능을 작은 단위로 나누어 PR을 만든다.
7. 모든 파일 처리 함수에는 테스트를 작성한다.
8. 실제 삭제 기능은 충분한 테스트 이후에만 활성화한다.

## 초기 디렉토리 구조 제안

```text
lora-dataset-curator/
  README.md
  pyproject.toml
  src/
    lora_dataset_curator/
      __init__.py
      app.py
      scanner.py
      metadata.py
      hashing.py
      similarity.py
      grouping.py
      actions.py
      database.py
      ui/
        __init__.py
        main_window.py
        image_card.py
        review_panel.py
  tests/
    test_scanner.py
    test_actions.py
    test_grouping.py
  docs/
    architecture.md
    data-model.md
```

## 라이선스

초기에는 미정입니다.

공개 배포를 고려한다면 MIT License를 우선 검토합니다.
