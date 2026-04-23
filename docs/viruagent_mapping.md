# viruagent-cli → Python 포팅 매핑표

> 분석일: 2026-04-23 (Phase 0 Day 2)
> 대상: `vendor/viruagent-cli@0.9.6` (MIT License, Node.js+Playwright)
> 포팅 목적: 네이버 블로그 발행 로직을 Python으로 이식하여 `src/autoblog/` 에 통합

---

## 1. 전체 아키텍처 요약

viruagent-cli는 다중 플랫폼(Tistory/Naver/Instagram/X/Reddit/Threads) 발행을 지원하는 CLI. 우리는 **Naver 블로그 부분만** 포팅한다.

### 네이버 발행은 **하이브리드** 방식
- **로그인**: Playwright로 실제 Chrome 실행 (페르시스턴트 프로필) → `NID_AUT`, `NID_SES` 쿠키 확보
- **발행**: 순수 HTTP (쿠키로 인증) — **Playwright 불필요**

즉, 로그인 한 번 + 이후 발행은 모두 HTTP API. 우리 설계의 "사용자 Chrome 프로필 재사용" 전략과 정확히 일치.

### 네이버 프로바이더 파일 8개 + 서비스 1개

| 파일 | 줄 수 | 역할 |
|---|---|---|
| `src/providers/naver/index.js` | 470 | Provider 통합 인터페이스(login/publish/listPosts 등) |
| `src/providers/naver/auth.js` | 194 | 로그인 자동화 (Playwright) |
| `src/providers/naver/session.js` | 113 | 쿠키 추출·저장·검증·자동 재로그인 |
| `src/providers/naver/editorConvert.js` | 198 | HTML → SmartEditor SE3 컴포넌트 변환 |
| `src/providers/naver/imageUpload.js` | 111 | 이미지 버퍼 페치 + 업로드 오케스트레이션 |
| `src/providers/naver/cafeApiClient.js` | 565 | **카페 전용** 비공식 API (블로그엔 불필요) |
| `src/providers/naver/selectors.js` | 23 | 로그인 폼 selector + 에러 패턴 |
| `src/providers/naver/utils.js` | 56 | 자격증명/태그/가시성 파싱 유틸 |
| `src/services/naverApiClient.js` | 493 | **블로그 REST API 핵심** (발행·업로드·목록) |

**핵심 우선순위**: `naverApiClient.js` > `editorConvert.js` > `auth.js` > `session.js` > `imageUpload.js` > `index.js`(통합). 카페 관련(`cafeApiClient.js`)은 **포팅 대상 아님**이나 비공식 API 엔드포인트 패턴이 블로그와 동일 계열이라 참고용 가치 있음.

---

## 2. 핵심 비공식 API 엔드포인트 (블로그 발행용)

실제 발행 한 건에 호출되는 API를 순서대로 정리했다.

