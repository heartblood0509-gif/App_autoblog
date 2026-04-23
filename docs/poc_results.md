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

## PoC 2 — (예정) 사용자 Chrome 프로필로 네이버 로그인 상태 감지

**예정일**: Day 4
**스크립트**: `scripts/poc_session.py` (예정)
**필요한 것**: 네이버 테스트 계정 1개

**검증 항목**:
- nodriver로 사용자 Chrome 프로필 attach 가능?
- `https://nid.naver.com/user2/help/myInfo` 방문 시 로그인 상태 자동 판별 가능?
- `NID_AUT`, `NID_SES` 쿠키 추출 성공?

---

## PoC 3 — (예정) Gemini 2.5 + Nano Banana 2

**예정일**: Day 5
**스크립트**: `scripts/poc_gemini.py` (예정)
**필요한 것**: 사용자 Google API 키 1개

**검증 항목**:
- `gemini-2.5-flash`로 한국어 문단 생성
- `gemini-3.1-flash-image-preview`로 이미지 1장 생성
- 실비용 측정 (1회 호출당 대략 얼마)

---

## PoC 4 — (예정) 이미지 업로드 (`blog.upphoto.naver.com`)

**예정일**: Day 6
**스크립트**: `scripts/poc_upload.py` (예정)
**필요한 것**: PoC 2의 쿠키 + PoC 3의 생성 이미지

---

## PoC 5 — (예정) qasync로 PySide6 + asyncio 통합

**예정일**: Day 6
**스크립트**: `scripts/poc_qasync.py` (예정)

**검증 항목**:
- Qt 창에 버튼 1개, 클릭 시 `httpx.get()` 비동기 호출
- UI 프리즈 없이 네트워크 응답을 Qt 라벨에 반영

---

## Day 7 — 회고 예정

5개 PoC 결과 종합 → Phase 1 MVP 설계 최종 확정.
