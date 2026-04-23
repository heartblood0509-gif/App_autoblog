"""PoC 4 — 네이버 이미지 업로드 API 동작 검증.

목적:
  - blog.upphoto.naver.com/{sessionKey}/simpleUpload/0 업로드 성공?
  - XML 응답에서 url/width/height/fileName/fileSize 추출 가능?
  - 업로드 세션키 발급(platform.editor.naver.com)이 쿠키만으로 가능?

플로우:
  1. PoC 2에서 저장한 쿠키 로드 (~/.autoblog/sessions/naver.json)
  2. GET https://blog.naver.com/MyBlog.naver → HTML에서 blogId 추출
  3. GET PostWriteFormSeOptions.naver → Se-Authorization 토큰
  4. GET platform.editor.naver.com/.../session-key → sessionKey
  5. POST blog.upphoto.naver.com/{sessionKey}/simpleUpload/0
     → multipart/form-data (이미지 파일)
  6. XML 응답 파싱

필요한 것 (실행 전):
  - PoC 2 완료 (~/.autoblog/sessions/naver.json 존재)
  - 업로드할 이미지 파일 (PoC 3에서 생성한 poc3_nano_banana_2_test.png 권장)

실행:
  uv run python scripts/poc_upload.py
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("✗ httpx 미설치. `uv sync` 후 재실행.")
    sys.exit(1)

APP_DATA = Path.home() / ".autoblog"
SESSION_FILE = APP_DATA / "sessions" / "naver.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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


def load_cookies() -> str | None:
    if not SESSION_FILE.exists():
        print(f"✗ 세션 파일 없음: {SESSION_FILE}")
        print("  먼저 PoC 2 (scripts/poc_session.py) 를 실행하세요.")
        return None

    payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    cookies = payload.get("cookies", [])
    if not cookies:
        print("✗ 세션 파일에 쿠키 없음.")
        return None

    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("value"))


def pick_image() -> Path | None:
    for candidate in IMAGE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def build_headers(cookie_str: str, *, referer: str = BLOG_HOST) -> dict[str, str]:
    return {
        "Cookie": cookie_str,
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
    }


def fetch_blog_id(client: httpx.Client, cookie_str: str) -> str:
    print("\n▶ 1. blogId 추출")
    response = client.get(
        f"{BLOG_HOST}/MyBlog.naver",
        headers=build_headers(cookie_str),
        follow_redirects=True,
        timeout=20.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"MyBlog.naver 실패: {response.status_code}")

    if "로그인" in response.text or "login" in response.url.path.lower():
        raise RuntimeError("로그인 만료됨. PoC 2 재실행 필요.")

    m = BLOG_ID_RE.search(response.text)
    if not m:
        raise RuntimeError("HTML에서 blogId 찾지 못함")

    blog_id = m.group(1)
    print(f"  ✓ blogId = {blog_id}")
    return blog_id


def fetch_se_token(client: httpx.Client, cookie_str: str, blog_id: str) -> str:
    print("\n▶ 2. Se-Authorization 토큰 발급")
    response = client.get(
        f"{BLOG_HOST}/PostWriteFormSeOptions.naver",
        params={"blogId": blog_id, "categoryNo": "0"},
        headers=build_headers(
            cookie_str,
            referer=f"{BLOG_HOST}/PostWriteForm.naver?blogId={blog_id}&categoryNo=0&Redirect=Write",
        ),
        timeout=20.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"SeOptions 실패: {response.status_code}")

    data = response.json()
    token = (data.get("result") or {}).get("token")
    if not token:
        raise RuntimeError(f"token 필드 없음. 응답 일부: {str(data)[:200]}")

    print(f"  ✓ Se-Authorization (길이 {len(token)}자)")
    return token


def fetch_session_key(client: httpx.Client, cookie_str: str, blog_id: str, token: str) -> str:
    print("\n▶ 3. 이미지 업로드 session-key 발급")
    response = client.get(
        f"{PLATFORM_EDITOR}/photo-uploader/session-key",
        headers={
            **build_headers(
                cookie_str,
                referer=f"{BLOG_HOST}/PostWriteForm.naver?blogId={blog_id}&categoryNo=0",
            ),
            "Se-Authorization": token,
        },
        timeout=20.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"session-key 실패: {response.status_code} / {response.text[:200]}")

    data = response.json()
    session_key = data.get("sessionKey")
    if not session_key:
        raise RuntimeError(f"sessionKey 필드 없음. 응답: {str(data)[:200]}")

    print(f"  ✓ sessionKey = {session_key[:16]}...")
    return session_key


def upload_image(
    client: httpx.Client,
    cookie_str: str,
    blog_id: str,
    session_key: str,
    image_path: Path,
) -> dict[str, Any]:
    print(f"\n▶ 4. 이미지 업로드 ({image_path.name}, {image_path.stat().st_size:,} bytes)")
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

    with image_path.open("rb") as f:
        files = {
            "image": (
                image_path.name,
                f,
                "image/jpeg" if image_path.suffix != ".png" else "image/png",
            )
        }
        response = client.post(
            upload_url,
            params=params,
            headers={
                "Cookie": cookie_str,
                "User-Agent": USER_AGENT,
                "Referer": f"{BLOG_HOST}/{blog_id}",
            },
            files=files,
            timeout=60.0,
        )

    if response.status_code != 200:
        raise RuntimeError(f"업로드 실패: {response.status_code} / {response.text[:300]}")

    xml = response.text
    if "<url>" not in xml:
        raise RuntimeError(f"응답에 <url> 태그 없음. 원본: {xml[:300]}")

    result: dict[str, Any] = {m.group(1): m.group(2) for m in XML_TAG_RE.finditer(xml)}
    for k in ("width", "height", "fileSize"):
        if k in result:
            with contextlib.suppress(ValueError):
                result[k] = int(result[k])

    return result


def main() -> int:
    print("=" * 60)
    print("PoC 4 — 네이버 이미지 업로드 API")
    print("=" * 60)

    cookie_str = load_cookies()
    if not cookie_str:
        return 1

    image_path = pick_image()
    if not image_path:
        print("✗ 업로드할 이미지 없음. 다음 중 하나가 필요:")
        for c in IMAGE_CANDIDATES:
            print(f"    - {c}")
        print("  PoC 3 먼저 실행해서 이미지 생성하거나 직접 파일 준비.")
        return 1

    print(f"\n세션 파일  : {SESSION_FILE}")
    print(f"업로드 이미지: {image_path}")

    try:
        with httpx.Client() as client:
            blog_id = fetch_blog_id(client, cookie_str)
            token = fetch_se_token(client, cookie_str, blog_id)
            session_key = fetch_session_key(client, cookie_str, blog_id, token)
            result = upload_image(client, cookie_str, blog_id, session_key, image_path)
    except Exception as e:
        print(f"\n✗ 업로드 파이프라인 실패: {e}")
        return 1

    print("\n" + "=" * 60)
    print("업로드 성공! 응답:")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k:12s} = {v}")

    print("\n✓ Phase 1 이미지 업로드 로직 구현 가능.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
