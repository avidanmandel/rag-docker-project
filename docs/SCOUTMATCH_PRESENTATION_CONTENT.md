# ScoutMatch Presentation Content (six slides)

Use this outline to build the course deck. **No final PPTX is committed** in this repository as of 2026-06-04.

## 1. About Me

- Student: Avidan (user5 course environment)
- Project: ScoutMatch AI — football recruitment assistant
- Focus: grounded RAG + optional dynamic sporting-director workflow

## 2. Project Overview

- **Problem:** Small clubs need evidence-based recruitment without hallucinated player facts.
- **Users:** Sporting director / coach / scout.
- **Solution:** Upload CVs and club documents → Bedrock Knowledge Base → Flask chat with strict source validation.
- **Extension:** Recruitment Advisor uses Bedrock Agent with **four** operational Tools for squad planning, management notification, and lineup boards.

## 3. Technologies Used

- Python, Flask, boto3
- Amazon S3, Bedrock Knowledge Base, Bedrock Agent, Lambda
- DynamoDB (operational state), SNS (management alerts), Step Functions (optional workflow)
- Docker on Amazon EC2
- SQLite (v14 sessions/uploads only)

## 4. System Architecture

**Production v14**

```
Browser → EC2 Docker → Flask → boto3 retrieve(KB) → grounded answer + source cards
```

**Recruitment Advisor (local / extension)**

```
Browser → Flask → bedrock-agent-runtime invoke_agent
  → Agent + Knowledge Base (RAG)
  → 4 user-facing Tools → Lambda → DynamoDB / S3 / SNS
```

Static policy and reports: **Knowledge Base**. Live budget, selections, lineups: **DynamoDB**.

## 5. Live Demo

- Public grounded budget question with sources
- Barcelona 4-3-3 context, Ron Ben Ari selection, confirmation, reservation
- Inline SVG lineup board with pending-management badge
- Unsupported question refusal

See `docs/SCOUTMATCH_FINAL_DEMO_SCRIPT.md`.

## 6. Challenges and Next Steps

- **Challenges:** Bedrock 10-API quota → simplified four-tool design; separating static KB from dynamic state; confirmation/idempotency for budget reservations.
- **Next steps:** Approved `--apply` for simplified Agent attach; capture dynamic screenshots; optional Advisor history persistence; cleanup after explicit approval (`docs/SCOUTMATCH_AWS_CLEANUP_PLAN.md`).

## PPTX status

| Item | Status |
|------|--------|
| Final `.pptx` in repository | **Not found** |
| Slide content ready | **Yes** (this file) |
| Reflects current architecture | **Yes** (four-tool simplified design) |
