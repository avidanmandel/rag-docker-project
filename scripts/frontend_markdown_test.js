#!/usr/bin/env node
/**
 * Lightweight regression harness for markdown helpers in static/js/app.js.
 * Run: node scripts/frontend_markdown_test.js
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appJs = fs.readFileSync(
  path.join(__dirname, "..", "static", "js", "app.js"),
  "utf-8"
);

function extractFunction(name) {
  const start = appJs.indexOf(`function ${name}`);
  if (start < 0) throw new Error(`missing function ${name}`);
  let depth = 0;
  let started = false;
  for (let i = start; i < appJs.length; i += 1) {
    const ch = appJs[i];
    if (ch === "{") {
      depth += 1;
      started = true;
    } else if (ch === "}") {
      depth -= 1;
      if (started && depth === 0) {
        return appJs.slice(start, i + 1);
      }
    }
  }
  throw new Error(`unterminated function ${name}`);
}

function escapeHtmlLite(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const sandbox = {
  document: {
    createElement() {
      let text = "";
      let html = "";
      const nodes = [];
      const root = {
        get textContent() {
          return text;
        },
        set textContent(value) {
          text = String(value ?? "");
          html = "";
        },
        get innerHTML() {
          return html || escapeHtmlLite(text);
        },
        set innerHTML(value) {
          html = String(value ?? "");
          text = "";
        },
        attributes: [],
        childNodes: nodes,
        content: {
          querySelectorAll(selector) {
            if (selector.includes("script")) return [];
            return nodes;
          },
        },
        remove() {},
        removeAttribute() {},
      };
      return root;
    },
  },
  console,
};

vm.createContext(sandbox);
[
  "normalizeMarkdownInput",
  "escapeHtml",
  "formatInlineMarkdown",
  "sanitizeRenderedHtml",
  "renderMarkdown",
  "stripInternalDetails",
].forEach((name) => {
  vm.runInContext(extractFunction(name), sandbox);
});

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL:", message);
    process.exit(1);
  }
}

const { normalizeMarkdownInput, renderMarkdown, stripInternalDetails, sanitizeRenderedHtml } = sandbox;

assert(
  normalizeMarkdownInput("Weaknesses.### Squad gaps").includes("\n### Squad"),
  "inline heading split onto new line"
);
assert(
  !renderMarkdown("Weaknesses.### Squad gaps").includes("###"),
  "rendered inline heading has no literal markers"
);
assert(
  renderMarkdown("Weaknesses.### Squad gaps").includes("<h3>"),
  "inline heading renders as h3"
);
assert(
  renderMarkdown("### Clean heading").includes("<h3>Clean heading</h3>"),
  "standard heading renders"
);
assert(
  !renderMarkdown("###").includes("###"),
  "bare heading markers are omitted"
);
assert(
  renderMarkdown("| A | B |\n| --- | --- |\n| 1 | 2 |").includes("<table>"),
  "tables still render"
);
assert(
  renderMarkdown("**Bold** item").includes("<strong>Bold</strong>"),
  "bold text still renders"
);

const stripped = stripInternalDetails(
  "Board ready.\nView: /api/recruitment-advisor/lineups/current/image"
);
assert(!stripped.includes("/api/recruitment-advisor/lineups/current/image"), "proxy route hidden");
assert(stripped.includes("Board ready"), "user-facing text preserved");

assert(
  normalizeMarkdownInput("- depth is thin 4. Midfield Pressure — MEDIUM").includes("\n4."),
  "inline numbered section split onto new line"
);
assert(
  renderMarkdown("- depth is thin 4. Midfield Pressure — MEDIUM").includes("Midfield Pressure"),
  "inline numbered section renders separately"
);

console.log("frontend_markdown_test: OK");
