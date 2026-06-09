#!/usr/bin/env python3
"""Quick homepage no-scroll + hero shield checks."""

from __future__ import annotations

import json
import sys
import urllib.request
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
            metrics = page.evaluate(
                """() => {
                    const messages = document.getElementById('messages');
                    const heroLeft = document.querySelector('.hero-left');
                    const cards = [...document.querySelectorAll('.home-hero .suggestion')];
                    const visibleCards = cards.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.top >= 0 && r.bottom <= window.innerHeight;
                    }).length;
                    const heroImg = document.querySelector('.dashboard-stage__panel-img');
                    return {
                        messages_scrollable: messages.scrollHeight > messages.clientHeight + 2,
                        hero_left_scrollable: heroLeft ? heroLeft.scrollHeight > heroLeft.clientHeight + 2 : false,
                        page_scrollable: document.documentElement.scrollHeight > window.innerHeight + 2,
                        quick_start_cards_total: cards.length,
                        quick_start_cards_visible: visibleCards,
                        hero_src: heroImg ? heroImg.getAttribute('src') || '' : '',
                        title_ok: (document.querySelector('.brand__title')?.textContent || '').trim() === 'ScoutMatch AI',
                        no_brand_icon: document.querySelectorAll('.brand__mark').length === 0,
                    };
                }"""
            )
            shot = OUT / f"ui_polish_homepage_no_scroll_{label}.png"
            page.screenshot(path=str(shot), full_page=False)
            report["checks"][label] = {
                **metrics,
                "hero_uses_clean_art": "home-dashboard-art-clean.png" in metrics.pop("hero_src", ""),
            }
            report["screenshots"].append(str(shot))
            page.close()

        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(BASE, wait_until="networkidle", timeout=120000)
        page.locator(".home-hero .suggestion").first.click()
        page.wait_for_selector(".message--assistant", timeout=120000)
        page.evaluate("""() => {
            const m = document.getElementById('messages');
            for (let i = 0; i < 40; i++) m.insertAdjacentHTML('beforeend', '<div class="message message--assistant"><div class="message__avatar">S</div><div class="message__content">Padding line ' + i + '</div></div>');
        }""")
        chat_scroll = page.evaluate(
            "() => { const m = document.getElementById('messages'); return m.scrollHeight > m.clientHeight + 2; }"
        )
        page.locator("#backToWorkspaceBtn").click()
        page.wait_for_selector(".home-hero", timeout=30000)
        back_ok = page.locator("#backToWorkspaceBtn").is_hidden() and page.locator(".home-hero").is_visible()
        report["checks"]["chat_flow"] = {
            "chat_messages_scrollable": chat_scroll,
            "back_to_workspace_ok": back_ok,
        }
        browser.close()

    report["checks"]["homepage_http"] = urllib.request.urlopen(BASE, timeout=30).status
    ok_viewports = all(
        not report["checks"][k]["messages_scrollable"]
        and not report["checks"][k]["hero_left_scrollable"]
        and not report["checks"][k]["page_scrollable"]
        and report["checks"][k]["quick_start_cards_visible"] == report["checks"][k]["quick_start_cards_total"] == 6
        for k in ("1366x768", "1440x900")
    )
    report["status"] = "OK" if ok_viewports and report["checks"]["homepage_http"] == 200 else "PARTIAL"
    (OUT / "ui_polish_homepage_no_scroll_check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())