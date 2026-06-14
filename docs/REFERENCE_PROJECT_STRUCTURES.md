# Reference Project Structures

이 문서는 LoRA Dataset Curator의 유사 이미지 탐지 구조를 설계하기 위해 참고할 만한 기존 프로젝트와 시스템 구조를 정리한 것이다.

목표는 특정 프로젝트를 그대로 복제하는 것이 아니라, 대량 이미지에서 전체 pair 비교를 피하고 사람이 검수할 수 있는 후보 그룹을 만드는 구조를 가져오는 것이다.

## 1. 공통 결론

대부분의 중복/유사 이미지 프로젝트는 다음 구조를 사용한다.

```text
scan
  ↓
feature/hash encoding
  ↓
cache/index
  ↓
candidate generation
  ↓
exact distance/scoring
  ↓
grouping/clustering
  ↓
manual or heuristic decision
```

LoRA Dataset Curator도 같은 방향으로 간다.

```text
전체 pair 비교 금지
→ 해시/메타데이터 캐싱
→ 후보 pair 생성
→ 후보에만 Hamming distance/SSIM 계산
→ Union-Find로 그룹화
→ 사람이 최종 판단
```

## 2. imagededup

Reference:

- https://idealo.github.io/imagededup/user_guide/finding_duplicates/
- https://github.com/idealo/imagededup

### 구조

`imagededup`은 먼저 이미지별 encoding을 만든 뒤, 그 encoding map을 기반으로 중복을 찾는다.

지원 방식:

```text
PHash
AHash
DHash
WHash
CNN
```

문서상 API 구조는 다음과 같다.

```python
from imagededup.methods import PHash

phasher = PHash()
duplicates = phasher.find_duplicates(
    image_dir="path/to/image/directory",
    max_distance_threshold=12,
    scores=True,
)
```

또는 encoding을 미리 만든 뒤 재사용할 수 있다.

```python
duplicates = phasher.find_duplicates(
    encoding_map=encoding_map,
    max_distance_threshold=12,
)
```

### 중요한 설계 포인트

`imagededup`은 탐지 결과를 단순 pair list가 아니라 dictionary 형태로 반환한다.

```text
{
  "image1.jpg": ["image1_duplicate1.jpg", "image1_duplicate2.jpg"],
  "image2.jpg": [...]
}
```

score를 켜면 Hamming distance 또는 cosine similarity도 함께 반환한다.

```text
{
  "image1.jpg": [("image1_duplicate1.jpg", score), ...]
}
```

### threshold 구조

문서 기준:

```text
hashing method:
  max_distance_threshold
  Hamming distance
  default: 10

CNN method:
  min_similarity_threshold
  cosine similarity
  default: 0.9
```

### 우리 프로젝트에 가져올 점

```text
1. 이미지별 encoding/hash를 먼저 계산한다.
2. encoding_map을 캐싱해서 재사용한다.
3. threshold 기반으로 후보를 만든다.
4. 결과는 pair list보다 group/dictionary 형태로 다룬다.
5. 자동 삭제용 list는 위험하므로, 수동 검수용 duplicate map을 우선 사용한다.
```

### 우리 프로젝트에서 다르게 할 점

`imagededup`은 일반 중복 이미지 탐지 라이브러리다. LoRA Dataset Curator는 caption/json/tag 파일까지 같이 관리해야 하므로, 다음이 추가로 필요하다.

```text
image_path
caption_path
metadata_path
post_id
source_md5
source_url
tag categories
review_status
```

즉, `imagededup`식 encoding/distance 구조는 참고하되, 결과 처리는 LoRA dataset 전용 group 모델로 감싸야 한다.

## 3. Czkawka

Reference:

- https://github.com/qarmin/czkawka

### 구조

Czkawka는 일반 중복 파일, 유사 이미지, 깨진 파일, 잘못된 확장자 등 여러 정리 기능을 가진 로컬 앱이다.

README 기준 구조적 특징:

```text
core library
CLI frontend
GUI frontend
cache support
multithreading
duplicate finder
similar image finder
```

프로젝트 폴더도 다음처럼 core와 frontend가 분리되어 있다.

```text
czkawka_core/
czkawka_cli/
czkawka_gui/
krokiet/
cedinia/
```

### 중요한 설계 포인트

Czkawka의 핵심은 UI와 core logic 분리다.

```text
czkawka_core
  → 중복/유사 이미지 탐지 로직

czkawka_cli
  → 자동화/스크립트용 실행 경로

czkawka_gui / krokiet
  → 사용자 검수 UI
```

