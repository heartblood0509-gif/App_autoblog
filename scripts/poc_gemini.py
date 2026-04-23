"""PoC 3 — Google Gemini 2.5 + Nano Banana 2 API 동작 검증.

목적:
  - 사용자 API 키로 Gemini 2.5 Flash가 한국어 문단 생성 가능한가?
  - Nano Banana 2 (gemini-3.1-flash-image-preview)가 이미지 생성 가능한가?
  - 1회 호출당 실제 비용은?
  - CR-005 BYOK 안전 장치: 모델 화이트리스트, 소액 테스트 호출이 실전에서 동작하는가?

필요한 것 (실행 전):
  - **사용자 Google Gemini API 키 1개**
  - 환경변수 GEMINI_API_KEY 또는 프로젝트 루트 .env 파일에 `GEMINI_API_KEY=AIza...`
  - (프로덕션 앱에서는 keyring 사용. PoC는 환경변수 허용)

실행:
  export GEMINI_API_KEY=AIza...your_key...
  uv run python scripts/poc_gemini.py

주의:
  - Nano Banana 2는 Free tier에서 사용 불가. Google Cloud 결제 카드 등록 필요.
  - 결제 등록 전이면 이 PoC의 이미지 단계는 실패 예상. Gemini 2.5 Flash 텍스트만 확인 가능.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("✗ google-genai 미설치. `uv sync` 후 재실행.")
    sys.exit(1)

# CR-005: 모델 화이트리스트 하드코딩
ALLOWED_MODELS = {
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-image-preview",
}

TEXT_MODEL = "gemini-2.5-flash"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"

PROMPT_KOREAN = """연남동의 작은 카페를 다녀온 블로그 후기를 2~3문단으로 한국어로 작성해주세요.
자연스러운 일상 블로거 말투(~더라구요, ~였어요)를 사용하세요.
광고 느낌 없이, 구체적인 감각적 디테일(맛·분위기·음악 등)을 포함해주세요.
약 300자 분량."""

PROMPT_IMAGE = (
    "A cozy small cafe interior in Seoul's Yeonnam-dong neighborhood, "
    "warm afternoon sunlight through large windows, wooden tables, "
    "a latte and tiramisu on a rustic wooden table, "
    "amateur smartphone photo style, shallow depth of field"
)

OUTPUT_DIR = Path("docs/poc_responses")


def load_api_key() -> str | None:
    # 1) 환경변수
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key

    # 2) .env 파일 (간단 파서, python-dotenv 없이)
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def mask_key(key: str) -> str:
    if len(key) < 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def validate_model(model_id: str) -> None:
    if model_id not in ALLOWED_MODELS:
        raise ValueError(
            f"모델 {model_id}는 화이트리스트에 없습니다. 허용 모델: {sorted(ALLOWED_MODELS)}"
        )


def test_text_generation(client: genai.Client) -> tuple[bool, str]:
    print("\n" + "─" * 60)
    print(f"▶ 시나리오 1: {TEXT_MODEL} 한국어 블로그 후기 생성")
    print("─" * 60)

    validate_model(TEXT_MODEL)

    try:
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=PROMPT_KOREAN,
        )
    except Exception as e:
        print(f"✗ 호출 실패: {e}")
        return False, str(e)

    text = response.text or ""
    print(f"\n  [생성된 본문, 길이 {len(text)}자]")
    print("  " + "\n  ".join(text.split("\n")[:10]))

    # 사용량 정보 추출 시도
    try:
        usage = response.usage_metadata
        if usage:
            print("\n  [사용량]")
            print(f"    입력 토큰: {usage.prompt_token_count}")
            print(f"    출력 토큰: {usage.candidates_token_count}")
            # Flash 가격: 입력 $0.30/1M, 출력 $2.50/1M
            cost = (usage.prompt_token_count or 0) * 0.30 / 1_000_000 + (
                usage.candidates_token_count or 0
            ) * 2.50 / 1_000_000
            print(f"    예상 비용: ${cost:.6f} (약 {cost * 1450:.3f}원)")
    except Exception:
        print("  [사용량 정보 없음]")

    return True, text


def test_image_generation(client: genai.Client) -> tuple[bool, str]:
    print("\n" + "─" * 60)
    print(f"▶ 시나리오 2: {IMAGE_MODEL} (Nano Banana 2) 이미지 생성")
    print("─" * 60)

    validate_model(IMAGE_MODEL)

    try:
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=PROMPT_IMAGE,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="4:3",
                    image_size="1K",
                ),
            ),
        )
    except Exception as e:
        print(f"✗ 호출 실패: {e}")
        print("  (무료 tier는 이미지 생성 불가. 결제 카드 등록 필요.)")
        return False, str(e)

    # 이미지 바이트 추출
    image_bytes: bytes | None = None
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                break
        if image_bytes:
            break

    if not image_bytes:
        print("✗ 응답에 이미지 데이터 없음.")
        return False, "no_image_data"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "poc3_nano_banana_2_test.png"
    out_path.write_bytes(image_bytes)

    print(f"\n  ✓ 이미지 저장됨: {out_path} ({len(image_bytes):,} bytes)")
    print("  ✓ Nano Banana 2 1K = $0.067/이미지 (약 97원)")

    return True, str(out_path)


def main() -> int:
    print("=" * 60)
    print("PoC 3 — Google Gemini 2.5 + Nano Banana 2")
    print("=" * 60)

    api_key = load_api_key()
    if not api_key:
        print("\n✗ API 키를 찾을 수 없습니다.")
        print("  환경변수 GEMINI_API_KEY 또는 .env 파일에 설정해주세요.")
        print("  키 발급: https://aistudio.google.com/app/apikey")
        return 1

    print(f"\nAPI 키 (마스킹): {mask_key(api_key)}")
    print(f"허용 모델 화이트리스트: {sorted(ALLOWED_MODELS)}")

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"✗ 클라이언트 생성 실패: {e}")
        return 1

    text_ok, _text = test_text_generation(client)
    image_ok, _image = test_image_generation(client)

    print("\n" + "=" * 60)
    print("판정")
    print("=" * 60)
    print(f"  Gemini 2.5 Flash (텍스트)    : {'✓' if text_ok else '✗'}")
    print(f"  Nano Banana 2 (이미지)       : {'✓' if image_ok else '✗'}")

    if text_ok and image_ok:
        print("\n✓ 전체 통과. Phase 1 AI 파이프라인 구축 가능.")
        return 0
    elif text_ok:
        print("\n△ 텍스트만 통과. 이미지는 결제 카드 등록 후 재시도 권장.")
        return 0
    else:
        print("\n✗ 텍스트 생성도 실패. API 키/권한/할당량 재점검 필요.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
