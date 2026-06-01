/* ScoutMatch AI frontend */

const API = {
    status: () => fetch("/api/status").then(r => r.json()),
    listSessions: () => fetch("/api/sessions").then(r => r.json()),
    createSession: () =>
        fetch("/api/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        }).then(r => r.json()),
    getSession: id => fetch(`/api/sessions/${id}`).then(r => r.json()),
    renameSession: (id, title) =>
        fetch(`/api/sessions/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
        }).then(r => r.json()),
    deleteSession: (id, { deleteDocuments = false } = {}) =>
        fetch(`/api/sessions/${id}`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ delete_documents: deleteDocuments }),
        }).then(async r => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Delete failed");
            return data;
        }),
    sendMessage: (id, content) =>
        fetch(`/api/sessions/${id}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content }),
        }).then(async r => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.detail || data.error || "Request failed");
            return data;
        }),
    listDocuments: sessionId =>
        fetch(`/api/sessions/${sessionId}/documents`).then(r => r.json()),
    uploadDocument: (sessionId, file) => {
        const fd = new FormData();
        fd.append("file", file);
        return fetch(`/api/sessions/${sessionId}/documents/upload`, {
            method: "POST",
            body: fd,
        }).then(async r => {
            const data = await r.json();
            if (!r.ok) {
                const err = new Error(data.error || "Upload failed");
                err.partialIndexed = !!(data.partial && Array.isArray(data.stored_paths));
                throw err;
            }
            return data;
        });
    },
    clearSessionDocuments: sessionId =>
        fetch(`/api/sessions/${sessionId}/documents/clear`, {
            method: "POST",
        }).then(async r => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Clear documents failed");
            return data;
        }),
    deleteSessionDocument: (sessionId, documentId) =>
        fetch(`/api/sessions/${sessionId}/documents/${documentId}`, {
            method: "DELETE",
        }).then(async r => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Delete document failed");
            return data;
        }),
    ingestionStatus: jobId =>
        fetch(`/api/ingestion/status${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`).then(
            r => r.json()
        ),
    resetAll: () =>
        fetch("/api/reset-all", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ confirm: true }),
        }).then(async r => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Reset failed");
            return data;
        }),
    resetSessionUploads: () =>
        fetch("/api/session-uploads/reset", { method: "POST" }).then(async r => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Reset failed");
            return data;
        }),
};

const state = {
    sessions: [],
    activeSessionId: null,
    messages: [],
    engineReady: false,
    isSending: false,
    awsMode: false,
    kbSyncInProgress: false,
    ingestionJobId: null,
};

const els = {
    app: document.querySelector(".app"),
    sidebar: document.getElementById("sidebar"),
    sessionList: document.getElementById("sessionList"),
    newChatBtn: document.getElementById("newChatBtn"),
    newChatBtnLarge: document.getElementById("newChatBtnLarge"),
    toggleSidebar: document.getElementById("toggleSidebar"),
    renameBtn: document.getElementById("renameBtn"),
    deleteBtn: document.getElementById("deleteBtn"),
    messages: document.getElementById("messages"),
    emptyState: document.getElementById("emptyState"),
    conversationTitle: document.getElementById("conversationTitle"),
    conversationMeta: document.getElementById("conversationMeta"),
    form: document.getElementById("chatForm"),
    input: document.getElementById("chatInput"),
    sendBtn: document.getElementById("sendBtn"),
    statusDot: document.querySelector(".status__dot"),
    statusText: document.querySelector(".status__text"),
    suggestions: document.getElementById("suggestions"),
    uploadBtn: document.getElementById("uploadBtn"),
    uploadInput: document.getElementById("uploadInput"),
    uploadStatus: document.getElementById("uploadStatus"),
    syncStatus: document.getElementById("syncStatus"),
    documentList: document.getElementById("documentList"),
    clearDocumentsBtn: document.getElementById("clearDocumentsBtn"),
    resetProjectBtn: document.getElementById("resetProjectBtn"),
    awsBadge: document.getElementById("awsBadge"),
};

const REFUSAL_MARKERS = [
    "do not have enough information in the uploaded player",
    "אין לי מספיק מידע במסמכי השחקנים",
];

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
}