| # | 목적 | Method | 엔드포인트 | 필요 쿠키 | 비고 |
|---|---|---|---|---|---|
| 1 | blogId 추출 | GET | `https://blog.naver.com/MyBlog.naver` | NID_AUT, NID_SES | HTML 응답에서 `blogId = 'xxx'` 정규식 파싱 |
| 2 | Se-Authorization 토큰 | GET | `https://blog.naver.com/PostWriteFormSeOptions.naver?blogId={id}&categoryNo={n}` | NID_AUT, NID_SES | `result.token` 추출 |
| 3 | 카테고리 목록 + editorSource | GET | `https://blog.naver.com/PostWriteFormManagerOptions.naver?blogId={id}&categoryNo=0` | NID_AUT, NID_SES | `result.formView.categoryListFormView.categoryFormViewList` 배열 |
| 4 | editor ID 확보 | GET | `https://platform.editor.naver.com/api/blogpc001/v1/service_config` | NID_AUT, NID_SES + `Se-Authorization` 헤더 | `editorInfo.id` 추출 |
| 5 | 이미지 업로드 세션키 | GET | `https://platform.editor.naver.com/api/blogpc001/v1/photo-uploader/session-key` | NID_AUT, NID_SES + `Se-Authorization` | 응답 `sessionKey` |
| 6 | 이미지 업로드 | POST | `https://blog.upphoto.naver.com/{sessionKey}/simpleUpload/0?userId={blogId}&extractExif=true&extractAnimatedCnt=true&autorotate=true&extractDominantColor=false&denyAnimatedImage=false&skipXcamFiltering=false` | NID_AUT, NID_SES | multipart/form-data, `image` 필드 / XML 응답 |
| 7 | HTML → SE3 컴포넌트 변환 | POST | `https://upconvert.editor.naver.com/blog/html/components?documentWidth=886&userId={blogId}` | NID_AUT, NID_SES | Content-Type `text/html; charset=utf-8`, body는 `<html><body><!--StartFragment-->...<!--EndFragment--></body></html>` / JSON 배열 응답 |
| 8 | **발행** | POST | `https://blog.naver.com/RabbitWrite.naver` | NID_AUT, NID_SES | Content-Type `application/x-www-form-urlencoded` / body: `blogId`, `documentModel(JSON)`, `populationParams(JSON)`, `productApiVersion=v1` |
| 9 | 글 목록 | GET | `https://blog.naver.com/PostTitleListAsync.naver?blogId={id}&viewdate=&currentPage=1&categoryNo=0&parentCategoryNo=0&countPerPage=20` | NID_AUT, NID_SES | JSON에 잘못된 이스케이프(`\'`)가 섞이므로 sanitize 필요 |
| 10 | 글 상세 | GET | `https://blog.naver.com/PostView.naver?blogId={id}&logNo={postId}` | NID_AUT, NID_SES | HTML 응답 |

### 공통 헤더

```
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
Accept: application/json
Cookie: NID_AUT=...; NID_SES=...; (기타 naver.com 쿠키 전부)
Referer: https://blog.naver.com/PostWriteForm.naver?blogId={id}&categoryNo={n}&Redirect=Write
```

User-Agent는 **반드시 Chrome 131로 위장**. Referer도 중요(안 넣으면 403).

### 업로드 XML 응답 포맷 (엔드포인트 #6)

```xml
<url>/MyFiles/path/abc.jpg</url>
<width>1080</width>
<height>1440</height>
<fileName>IMG_20260423_093045.jpg</fileName>
<fileSize>284523</fileSize>
```

정규식 `<{tag}>([^<]*)</{tag}>` 으로 태그별 추출.

### 발행 성공 응답 (엔드포인트 #8)

```json
{
  "isSuccess": true,
  "result": {
    "redirectUrl": "https://blog.naver.com/PostView.naver?blogId=heartblood0509&logNo=223...&redirect=..."
  }
}
```

최종 URL 구성: `https://blog.naver.com/{blogId}/{logNo}`

---

## 3. 로그인 흐름 (Playwright 의존 부분)

### viruagent-cli의 방식

```
1. launchChrome(NAVER_PROFILE_DIR)
   → 페르시스턴트 프로필로 실제 Chrome을 CDP 포트로 띄움
2. page.goto('https://nid.naver.com/user2/help/myInfo')
   → 리다이렉트되지 않으면 "이미 로그인됨"으로 판정
3. 이미 로그인: persistNaverSession() 호출해 쿠키 저장 후 종료
4. 아니면 page.goto('https://nid.naver.com/nidlogin.login')
5. --manual 모드: 5분간 사용자 직접 입력 대기
6. --automatic 모드:
   page.evaluate((id) => { document.getElementById('id').value = id }, username)
   page.evaluate((pw) => { document.getElementById('pw').value = pw }, password)
   page.click('#log\\.login')
7. checkLoginResult(page): 페이지 content에서 에러 메시지 패턴 검색
8. waitForNaverLoginFinish(): 15초간 URL+쿠키 체크
9. persistNaverSession(): CDP Network.getAllCookies로 httpOnly 포함 전체 쿠키 저장
```

### 핵심 안티 감지 트릭

