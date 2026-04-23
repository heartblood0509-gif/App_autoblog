"""PoC 2 — Playwright로 네이버 로그인 자동화 + 쿠키 추출 검증.

nodriver가 macOS에서 Chrome 연결 실패(알려진 이슈)하여 CR-002 폴백인 Playwright로 전환.
사용자 본인 `app-blog2` 프로젝트와도 동일한 스택이라 통합에 유리.

목적:
  - Playwright + 시스템 Chrome + persistent context로 로그인 상태 자동 감지
  - NID_AUT / NID_SES 쿠키를 추출해 JSON 파일로 저장

설계 원칙:
  - 사용자의 메인 Chrome 프로필은 절대 건드리지 않음.
  - 프로젝트 전용 프로필(`~/.autoblog/chrome-profiles/naver/`)에만 저장.
  - 첫 실행은 사용자가 직접 로그인 (수동). 이후엔 쿠키 재사용.

필요한 것 (실행 전):
  - **네이버 테스트 계정 1개** (메인 계정 금지)
  - `uv sync --extra fallback` 실행됨

실행:
  uv run python scripts/poc_session.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from playwright.async_api import BrowserContext, Page, async_playwright
except ImportError:
    print("✗ playwright 미설치. `uv sync --extra fallback` 후 재실행.")
    sys.exit(1)

# 프로젝트 데이터 디렉토리 (사용자 메인 Chrome과 격리)
APP_DATA = Path.home() / ".autoblog"
PROFILE_DIR = APP_DATA / "chrome-profiles" / "naver"
SESSION_FILE = APP_DATA / "sessions" / "naver.json"

NAVER_MYINFO = "https://nid.naver.com/user2/help/myInfo"
LOGIN_HOST = "nid.naver.com/nidlogin"
LOGIN_WAIT_SEC = 1800  # 30분 수동 로그인 허용 (여유롭게)
CHECK_INTERVAL_SEC = 2


def is_on_login_page(url: str) -> bool:
    return LOGIN_HOST in url


def mask_cookie(value: str, keep: int = 4) -> str:
    """쿠키 값을 로그용으로 마스킹."""
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}...{value[-keep:]} ({len(value)}자)"


async def wait_for_login(page: Page, timeout_sec: int) -> bool:
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


async def extract_naver_cookies(context: BrowserContext) -> list[dict[str, Any]]:
    """Playwright context에서 naver.com 쿠키 전체 추출 (httpOnly 포함)."""
    all_cookies = await context.cookies()
    return [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "expires": c.get("expires"),
            "http_only": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "same_site": c.get("sameSite"),
        }
        for c in all_cookies
        if "naver.com" in c.get("domain", "")
    ]


def save_session(cookies: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "captured_at": datetime.now().isoformat(),
        "cookies": cookies,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def summarize_cookies(cookies: list[dict[str, Any]]) -> None:
    auth_cookies = {c["name"]: c for c in cookies if c["name"] in {"NID_AUT", "NID_SES", "NID_JKL"}}
    print(f"\n  총 네이버 쿠키 개수: {len(cookies)}")
    print("  인증 쿠키 상태:")
    for name in ("NID_AUT", "NID_SES", "NID_JKL"):
        c = auth_cookies.get(name)
        if c:
            value = str(c["value"])
            domain = c["domain"]
            http_only = c["http_only"]
            print(
                f"    ✓ {name:10s} = {mask_cookie(value)}  domain={domain}  httpOnly={http_only}"
            )
        else:
            required = name in {"NID_AUT", "NID_SES"}
            mark = "✗" if required else "-"
            print(f"    {mark} {name:10s} = (없음){'  [필수]' if required else ''}")


async def main() -> int:
    print("=" * 60)
    print("PoC 2 (Playwright) — 네이버 로그인 자동화 + 쿠키 추출")
    print("=" * 60)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nChrome 프로필 : {PROFILE_DIR}")
    print(f"세션 저장 위치: {SESSION_FILE}")

    print("\n▶ Playwright로 Chrome 실행 중 (시스템 Google Chrome 사용)...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            print("▶ 네이버 '내 정보' 페이지 접속...")
            await page.goto(NAVER_MYINFO, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Chrome 창을 화면 전면으로 가져오기 (다른 창에 가려지지 않게)
            try:
                await page.bring_to_front()
            except Exception:
                pass  # 일부 환경에서 실패 가능, 치명적이진 않음

            current_url = page.url
            print(f"  현재 URL: {current_url}")

            if is_on_login_page(current_url):
                print("  → 로그인 안 된 상태")
                logged_in = await wait_for_login(page, LOGIN_WAIT_SEC)
                if not logged_in:
                    print(f"\n✗ {LOGIN_WAIT_SEC // 60}분 내 로그인 미완료. 종료.")
                    return 1
                print("  ✓ 로그인 감지됨")
            else:
                print("  ✓ 이미 로그인 상태 (쿠키 재사용 중)")

            print("\n▶ 쿠키 추출 중...")
            cookies = await extract_naver_cookies(context)

            if not cookies:
                print("✗ 네이버 쿠키가 하나도 추출되지 않음. 실패.")
                return 1

            summarize_cookies(cookies)

            save_session(cookies, SESSION_FILE)
            print(f"\n✓ 세션 파일 저장: {SESSION_FILE}")

            has_both = {"NID_AUT", "NID_SES"}.issubset({c["name"] for c in cookies})
            has_auth = any(c["name"] in {"NID_AUT", "NID_SES"} for c in cookies)

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
            await context.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
