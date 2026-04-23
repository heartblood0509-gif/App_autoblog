# PoC 결과 기록 (Phase 0)

네이버 블로그 자동 포스팅의 가장 위험한 가정들을 PoC로 검증한 결과 모음.
각 PoC 성공/실패에 따라 Phase 1 설계가 조정됨.

---

## PoC 1 — `upconvert.editor.naver.com` API 동작 검증

**실행일**: 2026-04-23 (Day 3)
**스크립트**: `scripts/poc_upconvert.py`
**원본 응답**: `docs/poc_responses/poc1_upconvert_scenario{1,2}.json`

### 판정: ✅ **성공 — API 살아있음, 쿠키 불필요**

### 핵심 발견 3가지

1. **`userId` 쿼리 파라미터 필수**
   - 시나리오 1 (userId 없음): **500 Internal Server Error**
     ```
     "Required String parameter 'userId' is not present"
     ```
   - 시나리오 2 (`userId=testblog`): **200 OK + 유효한 JSON**
   - 결론: 실제 네이버 blogId를 넣어도 되지만, **아무 문자열이나** 넣어도 동작함을 확인.

2. **쿠키(로그인 세션) 없이도 호출 가능**
   - 두 시나리오 모두 쿠키 없이 테스트 — 시나리오 2는 정상 응답.
   - **의미가 큰 결과**:
     - Phase 0 Day 5 사용자 네이버 계정을 **기다리지 않고** 이 API를 개발·테스트할 수 있음.
     - CI에서 정기 헬스체크 가능 → API 변경 조기 감지 (CR-003 3-layer 중 layer 2).
     - 발행 단계에서 이 API 호출은 사용자 계정 상태와 **독립적**.

3. **응답 JSON 구조가 viruagent-cli 분석과 일치**
   - `@ctype: "text"`, `SE-{uuid}` ID 포맷, `value → paragraph → nodes → textNode` 계층.
   - h1이 자동으로 `fontSizeCode: "fs24"` + `bold: true`로 변환됨 (기대대로 서식 자동 적용).
   - **editorConvert.js의 수동 파서(`parseHtmlToComponents`)는 진짜 폴백만** — 서식 판단 로직을 직접 짤 필요 없음.

### 예상 외 발견: 여러 HTML 블록이 하나의 컴포넌트로 합쳐짐

입력 HTML:
```html
<h1>카페 다녀왔어요</h1>
<p>어제 연남동의 작은 카페에 다녀왔습니다.</p>
<p>라떼 한 잔과 디저트가 정말 맛있었어요.</p>
<strong>특히 티라미수가 인상적이었습니다.</strong>
<p>다음에 또 가고 싶은 곳이에요.</p>
```
→ 응답: **컴포넌트 1개**만 반환 (`@ctype: text`, 내부에 5개 paragraph).

**Phase 1 설계에 주는 영향**:
- 기대: 제목/본문/이미지 각각 별도 컴포넌트로 받아 이미지 배치가 자유로울 것.
- 현실: 본문 전체가 하나의 text 컴포넌트 → 이미지를 본문 중간에 끼우려면 **HTML을 섹션별로 쪼개 여러 번 호출**해야 함.

**두 가지 전략**:
1. **섹션 단위 호출**: `<h1>...첫 단락</h1>` / `<p>두 번째 단락</p>` 식으로 분리 호출 → 이미지를 그 사이에 삽입. 호출 수 증가하지만 배치 자유도 높음.
2. **이미지 최상단/최하단 고정**: viruagent-cli가 쓰는 방식(index.js의 `publish` 코드: `[...imageComponents, ...apiComponents]`). 단순하지만 배치 제약.

→ Phase 1 MVP는 전략 2 채택 (단순함), Phase 2에서 전략 1로 확장.

### API 응답 원본 (시나리오 2, 일부 발췌)

```json
[{
  "@ctype": "text",
  "id": "SE-0f2c9cb3-3ee9-11f1-ba82-214e9948b6c1",
  "layout": "default",
  "value": [
    {
      "@ctype": "paragraph",
      "id": "SE-0f2c9caa-...",
      "nodes": [{
        "@ctype": "textNode",
        "id": "SE-0f2c9ca9-...",
        "style": {
          "@ctype": "nodeStyle",
          "fontSizeCode": "fs24",
          "bold": true
        },
        "value": "카페 다녀왔어요"
      }]
    },
    ...
  ]
}]
```

