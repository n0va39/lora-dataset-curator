# Reference Libraries and Technologies

이 문서는 LoRA Dataset Curator에서 참고하거나 사용할 수 있는 라이브러리와 기술을 정리한다.

원칙은 다음과 같다.

```text
1. 검증된 라이브러리가 있으면 우선 사용한다.
2. 프로젝트 구조나 알고리즘 흐름은 참고하되, 코드 복제는 최소화한다.
3. 코드 복제가 필요하면 라이선스를 먼저 확인한다.
4. exe 배포를 고려해 무거운 의존성은 optional extra로 둔다.
```

## 1. 요약 추천

| 영역 | 1차 선택 | 역할 | 적용 단계 |
|---|---|---|---|
| 이미지 로딩 | Pillow | 이미지 열기, 크기 확인 | MVP 1 |
| perceptual hash | ImageHash | pHash/dHash/wHash 계산 | MVP 2 |
| 후보 검색 | 자체 bucket index | 전체 pair 비교 회피 | MVP 2 |
| BK-tree 검색 | pybktree 또는 자체 구현 | Hamming distance threshold 검색 | MVP 3+ |
| 구조 유사도 | scikit-image | SSIM 계산 | MVP 3+ |
| 이미지 품질 검사 | OpenCV | blur/dark/bright 검사 | MVP 4 |
| 캐시/상태 저장 | SQLite | hash, metadata, pair, group cache | MVP 2+ |
| 벡터 검색 | FAISS 또는 hnswlib | embedding top-k 검색 | MVP 5 |
| 이미지 임베딩 | OpenCLIP / DINOv2 | 의미적 유사 이미지 검색 | MVP 5 |
| GUI | PySide6 | Windows 로컬 GUI | MVP GUI |
| exe 빌드 | PyInstaller | Windows exe 배포 | 배포 단계 |

## 2. Pillow

### 용도

```text
이미지 열기
이미지 크기 확인
테스트용 임시 이미지 생성
ImageHash 입력 이미지 제공
```

### 적용 위치

이미 `scanner.py`에서 이미지 크기 확인에 사용 중이다.

```python
from PIL import Image

with Image.open(path) as image:
    width, height = image.size
```

### 판단

필수 의존성으로 유지한다.

## 3. ImageHash

Reference:

- https://github.com/JohannesBuchner/imagehash

### 용도

```text
pHash
DHash
WHash
AHash
ColorHash
Crop-resistant hash
```

ImageHash는 Python perceptual image hashing 라이브러리다. cryptographic hash와 달리, 시각적으로 비슷한 이미지가 비슷한 hash를 갖도록 설계된 방식이다.

### 우리 프로젝트에서의 역할

```text
리사이즈된 이미지
재압축된 이미지
JPG/PNG 변환 이미지
거의 동일한 이미지
```

이런 후보를 찾는다.

### 사용 예시

```python
import imagehash
from PIL import Image

with Image.open(path) as image:
    phash = imagehash.phash(image)
    dhash = imagehash.dhash(image)
```

### 주의

ImageHash는 hash 계산용이다. 대량 이미지에서 전체 pair 비교를 피하는 index 구조는 직접 구현해야 한다.

따라서 구조는 다음처럼 가져간다.

```text
ImageHash로 phash/dhash 계산
→ hash를 cache에 저장
→ bucket index 생성
→ 후보 pair만 Hamming distance 계산
```

### 적용 단계

```text
MVP 2
```

## 4. imagededup

Reference:

- https://github.com/idealo/imagededup
- https://idealo.github.io/imagededup/user_guide/finding_duplicates/

### 용도

이미지 중복 탐지 라이브러리.

지원 방식:

```text
PHash
AHash
DHash
WHash
CNN
```

### 참고할 구조

`imagededup`은 이미지별 encoding map을 만들고, threshold 기반으로 중복 후보를 찾는다.

```text
image_dir
  ↓
encoding_map
  ↓
find_duplicates
  ↓
duplicate dictionary
```

결과 구조 예시:

```text
{
  "image1.jpg": ["image1_duplicate1.jpg", "image1_duplicate2.jpg"],
  "image2.jpg": [...]
}
```

score 옵션을 사용하면 Hamming distance 또는 cosine similarity를 함께 반환하는 구조다.

### 우리 프로젝트에 가져올 점

```text
encoding_map 구조
threshold search 구조
duplicate dictionary 구조
```

### 직접 의존성으로 넣을지 여부

초기에는 직접 의존성으로 넣지 않는다.

이유:

```text
LoRA Dataset Curator는 image + txt + json sidecar를 함께 관리해야 함
결과를 자체 DuplicateGroup 모델로 감싸야 함
ImageHash + 자체 bucket으로 충분히 시작 가능
```

필요하면 나중에 optional backend로 검토한다.

```text
candidate_backend = "internal_bucket" | "imagededup"
```

## 5. 자체 hash bucket index

### 용도