| 트릭 | 코드 | 효과 |
|---|---|---|
| `page.fill()` 대신 `page.evaluate()`로 `element.value = x` 직접 대입 | `auth.js:127-136` | 키 입력 이벤트 없이 값만 바꿈 → 봇 감지 회피 |
| 페르시스턴트 프로필 재사용 (`--user-data-dir`) | `chromeManager.js` | 쿠키/플러그인/히스토리 살아있어 "신규 기기" 신호 감소 |
| `navigator.webdriver` 등 마스킹 | `auth.js:13-18` | `Object.defineProperty(navigator, 'webdriver', { get: () => undefined })` |
| Manual fallback 5분 | `auth.js:124` | 캡차/2FA 뜨면 인간 개입 |

### 로그인 실패 패턴 (한국어 문자열 매칭)

```js
wrongPassword:      '비밀번호가 잘못'
accountProtected:   '회원님의 아이디를 보호'
phoneNumberMismatch:'등록된 정보와 일치하지'
regionBlocked:      '허용하지 않은 지역에서'
captcha:            ['자동입력 방지 문자', '자동입력 방지문자', 'captcha']
usageRestricted:    '비정상적인 활동이 감지되어'
twoFactor:          '2단계 인증 알림'
operationViolation: '운영원칙 위반'          // 성공 (경고만 뜬 상태)
newDevice:          '새로운 기기(브라우저)에서 로그인되었습니다.'  // 성공
```

---

## 4. SmartEditor SE3 컴포넌트 구조

### ID 규칙
모든 컴포넌트 ID는 `SE-{uuid}` 형식. JS: `SE-${crypto.randomUUID()}` → Python: `f"SE-{uuid.uuid4()}"`

### 텍스트 컴포넌트

```json
{
  "id": "SE-xxx",
  "layout": "default",
  "value": [{
    "id": "SE-yyy",
    "nodes": [{
      "id": "SE-zzz",
      "value": "실제 본문 텍스트",
      "style": {
        "fontColor": "#333333",
        "fontSizeCode": "fs16",        // fs16 일반, fs24 소제목, fs38 대제목
        "bold": "false",
        "@ctype": "nodeStyle"
      },
      "@ctype": "textNode"
    }],
    "style": {
      "align": "left",                  // left|center|right
      "lineHeight": "1.8",
      "@ctype": "paragraphStyle"
    },
    "@ctype": "paragraph"
  }],
  "@ctype": "text"                      // text | quotation
}
```

### 이미지 컴포넌트

```json
{
  "id": "SE-xxx",
  "layout": "default",
  "align": "center",
  "src": "https://blogfiles.pstatic.net{path}?type=w1",
  "internalResource": "true",
  "represent": "false",                 // 첫 이미지만 "true" (썸네일)
  "path": "/MyFiles/abc.jpg",
  "domain": "https://blogfiles.pstatic.net",
  "fileSize": 284523,
  "width": 1080,
  "widthPercentage": 0,
  "height": 1440,
  "originalWidth": 1080,
  "originalHeight": 1440,
  "fileName": "IMG_20260423_093045.jpg",
  "caption": null,
  "format": "normal",
  "displayFormat": "normal",
  "imageLoaded": "true",
  "contentMode": "normal",
  "origin": { "srcFrom": "local", "@ctype": "imageOrigin" },
  "ai": "false",
  "@ctype": "image"
}
```

### 제목 컴포넌트 (문서 최상단)

```json
{
  "id": "SE-xxx",
  "layout": "default",
  "title": [{
    "id": "SE-yyy",
    "nodes": [{
      "id": "SE-zzz",
      "value": "글 제목",
      "@ctype": "textNode"
    }],
    "@ctype": "paragraph"
  }],
  "subTitle": null,
  "align": "left",
  "@ctype": "documentTitle"
}
```

### 발행 시 전송 JSON 구조 (`documentModel`)

```json
{
  "documentId": "",
  "document": {
    "version": "2.9.0",
    "theme": "default",
    "language": "ko-KR",
    "id": "editorId값",
    "components": [
      { "@ctype": "documentTitle", ... },
      { "@ctype": "image", ... },
      { "@ctype": "text", ... },
      ...
    ]
  }
}
```

### 발행 시 `populationParams`

