# ScoutMatch AI — Demo Questions

Expected behaviour for live recruitment demos. Upload documents from `sample_scout_data/` to S3 and sync the Knowledge Base before running positive tests.

---

## 1. Positive grounded question (Hebrew)

**Question:**
```
אני מחפש שוער עם לפחות 5 שנות ניסיון, רגוע תחת לחץ, טוב במשחק רגל, מוכן לעבור לצפון ושכרו עד 80,000 אירו לעונה. מי המועמד המתאים ביותר ולמה?
```

**Expected:**
- Recommend **Daniel Cohen** based on uploaded documents
- Mention salary (~75,000 EUR), relocation willingness, build-up / back-pass ability
- Show sources: `goalkeeper_daniel_cohen.txt`, team requirements, scouting report
- Label as AI-assisted assessment

---

## 2. Comparison question (Hebrew)

**Question:**
```
למה עומר אזולאי פחות מתאים למרות שיש לו יותר שנות ניסיון?
```

**Expected:**
- Explain using Omer Azulay CV/report only (inconsistent passing under pressure, higher salary)
- Do not invent facts not in documents

---

## 3. Follow-up question

**First:** (from question 1)

**Then:**
```
ומה השכר של המועמד שהמלצת עליו?
```

**Expected:**
- Understand prior context (Daniel Cohen)
- Answer salary from CV (~75,000 EUR per season)

---

## 4. Defender question (Hebrew)

**Question:**
```
אני מחפש בלם שמתאים לקו הגנה גבוה, קורא את המשחק טוב ורגוע עם הכדור. מי מתאים?
```

**Expected:**
- Retrieve defender documents
- Recommend **Amit Levy** (high line, reads game, composed on ball) with evidence

---

## 5. Refusal — general knowledge (Hebrew)

**Question:**
```
מי זה דונלד טראמפ?
```

**Expected:**
```
אין לי מספיק מידע במסמכי השחקנים ובמסמכי הקבוצה כדי לענות על השאלה הזאת.
```

---

## 6. Refusal — geography (English)

**Question:**
```
What is the capital of New Zealand?
```

**Expected:** Strict refusal (English version)

---

## 7. Missing data question

**Question:**
```
אני מחפש מגן שמאלי עם ניסיון בליגה היפנית. מי מתאים?
```

**Expected:**
- Refuse or state insufficient information
- Do not invent a Japanese-league player

---

## 8. Live upload demo

**Step A — Ask:**
```
מי השוער המתאים ביותר להנעת כדור מאחור?
```

**Expected:** Daniel Cohen (or similar grounded comparison among existing GKs)

**Step B — Upload:**
`sample_scout_data/demo_upload_later/goalkeeper_marco_silva.txt`

**Step C — Wait** for KB sync COMPLETE

**Step D — Ask again:**
```
מי השוער המתאים ביותר להנעת כדור מאחור?
```

**Expected:**
- Mention **Marco Silva** when relevant
- New source appears in citations
- Updated or expanded comparison

---

## English sample prompts (UI buttons)

| Prompt | Expected focus |
|--------|----------------|
| Find a goalkeeper for build-up play | Daniel Cohen (pre-upload) / Marco Silva (post-upload) |
| Compare the most suitable defenders | Amit Levy vs others with evidence |
| Which midfielder performs well under pressure? | Roy Cohen or grounded match |
| Show candidates willing to relocate | Players with relocation=yes in CVs |