pHash/dHash 전체 pair 비교를 피하기 위한 후보 생성 방식.

### 구조

64-bit hash 문자열을 segment로 나눈다.

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

같은 bucket에 들어온 이미지끼리만 후보 pair를 생성한다.

### 장점

```text
구현이 단순함
DB/SQLite와 잘 맞음
전체 pair 비교를 피할 수 있음
외부 의존성이 없음
```

### 단점

```text
설계에 따라 후보 누락 가능
큰 bucket이 생길 수 있음
threshold별 segment 전략 조정 필요
```

### 후보 폭발 방지

```text
bucket_size_limit = 500
max_candidates_per_image = 100
aspect_ratio_filter = optional
```

### 적용 단계

```text
MVP 2 최우선
```

## 6. pybktree / BK-tree

Reference:

- https://github.com/benhoyt/pybktree
- https://en.wikipedia.org/wiki/BK-tree

### 용도

Hamming distance threshold 이하의 가까운 hash를 검색한다.

### 구조

```text
모든 pHash 값을 BK-tree에 insert
각 이미지 pHash로 threshold 이하 neighbor 검색
candidate pair 생성
```

### 장점

```text
Hamming distance 검색에 직접적
threshold search 구조가 명확함
작은 검색 반경에서 유용함
```

### 단점

```text
데이터 분포에 따라 성능 차이 있음
threshold가 커지면 후보 수가 늘어남
bucket 방식보다 구현/테스트가 약간 복잡함
```

### 적용 방침

초기에는 자체 bucket index를 구현한다. 후보 수가 많거나 누락이 문제가 되면 pybktree backend를 optional로 추가한다.

```text
candidate_backend = "bucket" | "bktree"
```

## 7. scikit-image

Reference:

- https://scikit-image.org/
- https://scikit-image.org/docs/stable/api/skimage.metrics.html

### 용도

```text
SSIM 계산
이미지 품질/구조 유사도 평가
```

SSIM은 후보 pair에 대해서만 계산한다.

```text
전체 pair에 SSIM 계산 금지
pHash/dHash 후보 pair
  → SSIM 계산
```

### 사용 예시

```python
from skimage.metrics import structural_similarity
```

### 적용 단계

```text
MVP 3+
```

### 주의

두 이미지를 같은 크기와 같은 color mode로 맞춘 뒤 계산해야 한다.

## 8. OpenCV

Reference:

- https://opencv.org/

### 용도

```text
blur detection
brightness/darkness detection
image resize/normalization
optional SSIM preprocessing
```

### 적용 단계

```text
MVP 4
```

### 주의

OpenCV는 exe 빌드 크기를 키울 수 있다. 기본 기능에는 꼭 필요한 부분만 사용한다.

## 9. SQLite

### 용도

```text
scan cache
hash cache
metadata cache
similarity pair cache
duplicate group state
review action log
```

### 장점

```text
Python 표준 라이브러리 sqlite3 사용 가능
외부 서버 필요 없음
Windows 로컬 앱에 적합
대량 데이터셋의 재스캔 비용 절감
```

### 적용 단계

```text
MVP 2
```

### 추천 테이블

```text
images
hash_buckets
similarity_pairs
duplicate_groups
group_members
review_actions
settings
```

## 10. FAISS

Reference:

- https://github.com/facebookresearch/faiss
- https://faiss.ai/

### 용도

고차원 embedding vector의 빠른 유사도 검색.

```text
image embedding
  ↓
FAISS index
  ↓
top-k similar images
```

### 장점

```text
대량 벡터 검색에 강함
OpenCLIP/DINO embedding 검색에 적합
```

### 단점

```text
초기 exe 배포에는 무거움
설치/빌드 환경 이슈 가능
GPU 기능은 배포 난이도 높음
```

### 적용 단계

```text
MVP 5 또는 고급 옵션
```

기본 설치에 넣지 말고 optional extra로 둔다.

```toml
[project.optional-dependencies]
embedding = [
  "faiss-cpu",
  "open_clip_torch",
]
```

## 11. hnswlib

Reference:

- https://github.com/nmslib/hnswlib

### 용도

HNSW 기반 approximate nearest neighbor 검색.

### FAISS와 비교

```text
FAISS:
  기능이 많고 대규모 검색에 강함
  설치/배포가 더 무거울 수 있음

hnswlib:
  비교적 단순한 HNSW vector index
  top-k 검색용으로 가볍게 쓰기 좋음
```

### 적용 단계

```text
MVP 5 optional
```

## 12. OpenCLIP

Reference:

- https://github.com/mlfoundations/open_clip

### 용도

이미지를 embedding vector로 변환한다.

```text
image
  ↓
OpenCLIP image encoder
  ↓
embedding vector
```

### 우리 프로젝트에서의 역할

```text
같은 캐릭터 후보
비슷한 구도 후보
비슷한 작가 스타일 후보
semantic similar mode
```

### 주의