function formatDate(iso) {
    if (!iso) return "";
    try {
        const d = new Date(iso);
        const isToday = d.toDateString() === new Date().toDateString();
        return isToday
            ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
            : d.toLocaleDateString([], { month: "short", day: "numeric" });
    } catch {
        return "";
    }
}

function autoresize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
}

let toastEl = null;
let toastTimer = null;
function toast(message, { error = false } = {}) {
    if (!toastEl) {
        toastEl = document.createElement("div");
        toastEl.className = "toast";
        document.body.appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.classList.toggle("toast--error", error);
    toastEl.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("is-visible"), 3500);
}

function setUploadStatus(message, kind) {
    if (!els.uploadStatus) return;
    if (!message) {
        els.uploadStatus.hidden = true;
        els.uploadStatus.textContent = "";
        els.uploadStatus.className = "upload-card__status";
        return;
    }
    els.uploadStatus.hidden = false;
    els.uploadStatus.textContent = message;
    els.uploadStatus.className = `upload-card__status upload-card__status--${kind || "info"}`;
}

function setSyncStatus(message, kind) {
    if (!els.syncStatus) return;
    if (!message) {
        els.syncStatus.hidden = true;
        els.syncStatus.textContent = "";
        els.syncStatus.className = "sync-status";
        return;
    }
    els.syncStatus.hidden = false;
    els.syncStatus.textContent = message;
    els.syncStatus.className = `sync-status sync-status--${kind || "info"}`;
}

function updateComposerState() {
    const blocked = !state.engineReady || state.isSending || state.kbSyncInProgress;
    els.input.disabled = blocked;
    els.sendBtn.disabled = blocked;
}

async function refreshKbDocuments() {
    if (!state.activeSessionId) {
        renderKbDocuments([]);
        return;
    }
    try {
        const d = await API.listDocuments(state.activeSessionId);
        renderKbDocuments(d.documents || []);
    } catch {
        renderKbDocuments([]);
    }
}

function renderKbDocuments(docs) {
    if (!els.documentList) return;
    els.documentList.innerHTML = "";
    if (!docs.length) {
        const empty = document.createElement("div");
        empty.className = "document-list__empty";
        empty.textContent = state.awsMode
            ? "Upload player CVs or scouting reports to start recruiting."
            : "No documents indexed yet.";
        els.documentList.appendChild(empty);
        return;
    }
    docs.forEach(doc => {
        const row = document.createElement("div");
        row.className = "document-list__item";
        const cat = (doc.category || "TXT").toUpperCase();
        let slug = "txt";
        if (cat.includes("PDF")) slug = "pdf";
        else if (cat.includes("PLAYER")) slug = "cv";
        else if (cat.includes("SCOUT")) slug = "scout";
        else if (cat.includes("TEAM")) slug = "team";
        else if (cat === "DOCX") slug = "pdf";
        else if (cat === "CSV") slug = "txt";
        const rawShown = doc.display_name || doc.display_source || doc.name || "";
        const shown = rawShown.includes("/") ? rawShown.split("/").pop() : rawShown;
        row.innerHTML = `
            <span class="document-list__badge document-list__badge--${slug}">${escapeHtml(cat.split(" ")[0])}</span>
            <span class="document-list__name" title="${escapeHtml(rawShown)}">${escapeHtml(shown)}</span>
        `;
        els.documentList.appendChild(row);
    });
}

async function pollIngestion(jobId) {
    state.kbSyncInProgress = true;
    state.ingestionJobId = jobId;
    updateComposerState();
    setSyncStatus("Updating the ScoutMatch knowledge base...", "progress");

    const terminal = new Set(["COMPLETE", "FAILED", "STOPPED"]);
    let attempts = 0;
    const maxAttempts = 120;

    while (attempts < maxAttempts) {
        attempts += 1;
        try {
            const status = await API.ingestionStatus(jobId);
            const st = status.status || "IN_PROGRESS";
            if (st === "COMPLETE") {
                setSyncStatus("Knowledge base updated. You can now ask questions about the new player.", "progress");
                toast("Knowledge base sync complete.");
                state.kbSyncInProgress = false;
                updateComposerState();
                await refreshKbDocuments();
                setTimeout(() => setSyncStatus("", ""), 8000);
                return;
            }
            if (st === "FAILED" || st === "STOPPED") {
                setSyncStatus(
                    "The file was uploaded, but the knowledge base sync failed. Please review the AWS configuration.",
                    "error"
                );
                state.kbSyncInProgress = false;
                updateComposerState();
                return;
            }
            setSyncStatus(`Updating the ScoutMatch knowledge base... (${st})`, "progress");
        } catch {
            /* retry */
        }
        await new Promise(r => setTimeout(r, 3000));
    }
    state.kbSyncInProgress = false;
    updateComposerState();
}