```json
{
  "configuration": {
    "openType": 2,                    // 0=비공개, 1=이웃공개, 2=전체공개
    "commentYn": true,
    "searchYn": true,                 // 검색 허용
    "sympathyYn": true,               // 공감 허용
    "scrapType": 2,
    "outSideAllowYn": true,
    "twitterPostingYn": false,
    "facebookPostingYn": false,
    "cclYn": false
  },
  "populationMeta": {
    "categoryId": "3",
    "logNo": null,
    "directorySeq": 0,
    "directoryDetail": null,
    "mrBlogTalkCode": null,
    "postWriteTimeType": "now",       // "now" | "reserve"
    "tags": "태그1,태그2,태그3",      // 콤마 구분
    "moviePanelParticipation": false,
    "greenReviewBannerYn": false,
    "continueSaved": false,
    "noticePostYn": false,
    "autoByCategoryYn": false,
    "postLocationSupportYn": false,
    "postLocationJson": null,
    "prePostDate": null,
    "thisDayPostInfo": null,
    "scrapYn": false
  },
  "editorSource": "blogpc001"
}
```

---

## 5. 파일별 Python 포팅 매핑

### 5-A. `naverApiClient.js` → `src/autoblog/automation/naver_api_client.py`

**JS 메소드 → Python 메소드**

| JS | Python | 구현 노트 |
|---|---|---|
| `createNaverApiClient({sessionPath})` | `class NaverApiClient:` with `__init__(self, cookies: CookieJar)` | 세션파일 읽기는 `NaverSession` 쪽에서. API 클라이언트는 쿠키만 받음 |
| `initBlog()` | `async def ensure_blog_id() -> str` | `httpx.AsyncClient` 사용. 정규식 `r"blogId\s*=\s*'([^']+)'"` |
| `getToken(categoryNo)` | `async def get_se_token(self, category_no: str = "0") -> str` | |
| `getCategories()` | `async def get_categories(self) -> dict[str, int]` | |
| `getEditorInfo(categoryNo)` | `async def get_editor_info(self, category_no: str) -> EditorInfo` | dataclass 반환 |
| `getUploadSessionKey(token)` | `async def get_upload_session_key(self, token: str) -> str` | |
| `uploadImage(buffer, filename, token)` | `async def upload_image(self, data: bytes, filename: str, token: str) -> UploadedImage` | `httpx files=` multipart. XML 응답 파싱 |
| `convertHtmlToComponents(html)` | `async def html_to_components(self, html: str) -> list[dict]` | |
| `publishPost({title, content, categoryNo, tags, openType})` | `async def publish_post(self, title, components, category_no, tags, open_type=2) -> PublishResult` | `urlencode` 본문 |
| `getPosts({page, countPerPage})` | `async def list_posts(self, page=1, per_page=20)` | |
| `getPost({postId})` | `async def get_post(self, post_id: str)` | |
| `resetState()` | `def reset_state(self)` | blog_id 캐시 무효화 |

**Python 의존성**: `httpx` (async HTTP), `pydantic` (응답 모델)

### 5-B. `auth.js` + `session.js` → `src/autoblog/automation/naver_session.py`

| JS 함수 | Python | 비고 |
|---|---|---|
| `isLoggedInByCookies(context, page)` | `async def is_logged_in(self) -> bool` | nodriver/Playwright context에서 쿠키 조회 |
| `persistNaverSession(context, page, path)` | `async def persist(self) -> None` | `NID_AUT`, `NID_SES` 중심으로 JSON 저장 |
| `validateNaverSession(path)` | `def validate_session_file(path: Path) -> bool` | 파일 존재+쿠키 2종 검사 |
| `createAskForAuthentication({...})` | `async def ensure_logged_in(self, manual=False)` | Playwright 대신 **nodriver 우선, Playwright 폴백** |
| `waitForNaverLoginFinish()` | `async def _wait_login_finish(self, timeout_sec=45)` | URL+쿠키 polling |
| `checkLoginResult(page)` | `async def _check_login_result(self, page) -> LoginResult` | dataclass 반환 |
| `createNaverWithProviderSession(...)` | `async def with_session(self, coro)` context/decorator | 401/403 감지 시 자동 재로그인 |

**Python 의존성**: `nodriver` (메인), `playwright-python` (폴백)

**보안**: 사용자 자격증명은 **환경변수 금지**, Windows Credential Manager (`keyring` 패키지) 사용. macOS 개발 중엔 keyring이 Keychain으로 자동 연결.

