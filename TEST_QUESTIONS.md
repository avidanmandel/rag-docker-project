# Test Questions

These questions are used to validate the RAG pipeline. They cover the three
main topics in the knowledge base (Flask, Docker, AWS) plus one
**out-of-scope** question that should be refused.

Run them all at once with:

```powershell
python tests/test_rag.py
```

The runner prints the question, the model's answer, whether the assistant
refused, and the top retrieved chunks (file, page, similarity score).

---

## 1. What is Flask?

**Expected behaviour**
- Retrieves chunks from `Flask-lecture1.pdf`.
- Answers that Flask is a lightweight / micro Python web framework used to
  build web applications.
- `refused` is `false`.

## 2. How do I define a route in Flask?

**Expected behaviour**
- Retrieves chunks from `Flask-lecture1.pdf` or `Flask-lecture2.pdf`.
- Explains the `@app.route("/path")` decorator pattern bound to a view
  function returning a response.
- `refused` is `false`.

## 3. What is a Docker container, and how is it different from a virtual machine?

**Expected behaviour**
- Retrieves chunks from `docker_aws.pdf`.
- Explains that a container packages an application with its dependencies and
  shares the host OS kernel, while a VM runs a full guest OS on a hypervisor
  (so containers are lighter and start faster).
- `refused` is `false`.

## 4. How do I write a Dockerfile for a Flask application?

**Expected behaviour**
- Retrieves chunks from `docker_aws.pdf` (and possibly Flask lectures).
- Outlines the steps that appear in the materials: base Python image, copy
  source, install requirements, expose the port, define `CMD`.
- `refused` is `false`.

## 5. What AWS services are mentioned for deploying a web application?

**Expected behaviour**
- Retrieves chunks from `docker_aws.pdf`.
- Lists AWS services covered by the lecture (e.g. EC2 / Elastic Beanstalk /
  ECS / etc., as covered in the PDF).
- `refused` is `false`.

---

## 6. (Out of scope) What is the capital of France?

**Expected behaviour**
- The best retrieved chunk has a low cosine score (typically below 0.30), or
  the LLM judges the context as irrelevant.
- The assistant replies with **exactly**:

  > I don't have enough information in the course materials (Flask lectures,
  > Docker/AWS notes) to answer that.

- `refused` is `true`.

This validates the homework requirement: *"If the answer is not in the
context, say that there is not enough information in the knowledge base."*