async function pollEngineStatus() {
    try {
        const s = await API.status();
        state.awsMode = s.aws_mode === true || s.rag_backend === "aws_kb";

        if (els.awsBadge) {
            els.awsBadge.hidden = !state.awsMode;
        }
        if (els.resetProjectBtn) {
            els.resetProjectBtn.hidden = state.awsMode;
        }

        if (s.error) {
            state.engineReady = false;
            els.statusDot.dataset.state = "error";
            els.statusText.textContent = s.error.message;
            updateComposerState();
            setTimeout(pollEngineStatus, 5000);
            return;
        }

        if (s.config_missing?.length) {
            state.engineReady = false;
            els.statusDot.dataset.state = "error";
            els.statusText.textContent = `Missing AWS config: ${s.config_missing.join(", ")}`;
            updateComposerState();
            setTimeout(pollEngineStatus, 5000);
            return;
        }

        if (s.ready) {
            state.engineReady = true;
            els.statusDot.dataset.state = "ready";
            if (state.awsMode) {
                els.statusText.textContent = "AWS Bedrock KB ready";
            } else {
                els.statusText.textContent = `Ready — ${s.chunks} chunks indexed`;
            }
            await refreshKbDocuments();
            updateComposerState();
            els.input.placeholder = "Ask about players, positions, salary, or squad fit...";
            return;
        }

        state.engineReady = false;
        updateComposerState();
        els.statusDot.dataset.state = "loading";
        els.statusText.textContent = humanizeStatus(s.status);
        await refreshKbDocuments();
        setTimeout(pollEngineStatus, 1500);
    } catch {
        els.statusDot.dataset.state = "error";
        els.statusText.textContent = "Server unreachable";
        setTimeout(pollEngineStatus, 3000);
    }
}

function humanizeStatus(key) {
    const map = {
        not_initialised: "Starting ScoutMatch...",
        initialising: "Connecting to AWS Knowledge Base...",
        ready: "Ready",
    };
    return map[key] || "Starting ScoutMatch...";
}

async function loadSessions() {
    const data = await API.listSessions();
    state.sessions = data.sessions || [];
    renderSessions();
}

function renderSessions() {
    els.sessionList.innerHTML = "";
    if (state.sessions.length === 0) {
        const empty = document.createElement("div");
        empty.className = "session-list__empty";
        empty.textContent = "No conversations yet";
        els.sessionList.appendChild(empty);
        return;
    }
    for (const s of state.sessions) {
        const item = document.createElement("div");
        item.className = "session-item";
        if (s.id === state.activeSessionId) item.classList.add("is-active");
        item.dataset.id = s.id;
        item.innerHTML = `
            <span class="session-item__title">${escapeHtml(s.title)}</span>
            <span class="session-item__date">${formatDate(s.updated_at)}</span>
        `;
        item.addEventListener("click", () => selectSession(s.id));
        els.sessionList.appendChild(item);
    }
}

async function selectSession(id) {
    state.activeSessionId = id;
    const data = await API.getSession(id);
    state.messages = data.messages || [];
    els.conversationTitle.textContent = data.title || "Conversation";
    els.conversationMeta.textContent =
        state.messages.length > 0
            ? `${state.messages.length} message${state.messages.length === 1 ? "" : "s"}`
            : "No messages yet";
    els.renameBtn.disabled = false;
    els.deleteBtn.disabled = false;
    renderMessages();
    renderSessions();
    await refreshKbDocuments();
}