### 5-C. `editorConvert.js` → `src/autoblog/editor/se3_models.py` + `src/autoblog/editor/html_to_components.py`

| JS 함수 | Python |
|---|---|
| `seId()` | `def se_id() -> str: return f"SE-{uuid.uuid4()}"` |
| `createTextComponent(text, opts)` | `def create_text_component(text: str, *, font_size="fs16", bold=False, align="left", line_height="1.8", ctype="text") -> dict` |
| `createImageComponent(img_data)` | `def create_image_component(img: UploadedImage, represent: bool = False) -> dict` |
| `createDocumentTitle(title)` | `def create_document_title(title: str) -> dict` (신규 추가 — 원본은 publishPost에 인라인) |
| `convertHtmlToEditorComponents(api, html, images)` | `async def html_to_editor_components(api, html, images) -> list[dict]` |
| `parseHtmlToComponents(html, images)` | `def parse_html_fallback(html, images)` (upconvert API 실패 시) |
| `intersperse(components, images)` | `def intersperse(components, images) -> list[dict]` |

**Python 의존성**: `beautifulsoup4` (HTML 파싱 — JS의 `segment.split(/.../)` 대체)

### 5-D. `imageUpload.js` → `src/autoblog/image/uploader.py`

| JS 함수 | Python |
|---|---|
| `fetchImageBuffer(source)` | `async def fetch_image_bytes(source: str \| Path) -> tuple[bytes, str]` |
| `uploadAndCreateImageComponents(api, sources, token)` | `async def upload_images(api, sources: list[str], token: str) -> UploadResult` |
| `collectAndUploadImages({urls, keywords, token, limit})` | `async def collect_and_upload(api, *, urls, keywords, token, limit=2) -> UploadResult` |

**주의**: Tistory의 `buildKeywordImageCandidates`는 포팅 안 함 (우리는 Nano Banana 2 생성 이미지 + 사용자 제공 이미지만 사용).

### 5-E. `index.js` publish() → `src/autoblog/automation/post_publisher.py`

단일 함수(약 75줄)로 포팅:

```python
async def publish(
    api: NaverApiClient,
    draft: PostDraft,
    *,
    open_type: int = 2,
    image_upload_limit: int = 5,
) -> PublishResult:
    await api.ensure_blog_id()
    categories = await api.get_categories()
    category_no = resolve_category(draft.category, categories)

    # 1. 이미지 업로드
    image_components = []
    if draft.images:
        token = await api.get_se_token(category_no)
        image_components = await upload_images(api, draft.images, token)

    # 2. HTML → SE3 컴포넌트
    content_components = await html_to_editor_components(
        api, draft.body_html, image_components,
    )

    # 3. 발행
    return await api.publish_post(
        title=draft.title,
        components=content_components,
        category_no=category_no,
        tags=",".join(draft.tags[:10]),
        open_type=open_type,
    )
```

### 5-F. `selectors.js` → `src/autoblog/automation/selectors.py`

```python
NAVER_LOGIN_SELECTORS = {
    "username": "#id",
    "password": "#pw",
    "submit": "#log\\.login",
    "keep_login": ".keep_check",
}

NAVER_LOGIN_ERROR_PATTERNS = {
    "wrong_password":      "비밀번호가 잘못",
    "account_protected":   "회원님의 아이디를 보호",
    "phone_mismatch":      "등록된 정보와 일치하지",
    "region_blocked":      "허용하지 않은 지역에서",
    "captcha":             ["자동입력 방지 문자", "자동입력 방지문자", "captcha"],
    "usage_restricted":    "비정상적인 활동이 감지되어",
    "two_factor":          "2단계 인증 알림",
    "operation_violation": "운영원칙 위반",     # 성공 처리
    "new_device":          "새로운 기기(브라우저)에서 로그인되었습니다.",  # 성공 처리
}
```

**추가**: 이 상수들은 **selector 핫업데이트 채널**에서 원격으로 오버라이드 가능해야 함 → pydantic 모델 + 원격 JSON 로더.

### 5-G. `utils.js` → `src/autoblog/automation/_utils.py`

