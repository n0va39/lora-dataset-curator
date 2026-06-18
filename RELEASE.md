# Release Notes

## 0.1.1

버그 수정 릴리즈입니다.

### 수정 사항

- 이동 실행 중 원본 파일이 사라지거나 대상 파일명이 충돌해도 exe가 종료되지 않도록 수정
- 출력 폴더에 같은 파일명이 있으면 sidecar와 함께 `_1`, `_2` suffix로 안전하게 저장
- 입력 폴더와 출력 폴더가 같을 때 source/target 동일 경로를 no-op 처리
- GUI 오류 로그 저장 및 `파일 > 오류 로그 보기` 추가
- `캐시 준비` 중 이미지별 SHA256/pHash/dHash 계산 실패 시 해당 파일만 건너뛰도록 수정
- GUI `캐시 준비`와 `분석`을 단일 worker 해시 계산으로 실행해 exe 환경 안정성 개선
- 중복 그룹 탭에 pHash/dHash 기준값 의미와 권장 범위 안내 추가

### 검증

- `uv run ruff check`
- `uv run pytest`
- `scripts/build_windows.ps1`

## 0.1.0

초기 GUI MVP 릴리즈입니다.

### 포함 기능

- Windows 로컬 GUI 실행
- PyInstaller 기반 단일 exe 빌드
- 이미지, `.txt`, `.json` sidecar 스캔
- 같은 폴더 구조와 `images/`, `captions/`, `metadata/` 분리 구조 지원
- 검수 표와 이미지 미리보기
- 큰 미리보기 창
- 큰 미리보기 썸네일 목록
- `A`, `D`, `S` 결정 단축키
- 방향키 이미지 이동
- 중복/유사 이미지 그룹 분석
- SHA256/MD5/post id/source 기반 그룹화
- pHash/dHash 기반 유사 이미지 후보 탐지
- 그룹별 추천 keep 이미지 점수 표시
- 결정 상태 자동 저장
- 해시 캐시와 중복 그룹 캐시
- 이미지별 crop 설정
- 사각형 프레임 기반 crop 드래그 조절
- 방향별 픽셀 crop 입력
- 방향별 비율 일괄 crop 적용
- 전체 크기 crop은 저장/실행하지 않는 방어
- 이동 결정 파일을 출력 폴더 바로 아래에 저장
- 삭제 예정 파일을 앱 data 휴지통으로 이동
- 휴지통 복구와 비우기
- 캐시 폴더 열기, 데이터 폴더 열기, 캐시 삭제
- 실행 시 사라진 원본 파일 skip 처리

### 배포 파일

릴리즈 zip에는 아래 파일을 포함합니다.

```text
LoRA-Dataset-Curator.exe
README.md
RELEASE.md
docs/
  USER_GUIDE.md
  BUILD_DISTRIBUTION.md
```

### 실행

```text
LoRA-Dataset-Curator.exe
```

### 저장 위치

기본적으로 exe 옆 `data/` 폴더에 설정, 캐시, 상태, 휴지통을 저장합니다. 해당 위치에 쓸 수 없으면 `%LOCALAPPDATA%\lora-dataset-curator`를 사용합니다.

### 알려진 제한

- 이미지 다운로드 기능 없음
- Danbooru/Gelbooru API 호출 기능 없음
- 자동 영구 삭제 기능 없음
- GUI는 MVP 단계이며, 대량 데이터셋에서 최초 pHash/dHash 분석은 시간이 걸릴 수 있음
