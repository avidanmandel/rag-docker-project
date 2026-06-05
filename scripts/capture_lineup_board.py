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


def _wait_for_response_complete(page, before: int, timeout_ms: int = 300000) -> None:
    page.wait_for_function(
        f"document.querySelectorAll('.message--assistant').length > {before}",
        timeout=timeout_ms,
    )
    try:
        page.wait_for_function(
            "document.getElementById('typingIndicator') === null",
            timeout=timeout_ms,
        )
    except Exception:
        pass
    page.wait_for_timeout(3000)


def _last_assistant_text(page) -> str:
    return page.locator(".message--assistant").last.inner_text()


def _send_message(page, text: str) -> None:
    before = _assistant_count(page)
    page.locator("#chatInput").fill(text)
    page.locator("#sendBtn").click()
    _wait_for_response_complete(page, before)


def _maybe_answer_planning_clarification(page) -> None:
    text = _last_assistant_text(page).lower()
    if any(token in text for token in ("opponent", "squad context", "formation", "playing style")):
        _send_message(
            page,
            "Opponent is Barcelona. Squad context is the opening season demo with weak right-back depth. "
            "Preferred formation is 4-3-3.",
        )


def _send_step(page, step: str) -> None:
    if step == "__confirm__":
        before = _assistant_count(page)
        confirm = page.locator(".confirm-card__btn--confirm").last
        try:
            confirm.wait_for(state="visible", timeout=60000)
            confirm.click()
        except Exception:
            page.locator("#chatInput").fill("Confirm")
            page.locator("#sendBtn").click()
        _wait_for_response_complete(page, before)
    else:
        _send_message(page, step)


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
            "Show me the current proposed lineup.",
            (
                "Plan match tactics for opening season with budget 100000 EUR. "
                "Opponent is Barcelona. Squad context is opening season demo with weak right-back depth. "
                "Preferred formation is 4-3-3."
            ),
            "__clarify__",
            "I choose Ron Ben Ari because he is the more aggressive right-back option. Submit the player recommendation to management.",
            "__confirm__",
            "Save the proposed demo 4-3-3 lineup with Ron Ben Ari at right-back for head-coach review.",
            "__confirm__",
            "Show me the current proposed lineup.",
        ]
        confirm_steps = 0
        for step in steps:
            if step == "__clarify__":
                _maybe_answer_planning_clarification(page)
                continue
            _send_step(page, step)
            if step == "__confirm__":
                confirm_steps += 1
                if confirm_steps == 1:
                    last_text = _last_assistant_text(page)
                    budget_hint = (
                        page.locator(".agent-budget").last.inner_text()
                        if page.locator(".agent-budget").count()
                        else ""
                    )
                    has_budget = "57,000" in budget_hint or "57000" in budget_hint.replace(",", "")
                    has_reserve = "43,000" in last_text or "43000" in last_text.replace(",", "")
                    if not has_budget and not has_reserve:
                        page.screenshot(path=str(debug_path), full_page=True)
                        raise RuntimeError(
                            f"Ron confirmation did not reserve budget; budget={budget_hint!r}"
                        )

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