| JS 함수 | Python |
|---|---|
| `readNaverCredentials()` | `def read_credentials() -> NaverCredentials` (keyring 사용) |
| `parseNaverSessionError(err)` | `def is_session_error(exc: Exception) -> bool` |
| `normalizeNaverTagList(val)` | `def normalize_tags(raw: str \| list) -> list[str]` (최대 10개) |
| `mapNaverVisibility(v)` | `def map_visibility(v: Literal["public","mutual","protected","private"]) -> int` |
| `sleep(ms)` | 불필요 (`await asyncio.sleep(sec)`) |

### 5-H. `cafeApiClient.js` → **포팅 안 함**

우리 MVP는 블로그 전용. 단, 파일의 가치:
- `upconvert.editor.naver.com/blog/html/components` 엔드포인트 확인용 (blog와 cafe가 동일 경로 사용)
- 이미지 업로드 도메인 `cafe.upphoto.naver.com` vs `blog.upphoto.naver.com` 차이 확인

### 5-I. `chromeManager.js` → `src/autoblog/automation/browser.py`

vendor 코드는 읽지 않았지만 **함수 시그니처만 포팅**:
- `launchChrome(profileDir)` → `async def launch_chrome(profile_dir: Path) -> BrowserHandle`
- `connectChrome(port)` → `async def connect_chrome(port: int) -> BrowserContext`
- `extractAllCookies(context, page)` → `async def extract_all_cookies(context) -> list[Cookie]` (httpOnly 포함)
- `filterCookies(cookies, domains)` → `def filter_cookies(cookies, domain_patterns)`
- `cookiesToSessionFormat(cookies)` → `def cookies_to_session(cookies) -> dict`

**Python 실현**: nodriver의 `browser.main_tab.send(cdp.network.get_all_cookies())` 또는 Playwright `context.cookies()`.

---

## 6. Python 신규 의존성

Day 2 시점에 이미 설치된 것: `pydantic`, `loguru`, `pytest`, `ruff`, `mypy`, `pre-commit`.

**Phase 0~1 동안 추가할 것** (`uv add`로):

```toml
dependencies = [
    # 이미 있음
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "loguru>=0.7.2",

    # HTTP/비동기
    "httpx>=0.28",
    "tenacity>=9.0",          # 재시도 데코레이터

    # 브라우저 자동화
    "nodriver>=0.39",          # 메인
    "playwright>=1.48",        # 폴백

    # HTML/파싱
    "beautifulsoup4>=4.12",
    "lxml>=5.3",

    # 자격증명 안전 저장
    "keyring>=25.5",          # macOS Keychain / Windows Credential Manager

    # 이미지 (Phase 2 본격 사용)
    "pillow>=11.0",
    "piexif>=1.1",

    # Google Gemini (Phase 2)
    "google-genai>=0.3",
]
```

---

## 7. 블로그 발행 End-to-End 흐름 (Python 관점)

```
┌─────────────────────────────────────────────────────────────┐
│ [사용자] "이번 주 다녀온 카페 후기 올려줘"                   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ content.ContentProvider.generate_post(topic, options)        │
│   → PostDraft(title, body_html, images, tags, category, ...) │
│   ※ 본문은 "사용자 보유 글쓰기 로직"이 HTML로 만들어 반환    │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ safety.SafetyGate.preflight(draft)                           │
│   - 일 3건 / 시간 1건 하드캡                                 │
│   - 발행 간 최소 4시간 확인                                  │
│   - experience_paragraph ≥ 80자 검증                         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ gui.ReviewGateDialog.show(draft) → 사용자 승인 또는 수정     │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ image.ImagePipeline.run(draft.image_prompts)                 │
│   - Nano Banana 2 생성 or 사용자 제공                        │
│   - ImagePostProcessor.humanize() (EXIF/노이즈/리사이즈)     │
│   → list[Path] (로컬 JPG 파일)                               │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ automation.NaverSession.ensure_logged_in()                   │
│   - nodriver로 사용자 Chrome 프로필 attach                   │
│   - NID_AUT/NID_SES 쿠키 확인                                │
│   - 없으면 로그인 창 띄우고 수동 완료 대기                   │
│   - 쿠키를 httpx cookie jar로 복사                           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ automation.NaverApiClient (httpx 순수 HTTP)                  │
│   1. ensure_blog_id()           [GET MyBlog.naver]           │
│   2. get_categories()           [카테고리 선택]              │
│   3. get_se_token(category_no)  [토큰 발급]                  │
│   4. get_upload_session_key()   [업로드 키]                  │
│   5. upload_image() × N         [이미지 업로드]              │
│   6. html_to_components(html)   [HTML→SE3 변환]              │
│   7. publish_post(...)          [발행!]                      │
│   → PublishResult(url=https://blog.naver.com/{id}/{logNo})   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ db.PublishHistoryRepository.record(draft, result)            │
│ gui.notify("발행 완료", url)                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. 우리 프로젝트에 그대로 쓸 코드 스니펫 Top 5

### 8-1. blogId 추출 정규식 (`naverApiClient.js:123`)

```python
import re
BLOG_ID_RE = re.compile(r"blogId\s*=\s*'([^']+)'")
match = BLOG_ID_RE.search(html)
```

### 8-2. upconvert API 호출 (`naverApiClient.js:266-293`)

```python
UPCONVERT_URL = "https://upconvert.editor.naver.com/blog/html/components"

