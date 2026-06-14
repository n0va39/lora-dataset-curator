# Project Plan

이 문서는 LoRA Dataset Curator를 Codex에서 단계적으로 구현하기 위한 작업 계획이다.

## 1. 프로젝트 목적

LoRA 학습용 이미지 데이터셋을 사람이 빠르게 검수하고 정리할 수 있는 로컬 GUI 프로그램을 만든다.

이 프로젝트는 다운로드 도구가 아니다. 이미지와 caption, metadata는 이미 준비되어 있다고 가정한다.

주요 목적은 다음과 같다.

- 이미지와 연결된 `.txt`, `.json` 파일을 함께 관리한다.
- Danbooru 계열 metadata를 읽어서 검수 화면에 표시한다.
- 중복 또는 거의 동일한 이미지를 자동으로 후보 그룹으로 묶는다.
- 그룹 안에서 보존 우선순위가 높은 이미지를 먼저 보여준다.
- 최종 keep, move, delete, quarantine 판단은 사람이 한다.
- 처리 결과를 로그로 남긴다.

## 2. 전제

이미지와 태그 다운로드는 별도 프로그램에서 수행한다.

우선 연동 대상:

- <https://github.com/n0va39/danbooru-downloader>

`danbooru-downloader`에서 저장 가능한 post id, md5, source URL, rating, tag category 정보를 최대한 활용한다.

## 3. 비목표

초기 구현에서는 다음을 하지 않는다.

- Danbooru/Gelbooru 다운로드 기능 구현
- Civitai 업로드 기능 구현
- LoRA 학습 실행
- 자동 caption 생성
- 자동 태그 번역
- 완전 자동 삭제

파일 삭제는 위험하므로 MVP에서는 quarantine 또는 dry-run 중심으로 구현한다.

## 4. 지원할 입력 구조

우선 두 가지 구조를 지원한다.

### 4.1 같은 폴더 구조

```text
dataset/
  1234567.jpg
  1234567.txt
  1234567.json
  1234568.png
  1234568.txt
  1234568.json
```

### 4.2 분리 폴더 구조

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

파일 연결은 기본적으로 stem 기준으로 한다.

예시:

```text
1234567.jpg -> 1234567.txt -> 1234567.json
```

## 5. 데이터 모델

### 5.1 ImageRecord

이미지 하나를 표현하는 기본 단위.

필드 후보:

```text
id
image_path
caption_path
metadata_path
stem
extension
width
height
file_size
sha256
md5
post_id
source_url
rating
tags_artist
tags_character
tags_copyright
tags_general
tags_meta
caption_text
review_status
created_at
updated_at
```

### 5.2 SimilarityPair

이미지 두 개의 유사도 관계.

```text
image_id_a
image_id_b
sha256_match
md5_match
phash_distance
dhash_distance
ssim_score
embedding_score
tag_similarity
pair_status
```

### 5.3 DuplicateGroup

유사 이미지 후보 묶음.

```text
group_id
image_ids
recommended_keep_id
group_status
created_by
created_at
updated_at
```

### 5.4 ReviewAction

사용자가 내린 판단 기록.

```text
action_id
image_id
group_id
action
target_path
reason
timestamp
```

## 6. 유사 이미지 탐지 전략

초기에는 빠르고 안전한 방식부터 구현한다.

### 6.1 완전 동일 파일

- SHA256 계산
- 같은 SHA256이면 확정 duplicate 후보

### 6.2 Danbooru metadata 기반 동일성

- metadata에 md5가 있으면 사용
- post_id가 같으면 같은 원본 post 계열로 표시
- source URL이 같으면 보조 정보로 표시

### 6.3 Perceptual hash

- pHash
- dHash
- Hamming distance 기반 후보 생성

초기 threshold는 보수적으로 둔다.

```text
phash_distance <= 6
dhash_distance <= 6
```

이 값은 UI 설정에서 바꿀 수 있게 한다.

### 6.4 SSIM

pHash/dHash로 후보가 된 pair에 대해서만 계산한다.

목적:

- 같은 이미지의 리사이즈/압축 차이를 더 정확히 확인
- 모든 pair에 대해 계산하지 않음

### 6.5 Embedding 기반 유사도

후기 단계에서 추가한다.

- OpenCLIP 또는 DINO 계열 모델
- FAISS index
- top-k 후보 생성

주의:

임베딩 유사도는 같은 캐릭터, 같은 작가, 비슷한 구도까지 잡을 수 있다. 자동 삭제 기준으로 쓰지 않는다.

## 7. 그룹화 정책

SimilarityPair를 그래프로 보고 연결 요소를 DuplicateGroup으로 만든다.

기본 그룹 생성 조건:

```text
sha256_match == true
or md5_match == true
or phash_distance <= threshold
or dhash_distance <= threshold
```

그룹 상태:

```text
pending
confirmed_duplicate
alternate
false_positive
split
completed
```

사용자가 그룹에서 이미지를 분리할 수 있어야 한다.

## 8. 품질 우선순위 추천

그룹 안에서 먼저 보여줄 이미지를 추천한다.

점수 계산 후보:

```text
resolution_score
file_size_score
metadata_score
caption_score
format_score
watermark_penalty
sample_penalty
```

기본 우선순위:

