"""PoC 4 (Playwright 버전) — 네이버 이미지 업로드 API 동작 검증.

왜 Playwright 기반으로 재작성:
  - httpx 단일 요청으로는 blog.upphoto.naver.com이 LOGIN 에러 반환
  - 2025-07 네이버 보안 강화로 업로드 API가 "진짜 브라우저 세션"에만 응답하는 것으로 추정
  - Playwright context.request를 쓰면 persistent profile의 쿠키+핑거프린트가 함께 전달 → 브라우저로 인식

플로우:
  1. PoC 2에서 저장한 persistent Chrome 프로필 재사용 (헤드리스로 Chrome 실행)
  2. context.request.get MyBlog.naver → HTML에서 blogId 추출
  3. PostWriteFormSeOptions.naver → Se-Authorization 토큰
  4. platform.editor.naver.com/photo-uploader/session-key → sessionKey
  5. blog.upphoto.naver.com/{sessionKey}/simpleUpload/0 → multipart 업로드
  6. XML 응답 파싱

필요한 것 (실행 전):
  - PoC 2 완료 (~/.autoblog/chrome-profiles/naver/ 에 로그인 쿠키 저장됨)
  - 업로드할 이미지 (PoC 3 생성물 또는 직접 준비)

실행:
  uv run python scripts/poc_upload.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from playwright.async_api import BrowserContext, async_playwright
except ImportError:
    print("✗ playwright 미설치. `uv sync --extra fallback` 후 재실행.")
    sys.exit(1)

APP_DATA = Path.home() / ".autoblog"
PROFILE_DIR = APP_DATA / "chrome-profiles" / "naver"
SESSION_FILE = APP_DATA / "sessions" / "naver.json"


def load_cookies_for_playwright() -> list[dict[str, Any]]:
    """PoC 2에서 저장한 쿠키를 Playwright add_cookies 포맷으로 변환."""
    if not SESSION_FILE.exists():
        return []
    payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    result: list[dict[str, Any]] = []
    for c in payload.get("cookies", []):
        if not c.get("value"):
            continue
        same_site = c.get("same_site")
        if same_site not in ("Strict", "Lax", "None"):
            same_site = "Lax"
        expires = c.get("expires")
        if expires is None or expires <= 0:
            # 세션 쿠키는 24시간 유효로 강제 (업로드 시점까지만 버티면 됨)
            import time as _t

            expires = int(_t.time()) + 86400
        result.append(
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "expires": float(expires),
                "httpOnly": c.get("http_only", False),
                "secure": c.get("secure", False),
                "sameSite": same_site,
            }
        )
    return result

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
BLOG_HOST = "https://blog.naver.com"
PLATFORM_EDITOR = "https://platform.editor.naver.com/api/blogpc001/v1"
UPLOAD_DOMAIN = "https://blog.upphoto.naver.com"

IMAGE_CANDIDATES = [
    Path("docs/poc_responses/poc3_nano_banana_2_test.png"),
    Path("docs/poc_responses/sample.jpg"),
]

BLOG_ID_RE = re.compile(r"blogId\s*=\s*'([^']+)'")
XML_TAG_RE = re.compile(r"<(\w+)>([^<]*)</\1>")


def pick_image() -> Path | None:
    for candidate in IMAGE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


async def fetch_blog_id(ctx: BrowserContext) -> str:
    print("\n▶ 1. blogId 추출")
    response = await ctx.request.get(f"{BLOG_HOST}/MyBlog.naver")
    if response.status != 200:
        raise RuntimeError(f"MyBlog.naver 실패: {response.status}")
    body = await response.text()
    if "로그인" in body and "nidlogin" in body:
        raise RuntimeError("로그인 만료됨. PoC 2 재실행 필요.")
    m = BLOG_ID_RE.search(body)
    if not m:
        raise RuntimeError("HTML에서 blogId 찾지 못함")
    blog_id = m.group(1)
    print(f"  ✓ blogId = {blog_id}")
    return blog_id


async def fetch_se_token(ctx: BrowserContext, blog_id: str) -> str:
    print("\n▶ 2. Se-Authorization 토큰 발급")
    response = await ctx.request.get(
        f"{BLOG_HOST}/PostWriteFormSeOptions.naver",
        params={"blogId": blog_id, "categoryNo": "0"},
        headers={
            "Referer": (
                f"{BLOG_HOST}/PostWriteForm.naver"
                f"?blogId={blog_id}&categoryNo=0&Redirect=Write"
            ),
        },
    )
    if response.status != 200:
        raise RuntimeError(f"SeOptions 실패: {response.status}")
    data = await response.json()
    token = (data.get("result") or {}).get("token")
    if not token:
        raise RuntimeError(f"token 필드 없음. 응답: {str(data)[:200]}")
    print(f"  ✓ Se-Authorization (길이 {len(token)}자)")
    return token


async def fetch_session_key(ctx: BrowserContext, blog_id: str, token: str) -> str:
    print("\n▶ 3. 이미지 업로드 session-key 발급")
    response = await ctx.request.get(
        f"{PLATFORM_EDITOR}/photo-uploader/session-key",
        headers={
            "Referer": (
                f"{BLOG_HOST}/PostWriteForm.naver?blogId={blog_id}&categoryNo=0"
            ),
            "Se-Authorization": token,
        },
    )
    if response.status != 200:
        raise RuntimeError(f"session-key 실패: {response.status}")
    data = await response.json()
    session_key = data.get("sessionKey")
    if not session_key:
        raise RuntimeError(f"sessionKey 필드 없음. 응답: {str(data)[:200]}")
    print(f"  ✓ sessionKey = {session_key[:16]}...")
    return session_key


async def upload_image(
    ctx: BrowserContext,
    blog_id: str,
    session_key: str,
    image_path: Path,
    token: str,
) -> dict[str, Any]:
    print(f"\n▶ 4. 이미지 업로드 ({image_path.name}, {image_path.stat().st_size:,} bytes)")

    image_bytes = image_path.read_bytes()
    mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"

    upload_url = f"{UPLOAD_DOMAIN}/{session_key}/simpleUpload/0"
    params = {
        "userId": blog_id,
        "extractExif": "true",
        "extractAnimatedCnt": "true",
        "autorotate": "true",
        "extractDominantColor": "false",
        "denyAnimatedImage": "false",
        "skipXcamFiltering": "false",
    }

    response = await ctx.request.post(
        upload_url,
        params=params,
        multipart={
            "image": {
                "name": image_path.name,
                "mimeType": mime_type,
                "buffer": image_bytes,
            }
        },
        headers={
            "Referer": (
                f"{BLOG_HOST}/PostWriteForm.naver?blogId={blog_id}&categoryNo=0&Redirect=Write"
            ),
            "Origin": BLOG_HOST,
            "Se-Authorization": token,
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
        },
    )

    if response.status != 200:
        body = await response.text()
        raise RuntimeError(f"업로드 HTTP 실패: {response.status} / {body[:300]}")

    xml = await response.text()
    if "<url>" not in xml:
        raise RuntimeError(f"응답에 <url> 없음. 원본: {xml[:300]}")

    result: dict[str, Any] = {m.group(1): m.group(2) for m in XML_TAG_RE.finditer(xml)}
    for k in ("width", "height", "fileSize"):
        if k in result:
            try:
                result[k] = int(result[k])
            except ValueError:
                pass
    return result


async def main() -> int:
    print("=" * 60)
    print("PoC 4 (Playwright) — 네이버 이미지 업로드 API")
    print("=" * 60)

    if not PROFILE_DIR.exists():
        print(f"✗ Chrome 프로필 없음: {PROFILE_DIR}")
        print("  먼저 PoC 2 (scripts/poc_session.py) 를 실행하세요.")
        return 1

    image_path = pick_image()
    if not image_path:
        print("✗ 업로드할 이미지 없음. 다음 중 하나가 필요:")
        for c in IMAGE_CANDIDATES:
            print(f"    - {c}")
        return 1

    print(f"\n프로필     : {PROFILE_DIR}")
    print(f"업로드 이미지: {image_path}")

    cookies = load_cookies_for_playwright()
    print(f"\n세션 쿠키 주입 예정: {len(cookies)}개")

    print("\n▶ Playwright 실행 중 (headless Chrome)...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            channel="chrome",
            user_agent=USER_AGENT,
        )
        try:
            if cookies:
                await context.add_cookies(cookies)
                print(f"  ✓ 쿠키 {len(cookies)}개 주입 완료")
            blog_id = await fetch_blog_id(context)
            token = await fetch_se_token(context, blog_id)
            session_key = await fetch_session_key(context, blog_id, token)
            result = await upload_image(context, blog_id, session_key, image_path, token)
        except Exception as e:
            print(f"\n✗ 업로드 파이프라인 실패: {e}")
            return 1
        finally:
            await context.close()

    print("\n" + "=" * 60)
    print("업로드 성공! 응답:")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k:12s} = {v}")

    print("\n✓ Phase 1 이미지 업로드 로직 구현 가능 (Playwright context.request 기반).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