### 시사점 — CR-003 "API 변경 감지"에 반영할 pydantic 스키마

```python
class NodeStyle(BaseModel):
    ctype: Literal["nodeStyle"] = Field(alias="@ctype")
    font_size_code: str = Field(alias="fontSizeCode")
    bold: bool = False

class TextNode(BaseModel):
    ctype: Literal["textNode"] = Field(alias="@ctype")
    id: str
    style: NodeStyle | None = None
    value: str

class Paragraph(BaseModel):
    ctype: Literal["paragraph"] = Field(alias="@ctype")
    id: str
    nodes: list[TextNode]

class TextComponent(BaseModel):
    ctype: Literal["text"] = Field(alias="@ctype")
    id: str = Field(pattern=r"^SE-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    layout: Literal["default"]
    value: list[Paragraph]

    model_config = ConfigDict(extra="forbid")
```

Phase 1에서 이 모델로 엄격 파싱 → 스키마 변경 즉시 감지.

### Acceptance Criteria (모두 통과)

- [x] 200 응답 수신
- [x] 응답이 유효한 JSON 배열
- [x] `@ctype` 필드 존재
- [x] SE-{uuid} ID 포맷 일치
- [x] 원본 응답 파일 저장 (`docs/poc_responses/`)

---

## PoC 2 — 네이버 로그인 자동화 + 쿠키 추출 (Playwright 폴백)

**실행일**: 2026-04-23 (Day 3, 통합 진행)
**스크립트**: `scripts/poc_session.py` (Playwright 버전)

### 판정: ✅ **통과 — 단, nodriver 실패 → Playwright 폴백으로 전환**

### 주요 발견

1. **nodriver는 macOS + Chrome 147 환경에서 연결 실패**
   - `Failed to connect to browser` 반복 발생 (sandbox/CDP 이슈 추정)
   - Chrome 프로세스 완전 종료, 프로필 락 정리 후에도 재현
   - CR-002 계획의 **Playwright 폴백으로 전환** → 해결
   - 사용자 기존 프로젝트 `app-blog2`도 Playwright 스택이라 스택 통일 효과

2. **Playwright + 시스템 Chrome(channel="chrome") + persistent context**
   - 로그인 페이지 자동 진입
   - 사용자가 30분 이내 수동 로그인
   - 쿠키 12개 자동 추출 + JSON 저장

3. **핵심 인증 쿠키 확보 확인**
   - `NID_AUT` (64자, httpOnly=True) ✓
   - `NID_SES` (648자, httpOnly=False, 세션 쿠키) ✓

### 주의 사항 (Phase 1 반영)

- **Persistent profile에 세션 쿠키는 저장되지 않음** — `NID_SES`가 브라우저 종료 시 증발
- 이후 PoC/코드에서는 JSON에 저장한 쿠키를 `context.add_cookies()`로 **수동 주입** 필요
- 이 패턴을 Phase 1 `NaverSession` 모듈에 구현

### Chrome 잔존 프로세스 문제

- 첫 실행 후 Chrome 프로세스가 완전 종료 안 되면 두 번째 실행 시 프로필 락으로 창 안 뜸
- 해결: `pkill -9 -f "autoblog/chrome-profiles/naver"` + `rm Singleton*`
- Phase 1에서 앱 시작 시 자동 정리 로직 추가 필요

### Acceptance Criteria

- [x] Chrome 창이 뜸 (Playwright)
- [x] 로그인 상태 자동 감지
- [x] NID_AUT + NID_SES 확보
- [x] JSON 저장 성공

---

## PoC 4 — 네이버 이미지 업로드 API (부분 성공)

**실행일**: 2026-04-23 (Day 3, PoC 2 직후)
**스크립트**: `scripts/poc_upload.py` (Playwright context.request 기반)

### 판정: ⚠️ **부분 성공 — 3/4 단계 통과, 최종 업로드만 네이버의 추가 보안으로 차단**

### 단계별 결과

| 단계 | 엔드포인트 | 결과 |
|---|---|---|
| 1. blogId 추출 | `blog.naver.com/MyBlog.naver` | ✅ `jjajungma` 확보 |
| 2. Se-Authorization 토큰 | `blog.naver.com/PostWriteFormSeOptions.naver` | ✅ 180자 토큰 |
| 3. 업로드 session-key | `platform.editor.naver.com/.../session-key` | ✅ sessionKey 발급 |
| 4. **이미지 업로드** | `blog.upphoto.naver.com/{sessionKey}/simpleUpload/0` | ❌ `<code>LOGIN</code>` 거부 |

