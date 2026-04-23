# Critical 기술 결정 (Phase 0 Day 2 리뷰 이후)

> 시니어 코드 리뷰로 식별한 5개 Critical 허점에 대한 공식 결정.
> 일반 ADR(Architecture Decision Record) 형식. 번복 시 새 ID로 추가, 기존은 "Superseded by CR-NNN" 표기.

---

## CR-001 — Windows 개발/빌드 환경 전략

**상태**: Accepted (2026-04-23)

**맥락**
개발은 macOS, 배포 타겟은 Windows `.exe`. Python+PySide6+nodriver+PyInstaller의 Windows 전용 이슈(DPI 스케일, Credential Manager, 클립보드 훅, Defender 오탐)가 Phase 3 배포 직전에 드러나면 릴리스 일정 치명타.

**결정**
1. **Phase 0 내**: GitHub Actions `windows-latest` runner로 lint + mypy + pytest 자동화 (CI에 포함).
2. **Phase 1 시작 전**: Windows 11 실환경 확보 (UTM/Parallels VM 또는 중고 Windows 노트북).
3. **Windows 전용 코드 격리**: `src/autoblog/utils/windows.py` 에만 Windows-specific 의존성 코드 배치. 나머지 모듈은 POSIX와 호환되게 작성.
4. **PyInstaller 빌드**: GitHub Actions Windows runner에서 수행. macOS에서는 빌드 자체를 시도하지 않음.

**결과**
- CI에서 모든 PR이 Linux + Windows 양쪽에서 테스트됨 → Windows 회귀 조기 감지.
- Windows 실환경 확보는 Phase 0 지출로 계획(대략 30~60만원 또는 VM 라이선스 20만원).

**대안과 기각 이유**
- *개발기도 Windows로 변경*: 개발자가 macOS 숙련, 생산성 손실 큼.
- *macOS에서 PyInstaller 크로스 컴파일*: 공식 지원 안 함, 불가능.

---

## CR-002 — async ↔ Qt 이벤트 루프 브릿지 = `qasync`

**상태**: Accepted (2026-04-23)

**맥락**
우리 스택의 IO 계층(httpx, nodriver, google-genai SDK)은 전부 asyncio 기반. UI 계층은 PySide6(Qt) 기반으로 자체 이벤트 루프. 그대로 섞으면 UI 프리즈, `RuntimeError: no running event loop`, 또는 race condition.