async function newSession({ select = true } = {}) {
    if (!state.awsMode) {
        try {
            await API.resetSessionUploads();
            state.engineReady = false;
            updateComposerState();
            await refreshKbDocuments();
            pollEngineStatus();
        } catch (err) {
            toast(err.message || "Could not reset session uploads", { error: true });
        }
    }

    const session = await API.createSession();
    state.sessions.unshift(session);
    renderSessions();
    if (select) {
        await selectSession(session.id);
        els.input.focus();
    }
    return session;
}

async function renameActiveSession() {
    if (!state.activeSessionId) return;
    const current = state.sessions.find(s => s.id === state.activeSessionId);
    const title = prompt("Rename conversation", current?.title || "");
    if (!title || title.trim() === "") return;
    const updated = await API.renameSession(state.activeSessionId, title.trim());
    const idx = state.sessions.findIndex(s => s.id === updated.id);
    if (idx !== -1) state.sessions[idx] = updated;
    els.conversationTitle.textContent = updated.title;
    renderSessions();
}

async function deleteActiveSession() {
    if (!state.activeSessionId) return;
    if (
        !confirm(
            "Delete this conversation and its uploaded documents?\nThis action cannot be undone."
        )
    ) {
        return;
    }
    const id = state.activeSessionId;
    els.deleteBtn.disabled = true;
    try {
        const result = await API.deleteSession(id, { deleteDocuments: true });
        state.sessions = state.sessions.filter(s => s.id !== id);
        if (state.awsMode && result.ingestion_job_id) {
            pollIngestion(result.ingestion_job_id);
        }
        if (state.sessions.length > 0) {
            await selectSession(state.sessions[0].id);
        } else {
            state.activeSessionId = null;
            state.messages = [];
            els.conversationTitle.textContent = "New conversation";
            els.conversationMeta.textContent = "";
            els.renameBtn.disabled = true;
            els.deleteBtn.disabled = true;
            renderSessions();
            renderMessages();
            await refreshKbDocuments();
            await newSession({ select: true });
        }
        toast("Conversation deleted");
    } catch (err) {
        toast(err.message || "Could not delete conversation", { error: true });
        els.deleteBtn.disabled = false;
    }
}

async function clearActiveDocuments() {
    if (!state.activeSessionId) {
        toast("Choose a conversation first", { error: true });
        return;
    }
    if (
        !confirm(
            "Clear all uploaded documents from this conversation?\nThis action cannot be undone."
        )
    ) {
        return;
    }
    els.clearDocumentsBtn.disabled = true;
    try {
        const result = await API.clearSessionDocuments(state.activeSessionId);
        toast("Conversation documents cleared");
        if (state.awsMode && result.ingestion_job_id) {
            pollIngestion(result.ingestion_job_id);
        } else {
            await refreshKbDocuments();
        }
    } catch (err) {
        toast(err.message || "Could not clear documents", { error: true });
    } finally {
        els.clearDocumentsBtn.disabled = false;
    }
}

async function handleResetProject() {
    if (
        !confirm(
            "Are you sure? This will delete uploaded files and clear all chat memory."
        )
    ) {
        return;
    }
    els.resetProjectBtn.disabled = true;
    try {
        await API.resetAll();
        toast("Reset complete — rebuilding knowledge base…");
        state.activeSessionId = null;
        state.messages = [];
        els.conversationTitle.textContent = "New conversation";
        els.conversationMeta.textContent = "";
        els.renameBtn.disabled = true;
        els.deleteBtn.disabled = true;
        await loadSessions();
        renderMessages();
        await refreshKbDocuments();
        state.engineReady = false;
        updateComposerState();
        pollEngineStatus();
    } catch (err) {
        toast(err.message || "Reset failed", { error: true });
    } finally {
        els.resetProjectBtn.disabled = false;
    }
}

function renderMessages() {
    els.messages.innerHTML = "";
    if (state.messages.length === 0) {
        els.messages.appendChild(els.emptyState);
        return;
    }
    const inner = document.createElement("div");
    inner.className = "messages__inner";
    for (const m of state.messages) inner.appendChild(renderMessage(m));
    els.messages.appendChild(inner);
    requestAnimationFrame(() => {
        els.messages.scrollTop = els.messages.scrollHeight;
    });
}

