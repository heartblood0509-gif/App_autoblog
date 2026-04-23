# scripts/

Phase 0 동안 "가장 위험한 가정"을 검증하는 PoC(Proof of Concept) 스크립트 모음.
실행 결과는 `docs/poc_results.md`에 기록되며, 원본 응답은 `docs/poc_responses/` 에 저장된다.

## 실행 방법

모든 스크립트는 프로젝트 루트에서 `uv run`으로 실행한다.

```bash
uv run python scripts/poc_upconvert.py
```

## 스크립트 목록

| 파일 | 검증 내용 | 필요한 것 | 상태 |
|---|---|---|---|
| `poc_upconvert.py` | upconvert.editor.naver.com API 동작 | (없음) | ✅ 통과 |
| `poc_session.py` | 네이버 로그인 자동화 / 쿠키 추출 | 네이버 테스트 계정 | 작성 예정 |
| `poc_gemini.py` | Gemini 2.5 + Nano Banana 2 API | 사용자 Google API 키 | 작성 예정 |
| `poc_upload.py` | 이미지 업로드 (blog.upphoto.naver.com) | PoC 2 쿠키 + PoC 3 이미지 | 작성 예정 |
| `poc_qasync.py` | PySide6 + asyncio 통합 검증 | (없음) | 작성 예정 |

## PoC 스크립트 작성 규칙

1. 독립 실행 가능 (인자 없이 `uv run python scripts/poc_XXX.py`)
2. 결과 판정을 명확히 출력 (✅ / ✗ 기호)
3. 원본 응답은 `docs/poc_responses/` 에 저장
4. 외부 서비스 호출 실패를 네트워크/인증/스키마로 구분
5. 절대 실제 네이버 발행까지 가지 않음 (임시저장 또는 dry-run만)

## 주의

- 이 스크립트들은 프로덕션 코드가 아니다. 실험/검증용.
- 사용자 API 키/쿠키는 **절대 로그에 찍히지 않게** 마스킹.
- 실행 후 생성된 응답 파일은 민감정보 유무 확인 후 커밋.