1. post_id, md5, source가 있는 이미지
2. 해상도가 높은 이미지
3. 파일 크기가 큰 이미지
4. caption/tag 정보가 풍부한 이미지
5. PNG 또는 손실이 적은 형식
6. sample/resized/compressed로 보이는 파일명은 감점

추천은 자동 판단이 아니다. UI에서 사람이 확인할 기준으로만 사용한다.

## 9. GUI 요구사항

초기 GUI는 PySide6를 우선 검토한다.

### 9.1 메인 화면

필수 요소:

- 입력 디렉토리 선택
- 출력 디렉토리 선택
- scan 버튼
- 진행률 표시
- 현재 이미지 미리보기
- caption 표시/수정 영역
- metadata 표시 영역
- action 버튼

필수 action:

```text
keep
move
quarantine
skip
open file location
open source URL
```

### 9.2 유사 그룹 화면

그룹 내 이미지를 카드 형태로 보여준다.

각 카드 표시 정보:

```text
preview
filename
resolution
file_size
extension
post_id
md5
source_url exists
phash_distance
dhash_distance
ssim_score
tag_similarity
recommended rank
```

필수 action:

```text
keep this
quarantine others
mark as alternate
split from group
mark false positive
copy caption
merge caption
```

### 9.3 단일 이미지 검수

유사 이미지가 없어도 검수 화면에 표시한다.

표시 정보:

```text
preview
filename
resolution
file_size
caption
artist tags
character tags
copyright tags
general tags
post_id
source_url
rating
```

## 10. 파일 처리 원칙

이미지를 이동할 때 연결 파일도 함께 이동한다.

예시:

```text
1234567.jpg
1234567.txt
1234567.json
```

`1234567.jpg`가 이동되면 같은 stem의 `.txt`, `.json`도 함께 이동한다.

초기 출력 구조:

```text
output/
  keep/
  rejected/
  duplicate_quarantine/
  logs/
```

삭제 기능은 MVP에서는 실제 삭제하지 않고 quarantine으로 대체한다.

## 11. 로그와 되돌리기

모든 action은 CSV 또는 SQLite에 기록한다.

최소 로그 필드:

```text
timestamp
image_path
action
target_path
group_id
reason
```

후기에는 undo 기능을 구현한다.

## 12. 구현 단계

### MVP 1: 기본 스캔과 수동 검수

목표:

- 로컬 GUI 실행
- 입력 디렉토리 스캔
- 이미지와 `.txt`, `.json` 연결
- 단일 이미지 미리보기
- caption/metadata 표시
- keep/quarantine/skip 처리
- 로그 저장

작업 파일 후보:

```text
src/lora_dataset_curator/app.py
src/lora_dataset_curator/scanner.py
src/lora_dataset_curator/metadata.py
src/lora_dataset_curator/actions.py
src/lora_dataset_curator/ui/main_window.py
```

### MVP 2: 해시 기반 중복 후보

목표:

- SHA256 계산
- pHash/dHash 계산
- duplicate candidate 생성
- 그룹 단위 UI 표시
- 그룹 내 추천 순위 표시
- split/false positive 처리

작업 파일 후보:

```text
src/lora_dataset_curator/hashing.py
src/lora_dataset_curator/similarity.py
src/lora_dataset_curator/grouping.py
```

### MVP 3: metadata/tag 활용

목표:

- Danbooru metadata 필드 파싱
- artist/character/copyright/general/meta 태그 분리
- tag similarity 계산
- caption 병합/복사 기능
- source URL 열기

### MVP 4: 정밀 비교와 품질 검사

목표:

- SSIM 계산
- blur/dark/bright 검사
- 워터마크 가능성 보조 표시
- 그룹 추천 점수 개선

### MVP 5: 임베딩 기반 유사도

목표:

- OpenCLIP 또는 DINO 임베딩 추출
- FAISS index 생성
- top-k 유사 이미지 후보
- threshold 설정 UI

## 13. 초기 파일 구조

```text
lora-dataset-curator/
  README.md
  LICENSE
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
    PROJECT_PLAN.md
    DATA_MODEL.md
```

## 14. Codex 작업 규칙

Codex는 다음 규칙을 따른다.

1. 다운로드 기능을 구현하지 않는다.
2. 먼저 작고 실행 가능한 GUI를 만든다.
3. 파일 이동/삭제는 반드시 dry-run 또는 quarantine 중심으로 시작한다.
4. 이미지 파일만 이동하지 말고 같은 stem의 txt/json도 함께 처리한다.
5. 자동 삭제 기능은 만들지 않는다.
6. 유사도 결과는 사람이 판단할 후보로만 제시한다.
7. 각 기능은 작은 PR 단위로 나눈다.
8. 파일 처리, metadata 파싱, 그룹화 로직에는 테스트를 작성한다.
9. Windows 환경을 우선 고려한다.
10. 경로 처리는 pathlib 기반으로 작성한다.

## 15. 우선순위

가장 먼저 할 일:

1. `pyproject.toml` 생성
2. src 패키지 구조 생성
3. scanner 구현
4. metadata/caption 연결 구현
5. 최소 PySide6 GUI 구현
6. quarantine 기반 action 구현
7. 로그 저장 구현

그 다음 중복 탐지 기능을 붙인다.