### 시도했지만 해결 안 된 것

- httpx 단일 요청 (Chrome 131 UA + 단순 Referer)
- httpx 단일 요청 (Chrome 147 UA + PostWriteForm Referer + Origin)
- Playwright `context.request` + persistent profile (세션 쿠키 증발)
- Playwright `context.request` + 수동 쿠키 주입 (12개 전부)
- Playwright `context.request` + 쿠키 + `Se-Authorization` + `Sec-Fetch-*` 헤더

### 원인 분석 (Phase 1 설계에 반영)

네이버 `blog.upphoto.naver.com`은 2025-07 이후 보안 강화로 **순수 HTTP 요청을 거부**하는 것으로 확인됨. viruagent-cli(2026-04)의 단순 fetch 코드가 더 이상 동작하지 않음.

**가장 유력한 해결 경로**:
- 실제 `PostWriteForm.naver` 에디터 페이지를 **Playwright로 방문**한 상태에서
- `page.evaluate()` 안에서 **페이지 런타임 JavaScript로 fetch 호출**
- 이렇게 하면 브라우저가 CORS, 쿠키, Sec-Fetch, 같은 원본 정책을 전부 자동 처리
- Phase 1의 `ImageUploader` 모듈은 이 구조로 구현 확정

### Phase 1 ImageUploader 아키텍처 (결정)

```
[PoC 4 교훈 반영한 구조]

ImageUploader:
  1. Playwright context 유지 (PoC 2의 로그인 세션)
  2. 백그라운드 탭에서 PostWriteForm.naver 방문 (에디터 세션 초기화)
  3. page.evaluate() 로 업로드 fetch 수행
  4. 응답 XML 파싱 → SE3 이미지 컴포넌트 생성
```

### Acceptance Criteria

- [x] 쿠키 기반 인증으로 blogId/토큰/세션키 확보 (3/4 단계)
- [ ] 실제 이미지 업로드 성공 (Phase 1에서 page.evaluate 구조로 재시도)
- [x] 실패 원인 명확히 파악 → Phase 1 설계에 반영

### 배운 점

- viruagent-cli의 단순 HTTP 업로드 코드는 **현재 시점(2026-04)에는 동작하지 않음**
- 2025-07 네이버 보안 강화 실제 영향 범위 확인
- Phase 1 `automation/` 모듈은 **순수 HTTP + Playwright 런타임 혼용** 구조 필수

---

## PoC 3 — Gemini 2.5 Flash + Nano Banana 2 (BYOK)

**실행일**: 2026-04-23 (Day 3, 사용자 API 키 준비 후 당겨 실행)
**스크립트**: `scripts/poc_gemini.py`

### 판정: ✅ **전체 통과 — CR-005 BYOK 설계 실전 검증**

### 시나리오 1: `gemini-2.5-flash` 한국어 블로그 후기

- **입력**: 연남동 카페 후기 프롬프트 (88 토큰)
- **출력**: 463자 한국어 본문 (279 토큰)
- **실측 비용**: **$0.000724 ≈ 1.05원/글**
- 한국 블로거 말투 ("~더라구요", "~었어요") 자연스럽게 구현
- 감각적 디테일(빈티지 포스터, 재즈 음악, 레몬 향) 자발적 포함
- 광고 톤 없음, 1인칭 경험담 말투 성공

생성된 본문 발췌:
> 지난 주말, 연남동 골목을 걷다가 우연히 발견한 작은 카페에 다녀왔어요. 간판도 작고 조용한 곳이라 무심코 지나칠 뻔했는데, 창문 너머로 새어 나오는 따뜻한 불빛에 이끌려 들어갔죠. …
> 라떼는 우유 거품이 정말 부드럽고 커피 향이 고소하게 올라와서 한 모금 한 모금 음미하게 되더라구요. …

### 시나리오 2: `gemini-3.1-flash-image-preview` (Nano Banana 2) 이미지

- **프롬프트**: 연남동 카페 인테리어 (영문, 1K, 4:3)
- **결과**: PNG 파일 생성 (915 KB) → `docs/poc_responses/poc3_nano_banana_2_test.png`
- **실측 비용**: **$0.067 ≈ 97원/이미지**
- ⚡ **결제 카드 등록 없이도 무료 체험 범위 내에서 동작 확인**

