"""PoC 2 — nodriver로 네이버 로그인 자동화 + 쿠키 추출 검증.

목적:
  - nodriver로 Chrome을 사용자 프로필로 띄울 수 있는가?
  - 네이버 로그인 상태를 URL 리다이렉트로 판별 가능한가?
  - NID_AUT / NID_SES 쿠키를 추출해 JSON 파일로 저장 가능한가?

설계 원칙:
  - 사용자의 메인 Chrome 프로필은 절대 건드리지 않음.
  - 프로젝트 전용 프로필(`~/.autoblog/chrome-profiles/naver/`)에만 저장.
  - 첫 실행은 사용자가 직접 로그인 (수동). 이후엔 쿠키 재사용.

필요한 것 (실행 전):
  - **네이버 테스트 계정 1개** (메인 계정 금지)

실행:
  uv run python scripts/poc_session.py

실행 후 동작:
  1. Chrome 창이 열림 (프로젝트 전용 프로필)
  2. 네이버 '내 정보' 페이지로 이동
  3. 로그인 안 되어 있으면 → 로그인 페이지로 리다이렉트됨
     → 사용자가 직접 **테스트 계정**으로 로그인 (최대 5분 대기)
  4. 로그인 성공 감지 → 쿠키 추출 → `~/.autoblog/sessions/naver.json`에 저장
  5. 다음 실행부터는 이미 로그인된 상태로 즉시 쿠키 추출
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import nodriver as uc
except ImportError:
    print("✗ nodriver가 설치되지 않았습니다. `uv sync` 실행 후 다시 시도.")
    sys.exit(1)

# 프로젝트 데이터 디렉토리 (사용자 메인 Chrome과 격리)
APP_DATA = Path.home() / ".autoblog"
PROFILE_DIR = APP_DATA / "chrome-profiles" / "naver"
SESSION_FILE = APP_DATA / "sessions" / "naver.json"

NAVER_MYINFO = "https://nid.naver.com/user2/help/myInfo"
LOGIN_HOST = "nid.naver.com/nidlogin"
LOGIN_WAIT_SEC = 300  # 5분 수동 로그인 허용
CHECK_INTERVAL_SEC = 2


def is_on_login_page(url: str) -> bool:
    return LOGIN_HOST in url


def mask_cookie(value: str, keep: int = 4) -> str:
    """쿠키 값을 로그용으로 마스킹."""
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}...{value[-keep:]} ({len(value)}자)"


async def wait_for_login(page: uc.Tab, timeout_sec: int) -> bool:
    """로그인 페이지에서 빠져나올 때까지 대기."""
    deadline = asyncio.get_event_loop().time() + timeout_sec

    print(f"\n⏳ 로그인 페이지 감지됨. {timeout_sec}초 이내에 브라우저에서 로그인해주세요.")
    print("   (테스트 계정을 사용하세요. 메인 계정 금지)")

    while asyncio.get_event_loop().time() < deadline:
        current_url = page.url or ""
        if not is_on_login_page(current_url) and "naver.com" in current_url:
            return True
        await asyncio.sleep(CHECK_INTERVAL_SEC)

    return False


async def extract_naver_cookies(browser: uc.Browser) -> list[dict[str, str | bool | int | None]]:
    """CDP로 naver.com 전체 쿠키 추출 (httpOnly 포함)."""
    all_cookies = await browser.cookies.get_all()
    return [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "expires": c.expires,
            "http_only": c.http_only,
            "secure": c.secure,
            "same_site": str(c.same_site) if c.same_site else None,
        }
        for c in all_cookies
        if c.domain and "naver.com" in c.domain
    ]


def save_session(cookies: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "captured_at": datetime.now().isoformat(),
        "cookies": cookies,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def summarize_cookies(cookies: list[dict[str, object]]) -> None:
    auth_cookies = {c["name"]: c for c in cookies if c["name"] in {"NID_AUT", "NID_SES", "NID_JKL"}}
    print(f"\n  총 네이버 쿠키 개수: {len(cookies)}")
    print("  인증 쿠키 상태:")
    for name in ("NID_AUT", "NID_SES", "NID_JKL"):
        c = auth_cookies.get(name)
        if c:
            value = str(c["value"])
            domain = c["domain"]
            http_only = c["http_only"]
            print(f"    ✓ {name:10s} = {mask_cookie(value)}  domain={domain}  httpOnly={http_only}")
        else:
            required = name in {"NID_AUT", "NID_SES"}
            mark = "✗" if required else "-"
            print(f"    {mark} {name:10s} = (없음){'  [필수]' if required else ''}")


async def main() -> int:
    print("=" * 60)
    print("PoC 2 — 네이버 로그인 자동화 + 쿠키 추출")
    print("=" * 60)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nChrome 프로필 : {PROFILE_DIR}")
    print(f"세션 저장 위치: {SESSION_FILE}")

    print("\n▶ Chrome 실행 중...")
    browser = await uc.start(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
    )
    try:
        print("▶ 네이버 '내 정보' 페이지 접속...")
        page = await browser.get(NAVER_MYINFO)
        await asyncio.sleep(2)

        current_url = page.url or ""
        print(f"  현재 URL: {current_url}")

        if is_on_login_page(current_url):
            print("  → 로그인 안 된 상태")
            logged_in = await wait_for_login(page, LOGIN_WAIT_SEC)
            if not logged_in:
                print("\n✗ 5분 내 로그인 미완료. 종료.")
                return 1
            print("  ✓ 로그인 감지됨")
        else:
            print("  ✓ 이미 로그인 상태 (쿠키 재사용 중)")

        print("\n▶ 쿠키 추출 중...")
        cookies = await extract_naver_cookies(browser)

        if not cookies:
            print("✗ 네이버 쿠키가 하나도 추출되지 않음. 실패.")
            return 1

        summarize_cookies(cookies)

        save_session(cookies, SESSION_FILE)
        print(f"\n✓ 세션 파일 저장: {SESSION_FILE}")

        has_auth = any(c["name"] in {"NID_AUT", "NID_SES"} for c in cookies)
        has_both = {"NID_AUT", "NID_SES"}.issubset({c["name"] for c in cookies})

        print("\n" + "=" * 60)
        print("판정")
        print("=" * 60)
        if has_both:
            print("✓ NID_AUT + NID_SES 모두 확보. 다음 PoC(API 호출) 가능.")
            return 0
        elif has_auth:
            print("△ 일부 인증 쿠키만 확보. 재로그인 필요 가능성.")
            return 0
        else:
            print("✗ 인증 쿠키 누락. 로그인 플로우 재점검 필요.")
            return 1

    finally:
        print("\n▶ 브라우저 종료 중...")
        with contextlib.suppress(Exception):
            browser.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
