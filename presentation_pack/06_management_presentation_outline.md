# Six-Slide Management Presentation Outline

Build PPTX manually after screenshots are captured.

## Slide 1 — About Me

- Student: Avidan (user5 course environment)
- Focus: grounded football recruitment + dynamic sporting-director workflow

## Slide 2 — Project Overview

- Problem: evidence-based recruitment without invented player facts
- User: Sporting Director / coach / scout
- Solution: Bedrock Knowledge Base RAG + Bedrock Agent operational tools

## Slide 3 — Technologies Used

- Python, Flask, boto3, Docker, EC2
- Bedrock Agent, Knowledge Base, Guardrail, Lambda
- DynamoDB, SNS, private S3 SVG

## Slide 4 — System Architecture

- v14 grounded chat path
- Four-Lambda Advisor path (one Agent, one Guardrail, one KB, four tools)
- Static KB vs dynamic DynamoDB state
- Insert: `02_final_architecture.md` diagram or screenshot placeholders

## Slide 5 — Live Demo

- Budget question with sources
- Barcelona tactical planning → Ron Ben Ari selection → lineup board
- Insert screenshots from `05_screenshot_placeholders.md` where available

## Slide 6 — Challenges and Next Steps

- Challenges: Action Group quota, IAM table limits, confirmation/idempotency, separating KB from DynamoDB
- Completed: four dedicated Lambdas applied and live-validated
- Remaining: EC2 Advisor cutover, SNS email subscription, screenshot package, submission ZIP
- Cleanup deferred until explicit approval
