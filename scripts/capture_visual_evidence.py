#!/usr/bin/env python3
"""Capture homepage and chat visual evidence at 100% zoom."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "evidence" / "visual_repair"
URL = "http://3.239.47.249/"
VIEWPORTS = [
    ("1366x768", 1366, 768),
    ("1440x900", 1440, 900),
    ("1920x1080", 1920, 1080),
]
SQUAD_PROMPT = "squad weaknesses"


def _capture_homepages(browser) -> list[str]:
    paths: list[str] = []
    for label, width, height in VIEWPORTS:
        page = browser.new_page(viewport={"width": width, "height": height, "device_scale_factor": 1})
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        target = OUT / f"homepage_{label}.png"
        page.screenshot(path=str(target), full_page=False)
        paths.append(str(target))
        page.close()
    return paths


def _capture_chat_flow(browser) -> list[str]:
    paths: list[str] = []
    page = browser.new_page(viewport={"width": 1440, "height": 900, "device_scale_factor": 1})
    page.goto(URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(1500)

    suggestion = page.locator(".suggestion", has_text=SQUAD_PROMPT).first
    if suggestion.count() == 0:
        suggestion = page.locator(".suggestion").first
    suggestion.click()

    page.wait_for_selector(".message--assistant .message__content--markdown h3, .message--assistant .message__content--markdown table, .message--assistant .message__content--markdown p", timeout=240000)
    page.wait_for_timeout(3000)
    content_text = page.locator(".message--assistant .message__content--markdown").last.inner_text(timeout=5000)
    if "###" in content_text:
        raise RuntimeError("literal markdown heading markers still visible in chat response")

    assistant = page.locator(".message--assistant").last
    assistant.scroll_into_view_if_needed()
    top = OUT / "chat_squad_weakness_top.png"
    assistant.screenshot(path=str(top))
    paths.append(str(top))

    content = assistant.locator(".message__content--markdown")
    if content.count():
        content.evaluate("el => el.scrollTop = 0")
        page.wait_for_timeout(300)
        paths.append(str(OUT / "chat_squad_weakness_content_start.png"))
        page.screenshot(path=str(OUT / "chat_squad_weakness_content_start.png"), full_page=False)

        content.evaluate("el => el.scrollTop = Math.floor(el.scrollHeight / 2)")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "chat_squad_weakness_middle.png"), full_page=False)
        paths.append(str(OUT / "chat_squad_weakness_middle.png"))

    evidence = page.locator(".context-wrap details, .context-wrap summary").first
    if evidence.count():
        evidence.click()
        page.wait_for_timeout(500)
        expanded = OUT / "chat_evidence_expanded.png"
        page.screenshot(path=str(expanded), full_page=False)
        paths.append(str(expanded))

    table = page.locator(".message__content--markdown table").first
    if table.count():
        table_shot = OUT / "chat_table.png"
        table.screenshot(path=str(table_shot))
        paths.append(str(table_shot))

    page.close()
    return paths


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("PLAYWRIGHT_UNAVAILABLE")
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    all_paths: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        all_paths.extend(_capture_homepages(browser))
        try:
            all_paths.extend(_capture_chat_flow(browser))
        except Exception as exc:
            print(f"CHAT_CAPTURE_WARN={exc}")
        browser.close()

    for path in all_paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