또한 cache support를 제공하여 두 번째 이후 스캔을 빠르게 만든다.

### 우리 프로젝트에 가져올 점

```text
1. core logic과 GUI를 분리한다.
2. CLI는 유지한다.
3. GUI는 core API를 호출하는 껍데기로 만든다.
4. hash/metadata/thumbnail 결과는 cache한다.
5. 두 번째 스캔부터 변경된 파일만 재계산한다.
6. EXE 배포를 고려해 core dependency를 가볍게 유지한다.
```

### 우리 프로젝트 구조 제안

```text
src/lora_dataset_curator/
  scanner.py        # core
  metadata.py       # core
  hashing.py        # core
  similarity.py     # core
  grouping.py       # core
  actions.py        # core
  database.py       # core/cache
  app.py            # CLI
  ui/               # GUI frontend
```

초기 CLI가 존재해야 하는 이유:

```text
1. GUI 없이도 테스트 가능
2. Codex에서 실행 검증 쉬움
3. PyInstaller 빌드 전 core 동작 확인 가능
4. 나중에 batch mode 지원 가능
```

## 4. Pinterest web-scale near-duplicate system

Reference:

- https://arxiv.org/abs/2209.08433

### 구조

Pinterest의 near-duplicate 시스템은 web-scale 이미지에서 전체 비교를 피하기 위해 다음 3단계 구조를 사용한다.

```text
candidate generation
candidate selection
clustering
```

논문은 수십억 이미지 규모에서는 brute-force 비교가 불가능하므로, 후보를 먼저 줄이고, 후보만 다시 평가한 뒤, 마지막에 clustering하는 구조를 설명한다.

### 우리 프로젝트에 가져올 점

규모는 훨씬 작아도 구조는 동일하게 적용할 수 있다.

```text
candidate generation
  → sha256/source_md5/post_id group
  → pHash/dHash bucket
  → optional embedding top-k

candidate selection
  → Hamming distance
  → tag similarity
  → optional SSIM
  → grade A/B/C/D

clustering
  → Union-Find
  → DuplicateGroup
  → recommended_keep
```

### 우리 프로젝트용 변형

Pinterest 구조는 자동 시스템에 가깝지만, LoRA Dataset Curator는 사람이 검수하는 도구다.

따라서 최종 단계는 자동 제거가 아니라 다음 형태가 되어야 한다.

```text
cluster/group
  ↓
quality priority ranking
  ↓
manual keep/quarantine/split/alternate decision
```

## 5. LSH / bucket 방식

Reference:

- https://en.wikipedia.org/wiki/Locality-sensitive_hashing

### 구조

LSH는 비슷한 항목이 같은 bucket에 들어갈 가능성을 높이는 방식이다.

우리 프로젝트에서 pHash/dHash는 64-bit hash이므로, 전체 비교 대신 segment bucket을 만들 수 있다.

예시:

```text
phash = 9f8a3c12e0ffabcd

segment 0 = 9f8a
segment 1 = 3c12
segment 2 = e0ff
segment 3 = abcd
```

bucket key:

```text
("phash", 0, "9f8a")
("phash", 1, "3c12")
("phash", 2, "e0ff")
("phash", 3, "abcd")
```

같은 bucket에 들어온 이미지끼리만 후보 pair를 만든다.

### 우리 프로젝트에 가져올 점

```text
1. pHash/dHash 전체 pair 비교 금지
2. hash를 segment로 나눠 bucket index 생성
3. 같은 bucket 내부만 후보 pair 생성
4. 후보 pair에만 실제 Hamming distance 계산
5. threshold 이하만 similarity_pairs에 저장
```

### 후보 폭발 방지

```text
bucket_size_limit = 500
max_candidates_per_image = 100
aspect_ratio_filter = optional
same_post_or_md5_group = priority
```

큰 bucket은 단색 배경, 흰 배경, 비슷한 색감 이미지가 몰릴 수 있으므로 스킵하거나 더 세분화한다.

## 6. BK-tree 방식

### 구조

BK-tree는 거리 함수가 있는 값에서 threshold 이하의 이웃을 찾는 자료구조다.

pHash/dHash의 Hamming distance 검색에 잘 맞는다.

```text
insert all phash values into BK-tree
for each image:
  search neighbors within threshold
  create candidate pairs
```

### 장점

```text
Hamming distance 검색에 직접적
threshold 검색 구조가 명확함
Windows 환경에서도 라이브러리 없이 구현 가능
```

### 단점

```text
데이터 분포에 따라 성능 차이 있음
threshold가 커지면 후보가 많아짐
구현/테스트가 bucket 방식보다 조금 복잡함
```

