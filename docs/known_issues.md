# Known Issues — Phase 전환 시 반드시 점검

> Day 2 시니어 코드 리뷰 산출물. Critical 5개는 [critical_decisions.md](./critical_decisions.md) 로 별도 확정됨.
> 이 문서는 **Important 10개** + **Nice to have 13개** 체크리스트. 각 Phase 시작 전에 리뷰하여 해결·연기·기각 결정.

---

## Important — Phase 1 안에 해결

우선순위는 체크리스트 순서(가장 먼저 해야 할 것부터).

### Phase 1 시작 전 (가장 급함)
- [ ] **I-01: nodriver 단일 개발자 의존 리스크**
  - `BrowserAutomation` Protocol/ABC를 Phase 1 초반에 정의.
  - nodriver / Playwright 구현체 **둘 다 실제 동작 확인**.
  - 단일 실패 시 즉시 교체 가능한 구조.
  - 파일: `src/autoblog/automation/browser.py` (Protocol) + `browser_nodriver.py` + `browser_playwright.py`

- [ ] **I-02: GitHub Actions CI/pre-commit 미구성**
  - `.github/workflows/ci.yml`: Linux + Windows runner, ruff/mypy/pytest
  - `.pre-commit-config.yaml`: ruff, mypy, 기본 hooks (trailing-whitespace, end-of-file-fixer, check-yaml)
  - **Phase 0 Day 3~5 중 처리** (Critical CR-001 의 일부로 선반영됨)

- [ ] **I-03: 설정 / 상태 / 비밀 저장소 경계 정립**
  - **settings**: pydantic-settings (사용자 UI prefs)
  - **state**: SQLite (발행 이력, 현재 한도, 캐시)
  - **secrets**: keyring (API 키, 쿠키)
  - 규칙 문서화 → `docs/architecture.md`

- [ ] **I-04: 로깅에서 민감정보 자동 마스킹**
  - loguru `add(filter=redact_sensitive)` 로 `NID_AUT`, `NID_SES`, `api_key`, 비밀번호, 본문 자동 마스킹.
  - 테스트: `tests/unit/test_log_redaction.py`

### Phase 1 진행 중
- [ ] **I-05: 에러 처리 전략 = Result 패턴 + tenacity 재시도**
  - 모든 외부 호출(네이버 API, Gemini API, 이미지 업로드)에 `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential())`.
  - Result 패턴: 자체 `Success[T] | Failure[E]` dataclass 또는 `returns` 라이브러리.
  - 부분 실패 처리: "이미지 7/10 업로드 성공" 시 draft를 DB에 저장 + 이어쓰기.

- [ ] **I-06: 네이버 테스트 전략 구체화**
  - 발행 테스트는 `openType=0`(비공개)로만 → 저품질 회피.
  - `VCR.py`(vcrpy) 도입해 네이버 응답 녹화 → 오프라인 회귀 테스트.
  - "Dry-run 모드" 구현 (마지막 POST만 생략).
  - E2E 카나리아 전용 계정 분리.

- [ ] **I-07: 쿠키 만료 UX**
  - `NID_AUT` 유효기간 파싱 → 3일 전 사전 알림.
  - 앱 실행 시 백그라운드 세션 검증 (`HEAD https://blog.naver.com/MyBlog.naver`).
  - 만료 감지 시 GUI에 "재로그인 필요" 배너, 발행 시도 시 자동 로그인 창 띄움.

### Phase 2 시작 전
- [ ] **I-08: SafetyGate 서버 측 검증**
  - 로컬 SQLite 기반 일 3건 제한은 DB 삭제로 우회 가능.
  - Phase 3 라이선스 서버에 "오늘 발행 수" 동기화하여 머신ID 기반 검증.
  - 로컬만으로는 "정직한 사용자 보호용"으로 인식.

- [ ] **I-09: CS 인프라 결정**
  - 공개 지식베이스: Notion or GitBook
  - 이슈 트래커: GitHub Issues(private) 또는 Canny
  - 디버그 리포트 자동 수집 버튼 (민감정보 필터 후 업로드)

- [ ] **I-10: 사용자 draft 백업/복구**
  - PC 고장 시 draft 소실 방지.
  - 최소: JSON export 기능 (Phase 2 MVP).
  - 선택: Google Drive 백업 (Phase 3).

---

## Nice to have — Phase 2 이후 처리 가능

필요 시점에 다시 논의. 당장 코드/계획에 반영 불필요.

- [ ] **N-01**: 첫 발행 실패 시 사용자 친화 에러 메시지 + 해결 가이드 링크.
- [ ] **N-02**: 온보딩 복잡도 완화 — Chrome 프로필 자동 감지, 스크린샷 가이드.
- [ ] **N-03**: Semver + Conventional Commits 공식화.
- [ ] **N-04**: 개발자 문서 (ADR, 세팅 가이드, 기여 가이드).
- [ ] **N-05**: 1인 개발 bus factor 대비 — 모든 결정 ADR 기록, 코드 클린 유지.
- [ ] **N-06**: SafetyGate 점진적 완화 — "20일 무사고 → 일 5건으로 상향" 등.
- [ ] **N-07**: AI 탐지 회피 vs AI 투명성 — 장기적으로 "AI 사용 공개" 옵션 제공이 경쟁 우위일 수도.
- [ ] **N-08**: 수익 모델 현실성 시뮬레이션 — 환불률·불법 복제·마케팅 비용 스프레드시트.
- [ ] **N-09**: 이탈 관리 — "평생 1.0 지원, Major는 별도" 명시 or 구독 병행.
- [ ] **N-10**: 마케팅 플레이북 (Phase 3 완료 시점에 별도 문서).
- [ ] **N-11**: 접근성 — 고령자, 색각이상, 스크린리더.
- [ ] **N-12**: 다국어 — 한국어 외 (Phase 4+).
- [ ] **N-13**: DI 컨테이너 라이브러리 결정 — 현재는 팩토리 함수로 충분. `dependency-injector` 도입은 실제 복잡도 발생 시에만.

---

## 검토 주기

- **각 Phase 시작 시**: Important 전체 리뷰, 완료된 항목 체크, 새 이슈 추가.
- **분기별**: Nice to have 리뷰, 우선순위 재조정.
- **새 허점 발견 시**: 중요도 판단 → Important 또는 Nice에 추가 (Critical은 별도 ADR).

이 문서는 "살아있는 문서" — 커밋 로그로 진화 이력 추적 가능.
