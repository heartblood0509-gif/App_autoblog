"""PoC 1 — upconvert.editor.naver.com API 동작 검증.

목적:
  - 네이버 비공식 API(HTML → SmartEditor 컴포넌트 변환)가 실제로 동작하는가?
  - 쿠키 없이도 호출 가능한가? (가능하면 Day 5-6 사용자 계정 기다리지 않고 진행 가능)
  - 응답 JSON 구조는 viruagent-cli 분석과 일치하는가?

이 PoC가 실패하면 프로젝트 설계 전반을 재검토해야 함 (브라우저 DOM 조작으로 폴백).

실행:
  uv run python scripts/poc_upconvert.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

URL = "https://upconvert.editor.naver.com/blog/html/components"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TIMEOUT_SEC = 30.0

SAMPLE_HTML = """<h1>카페 다녀왔어요</h1>
<p>어제 연남동의 작은 카페에 다녀왔습니다.</p>
<p>라떼 한 잔과 디저트가 정말 맛있었어요.</p>
<strong>특히 티라미수가 인상적이었습니다.</strong>
<p>다음에 또 가고 싶은 곳이에요.</p>"""


def wrap_html(html: str) -> str:
    """naverApiClient.js:267 의 래핑 포맷 그대로."""
    return f"<html>\n<body>\n<!--StartFragment-->\n{html}\n<!--EndFragment-->\n</body>\n</html>"


async def call_api(
    *,
    cookie: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """upconvert API 호출. 응답을 구조화된 dict로 반환."""
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "User-Agent": USER_AGENT,
    }
    if cookie:
        headers["Cookie"] = cookie

    params: dict[str, str] = {"documentWidth": "886"}
    if user_id:
        params["userId"] = user_id

    async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
        response = await client.post(
            URL,
            params=params,
            content=wrap_html(SAMPLE_HTML).encode("utf-8"),
            headers=headers,
        )

    return {
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "body_text": response.text,
        "body_len": len(response.text),
    }


def save_response_files(results: list[dict[str, Any]], out_dir: Path) -> None:
    """Sync 파일 저장 헬퍼. async 함수에서는 asyncio.to_thread로 호출."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, result in enumerate(results, start=1):
        out_path = out_dir / f"poc1_upconvert_scenario{idx}.json"
        payload = {
            "status": result["status"],
            "content_type": result["content_type"],
            "body": result["body_text"],
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def summarize_response(label: str, result: dict[str, Any]) -> None:
    print(f"\n{'─' * 60}")
    print(f"▶ {label}")
    print(f"{'─' * 60}")
    print(f"  Status       : {result['status']}")
    print(f"  Content-Type : {result['content_type']}")
    print(f"  Body length  : {result['body_len']:,} bytes")

    if result["status"] != 200:
        print(f"  Body preview : {result['body_text'][:300]}")
        return

    try:
        data = json.loads(result["body_text"])
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON 파싱 실패: {e}")
        print(f"  Body preview : {result['body_text'][:300]}")
        return

    if not isinstance(data, list):
        print(f"  ✗ 응답이 배열 아님. 실제 타입: {type(data).__name__}")
        print(f"  Body preview : {result['body_text'][:500]}")
        return

    print(f"  ✓ JSON 배열 응답, 컴포넌트 개수: {len(data)}")
    ctypes = [c.get("@ctype", "?") for c in data]
    print(f"  컴포넌트 타입: {ctypes}")

    # 첫 컴포넌트 전체 덤프 (구조 확인용)
    if data:
        print("\n  [첫 컴포넌트 JSON]")
        dump = json.dumps(data[0], indent=2, ensure_ascii=False)
        for line in dump.split("\n")[:25]:
            print(f"    {line}")
        if dump.count("\n") > 25:
            print("    ...")


async def main() -> int:
    print("=" * 60)
    print("PoC 1 — upconvert.editor.naver.com/blog/html/components")
    print("=" * 60)
    print(f"\nURL         : {URL}")
    print("샘플 HTML    : 5개 요소 (h1 + p*3 + strong)")
    print(f"타임아웃     : {TIMEOUT_SEC}초")

    # 시나리오 1: 쿠키 없이, userId 없이
    try:
        result1 = await call_api()
    except httpx.HTTPError as e:
        print(f"\n✗ 시나리오 1 네트워크 에러: {e}")
        return 1
    summarize_response("시나리오 1: 쿠키 없음 + userId 없음", result1)

    # 시나리오 2: 쿠키 없이 + 가짜 userId
    try:
        result2 = await call_api(user_id="testblog")
    except httpx.HTTPError as e:
        print(f"\n✗ 시나리오 2 네트워크 에러: {e}")
        return 1
    summarize_response("시나리오 2: 쿠키 없음 + userId=testblog", result2)

    # 결과를 파일로 저장 (Day 7 회고 자료).
    # pathlib / file write는 blocking I/O라서 asyncio.to_thread로 감쌈 (ASYNC240 회피).
    out_dir = Path("docs/poc_responses")
    await asyncio.to_thread(save_response_files, [result1, result2], out_dir)
    print(f"\n✓ 원본 응답 저장됨: {out_dir}/")

    # 판정
    print("\n" + "=" * 60)
    print("판정")
    print("=" * 60)
    any_ok = any(r["status"] == 200 for r in [result1, result2])
    if any_ok:
        print("✓ API 살아 있음. 프로젝트 설계 유지 가능.")
        print("  다음: 응답 JSON 구조를 pydantic 모델로 정의 (CR-003).")
        return 0
    else:
        print("✗ 모든 시나리오 실패. 쿠키 필요하거나 API 스펙 변경 의심.")
        print("  → Day 5-6 사용자 네이버 계정으로 재시도 필요.")
        print("  → DOM 자동화 폴백 path 설계 시급.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
