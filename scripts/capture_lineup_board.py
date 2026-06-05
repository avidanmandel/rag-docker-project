#!/usr/bin/env python3
"""Capture lineup-board screenshot after full demo flow on public URL."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "evidence" / "lineup_board_repair"
URL = "http://3.239.47.249/"


def _assistant_count(page) -> int:
    return page.locator(".message--assistant").count()


def _wait_for_new_assistant(page, before: int, timeout_ms: int = 300000) -> None:
    page.wait_for_function(
        f"document.querySelectorAll('.message--assistant').length > {before}",
        timeout=timeout_ms,
    )
    page.wait_for_timeout(2500)


def _send_step(page, step: str) -> None:
    before = _assistant_count(page)
    if step == "__confirm__":
        confirm = page.locator(".confirm-card__btn--confirm").last
        confirm.wait_for(timeout=120000)
        confirm.click()
    else:
        page.locator("#chatInput").fill(step)
        page.locator("#sendBtn").click()
    _wait_for_new_assistant(page, before)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("PLAYWRIGHT_UNAVAILABLE")
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "lineup_board_eleven_players.png"
    debug_path = OUT / "lineup_board_capture_debug.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900, "device_scale_factor": 1})
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1500)
        new_chat = page.locator("#newChatBtn, #newChatBtnLarge, .new-chat").first
        if new_chat.count():
            new_chat.click()
            page.wait_for_timeout(1500)

        steps = [
            "Plan match tactics for opening season with budget 100000 EUR.",
            "I choose Ron Ben Ari because he is the more aggressive right-back option. Submit the player recommendation to management.",
            "__confirm__",
            "Save the proposed demo 4-3-3 lineup with Ron Ben Ari at right-back for head-coach review.",
            "__confirm__",
            "Show me the current proposed lineup.",
        ]
        for step in steps:
            _send_step(page, step)

        board = page.locator(".lineup-board-card").last
        for attempt in range(3):
            try:
                board.wait_for(timeout=90000)
                break
            except Exception:
                if attempt >= 2:
                    page.screenshot(path=str(debug_path), full_page=True)
                    raise
                _send_step(page, "Show me the current proposed lineup.")

        board.scroll_into_view_if_needed()
        page.wait_for_timeout(1000)
        board.screenshot(path=str(path))

        svg_resp = page.request.get(f"{URL.rstrip('/')}/api/recruitment-advisor/lineups/current/image")
        svg_text = svg_resp.text() if svg_resp.ok else ""
        marker_count = svg_text.count('r="22"')
        print(f"svg_http={svg_resp.status}")
        print(f"svg_markers={marker_count}")
        if marker_count != 11:
            page.screenshot(path=str(debug_path), full_page=True)
            raise RuntimeError(f"expected 11 SVG player markers, got {marker_count}")

        budget = page.locator(".agent-budget").last.inner_text()
        print(f"budget_text={budget}")
        if "57,000" not in budget and "57000" not in budget.replace(",", ""):
            page.screenshot(path=str(debug_path), full_page=True)
            raise RuntimeError(f"expected remaining budget 57,000 EUR, got {budget!r}")

        content = page.locator(".message--assistant .message__content--markdown").last.inner_text()
        if "PENDING_HEAD_COACH_REVIEW" in content:
            raise RuntimeError("raw internal lineup status still visible")
        if "/api/recruitment-advisor/lineups" in content:
            raise RuntimeError("raw proxy route still visible")

        browser.close()

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
