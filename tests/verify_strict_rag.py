"""Verify strict RAG behaviour and Risk Analysis Report test cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag_engine import RAGEngine  # noqa: E402


def main() -> int:
    engine = RAGEngine()
    print("Initialising engine...")
    engine.initialise()

    sources = sorted({Path(c.source).name for c in engine.chunks})
    print(f"ready={engine.ready} chunks={len(engine.chunks)}")
    print(f"sources={sources}")

    tests = [
        ("A", "What is the purpose of the Risk Analysis Report?", [
            "identifies", "evaluates", "prioritises", "confidentiality", "integrity", "availability",
        ]),
        ("B", "Who is the owner of the report?", ["Chief Risk Officer", "CRO"]),
        ("C", "What are the risks R-01 to R-05?", ["R-01", "R-02", "R-03", "R-04", "R-05"]),
        ("D", "What is the treatment strategy for R-02?", ["Patch VPN", "MFA", "24 hours"]),
        ("E", "What is the deadline for R-05?", ["31 Dec 2025", "2025"]),
        ("F", "איזה סיכון קשור ל-VPN?", ["R-02", "VPN"]),
        ("France", "What is the capital of France?", []),
    ]

    results: dict = {}
    fails = 0

    for label, question, keywords in tests:
        result = engine.answer(question)
        answer = result["answer"]
        refused = result["refused"]

        if label == "France":
            ok = (
                refused
                and "Paris" not in answer
                and "do not have enough information" in answer.lower()
            )
        else:
            ok = (not refused) and any(k.lower() in answer.lower() for k in keywords)

        if not ok:
            fails += 1

        results[label] = {
            "pass": ok,
            "refused": refused,
            "answer_preview": answer[:250],
        }
        print(f"{label}: {'PASS' if ok else 'FAIL'} (refused={refused})")
        print(f"  {answer[:200].replace(chr(10), ' ')}")

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
