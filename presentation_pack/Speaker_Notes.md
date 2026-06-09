# ScoutMatch AI — Speaker Notes

Total main deck time: **5–7 minutes** (appendix for Q&A only).

## Slide 1 — About Me (~45s)
- Avidan Mendelman, The Open University of Israel, B.Sc. Computer Science.
- Passionate about software development and useful AI applications.

## Slide 2 — Project Overview (~60s)
- Club finished fourth; strengthen before transfer window closes.
- Scout/recruitment analyst using club documents, squad data, candidate reports.
- Weaknesses, transfer-out, missions, recommendations, budget on Confirm, visual lineup.
- Live demo: http://3.239.47.249/

## Slide 3 — Technologies Used (~50s)
- Python, Flask, HTML/CSS/JS; Docker on EC2; Git/GitHub.
- Bedrock Agent, Knowledge Base, RAG, Guardrail, boto3, IAM Role; S3, Lambda, DynamoDB.
- Exactly 4 Tools, 4 Action Groups, 4 Lambdas — not a standalone MCP server.

## Slide 4 — System Architecture (~60s)
- Browser to EC2 to Docker to Flask to boto3/IAM to Bedrock Agent to KB/RAG to Action Group to Lambda to DynamoDB or private S3 to Flask Proxy to Browser.
- Guardrail; Confirm/Deny preserves human approval.

## Slide 5 — Live Demo (~90s)
- Squad question, grounded answer, Ron recommendation, Confirm, budget, lineup board.

## Slide 6 — Challenges and Next Steps (~60s)
- What works, technical challenges, next steps.
- 481 tests passed, 0 failed, public browser reliability 3/3.

## Appendix (Q&A only)
- Use A1–A5 only when asked.
