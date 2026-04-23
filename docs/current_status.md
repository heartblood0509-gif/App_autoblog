# 📍 현재 상태 — 세션 핸드오프 문서

> 새 대화를 시작할 때 **제일 먼저 읽어야 하는 파일**.
> "이 프로젝트가 어디까지 왔고, 다음에 뭘 해야 하는지" 1페이지 요약.

**마지막 갱신**: 2026-04-23 (Phase 0 Day 3 완결 시점)

---

## 🎯 프로젝트 한 줄

> **네이버 블로그 자동 포스팅 Windows 데스크톱 앱** (Python · Playwright · PySide6 · Gemini 2.5/Nano Banana 2 BYOK).
> 한국 1등 목표. 타겟: 일반 블로거(체험단/일상). 가격: 평생 199,000원.

---

## ✅ 완료된 것 (Phase 0)

### 인프라
- uv 0.11.7 + Python 3.12 환경
- 프로젝트 뼈대 (11개 서브패키지)
- GitHub Actions CI (Linux + Windows 매트릭스)
- pre-commit (ruff, mypy, 민감정보 감지)
- GitHub private repo: https://github.com/heartblood0509-gif/App_autoblog

### 의사결정 (모두 `docs/critical_decisions.md` 에 상세)
- **CR-001**: Windows 빌드 = GitHub Actions windows-latest + Phase 1 전 VM 확보
- **CR-002**: Qt ↔ asyncio = **qasync** (실전 검증 완료)
- **CR-003**: 비공식 API 변경 감지 = pydantic 엄격 파싱 + fingerprint + 원격 구성
- **CR-004**: EXIF 조작 = GPS 금지, 카메라 기종만 옵션 (표시광고법 안전)
- **CR-005**: BYOK = 모델 화이트리스트 + spending cap 강제 + 소액 테스트 + 로컬 로그

### PoC 실측 결과
| PoC | 검증 | 결과 |
|---|---|---|
| 1 | upconvert API | ✅ 쿠키 없이 동작 (userId만) |
| 2 | 네이버 로그인 | ✅ nodriver 실패 → **Playwright 채택** |
| 3 | Gemini + Nano Banana 2 | ✅ 1편당 약 486원 |
| 4 | 이미지 업로드 | ⚠️ 3/4 통과, 마지막은 Phase 1에서 `page.evaluate` 구조로 해결 필요 |
| 5 | qasync | ✅ Qt+asyncio+httpx 동시 동작 |

### 사용자 자산 파악
- **`app-blog2`** (사용자 별도 프로젝트, Playwright 기반) — 글쓰기 로직 보유
- Phase 2에서 `ContentProvider` 인터페이스로 주입 예정
- 스택이 Playwright로 통일돼 통합 용이

---

## 🟡 핵심 수정된 계획 (중요)

### 멀티 계정 지원 (Phase 4 → Phase 2로 앞당김)
- 최대 **5개 네이버 계정** 지원
- 계정별 Chrome 프로필 격리 (`~/.autoblog/chrome-profiles/naver/{slug}/`)
- 안전 정책: **계정당 하루 2건** + 계정 전환 후 **30분 간격** + 계정별 4시간 간격

### 브라우저 자동화 주/부 역전
- 원래: nodriver 메인 + Playwright 폴백
- 현재: **Playwright 메인** (nodriver는 macOS + Chrome 147에서 연결 실패 반복)

### 이미지 업로드 아키텍처 확정 (PoC 4 교훈)
- 순수 HTTP 요청은 거부됨 (네이버 2025-07 보안 강화)
- 반드시 **Playwright 페이지 런타임에서 `page.evaluate()`로 fetch** 해야 동작
- `PostWriteForm.naver` 페이지 방문 상태에서만 업로드 가능

### 세션 쿠키 취급
- Persistent profile도 `NID_SES`(세션 쿠키) 저장 안 함
- JSON으로 보존 → `context.add_cookies()`로 수동 주입 패턴 필수

---

## ⏭️ 다음에 할 일 (Phase 1 Week 1)

### 먼저 결정 필요한 것
1. **Day 7 회고 문서 작성 여부** (또는 바로 Phase 1 착수)
2. 사용자님 네이버 계정 추가 준비 (현재 1개 `jjajungma`)

### Phase 1 MVP 범위 (4~6주)
- 1계정, 1포스트, 수동 트리거만
- 글쓰기는 stub(고정 텍스트)으로 시작 → Phase 2에서 `app-blog2` 통합

### Phase 1 Week 1 백로그
1. `src/autoblog/automation/browser.py` — Playwright 추상화
2. `src/autoblog/automation/naver_session.py` — 쿠키 JSON 저장/주입
3. `src/autoblog/editor/upconvert_client.py` — PoC 1 정식화
4. `src/autoblog/editor/se3_models.py` — pydantic 모델 (CR-003)
5. `src/autoblog/db/` — SQLite + alembic 초기 마이그레이션
6. `src/autoblog/safety/rate_limiter.py` — 계정당 2건 하드캡
7. `tests/integration/` — 각 모듈 통합 테스트

---

## 📂 중요 파일 맵

### 전체 그림 파악
1. `README.md` — 프로젝트 개요 (30초)
2. `~/.claude/plans/tidy-tickling-fountain.md` — 전체 계획 (비개발자 친화, 5분)
3. `docs/current_status.md` — **이 파일** (1분)

### 결정사항·허점
4. `docs/critical_decisions.md` — CR-001~005 상세
5. `docs/known_issues.md` — Important 10 + Nice 13 체크리스트

### 참고 자산
6. `docs/viruagent_mapping.md` — 참고 오픈소스 포팅 매핑
7. `docs/poc_results.md` — PoC 1~5 실측 결과

### 코드
8. `pyproject.toml` — 의존성 (gui/images/fallback extras)
9. `scripts/poc_*.py` — 검증된 동작 코드 (5개)
10. `src/autoblog/__main__.py` — 앱 진입점

---

## 🔐 민감 데이터 위치 (커밋 금지)

- `.env` — Gemini API 키 (gitignore됨)
- `~/.autoblog/sessions/naver.json` — 네이버 쿠키 (프로젝트 밖, 홈 디렉토리)
- `~/.autoblog/chrome-profiles/naver/` — Playwright Chrome 프로필

---

## 💬 새 대화에서 시작하는 법

한 줄만 말씀하시면 됩니다:

> "앞서 하던 네이버 블로그 자동화 프로젝트(App_autoblog) 이어가자. Phase 0 끝났고 Phase 1 시작할 차례야."

그러면 Claude가:
1. MEMORY.md 자동 로드 (사용자·프로젝트·참고 자산 컨텍스트)
2. 이 `current_status.md` 읽기 (최신 상태)
3. 필요 시 `plans/tidy-tickling-fountain.md` 확인
4. 그 다음 단계부터 진행

---

## 🗒️ 이 파일 갱신 규칙

Phase 전환 시점마다 또는 중요한 결정/발견이 있을 때마다 이 파일을 갱신.
그래야 컨텍스트 클리어 후에도 프로젝트가 끊김 없이 이어짐.
