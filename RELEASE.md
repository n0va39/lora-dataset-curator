# Release Notes

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