OpenCLIP은 duplicate 자동 삭제 기준으로 쓰면 안 된다.

```text
같은 캐릭터의 다른 이미지
같은 작가의 다른 이미지
비슷한 구도의 다른 이미지
```

이런 이미지도 높은 유사도로 나올 수 있기 때문이다.

따라서 OpenCLIP은 다음 용도로만 쓴다.

```text
의미적으로 비슷한 이미지 후보 보기
manual review 보조
```

### 적용 단계

```text
MVP 5 optional
```

## 13. DINOv2

Reference:

- https://github.com/facebookresearch/dinov2

### 용도

텍스트 없이 이미지 자체의 시각적 feature를 embedding으로 만든다.

### OpenCLIP과 비교

```text
OpenCLIP:
  이미지-텍스트 의미 공간
  태그/텍스트 연동 가능

DINOv2:
  이미지 자체의 visual feature에 강함
  이미지끼리 비교에 적합
```

### 적용 단계

```text
MVP 5 optional
```

## 14. PySide6

Reference:

- https://doc.qt.io/qtforpython-6/

### 용도

Windows 로컬 GUI.

### 이유

```text
로컬 파일 탐색과 이미지 미리보기에 적합
장기적으로 exe 배포 가능
Gradio보다 데스크톱 앱에 적합
```

### 적용 단계

```text
GUI MVP
```

### 주의

PyInstaller로 묶을 때 Qt plugin 포함 문제가 생길 수 있다. GUI MVP가 안정화된 뒤 build spec을 정리한다.

## 15. Gradio

Reference:

- https://www.gradio.app/

### 용도

빠른 프로토타입 UI.

### 장점

```text
빠르게 검수 UI를 만들 수 있음
이미지 grid, button, text area 구현 쉬움
```

### 단점

```text
로컬 데스크톱 exe 배포에는 PySide6보다 애매함
브라우저 기반 UI
파일 이동/폴더 열기 같은 로컬 UX가 불편할 수 있음
```

### 판단

프로토타입에는 가능하지만 최종 exe 목표라면 PySide6 우선.

## 16. PyInstaller

Reference:

- https://pyinstaller.org/
- https://pyinstaller.org/en/stable/spec-files.html

### 용도

Windows exe 빌드.

### 현재 프로젝트 상태

```text
scripts/entrypoint.py
scripts/build_windows.ps1
docs/BUILD_DISTRIBUTION.md
```

### 기본 명령

```powershell
uv run pyinstaller --noconfirm --clean --onefile --name "LoRA-Dataset-Curator" --paths "src" "scripts/entrypoint.py"
```

GUI가 붙은 뒤에는 다음 옵션 검토.

```powershell
--windowed
```

### 주의

```text
PySide6 plugin 포함 문제
OpenCV binary 포함 문제
torch/OpenCLIP 포함 시 exe 크기 증가
FAISS 포함 시 platform issue 가능
```

## 17. uv

Reference:

- https://github.com/astral-sh/uv

### 용도

Python 환경/의존성 관리.

### 현재 사용 방식

```powershell
uv sync --extra gui --extra image --extra build --extra dev
uv run pytest
uv run lora-dataset-curator scan "D:\dataset"
```

### 판단

계속 사용한다.

## 18. 라이선스 기준

이 프로젝트는 MIT License로 설정되어 있다.

라이브러리 선택 기준:

```text
MIT / BSD / Apache-2.0:
  사용하기 쉬움

GPL 계열:
  코드 복제 금지에 가깝게 취급
  구조 참고만 권장
```

코드 복제가 필요하면 다음을 지킨다.

```text
1. 원본 라이선스 확인
2. 원본 copyright 보존
3. 변경 내용 명시
4. 복제 범위 최소화
```

## 19. 최종 권장 구현 순서

### MVP 2

```text
ImageHash
SQLite cache
hash bucket index
candidate pair generation
Union-Find grouping
```

### MVP 3

```text
scikit-image SSIM
quality score
thumbnail cache
```

### MVP 4

```text
OpenCV 품질 검사
PySide6 GUI MVP
```

### MVP 5

```text
OpenCLIP or DINOv2
FAISS or hnswlib
semantic similar mode
```

## 20. Codex 지침

다음 구현에서 Codex는 아래 방침을 따른다.

```text
1. ImageHash는 dependency로 사용한다. 복제하지 않는다.
2. imagededup은 구조 참고 위주로 사용한다.
3. pHash/dHash 전체 pair 비교는 금지한다.
4. 우선 자체 hash bucket index를 구현한다.
5. pybktree는 optional backend로 설계만 열어둔다.
6. SSIM은 후보 pair에만 계산한다.
7. FAISS/OpenCLIP/DINOv2는 기본 의존성에 넣지 않는다.
8. EXE 빌드가 무거워지는 의존성은 optional extra로 둔다.
9. GUI는 PySide6를 기본 방향으로 둔다.
10. 자동 삭제 기능은 구현하지 않는다.
```
