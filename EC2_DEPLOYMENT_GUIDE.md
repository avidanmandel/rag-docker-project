# EC2 Deployment Guide — ScoutMatch AI

Deploy ScoutMatch AI globally so managers can access it from a phone or laptop via the EC2 public IP.

---

## Target architecture

```
Browser
  → http://EC2_PUBLIC_IP
  → Docker (host port 80 → container 5000)
  → Flask (0.0.0.0:5000)
  → boto3
  → Amazon S3 (scoutmatch/knowledge-base/)
  → Amazon S3 (scoutmatch/knowledge-base/)
  → Bedrock Knowledge Base retrieve()
  → ScoutMatch S3 source validation
  → Bedrock generation model
```

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| EC2 | Ubuntu, public IPv4, Docker installed |
| IAM role | S3 read/write, Bedrock KB, bedrock-agent permissions |
| Knowledge Base | Status ACTIVE, data source → `scoutmatch/knowledge-base/` |
| Security Group | Inbound TCP **80** (HTTP) |
| Secrets | Never commit `.env` or bake keys into image |

---

## Step 1 — Prepare AWS (manual, one-time)

1. Create or reuse an S3 bucket
2. Ensure Bedrock Knowledge Base exists
3. Create or update a **data source** pointing to:
   ```
   s3://YOUR_BUCKET/scoutmatch/knowledge-base/
   ```
4. Note `BEDROCK_KB_ID` and `BEDROCK_DATA_SOURCE_ID`
5. Attach IAM role to EC2 with permissions for S3, `bedrock:Retrieve`, `bedrock:RetrieveAndGenerate`, `bedrock-agent:StartIngestionJob`, `bedrock-agent:GetIngestionJob`

Do **not** delete existing course documents in S3 unless you choose to manually.

---

## Step 2 — Copy project to EC2

```bash
scp -i /path/to/key.pem -r Avidan_RAG_Docker_Project ec2-user@EC2_PUBLIC_IP:~/scoutmatch-ai
```

Or clone from your repository.

---

## Step 3 — Create `.env` on EC2

```bash
cd ~/scoutmatch-ai
cp .env.ec2.example .env
nano .env
chmod 600 .env
```

Set:
```
RAG_BACKEND=aws_kb
AWS_REGION=us-east-1
BEDROCK_KB_ID=your-kb-id
BEDROCK_DATA_SOURCE_ID=your-ds-id
BEDROCK_MODEL_ARN=arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0
AWS_S3_BUCKET=your-bucket
AWS_S3_PREFIX=scoutmatch/knowledge-base/
```

Credentials come from the **EC2 instance IAM role**, not from the image.

---

## Step 4 — Build and run Docker

```bash
docker build -t scoutmatch-ai .

docker run -d \
  --name scoutmatch \
  --restart unless-stopped \
  -p 80:5000 \
  --env-file .env \
  scoutmatch-ai
```

Flask listens on `0.0.0.0:5000` inside the container.

---

## Step 5 — Security Group

Add inbound rule:

| Type | Port | Source |
|------|------|--------|
| HTTP | 80 | Your IP or 0.0.0.0/0 (lab demo) |

---

## Step 6 — Verify

On EC2:

```bash
curl -s http://127.0.0.1/api/health
curl -s http://127.0.0.1/api/status | python3 -m json.tool
```

Expected status fields:
- `"rag_backend": "aws_kb"`
- `"engine_class": "AWSKnowledgeBaseEngine"`
- `"aws_mode": true`
- `"expected_s3_uri_prefix": "s3://YOUR_BUCKET/scoutmatch/knowledge-base/"`

From phone browser:

```
http://EC2_PUBLIC_IP
```

---

## Step 7 — Upload demo documents

Use the ScoutMatch UI **Upload CV** button or AWS Console to upload files from `sample_scout_data/`.

Wait for ingestion status **COMPLETE** before asking recruitment questions.

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| `config_missing` in `/api/status` | All required env vars in `.env` |
| Upload succeeds, sync fails | Data source ID and S3 prefix alignment |
| Empty answers | KB not synced; run ingestion in AWS Console |
| 403 on upload | IAM role S3 PutObject permission |

---

## Never commit

- `.env`
- AWS access keys
- PEM key files
- Real KB IDs in committed example files
