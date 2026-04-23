"""PoC 5 — qasync로 PySide6(Qt) + asyncio 통합 검증 (CR-002).

목적:
  - Qt 이벤트 루프를 asyncio 이벤트 루프로 교체 가능?
  - 버튼 클릭 → 비동기 httpx 호출 → UI 업데이트가 프리즈 없이 되는가?
  - Phase 1에서 쓸 패턴이 성립하는지 확인.

모드:
  - 기본 (GUI 모드):  Qt 창을 띄워서 사용자가 직접 버튼을 눌러 확인
  - 자동 모드:       POC5_AUTO_EXIT=1 환경변수 설정 시 창 없이 asyncio+Qt 통합만 자동 검증
                    (CI/headless에서 사용)

실행:
  uv sync --extra gui

  # GUI 모드
  uv run python scripts/poc_qasync.py

  # 자동 검증 모드
  POC5_AUTO_EXIT=1 uv run python scripts/poc_qasync.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# 실제 임포트는 런타임에 (gui extra 미설치 시 친절한 에러)
try:
    import httpx
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from qasync import QEventLoop, asyncSlot
except ImportError as e:
    missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
    print(f"✗ 필수 패키지 미설치: {missing}")
    print("  실행:  uv sync --extra gui")
    sys.exit(1)


AUTO_EXIT = os.environ.get("POC5_AUTO_EXIT") == "1"


class QasyncDemoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PoC 5 — qasync 통합 검증")
        self.setMinimumSize(480, 240)

        layout = QVBoxLayout(self)

        self.label = QLabel("버튼을 누르면 비동기 HTTP 호출을 시도합니다.")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.button = QPushButton("🌐 httpbin.org/delay/3 호출")
        self.button.clicked.connect(self.on_click)
        layout.addWidget(self.button)

        self.close_button = QPushButton("종료")
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)

    @asyncSlot()
    async def on_click(self) -> None:
        self.button.setEnabled(False)
        self.label.setText("⏳ 호출 중... (이 동안 UI가 프리즈되지 않아야 합니다)")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get("https://httpbin.org/delay/3")
                response.raise_for_status()
                data = response.json()
                self.label.setText(
                    f"✓ 응답 수신\nURL: {data.get('url')}\norigin: {data.get('origin')}"
                )
        except Exception as e:
            self.label.setText(f"✗ 호출 실패: {e}")
        finally:
            self.button.setEnabled(True)


async def _auto_verify(app: QApplication) -> int:
    """창 없이 qasync + asyncio + httpx 통합 검증."""
    print("\n[자동 검증 모드]")
    print("  ▶ asyncio 이벤트 루프 확인...")
    loop = asyncio.get_running_loop()
    print(f"    loop 타입: {type(loop).__name__}")

    print("  ▶ asyncio.sleep(0.3) 동안 Qt 이벤트도 살아있는지 확인...")
    timer_fired = [False]
    from PySide6.QtCore import QTimer

    def _on_timer() -> None:
        timer_fired[0] = True

    QTimer.singleShot(100, _on_timer)
    await asyncio.sleep(0.3)

    if not timer_fired[0]:
        print("  ✗ Qt 타이머 미발화. qasync 통합 실패.")
        return 1
    print("  ✓ Qt 타이머 + asyncio.sleep 동시 동작 확인")

    print("  ▶ httpx 비동기 호출 (httpbin.org/uuid)...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://httpbin.org/uuid")
            response.raise_for_status()
            data = response.json()
            print(f"  ✓ 응답 수신. uuid = {data.get('uuid', '?')}")
    except Exception as e:
        print(f"  ✗ httpx 호출 실패: {e}")
        return 1

    print("\n✓ qasync + asyncio + httpx 통합 검증 완료. Phase 1 GUI 패턴 확정 가능.")
    app.quit()
    return 0


def main() -> int:
    print("=" * 60)
    print("PoC 5 — qasync (PySide6 + asyncio) 통합 검증")
    print("=" * 60)

    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    exit_code = 0

    if AUTO_EXIT:
        # 창 없이 자동 검증 (CI용)
        task = asyncio.ensure_future(_auto_verify(app))

        with loop:
            loop.run_forever()

        exit_code = task.result() if task.done() else 1
    else:
        # GUI 모드 — 사용자가 직접 버튼 클릭
        print()
        print("창이 뜨면 'httpbin.org/delay/3 호출' 버튼을 눌러보세요.")
        print("UI가 얼지 않고 3초 후 응답이 표시되면 성공입니다.")
        print("확인 후 '종료' 버튼으로 창을 닫으세요.")
        print()

        window = QasyncDemoWindow()
        window.show()

        with loop:
            loop.run_forever()

        print("\n✓ qasync 이벤트 루프 정상 종료. Phase 1 GUI 아키텍처 확정 가능.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