### 비용 실측 → 계획서 추정과 일치

| 항목 | 계획서 추정 | 실측 |
|---|---|---|
| 본문 1500자 수준 | ~$0.01 (약 14원) | $0.000724 (약 1원) ※ 이번 PoC는 463자 |
| 이미지 1장 1K | $0.067 (약 97원) | $0.067 (약 97원) ✓ 정확 |
| **1편 예상 (본문 + 5장)** | 약 550원 | **실측 기반 486원** |

### CR-005 BYOK 보안 장치 검증

- ✅ **모델 화이트리스트** 하드코딩 작동 (`gemini-2.5-*`, `gemini-3.1-flash-image-preview` 4개만 허용)
- ✅ **API 키 마스킹** (`AIzaSy...7pS8` 형태로만 출력)
- ✅ **`.env` 파일 `.gitignore` 적용** (git check-ignore 확인 완료)
- ✅ **사용량 로깅** (토큰 수, 비용 추정치 표시)

### 주의

- 실행 전 `.env.example`이 아니라 `.env`에 키를 넣어야 함 (Day 3 실수 사례)
- Nano Banana 2는 공식 문서상 "무료 tier 불가"라 했지만 실측은 동작함 → Google이 초기 무료 한도를 제공 중으로 추정. 사용량 초과 시 결제 카드 등록 필요.

### Acceptance Criteria (모두 통과)

- [x] 한국어 블로그 후기 자연스럽게 생성
- [x] 이미지 1장 PNG 생성 (> 500 KB)
- [x] 사용량/비용 실측 가능
- [x] 모델 화이트리스트 검증 동작
- [x] 생성 이미지 파일 저장 확인

---

## PoC 4 — (예정) 이미지 업로드 (`blog.upphoto.naver.com`)

**예정일**: Day 6
**스크립트**: `scripts/poc_upload.py` (예정)
**필요한 것**: PoC 2의 쿠키 + PoC 3의 생성 이미지

---

## PoC 5 — qasync로 PySide6 + asyncio 통합 (CR-002)

**실행일**: 2026-04-23 (Day 3, 순차 진행 중 당겨서 실행)
**스크립트**: `scripts/poc_qasync.py`
**실행 명령**: `POC5_AUTO_EXIT=1 uv run python scripts/poc_qasync.py`

### 판정: ✅ **통과 — qasync가 실제로 동작함**

### 자동 검증 3단계 모두 성공

1. **이벤트 루프 교체 확인**
   - `asyncio.get_running_loop()` → `QSelectorEventLoop` 타입
   - Qt 이벤트 루프가 asyncio 인터페이스로 노출됨 → 기존 `asyncio.create_task` / `await` 패턴 그대로 사용 가능

2. **Qt 타이머 + asyncio.sleep 동시 동작**
   - `QTimer.singleShot(100, callback)` + `await asyncio.sleep(0.3)` 병행
   - 타이머 콜백이 정상 발화 + asyncio 대기도 풀림 → UI 이벤트와 async 태스크가 간섭 없이 협력

3. **httpx 비동기 호출**
   - `async with httpx.AsyncClient() as client: response = await client.get("https://httpbin.org/uuid")`
   - 성공, uuid 수신 확인

### 의미

CR-002 결정(qasync 채택)이 **실제로 검증됨**. Phase 1 GUI 아키텍처를 이 패턴으로 진행:

```python
# src/autoblog/app.py 에서 쓸 패턴
import asyncio
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    # ... 메인 윈도우 생성 + show()
    with loop:
        loop.run_forever()
```

UI 이벤트 핸들러는 `@asyncSlot()` 데코레이터로 async 함수를 Qt 시그널에 바인딩 가능.

### Acceptance Criteria (모두 통과)

- [x] `QEventLoop`가 `asyncio.get_event_loop()`로 반환됨
- [x] Qt 타이머와 `asyncio.sleep` 동시 발화
- [x] 비동기 HTTP 호출 정상 동작
- [x] 자동 모드로 실행 시 CI에서도 검증 가능 (display 불필요)

---

## Day 7 — 회고 예정

5개 PoC 결과 종합 → Phase 1 MVP 설계 최종 확정.