function isRefusalMessage(content) {
    const lower = (content || "").toLowerCase();
    return REFUSAL_MARKERS.some(m => lower.includes(m.toLowerCase()) || content.includes(m));
}

function renderMessage(msg) {
    const wrap = document.createElement("div");
    wrap.className = `message message--${msg.role}`;
    if (msg.role === "assistant" && (msg.refused || isRefusalMessage(msg.content))) {
        wrap.classList.add("message--refused");
    }

    const avatar = document.createElement("div");
    avatar.className = "message__avatar";
    avatar.textContent = msg.role === "user" ? "M" : "S";

    const body = document.createElement("div");
    body.className = "message__body";

    const role = document.createElement("div");
    role.className = "message__role";
    role.textContent = msg.role === "user" ? "Manager" : "ScoutMatch AI";

    const content = document.createElement("div");
    content.className = "message__content";
    content.textContent = msg.content;

    body.appendChild(role);
    body.appendChild(content);

    if (msg.role === "assistant" && Array.isArray(msg.context) && msg.context.length > 0) {
        body.appendChild(renderContext(msg.context, msg.main_source));
    }

    wrap.appendChild(avatar);
    wrap.appendChild(body);
    return wrap;
}

function renderContext(chunks, mainSource) {
    const wrap = document.createElement("div");
    wrap.className = "context-wrap";

    const main = mainSource || chunks.reduce(
        (best, c) =>
            (best === null || (c.score ?? -Infinity) > (best.score ?? -Infinity))
                ? c : best,
        null
    );

    if (main) {
        const banner = document.createElement("div");
        banner.className = "context__main";
        const src = main.source || main.s3_uri || "unknown";
        const short = src.includes("/") ? src.split("/").pop() : src;
        banner.innerHTML = `
            <span class="context__main-label">Main source</span>
            <span class="context__main-file">${escapeHtml(short)}</span>
        `;
        wrap.appendChild(banner);
    }

    const details = document.createElement("details");
    details.className = "context";
    details.open = chunks.length <= 3;

    const summary = document.createElement("summary");
    summary.className = "context__summary";
    summary.textContent = `Retrieved evidence (${chunks.length})`;
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "context__body";
    for (const c of chunks) {
        const item = document.createElement("div");
        item.className = "context__chunk";
        const src = c.source || c.s3_uri || "unknown";
        const short = src.includes("/") ? src.split("/").pop() : src;
        const meta = document.createElement("div");
        meta.className = "context__chunk-meta";
        meta.innerHTML = `
            <span>${escapeHtml(short)}</span>
            <span>${typeof c.score === "number" ? `score ${c.score.toFixed(3)}` : ""}</span>
        `;
        const text = document.createElement("div");
        text.textContent = c.text || "";
        item.appendChild(meta);
        item.appendChild(text);
        body.appendChild(item);
    }
    details.appendChild(body);
    wrap.appendChild(details);
    return wrap;
}

function appendMessageEphemeral(msg) {
    let inner = els.messages.querySelector(".messages__inner");
    if (!inner) {
        els.messages.innerHTML = "";
        inner = document.createElement("div");
        inner.className = "messages__inner";
        els.messages.appendChild(inner);
    }
    inner.appendChild(renderMessage(msg));
    els.messages.scrollTop = els.messages.scrollHeight;
}

function appendTypingIndicator() {
    let inner = els.messages.querySelector(".messages__inner");
    if (!inner) {
        els.messages.innerHTML = "";
        inner = document.createElement("div");
        inner.className = "messages__inner";
        els.messages.appendChild(inner);
    }
    const wrap = document.createElement("div");
    wrap.className = "message message--assistant";
    wrap.id = "typingIndicator";
    wrap.innerHTML = `
        <div class="message__avatar">S</div>
        <div class="message__body">
            <div class="message__role">ScoutMatch AI</div>
            <div class="message__content">
                <div class="typing"><span></span><span></span><span></span></div>
            </div>
        </div>
    `;
    inner.appendChild(wrap);
    els.messages.scrollTop = els.messages.scrollHeight;
}

function removeTypingIndicator() {
    const t = document.getElementById("typingIndicator");
    if (t) t.remove();
}