### 우리 프로젝트 적용 순서

초기에는 bucket 방식으로 구현하고, 후보 수가 많거나 누락이 문제되면 BK-tree를 추가한다.

```text
MVP 2:
  hash bucket

MVP 3+:
  optional BK-tree backend
```

## 7. Hydrus Network 스타일 관계 모델

Reference:

- https://hydrusnetwork.github.io/hydrus/

### 구조적으로 참고할 점

Hydrus는 이미지 파일 관리와 tag 관리에 강한 로컬 미디어 관리 프로그램이다.

LoRA Dataset Curator가 참고할 핵심은 duplicate를 단순 삭제 목록으로 보지 않고 관계 상태로 관리하는 방식이다.

우리 프로젝트에는 다음 관계 모델이 필요하다.

```text
duplicate
alternate
false_positive
split
keep
quarantine
```

### 우리 프로젝트에 가져올 점

```text
1. 유사하다고 바로 삭제하지 않는다.
2. duplicate와 alternate를 구분한다.
3. false positive를 저장해서 다시 추천되지 않게 한다.
4. 그룹에서 수동 split을 지원한다.
5. 추천 대표 이미지와 실제 keep 판단을 분리한다.
```

## 8. LoRA Dataset Curator에 적용할 최종 구조

### 8.1 Scan phase

```text
input_dir
  ↓
iter image files
  ↓
link txt/json sidecars
  ↓
read metadata
  ↓
read image size
  ↓
create ImageRecord
```

### 8.2 Cache phase

```text
ImageRecord
  ↓
compute sha256
  ↓
compute source_md5/post_id from metadata
  ↓
compute pHash/dHash
  ↓
store in SQLite or cache file
```

### 8.3 Candidate generation phase

```text
sha256 group
source_md5 group
post_id group
pHash bucket
dHash bucket
```

결과:

```text
candidate_pairs
```

### 8.4 Candidate selection phase

```text
candidate_pairs
  ↓
Hamming distance
  ↓
tag similarity
  ↓
optional SSIM
  ↓
similarity grade
```

등급:

```text
A: sha256/source_md5 match
B: pHash/dHash very close
C: pHash/dHash close
D: embedding/tag similar
E: weak/reference only
```

### 8.5 Grouping phase

```text
selected pairs
  ↓
Union-Find
  ↓
DuplicateGroup
  ↓
recommended_keep
```

### 8.6 Manual review phase

```text
DuplicateGroup
  ↓
show images by quality priority
  ↓
user decision
  ↓
keep/quarantine/split/alternate/false_positive
  ↓
log action
```

## 9. 구현 우선순위

### Phase 1: 이미 구현된 기본 구조

```text
scanner.py
metadata.py
actions.py
hashing.py
similarity.py
grouping.py
CLI scan/plan
```

### Phase 2: 다음에 구현할 구조

```text
SQLite cache
phash/dhash fields
hash bucket index
candidate pair generation
candidate count limit
similarity grade
```

### Phase 3: 정밀화

```text
SSIM
quality score
thumbnail cache
manual review UI
```

### Phase 4: 고급 기능

```text
OpenCLIP/DINO embedding
FAISS index
semantic similar mode
```

## 10. Codex 구현 지침

다음 구현 시에는 아래 규칙을 따른다.

```text
1. 절대 모든 이미지 pair를 직접 비교하지 않는다.
2. scan 결과와 hash 결과는 캐싱한다.
3. pHash/dHash는 bucket 또는 BK-tree를 통해 후보 pair만 생성한다.
4. Hamming distance는 후보 pair에만 계산한다.
5. SSIM은 Hamming distance를 통과한 pair에만 계산한다.
6. 결과는 pair list가 아니라 DuplicateGroup으로 묶는다.
7. duplicate, alternate, false_positive, split 상태를 분리한다.
8. 자동 삭제 기능은 만들지 않는다.
9. 사람이 판단할 수 있도록 추천 이유와 metric을 UI에 표시한다.
10. exe 배포를 고려해 heavy dependency는 optional extra로 둔다.
```

## 11. 우리 프로젝트에서 바로 가져올 구조 요약

```text
imagededup:
  encoding_map
  threshold search
  duplicate dictionary

Czkawka:
  core / CLI / GUI 분리
  cache support
  local app structure

Pinterest near-duplicate system:
  candidate generation
  candidate selection
  clustering

LSH/bucket:
  전체 pair 비교 회피
  같은 bucket 후보만 비교

Hydrus:
  duplicate relation state
  alternate / false positive / split 개념
```
