#!/usr/bin/env python3
"""Quick homepage visual checks for hero restore + no-scroll landing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "evidence"
BASE = "http://3.239.47.249/"


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    report = {"base_url": BASE, "checks": {}, "screenshots": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width, height, label in ((1366, 768, "1366x768"), (1440, 900, "1440x900")):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(BASE, wait_until="networkidle", timeout=120000)
            page.wait_for_selector(".brand__title", timeout=60000)
            scroll_h = page.evaluate("() => document.getElementById('messages').scrollHeight")
            client_h = page.evaluate("() => document.getElementById('messages').clientHeight")
            page_scroll = page.evaluate("() => document.documentElement.scrollHeight > window.innerHeight")
            cards = page.locator(".home-hero .suggestion").count()
            visible_cards = page.locator(".home-hero .suggestion").evaluate_all(
                "els => els.filter(el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight; }).length"
            )
            hero_src = page.locator(".dashboard-stage__panel-img").get_attribute("src") or ""
            shot = OUT / f"ui_polish_homepage_final_{label.replace('x', 'x')}.png"
            page.screenshot(path=str(shot), full_page=False)
            report["checks"][label] = {
                "messages_scrollable": scroll_h > client_h + 2,
                "page_scrollable": page_scroll,
                "quick_start_cards_total": cards,
                "quick_start_cards_visible": visible_cards,
                "hero_uses_clean_art": "home-dashboard-art-clean.png" in hero_src,
                "no_brand_icon": page.locator(".brand__mark").count() == 0,
                "title_ok": page.locator(".brand__title").inner_text().strip() == "ScoutMatch AI",
            }
            report["screenshots"].append(str(shot))
            page.close()

        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(BASE, wait_until="networkidle", timeout=120000)
        page.locator(".home-hero .suggestion").first.click()
        page.wait_for_selector(".message--assistant", timeout=120000)
        chat_scroll = page.evaluate(
            "() => { const m = document.getElementById('messages'); return m.scrollHeight > m.clientHeight; }"
        )
        page.locator("#backToWorkspaceBtn").click()
        page.wait_for_selector(".home-hero", timeout=30000)
        back_ok = page.locator("#backToWorkspaceBtn").is_hidden() and page.locator(".home-hero").is_visible()
        report["checks"]["chat_flow"] = {
            "chat_messages_scrollable": chat_scroll,
            "back_to_workspace_ok": back_ok,
        }
        browser.close()

    import urllib.request

    http_home = urllib.request.urlopen(BASE, timeout=30).status
    report["checks"]["homepage_http"] = http_home
    report["status"] = "OK" if all(
        not v.get("messages_scrollable", False)
        and not v.get("page_scrollable", False)
        and v.get("quick_start_cards_visible", 0) == v.get("quick_start_cards_total", 0)
        for k, v in report["checks"].items()
        if k in ("1366x768", "1440x900")
    ) and report["checks"].get("homepage_http") == 200 else "PARTIAL"

    out_json = OUT / "ui_polish_homepage_final_check.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())