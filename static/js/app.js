/* Course Assistant frontend */

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
    deleteSession: id =>
        fetch(`/api/sessions/${id}`, { method: "DELETE" }).then(r => r.json()),
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
    listDocuments: () => fetch("/api/documents").then(r => r.json()),
    uploadDocument: file => {
        const fd = new FormData();
        fd.append("file", file);
        return fetch("/api/documents/upload", {
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
};

const state = {
    sessions: [],
    activeSessionId: null,
    messages: [],
    engineReady: false,
    isSending: false,
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
    documentList: document.getElementById("documentList"),
    resetProjectBtn: document.getElementById("resetProjectBtn"),
};

const FALLBACK_PREFIX = "I could not find this in the documents.";

// ==========================================================
// Utilities
// ==========================================================
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

// ==========================================================
// Engine status polling
// ==========================================================
async function refreshKbDocuments() {
    try {
        const d = await API.listDocuments();
        renderKbDocuments(d.documents || []);
    } catch {
        renderKbDocuments([]);
    }
}

async function pollEngineStatus() {
    try {
        const s = await API.status();
        if (s.error) {
            state.engineReady = false;
            els.statusDot.dataset.state = "error";
            els.statusText.textContent = s.error.message;
            els.input.disabled = true;
            els.sendBtn.disabled = true;
            setTimeout(pollEngineStatus, 5000);
            return;
        }
        if (s.ready) {
            state.engineReady = true;
            els.statusDot.dataset.state = "ready";
            els.statusText.textContent = `Ready - ${s.chunks} chunks`;
            await refreshKbDocuments();
            els.input.disabled = false;
            els.sendBtn.disabled = false;
            els.input.placeholder = "Ask anything about your documents...";
            return;
        }
        state.engineReady = false;
        els.input.disabled = true;
        els.sendBtn.disabled = true;
        els.statusDot.dataset.state = "loading";
        let label = humanizeStatus(s.status);
        if (s.status === "embedding_documents" && s.progress?.total) {
            label = `Embedding ${s.progress.current}/${s.progress.total}...`;
        }
        els.statusText.textContent = label;
        await refreshKbDocuments();
        setTimeout(pollEngineStatus, 1500);
    } catch (e) {
        els.statusDot.dataset.state = "error";
        els.statusText.textContent = "Server unreachable";
        setTimeout(pollEngineStatus, 3000);
    }
}

function renderKbDocuments(docs) {
    if (!els.documentList) return;
    els.documentList.innerHTML = "";
    if (!docs.length) {
        const empty = document.createElement("div");
        empty.className = "document-list__empty";
        empty.textContent = "No documents indexed yet.";
        els.documentList.appendChild(empty);
        return;
    }
    docs.forEach(doc => {
        const row = document.createElement("div");
        row.className = "document-list__item";
        const cat = (doc.category || "TXT").toUpperCase();
        let badgeLabel = cat;
        let slug = "txt";
        if (cat === "PDF") slug = "pdf";
        else if (cat === "IMAGE") slug = "image";
        else if (cat === "OCR_TXT") {
            slug = "ocr";
            badgeLabel = "OCR";
        }
        const hint = doc.hint ? String(doc.hint) : "";
        const hintEsc = escapeHtml(hint);
        const rawShown = doc.display_source || doc.name || "";
        const shown =
            rawShown.includes("/") ? rawShown.split("/").pop() : rawShown;
        const titleFull = escapeHtml(doc.name || rawShown);
        row.innerHTML = `
            <span class="document-list__badge document-list__badge--${slug}" ${hint ? `title="${hintEsc}"` : ""}>${escapeHtml(badgeLabel)}</span>
            <span class="document-list__name" title="${titleFull}">${escapeHtml(shown)}</span>
        `;
        els.documentList.appendChild(row);
    });
}

function humanizeStatus(key) {
    const map = {
        not_initialised: "Starting engine...",
        loading_documents: "Loading documents...",
        chunking_documents: "Chunking text...",
        embedding_documents: "Computing embeddings...",
        building_index: "Building FAISS index...",
        saving_cache: "Saving cache...",
        loading_cache: "Loading cached index...",
        ready: "Ready",
    };
    return map[key] || "Starting engine...";
}

// ==========================================================
// Sessions
// ==========================================================
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
}

async function newSession({ select = true } = {}) {
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
    if (!confirm("Delete this conversation? This cannot be undone.")) return;
    const id = state.activeSessionId;
    await API.deleteSession(id);
    state.sessions = state.sessions.filter(s => s.id !== id);
    state.activeSessionId = null;
    state.messages = [];
    els.conversationTitle.textContent = "New conversation";
    els.conversationMeta.textContent = "";
    els.renameBtn.disabled = true;
    els.deleteBtn.disabled = true;
    renderSessions();
    renderMessages();
    toast("Conversation deleted");
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
        toast("Reset complete — rebuilding knowledge base from starter PDFs…");
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
        els.input.disabled = true;
        els.sendBtn.disabled = true;
        pollEngineStatus();
    } catch (err) {
        toast(err.message || "Reset failed", { error: true });
    } finally {
        els.resetProjectBtn.disabled = false;
    }
}