async function sendMessage(content) {
    if (state.isSending) return;
    if (!state.engineReady) {
        toast("ScoutMatch is still loading", { error: true });
        return;
    }
    if (state.kbSyncInProgress) {
        toast("Please wait for knowledge base sync to finish", { error: true });
        return;
    }

    const text = content.trim();
    if (!text) return;

    if (!state.activeSessionId) {
        await newSession({ select: true });
    }

    state.isSending = true;
    updateComposerState();

    const tempUser = {
        id: `tmp-${Date.now()}`,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
    };
    state.messages.push(tempUser);
    appendMessageEphemeral(tempUser);
    appendTypingIndicator();

    els.input.value = "";
    autoresize(els.input);

    try {
        const result = await API.sendMessage(state.activeSessionId, text);
        removeTypingIndicator();

        const userIdx = state.messages.findIndex(m => m.id === tempUser.id);
        if (userIdx !== -1) state.messages[userIdx] = result.user_message;
        state.messages.push(result.assistant_message);
        appendMessageEphemeral(result.assistant_message);

        await loadSessions();
        const updated = state.sessions.find(s => s.id === state.activeSessionId);
        if (updated) els.conversationTitle.textContent = updated.title;
        els.conversationMeta.textContent = `${state.messages.length} messages`;
    } catch (err) {
        removeTypingIndicator();
        toast(err.message || "Failed to send message", { error: true });
    } finally {
        state.isSending = false;
        updateComposerState();
        els.input.focus();
    }
}

async function handleUpload(file) {
    if (!file) return;
    const okExt = /\.(txt|md|html|pdf|doc|docx|csv|xls|xlsx)$/i.test(file.name);
    if (!okExt) {
        toast("Supported: TXT, MD, HTML, PDF, DOC, DOCX, CSV, XLS, XLSX", { error: true });
        return;
    }
    if (!state.activeSessionId) {
        await newSession({ select: true });
    }
    els.uploadBtn.disabled = true;
    setUploadStatus(`Uploading CV to Amazon S3... (${file.name})`, "info");
    try {
        const result = await API.uploadDocument(state.activeSessionId, file);
        setUploadStatus(result.message || "Upload complete.", "success");
        toast("Document uploaded to S3");

        if (state.awsMode && result.ingestion_job_id) {
            pollIngestion(result.ingestion_job_id);
        } else if (!state.awsMode) {
            state.engineReady = false;
            updateComposerState();
            pollEngineStatus();
        } else {
            await refreshKbDocuments();
        }
        setTimeout(() => setUploadStatus("", ""), 8000);
    } catch (err) {
        setUploadStatus(`Failed: ${err.message}`, "error");
        toast(err.message || "Upload failed", { error: true });
        if (err.partialIndexed) refreshKbDocuments();
    } finally {
        els.uploadBtn.disabled = false;
        els.uploadInput.value = "";
    }
}

els.form.addEventListener("submit", e => {
    e.preventDefault();
    sendMessage(els.input.value);
});

els.input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage(els.input.value);
    }
});

els.input.addEventListener("input", () => autoresize(els.input));

els.newChatBtn.addEventListener("click", () => newSession());
els.newChatBtnLarge.addEventListener("click", () => newSession());
els.renameBtn.addEventListener("click", renameActiveSession);
els.deleteBtn.addEventListener("click", deleteActiveSession);

els.toggleSidebar.addEventListener("click", () => {
    els.app.classList.toggle("sidebar-collapsed");
    els.app.classList.toggle("sidebar-open");
});

els.suggestions?.addEventListener("click", e => {
    const btn = e.target.closest(".suggestion");
    if (!btn) return;
    const q = btn.dataset.q;
    els.input.value = q;
    autoresize(els.input);
    sendMessage(q);
});

els.uploadBtn?.addEventListener("click", () => els.uploadInput?.click());
els.uploadInput?.addEventListener("change", e => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
});

els.clearDocumentsBtn?.addEventListener("click", clearActiveDocuments);
els.resetProjectBtn?.addEventListener("click", () => handleResetProject());

(async function boot() {
    pollEngineStatus();
    await loadSessions();
})();