**결정**
[`qasync`](https://github.com/CabbageDevelopment/qasync) 라이브러리를 채택하여 Qt 이벤트 루프를 asyncio 이벤트 루프로 교체.

```python
# src/autoblog/app.py (skeleton)
import asyncio
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

def main():
    app = QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_forever()
```

UI 이벤트 핸들러 내에서 `asyncio.create_task(some_async_fn())` 직접 호출 가능.

**결과**
- 비동기 발행 로직과 Qt UI가 단일 이벤트 루프에서 협력적으로 동작.
- 단 qasync는 소규모 커뮤니티 프로젝트이므로 버전 고정 필수 (`qasync>=0.27,<0.30`).

**대안과 기각 이유**
- *`QThread` + `run_coroutine_threadsafe`*: 모든 async 호출마다 스레드 간 통신 필요, 복잡도 폭발.
- *`PySide6.QtAsyncio` 공식 모듈*: PySide 6.5+ 제공이나 2026-04 기준 실사용 사례 적음, 세밀한 제어 부족.
- *PySide6 포기 + Tauri/Electron*: 스택 재결정 비용 큼.

---

## CR-003 — 비공식 API 변경 감지 & 대응 시스템

**상태**: Accepted (2026-04-23)

**맥락**
네이버 비공식 API(`upconvert.editor.naver.com`, `RabbitWrite.naver` 등) 응답 스키마가 바뀌면 앱 전체가 침묵 실패. 기존 계획의 "selector 핫업데이트"는 DOM 전용이고 API 레벨 변경을 놓침.

**결정**
3-layer 감지 체계:

1. **엄격한 스키마 검증 (첫 번째 방어선)**
   - 모든 네이버 API 응답을 pydantic 모델로 파싱, `model_config = ConfigDict(extra="forbid")`.
   - 스키마 불일치 시 `ValidationError` 즉시 발생 → 로깅 + 텔레메트리.
   - 파일 위치: `src/autoblog/automation/api_models.py`

2. **응답 fingerprint 저장 (두 번째)**
   - 각 엔드포인트별로 응답 구조 해시(필드명 정렬 후 SHA-256) 저장. 
   - 앱 시작 시점에 한 번 fingerprint 확인, 변경 감지 시 `selectors_cache` 테이블에 기록.

3. **원격 "엔드포인트 구성" 핫업데이트 (세 번째)**
   - `https://cdn.autoblog.kr/endpoints/v1.json` 로 엔드포인트 URL/헤더/파라미터 오버라이드 가능.
   - ed25519 서명 필수.
   - 본체 앱 업데이트 없이 긴급 패치 가능 (24h SLA).

**사용자 경험**
- 스키마 깨짐 감지 시 → 자동으로 발행 일시중지 + GUI 배너 "점검 중, 업데이트 기다려주세요".
- 핫패치 적용 시 → 앱 재시작 없이 다음 발행부터 새 구성 적용.

**결과**
- 네이버 변경에 대해 본체 빌드/사이닝/배포(며칠) 없이 1시간 이내 대응 가능.
- 사용자가 "왜 발행 안 되지?" 혼란 겪기 전에 자동 차단.

**대안과 기각 이유**
- *try/except 느슨하게 삼키기*: 무음 실패 → 사용자 불만 폭주.
- *본체 업데이트만으로 대응*: Microsoft Store/인스톨러 배포에 수일 걸림, SLA 위반.

---

## CR-004 — EXIF 조작 정책 (법적 안전)

**상태**: Accepted (2026-04-23, 이전 계획 번복)

**맥락**
이전 계획은 AI 이미지에 "핸드폰 카메라처럼 EXIF 주입 — 카메라 기종, 촬영 시각, GPS 좌표 랜덤"이었음. 체험단 후기에서 GPS 위조는:
- 표시광고법(공정거래위원회) 위반 소지
- 식품위생법(음식점 리뷰)·소비자기본법 위반 가능
- 2025~2026년 네이버가 "AI 생성 + 위치 위조" 집중 단속 중 (비즈한국 호텔 가짜 사례)

**결정**
1. **GPS 좌표 조작 절대 금지**. 코드에서 `GPS*` EXIF 태그 쓰기 기능 제거.
2. **카메라 Make/Model 주입은 옵션** (UI 토글, 기본 OFF, "실험적 기능" 라벨).
3. **촬영 시각(DateTimeOriginal)은 현재 시각 기반**만 허용 (과거 날짜 위조 금지).
4. **체험단 특화 모드**에서는 AI 이미지보다 **사용자가 찍은 실제 사진 업로드를 우선** 안내.
5. **약관 명시**: "이미지 메타데이터 수정은 사용자 책임. 허위 표시로 법적 분쟁 발생 시 회사는 책임지지 않음." 온보딩에서 별도 체크박스 동의.

**결과**
- 사진 자연스러움이 다소 줄어듦 (AI 이미지 특유 EXIF 결여).
- 대신 "사용자 실제 사진 우선" UX가 체험단 타겟과 더 맞음.
- 법적 리스크 대폭 감소.

**대안과 기각 이유**
- *EXIF 조작 옵션 유지 + 사용자 동의만*: 사용자 동의가 법적 책임을 완전히 면책하지 않음.
- *EXIF 전혀 건드리지 않음*: AI 이미지 탐지 더 쉬움, 타협안으로 카메라 기종만 허용.

---

## CR-005 — BYOK(사용자 Gemini API 키) 보안 장치

**상태**: Accepted (2026-04-23)

**맥락**
Google 공식문서 명시: "Production client-side API 키 사용 권장 안 함". 우리는 데스크톱 앱에 사용자 키를 저장하는 구조 → 기술적으로 client-side. 키 유출 시 사용자가 Google에 부과된 과금 전액 부담.

**결정**
5중 방어:

1. **모델 화이트리스트 하드코딩**
   - 앱이 호출할 수 있는 모델 ID를 코드에 고정: `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3.1-flash-image-preview`.
   - 다른 모델 호출 시도 시 앱이 거부.
   - 키 탈취 공격자도 이 제한은 못 벗어남(앱 코드 수정해야 함).

2. **Google Cloud spending cap 설정 강제**
   - 온보딩 단계에 "월 10만원 한도 설정" 가이드 + 설정 완료 체크박스 필수.
   - 스크린샷 단계별 가이드 제공.
   - 체크 안 하면 다음 단계로 진행 불가.

3. **첫 키 입력 시 소액 테스트 호출**
   - `gemini-2.5-flash-lite`로 "안녕" 1회 호출 (~$0.00001)
   - 성공 시 유효한 키로 판정, 저장.
   - 실패 시 구체 에러 메시지 + 해결 가이드.

4. **로컬 호출 로그**
   - 모든 Gemini API 호출의 (시각, 모델, 토큰 사용량, 성공 여부)를 SQLite `api_call_log` 테이블에 저장.
   - GUI에서 "이번 달 사용량" 표시 → 사용자가 Google Cloud 대시보드와 대조 가능.
   - 이 로그는 30일 후 자동 삭제.

5. **OS 자격증명 저장소 사용**
   - `keyring` 라이브러리로 Windows Credential Manager / macOS Keychain에 저장.
   - 절대 평문 파일이나 환경변수에 저장하지 않음.
   - 마스터키나 추가 암호 없음 (OS 보안에 위임).

**약관 조항 (온보딩 동의)**
> "본 앱은 귀하의 Google Gemini API 키를 귀하의 PC에 OS 보안 저장소로 보관합니다. 키 탈취·오용·과금에 대한 최종 책임은 귀하에게 있으며, 반드시 Google Cloud Console에서 spending cap을 설정하시기 바랍니다. 본 앱은 화이트리스트에 등록된 Gemini 모델(본 문서에 명시)만 호출합니다."

**결과**
- 사용자가 Google에 과도한 청구 받을 위험을 실질적으로 차단.
- "앱이 뭘 호출하는지" 투명성 확보 → 신뢰 구축.
- 약관으로 법적 방어선 구축.

**대안과 기각 이유**
- *우리 서버에 프록시 두고 사용자 키 받기*: 법적 리스크 오히려 증가(우리가 키 관리 주체가 됨), 서버 비용, 사용자 지연.
- *마스터 암호로 추가 암호화*: UX 악화, OS 보안 저장소로 충분.

---

## 참고
- Day 2 코드 리뷰 전체 허점 목록 → [known_issues.md](./known_issues.md)
- 최신 계획서 → `~/.claude/plans/tidy-tickling-fountain.md`
