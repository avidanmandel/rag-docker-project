(function () {
  const disabledEl = document.getElementById("advisor-disabled");
  const chatEl = document.getElementById("advisor-chat");
  const messagesEl = document.getElementById("advisor-messages");
  const formEl = document.getElementById("advisor-form");
  const inputEl = document.getElementById("advisor-input");
  const newSessionBtn = document.getElementById("advisor-new-session");
  const loadingEl = document.getElementById("advisor-loading");

  let sessionId = sessionStorage.getItem("scoutmatchAdvisorSession") || "";

  function renderMeta(meta) {
    if (!meta || typeof meta !== "object") return "";
    const parts = [];
    if (meta.documents_used && meta.documents_used.length) {
      parts.push("Documents used: " + meta.documents_used.join(", "));
    }
    if (meta.tools_executed && meta.tools_executed.length) {
      parts.push("Tools executed: " + meta.tools_executed.join(", "));
    }
    if (meta.workflow_status) parts.push("Workflow status: " + meta.workflow_status);
    if (meta.shortlist_action) parts.push("Shortlist action: " + meta.shortlist_action);
    if (meta.recruitment_brief_created) parts.push("Recruitment brief created: yes");
    if (meta.remaining_budget_eur != null) {
      parts.push("Remaining budget: " + meta.remaining_budget_eur + " EUR");
    }
    if (meta.warnings && meta.warnings.length) parts.push("Warnings: " + meta.warnings.join(", "));
    return parts.length ? '<div class="advisor-meta">' + parts.join(" | ") + "</div>" : "";
  }

  function renderLineupBoard(route) {
    if (!route) return "";
    const safeRoute = route.startsWith("/") ? route : "";
    if (!safeRoute) return "";
    return (
      '<div class="lineup-board-wrap">' +
      '<img class="lineup-board-image" src="' +
      safeRoute +
      '" alt="Current lineup board" loading="lazy" />' +
      '<a class="lineup-board-expand" href="' +
      safeRoute +
      '" target="_blank" rel="noopener">Open larger board</a>' +
      "</div>"
    );
  }

  function appendMessage(role, text, meta) {
    const div = document.createElement("div");
    div.className = role === "user" ? "msg-user" : "msg-assistant";
    const lineupHtml =
      role === "assistant" && meta && meta.lineup_image_route
        ? renderLineupBoard(meta.lineup_image_route)
        : "";
    div.innerHTML =
      "<strong>" +
      (role === "user" ? "Sporting Director" : "Advisor") +
      ":</strong> " +
      text +
      lineupHtml +
      renderMeta(meta);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setLoading(active) {
    if (!loadingEl) return;
    loadingEl.hidden = !active;
  }

  async function checkEnabled() {
    const resp = await fetch("/api/recruitment-advisor/status");
    const data = await resp.json();
    if (!data.enabled) {
      disabledEl.hidden = false;
      disabledEl.textContent = data.message || "Recruitment advisor is disabled.";
      chatEl.hidden = true;
      return false;
    }
    disabledEl.hidden = true;
    chatEl.hidden = false;
    return true;
  }

  formEl.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const text = (inputEl.value || "").trim();
    if (!text) return;
    appendMessage("user", text);
    inputEl.value = "";
    setLoading(true);
    try {
      const resp = await fetch("/api/recruitment-advisor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text, session_id: sessionId }),
      });
      const data = await resp.json();
      if (data.session_id) {
        sessionId = data.session_id;
        sessionStorage.setItem("scoutmatchAdvisorSession", sessionId);
      }
      appendMessage("assistant", data.answer || data.message || "No response.", data.metadata || {});
    } finally {
      setLoading(false);
    }
  });

  newSessionBtn.addEventListener("click", function () {
    sessionId = "";
    sessionStorage.removeItem("scoutmatchAdvisorSession");
    messagesEl.innerHTML = "";
    appendMessage("assistant", "Started a new advisor conversation.");
  });

  checkEnabled();
})();