async def html_to_components(client: httpx.AsyncClient, blog_id: str, html: str) -> list[dict]:
    wrapped = f"<html>\n<body>\n<!--StartFragment-->\n{html}\n<!--EndFragment-->\n</body>\n</html>"
    response = await client.post(
        UPCONVERT_URL,
        params={"documentWidth": "886", "userId": blog_id},
        content=wrapped.encode("utf-8"),
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
    if response.status_code != 200:
        return []
    return response.json()
```

### 8-3. 발행 요청 본문 (`naverApiClient.js:305-395`)

```python
from urllib.parse import urlencode

def build_publish_body(blog_id: str, document_model: dict, population_params: dict) -> str:
    return urlencode({
        "blogId": blog_id,
        "documentModel": json.dumps(document_model, ensure_ascii=False),
        "populationParams": json.dumps(population_params, ensure_ascii=False),
        "productApiVersion": "v1",
    })
```

### 8-4. 이미지 업로드 XML 파싱 (`naverApiClient.js:249-260`)

```python
import re
TAG_RE = re.compile(r"<(\w+)>([^<]*)</\1>")

def parse_upload_response(xml: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in TAG_RE.finditer(xml)}
```

### 8-5. 쿠키에서 로그인 판별 (`session.js:9-21`)

```python
def is_logged_in_by_cookies(cookies: list[dict]) -> bool:
    return any(
        "naver.com" in c.get("domain", "") and c.get("name") in {"NID_AUT", "NID_SES"}
        for c in cookies
    )
```

---

## 9. 라이선스 및 저작권 관리

**viruagent-cli 라이선스**: MIT (자유 사용·수정·배포 가능, 원작자 표기 필요)

**우리 취급 방침**:
1. 포팅한 파일 상단에 원작자 크레딧 주석 추가:
   ```python
   """
   Ported from viruagent-cli (MIT License, Copyright (c) greekr4)
   Original: https://github.com/greekr4/viruagent-cli/blob/main/src/providers/naver/auth.js
   """
   ```
2. 프로젝트 `LICENSE` 파일에 "Includes portions adapted from viruagent-cli (MIT)" 문구 추가 (Phase 1 종료 시점)
3. `vendor/viruagent-cli/` 자체는 **커밋하지 않음** (.gitignore 처리됨)

---

## 10. Day 3 이후 액션 아이템

Day 2가 "분석" 단계였다면, Day 3~7은 **PoC 검증** 단계.

### Day 3 PoC 1: `upconvert.editor.naver.com` API 동작 확인
- `scripts/poc_upconvert.py` 작성
- 간단한 HTML (`<h1>제목</h1><p>본문 테스트</p>`) 전송
- 쿠키 없이도 동작하는지 / 쿠키 필요한지 확인
- **검증 기준**: 200 응답 + 컴포넌트 JSON 배열 수신

### Day 4 PoC 2: nodriver로 네이버 로그인 상태 감지
- `scripts/poc_session.py`
- 사용자가 미리 로그인한 Chrome 프로필에 attach
- `https://blog.naver.com/MyBlog.naver` 방문 → HTML에서 blogId 추출
- **사용자 테스트 계정 필요** (Day 4까지 받기)

### Day 5 PoC 3: Gemini 2.5 + Nano Banana 2 API
- `scripts/poc_gemini.py`
- `google-genai` SDK 설치
- 사용자 API 키로 Gemini 2.5 Flash 호출 (본문 한 문단)
- Nano Banana 2 (`gemini-3.1-flash-image-preview`) 호출 (이미지 1장)
- **사용자 API 키 필요** (Day 5까지 발급 완료)

### Day 6 PoC 4: 이미지 업로드 (`blog.upphoto.naver.com`)
- `scripts/poc_upload.py`
- Day 4에서 얻은 쿠키 + Day 3/5에서 만든 이미지 조합
- **검증 기준**: XML 응답에 `<url>` 존재 + 이미지 URL 브라우저에서 열림

### Day 7 회고 & Phase 1 백로그 확정
- 4개 PoC 결과 종합
- 안 된 것 있으면 대안 설계
- Phase 1 MVP 범위 재검토

---

## 11. 주의사항 (함정 모음)

1. **User-Agent 고정**: Chrome 131로 맞추지 않으면 일부 엔드포인트가 403. 브라우저 버전 업데이트 시 주기적 조정 필요.
2. **Referer 필수**: 거의 모든 엔드포인트가 `blog.naver.com` 기반 Referer 요구.
3. **쿠키 도메인**: `naver.com`, `blog.naver.com`, `nid.naver.com` 등 여러 서브도메인 쿠키 전부 포함해야 함.
4. **Se-Authorization 헤더**: editor 관련 엔드포인트(#4, #5)는 쿠키만으론 401. 헤더 필수.
5. **JSON 이스케이프 이슈**: `PostTitleListAsync.naver`는 `\'` 같은 잘못된 이스케이프가 섞임 → sanitize 필요 (`naverApiClient.js:436`).
6. **이미지 업로드 응답은 XML**: blog는 XML, cafe는 pipe-delimited 텍스트 — **서로 다름**.
7. **`documentModel`의 `id` 필드**: editorId와 일치해야 함. 랜덤 UUID 쓰면 발행 실패 가능.
8. **openType 값**: 2=전체공개, 1=이웃공개, 0=비공개. 다른 값은 400.
9. **태그 상한**: `utils.js:36` 에서 `.slice(0, 10)` — 10개 초과 시 잘려 나감.
10. **카테고리 미지정**: `categoryNo="0"`으로 보내면 안 되고 `getDefaultCategoryNo()`로 실제 기본 카테고리 ID 조회해야 함.
11. **JSON.stringify vs urlencode**: 발행 body는 `application/x-www-form-urlencoded`인데 안에 들어가는 `documentModel`과 `populationParams`는 JSON 문자열. 이중 직렬화 주의.
12. **Content-Type 대소문자**: SmartEditor API는 `text/html; charset=utf-8`처럼 **charset 필수**.

---

## 12. 요약

**오늘 얻은 것**:
- 비공식 API 엔드포인트 10개 전부 문서화
- 로그인 + 발행 전체 흐름 파악
- SE3 컴포넌트 JSON 구조 확인
- Python 포팅 파일 배치 결정
- 봇 탐지 우회 트릭 4가지 식별

**핵심 발견**:
- **블로그는 로그인만 브라우저, 발행은 순수 HTTP** → 우리 설계와 일치
- upconvert API가 HTML→SE3 변환을 공짜로 해줌 → 자체 파서는 폴백만으로 충분
- viruagent-cli가 MIT 라이선스라 구조·상수·정규식을 그대로 가져올 수 있음

**즉시 활용 가능한 자산**:
- `NAVER_LOGIN_ERROR_PATTERNS` 한국어 에러 사전
- 엔드포인트 URL 10개
- SE3 컴포넌트 템플릿 3종
- 발행 populationParams 템플릿

**다음**: Day 3 PoC 1 (upconvert API 실제 호출 검증)