// ==========================================================
// Messages
// ==========================================================
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

function renderMessage(msg) {
    const wrap = document.createElement("div");
    wrap.className = `message message--${msg.role}`;
    if (
        msg.role === "assistant" &&
        (msg.content || "").startsWith(FALLBACK_PREFIX)
    ) {
        wrap.classList.add("message--fallback");
    }
    if (
        msg.role === "assistant" &&
        msg.generation_mode === "retrieval_fallback"
    ) {
        wrap.classList.add("message--retrieval-fallback");
    }

    const avatar = document.createElement("div");
    avatar.className = "message__avatar";
    avatar.textContent = msg.role === "user" ? "Y" : "C";

    const body = document.createElement("div");
    body.className = "message__body";

    const role = document.createElement("div");
    role.className = "message__role";
    role.textContent = msg.role === "user" ? "You" : "Assistant";

    const content = document.createElement("div");
    content.className = "message__content";
    content.textContent = msg.content;

    body.appendChild(role);
    body.appendChild(content);

    if (msg.role === "assistant" && Array.isArray(msg.context) && msg.context.length > 0) {
        body.appendChild(renderContext(msg.context));
    }

    wrap.appendChild(avatar);
    wrap.appendChild(body);
    return wrap;
}

function renderContext(chunks) {
    const wrap = document.createElement("div");
    wrap.className = "context-wrap";

    // Pick the highest-scoring chunk as the "main source"
    const main = chunks.reduce(
        (best, c) =>
            (best === null || (c.score ?? -Infinity) > (best.score ?? -Infinity))
                ? c : best,
        null
    );

    if (main) {
        const banner = document.createElement("div");
        banner.className = "context__main";
        const page = main.page ? ` p.${main.page}` : "";
        banner.innerHTML = `
            <span class="context__main-label">Main source</span>
            <span class="context__main-file">${escapeHtml((main.source || "unknown") + page)}</span>
        `;
        wrap.appendChild(banner);
    }

    const details = document.createElement("details");
    details.className = "context";

    const summary = document.createElement("summary");
    summary.className = "context__summary";
    summary.textContent = `All sources (${chunks.length})`;
    details.appendChild(summary);

    const body = document.createElement("div");
    body.className = "context__body";
    for (const c of chunks) {
        const item = document.createElement("div");
        item.className = "context__chunk";
        if (main && c === main) item.classList.add("context__chunk--main");
        const meta = document.createElement("div");
        meta.className = "context__chunk-meta";
        const page = c.page ? ` p.${c.page}` : "";
        meta.innerHTML = `
            <span>${escapeHtml((c.source || "unknown") + page)}</span>
            <span>score ${typeof c.score === "number" ? c.score.toFixed(3) : "-"}</span>
        `;
        const text = document.createElement("div");
        text.textContent = c.text;
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
        <div class="message__avatar">C</div>
        <div class="message__body">
            <div class="message__role">Assistant</div>
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

// ==========================================================
// Sending
// ==========================================================
async function sendMessage(content) {
    if (state.isSending) return;
    if (!state.engineReady) {
        toast("Engine is still loading", { error: true });
        return;
    }

    const text = content.trim();
    if (!text) return;

    if (!state.activeSessionId) {
        await newSession({ select: true });
    }

    state.isSending = true;
    els.sendBtn.disabled = true;
    els.input.disabled = true;

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
        els.sendBtn.disabled = !state.engineReady;
        els.input.disabled = !state.engineReady;
        els.input.focus();
    }
}

// ==========================================================
// Wiring
// ==========================================================
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

// ==========================================================
// Upload
// ==========================================================
function setUploadStatus(message, kind /* "info" | "success" | "error" | "" */) {
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

async function handleUpload(file) {
    if (!file) return;
    const okExt = /\.(pdf|txt|png|jpe?g|webp)$/i.test(file.name);
    if (!okExt) {
        toast("Supported: PDF, TXT, PNG, JPG, JPEG, WEBP", { error: true });
        return;
    }
    els.uploadBtn.disabled = true;
    const busyHint =
        /\.(png|jpe?g|webp)$/i.test(file.name)
            ? " (Vision / OCR extraction — may take a moment)"
            : "";
    setUploadStatus(`Uploading ${file.name}${busyHint}...`, "info");
    try {
        const result = await API.uploadDocument(file);
        const kb = Math.max(1, Math.round((result.size || 0) / 1024));
        const successMsg =
            result.message ||
            `Uploaded ${result.filename} (${kb} KB). Re-indexing...`;
        setUploadStatus(successMsg, "success");
        toast(successMsg);
        // Backend marked engine as not-ready and is rebuilding in the background.
        state.engineReady = false;
        els.input.disabled = true;
        els.sendBtn.disabled = true;
        pollEngineStatus();
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

els.uploadBtn?.addEventListener("click", () => els.uploadInput?.click());
els.uploadInput?.addEventListener("change", e => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
});

els.resetProjectBtn?.addEventListener("click", () => handleResetProject());

// ==========================================================
// Boot
// ==========================================================
(async function boot() {
    pollEngineStatus();
    await loadSessions();
})();
