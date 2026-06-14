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

## 관련 프로젝트

이미지와 태그 다운로드는 별도 도구에서 수행합니다.

- <https://github.com/n0va39/danbooru-downloader>

## 개발 문서

상세한 구현 계획과 Codex 작업 지침은 아래 문서에 정리합니다.

- [Project Plan](docs/PROJECT_PLAN.md)

## License

MIT License.
