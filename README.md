# AutoBlog — 네이버 블로그 자동 포스팅 앱

> 당신 계정을 지키는 자동화. Gemini 2.5 + Nano Banana 2 (BYOK).

## 프로젝트 개요

- **목표**: 한국 1등 네이버 블로그 자동 포스팅 데스크톱 앱
- **타겟**: 일반 한국 블로거 (체험단/일상)
- **핵심 가치**: 글 퀄리티 압도 + 계정 안전 + AI 비용 투명 (BYOK)

## 기술 스택

- Python 3.12
- PySide6 (GUI)
- nodriver 메인 + Playwright 폴백 (브라우저 자동화)
- Google Gemini API (사용자 본인 API 키)
  - 글쓰기: `gemini-2.5-pro` / `gemini-2.5-flash`
  - 이미지: `gemini-3.1-flash-image-preview` (Nano Banana 2)
- SQLite (로컬 데이터)

## 개발 환경 셋팅

```bash
# uv 설치 (macOS)
brew install uv

# Python 3.12 설치 + 의존성 설치
uv sync

# 실행
uv run autoblog
```

## 프로젝트 구조

```
src/autoblog/
├── config/       # 설정 + 안전 정책 상수
├── gui/          # PySide6 화면
├── core/         # 오케스트레이터, 이벤트 버스
├── content/      # 글 생성 (사용자 로직 주입)
├── image/        # Nano Banana 2 + EXIF 후처리
├── editor/       # SmartEditor HTML→컴포넌트 변환
├── automation/   # 브라우저 자동화 (nodriver)
├── safety/       # 일3건 하드캡, 검수 게이트
├── db/           # SQLite
├── telemetry/    # 로깅
└── utils/        # 공통 유틸
```

## 진행 단계

- **Phase 0** — PoC 및 환경 셋팅 (1주)
- **Phase 1** — MVP: 1포스트 즉시 발행 (4~6주)
- **Phase 2** — 베타: 10명 테스트, AI 이미지·사용자 글쓰기 통합 (4주)
- **Phase 3** — v1.0 정식 출시: 라이선스·자동 업데이트·EV 사이닝 (4주)

상세 계획: `~/.claude/plans/tidy-tickling-fountain.md`

## 라이선스

비공개 — 상용 배포 예정
