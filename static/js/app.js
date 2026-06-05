/* ScoutMatch AI frontend */

const API = {
    status: () => fetch("/api/status").then(r => r.json()),
    openingSeasonWorkspace: () => fetch("/api/opening-season/workspace").then(r => r.json()),
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
    agentMode: false,
    isSending: false,
    awsMode: false,
    kbSyncInProgress: false,
    kbOperationInProgress: false,
    sessionDocumentRevision: 0,
    ingestionJobId: null,
    workspace: null,
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
    homeHero: document.querySelector(".home-hero"),
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
    baselineDocumentList: document.getElementById("baselineDocumentList"),
    candidatePoolList: document.getElementById("candidatePoolList"),
    clearDocumentsBtn: document.getElementById("clearDocumentsBtn"),
    resetProjectBtn: document.getElementById("resetProjectBtn"),
    workspaceBadge: document.getElementById("workspaceBadge"),
    systemStatusList: document.getElementById("systemStatusList"),
    squadCountLabel: document.getElementById("squadCountLabel"),
    candidateCountLabel: document.getElementById("candidateCountLabel"),
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

function sanitizeUserError(message) {
    if (!message) return "Something went wrong. Please try again.";
    const lower = String(message).toLowerCase();
    if (
        lower.includes("conflictexception") ||
        lower.includes("bedrock") ||
        lower.includes("ingestion job") ||
        lower.includes("knowledge base sync")
    ) {
        return "The knowledge base is still updating. Please try again shortly.";
    }
    return message;
}

function beginKbUpdate(message = "Updating the ScoutMatch knowledge base...") {
    state.kbOperationInProgress = true;
    setSyncStatus(message, "progress");
    updateActionButtons();
}

function endKbUpdate() {
    state.kbOperationInProgress = false;
    updateActionButtons();
}

function updateActionButtons() {
    const busy = state.kbSyncInProgress || state.kbOperationInProgress;
    if (els.uploadBtn) els.uploadBtn.disabled = busy;
    if (els.clearDocumentsBtn) els.clearDocumentsBtn.disabled = busy;
    if (els.deleteBtn) els.deleteBtn.disabled = busy || !state.activeSessionId;
}

function updateComposerState() {
    const blocked =
        !state.engineReady ||
        state.isSending ||
        state.kbSyncInProgress ||
        state.kbOperationInProgress;
    els.input.disabled = blocked;
    els.sendBtn.disabled = blocked;
    updateActionButtons();
}

async function refreshKbDocuments() {
    const clubDocs =
        state.workspace?.club_knowledge ||
        (state.activeSessionId
            ? (await API.listDocuments(state.activeSessionId).catch(() => ({}))).club_knowledge
            : null) ||
        [];
    const poolDocs =
        state.workspace?.candidate_pool ||
        (state.activeSessionId
            ? (await API.listDocuments(state.activeSessionId).catch(() => ({}))).candidate_pool
            : null) ||
        [];
    renderBaselineDocuments(clubDocs);
    renderCandidatePool(poolDocs);
    if (!state.activeSessionId) {
        renderKbDocuments([]);
        return;
    }
    try {
        const d = await API.listDocuments(state.activeSessionId);
        renderBaselineDocuments(d.club_knowledge || clubDocs);
        renderCandidatePool(d.candidate_pool || poolDocs);
        renderKbDocuments(d.session_uploads || d.candidate_documents || []);
    } catch {
        renderKbDocuments([]);
    }
}

async function loadOpeningSeasonWorkspace() {
    try {
        const ws = await API.openingSeasonWorkspace();
        state.workspace = ws;
        if (els.squadCountLabel) {
            els.squadCountLabel.textContent = String(ws.club_player_count || 15);
        }
        if (els.candidateCountLabel) {
            els.candidateCountLabel.textContent = String(ws.candidate_pool_count || 8);
        }
        renderBaselineDocuments(ws.club_knowledge || []);
        renderCandidatePool(ws.candidate_pool || []);
        renderSuggestedPrompts(ws.suggested_prompts || [], ws.secondary_prompts || []);
        renderSystemStatus(ws.system_status || {});
    } catch {
        renderSuggestedPrompts([], []);
    }
}

function renderSuggestedPrompts(primary, secondary) {
    if (!els.suggestions) return;
    els.suggestions.innerHTML = "";
    [...primary, ...secondary].forEach(item => {
        const btn = document.createElement("button");
        btn.className = "suggestion";
        btn.type = "button";
        btn.dataset.q = item.query || item.label || "";
        btn.textContent = item.label || item.query || "";
        els.suggestions.appendChild(btn);
    });
}

function renderSystemStatus(status) {
    if (!els.systemStatusList) return;
    const rows = [
        ["Club knowledge", status.club_knowledge || "available"],
        ["Scouted candidates", status.scouted_candidates || "8 loaded"],
        ["Agent tools", status.agent_tools || "4 available"],
        ["Safety controls", status.safety_controls || "enabled"],
    ];
    els.systemStatusList.innerHTML = rows
        .map(([k, v]) => `<li><span>${escapeHtml(k)}</span><span>${escapeHtml(v)}</span></li>`)
        .join("");
}

function renderCandidatePool(docs) {
    if (!els.candidatePoolList) return;
    els.candidatePoolList.innerHTML = "";
    if (!docs.length) {
        const empty = document.createElement("div");
        empty.className = "document-list__empty";
        empty.textContent = "8 preloaded candidates";
        els.candidatePoolList.appendChild(empty);
        return;
    }
    docs.forEach(doc => {
        const row = document.createElement("div");
        row.className = "document-list__item document-list__item--readonly";
        const pos = (doc.primary_position || "Candidate").toUpperCase();
        const label = doc.display_name || doc.name || "Candidate";
        row.innerHTML = `
            <span class="document-list__badge document-list__badge--scout">${escapeHtml(pos.split(" ")[0])}</span>
            <span class="document-list__name" title="${escapeHtml(label)}">${escapeHtml(label)}</span>
            <span class="document-list__lock" title="Preloaded scouting report">&#128274;</span>
        `;
        els.candidatePoolList.appendChild(row);
    });
}

function renderBaselineDocuments(docs) {
    if (!els.baselineDocumentList) return;
    els.baselineDocumentList.innerHTML = "";
    if (!docs.length) {
        const empty = document.createElement("div");
        empty.className = "document-list__empty";
        empty.textContent = "Preloaded club data";
        els.baselineDocumentList.appendChild(empty);
        return;
    }
    docs.forEach(doc => {
        const row = document.createElement("div");
        row.className = "document-list__item document-list__item--readonly";
        const cat = (doc.category || "Club Knowledge").toUpperCase();
        const rawShown = doc.display_name || doc.display_source || doc.name || "";
        const shown = rawShown.includes("/") ? rawShown.split("/").pop() : rawShown;
        row.innerHTML = `
            <span class="document-list__badge document-list__badge--team">${escapeHtml(cat.split(" ")[0])}</span>
            <span class="document-list__name" title="${escapeHtml(rawShown)}">${escapeHtml(shown)}</span>
            <span class="document-list__lock" title="Read-only club knowledge">&#128274;</span>
        `;
        els.baselineDocumentList.appendChild(row);
    });
}

function renderKbDocuments(docs) {
    if (!els.documentList) return;
    els.documentList.innerHTML = "";
    const sessionDocs = (docs || []).filter(doc => doc.scope !== "baseline" && !doc.read_only);
    if (!sessionDocs.length) {
        const empty = document.createElement("div");
        empty.className = "document-list__empty";
        empty.textContent = state.awsMode
            ? "Upload player CVs or scouting reports to start recruiting."
            : "No documents indexed yet.";
        els.documentList.appendChild(empty);
        return;
    }
    sessionDocs.forEach(doc => {
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
            <button type="button" class="document-list__delete" title="Delete document" aria-label="Delete ${escapeHtml(shown)}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="3 6 5 6 21 6"></polyline>
                    <path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"></path>
                    <path d="M10 11v6"></path>
                    <path d="M14 11v6"></path>
                    <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"></path>
                </svg>
            </button>
        `;
        row.querySelector(".document-list__delete")?.addEventListener("click", e => {
            e.stopPropagation();
            deleteDocument(doc);
        });
        els.documentList.appendChild(row);
    });
}

async function deleteDocument(doc) {
    if (!state.activeSessionId || !doc?.id) return;
    if (state.kbOperationInProgress || state.kbSyncInProgress) return;
    const label = doc.display_name || doc.display_source || doc.name || "this document";
    const shown = label.includes("/") ? label.split("/").pop() : label;
    if (
        !confirm(
            `Delete "${shown}" from this conversation?\nThis action cannot be undone.`
        )
    ) {
        return;
    }
    beginKbUpdate("Updating the ScoutMatch knowledge base...");
    try {
        const result = await API.deleteSessionDocument(state.activeSessionId, doc.id);
        toast("Document deleted");
        if (state.awsMode && result.ingestion_job_id) {
            endKbUpdate();
            pollIngestion(result.ingestion_job_id);
        } else {
            endKbUpdate();
            await refreshKbDocuments();
        }
    } catch (err) {
        endKbUpdate();
        toast(sanitizeUserError(err.message) || "Could not delete document", { error: true });
    }
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
                if (state.activeSessionId) {
                    try {
                        const sessionData = await API.getSession(state.activeSessionId);
                        state.sessionDocumentRevision = sessionData.document_revision ?? 0;
                    } catch {
                        /* ignore */
                    }
                }
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

        if (els.workspaceBadge) {
            els.workspaceBadge.hidden = false;
            els.workspaceBadge.textContent =
                s.workspace_ready === false
                    ? "Opening-season workspace loading"
                    : "Opening-season workspace ready";
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

        state.agentMode = s.agent_extension_enabled === true || s.chat_backend === "bedrock_agent";

        if (s.ready || state.agentMode) {
            state.engineReady = true;
            els.statusDot.dataset.state = "ready";
            if (state.agentMode) {
                els.statusText.textContent = "Opening-season workspace ready";
            } else if (state.awsMode) {
                els.statusText.textContent = "Opening-season workspace ready";
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
    state.sessionDocumentRevision = data.document_revision ?? 0;
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
    if (state.kbOperationInProgress) return;
    if (
        !confirm(
            "Delete this conversation and its uploaded documents?\nThis action cannot be undone."
        )
    ) {
        return;
    }
    const id = state.activeSessionId;
    state.kbSyncInProgress = false;
    beginKbUpdate("Deleting conversation...");
    try {
        const result = await API.deleteSession(id, { deleteDocuments: true });
        state.sessions = state.sessions.filter(s => s.id !== id);
        await loadSessions();
        if (state.sessions.length > 0) {
            const nextId =
                state.sessions.find(s => s.id !== id)?.id || state.sessions[0].id;
            await selectSession(nextId);
        } else {
            state.activeSessionId = null;
            state.messages = [];
            els.conversationTitle.textContent = "New conversation";
            els.conversationMeta.textContent = "";
            els.renameBtn.disabled = true;
            renderSessions();
            renderMessages();
            await refreshKbDocuments();
            await newSession({ select: true });
        }
        toast(result.message || "Conversation deleted");
        if (state.awsMode && result.ingestion_job_id) {
            pollIngestion(result.ingestion_job_id);
        }
    } catch (err) {
        toast(sanitizeUserError(err.message) || "Could not delete conversation", { error: true });
    } finally {
        endKbUpdate();
    }
}

async function clearActiveDocuments() {
    if (!state.activeSessionId) {
        toast("Choose a conversation first", { error: true });
        return;
    }
    if (state.kbOperationInProgress || state.kbSyncInProgress) return;
    if (
        !confirm(
            "Clear all uploaded documents from this conversation?\nThis action cannot be undone."
        )
    ) {
        return;
    }
    beginKbUpdate("Updating the ScoutMatch knowledge base...");
    try {
        const result = await API.clearSessionDocuments(state.activeSessionId);
        toast("Conversation documents cleared");
        if (state.awsMode && result.ingestion_job_id) {
            endKbUpdate();
            pollIngestion(result.ingestion_job_id);
        } else {
            endKbUpdate();
            await refreshKbDocuments();
        }
    } catch (err) {
        endKbUpdate();
        toast(sanitizeUserError(err.message) || "Could not clear documents", { error: true });
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
    const hasMessages = state.messages.length > 0;
    els.messages.classList.toggle("messages--has-chat", hasMessages);
    els.messages.classList.toggle("messages--landing", !hasMessages);
    els.messages.innerHTML = "";
    if (!hasMessages) {
        if (els.homeHero) {
            els.messages.appendChild(els.homeHero);
        } else if (els.emptyState) {
            els.messages.appendChild(els.emptyState);
        }
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

function isCoachBriefMessage(content) {
    return /^\s*coach\s+brief\s*:/i.test(content || "");
}

function formatCoachBriefLabel(content) {
    return String(content || "").replace(/^\s*coach\s+brief\s*:\s*/i, "").trim();
}

function renderToolChips(tools) {
    const wrap = document.createElement("div");
    wrap.className = "agent-tools";
    for (const tool of tools || []) {
        const chip = document.createElement("span");
        chip.className = "agent-tools__chip";
        chip.textContent = `Tool executed: ${tool}`;
        wrap.appendChild(chip);
    }
    return wrap;
}

function renderConfirmationCard(card) {
    if (!card || card.state !== "pending") return null;
    const wrap = document.createElement("div");
    wrap.className = "confirm-card";
    const title = document.createElement("div");
    title.className = "confirm-card__title";
    title.textContent = "Action requires confirmation";
    wrap.appendChild(title);

    const params = card.parameters || {};
    const rows = [];
    if (params.candidate_name) rows.push(["Candidate", params.candidate_name]);
    if (params.target_role) rows.push(["Target role", params.target_role]);
    if (params.salary_eur) rows.push(["Salary", `${Number(params.salary_eur).toLocaleString()} EUR`]);
    if (params.formation) rows.push(["Formation", params.formation]);
    if (card.function === "FinalizeCurrentLineup") rows.push(["Players", "11"]);
    rows.push(["Action", card.action_label || card.title || "Confirm write action"]);

    const body = document.createElement("div");
    body.className = "confirm-card__body";
    for (const [label, value] of rows) {
        const row = document.createElement("div");
        row.className = "confirm-card__row";
        row.innerHTML = `<span class="confirm-card__label">${escapeHtml(label)}</span><span class="confirm-card__value">${escapeHtml(String(value))}</span>`;
        body.appendChild(row);
    }
    wrap.appendChild(body);

    const actions = document.createElement("div");
    actions.className = "confirm-card__actions";
    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "confirm-card__btn confirm-card__btn--confirm";
    confirmBtn.textContent = "Confirm";
    confirmBtn.addEventListener("click", () => sendMessage("Confirm"));
    const denyBtn = document.createElement("button");
    denyBtn.type = "button";
    denyBtn.className = "confirm-card__btn confirm-card__btn--deny";
    denyBtn.textContent = "Deny";
    denyBtn.addEventListener("click", () => sendMessage("Deny"));
    actions.append(confirmBtn, denyBtn);
    wrap.appendChild(actions);
    return wrap;
}

function renderLineupBoard(route) {
    if (!route || !route.startsWith("/")) return null;
    const wrap = document.createElement("div");
    wrap.className = "lineup-board-card";
    const badge = document.createElement("div");
    badge.className = "lineup-board-card__badge";
    badge.textContent = "PROPOSED LINEUP — PENDING HEAD COACH REVIEW";
    const img = document.createElement("img");
    img.className = "lineup-board-card__image";
    img.src = route;
    img.alt = "Current proposed lineup board";
    img.loading = "lazy";
    wrap.append(badge, img);
    return wrap;
}

function renderAgentExtras(msg) {
    const meta = msg.agent_metadata;
    if (!meta || typeof meta !== "object") return null;
    const frag = document.createDocumentFragment();
    if (Array.isArray(meta.tools_executed) && meta.tools_executed.length) {
        frag.appendChild(renderToolChips(meta.tools_executed));
    }
    const card = renderConfirmationCard(meta.confirmation_card);
    if (card) frag.appendChild(card);
    const board = renderLineupBoard(meta.lineup_image_route);
    if (board) frag.appendChild(board);
    if (meta.remaining_budget_eur != null) {
        const budget = document.createElement("div");
        budget.className = "agent-budget";
        budget.textContent = `Remaining budget: ${Number(meta.remaining_budget_eur).toLocaleString()} EUR`;
        frag.appendChild(budget);
    }
    return frag.childNodes.length ? frag : null;
}

function renderMessage(msg) {
    const wrap = document.createElement("div");
    wrap.className = `message message--${msg.role}`;
    if (msg.role === "assistant" && (msg.refused || isRefusalMessage(msg.content))) {
        wrap.classList.add("message--refused");
    }

    const avatar = document.createElement("div");
    avatar.className = "message__avatar";
    avatar.textContent = msg.role === "user" ? "A" : "S";

    const body = document.createElement("div");
    body.className = "message__body";

    const role = document.createElement("div");
    role.className = "message__role";
    if (msg.role === "user") {
        role.textContent = isCoachBriefMessage(msg.content)
            ? "Coach brief"
            : "Professional Analyst";
    } else {
        role.textContent = "ScoutMatch AI";
    }

    const content = document.createElement("div");
    content.className = "message__content";
    if (msg.role === "user" && isCoachBriefMessage(msg.content)) {
        wrap.classList.add("message--coach-brief");
        content.innerHTML = `<span class="coach-brief__label">Coach brief</span>${escapeHtml(formatCoachBriefLabel(msg.content))}`;
    } else {
        content.textContent = msg.content;
    }

    body.appendChild(role);
    body.appendChild(content);

    const isRefused =
        msg.role === "assistant" &&
        (msg.refused || isRefusalMessage(msg.content));
    if (
        msg.role === "assistant" &&
        !isRefused &&
        msg.document_revision_at_answer != null &&
        state.sessionDocumentRevision > msg.document_revision_at_answer
    ) {
        const stale = document.createElement("div");
        stale.className = "message__stale";
        stale.textContent = /[\u0590-\u05FF]/.test(msg.content || "")
            ? "תשובה זו נוצרה לפני שינוי המסמכים המצורפים לשיחה."
            : "This answer was generated before the uploaded documents changed.";
        body.appendChild(stale);
    }

    if (
        msg.role === "assistant" &&
        !isRefused &&
        Array.isArray(msg.context) &&
        msg.context.length > 0
    ) {
        body.appendChild(renderContext(msg.context, msg.main_source));
    }

    if (msg.role === "assistant" && !isRefused) {
        const extras = renderAgentExtras(msg);
        if (extras) body.appendChild(extras);
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
        const assistant = {
            ...result.assistant_message,
            agent_metadata: result.agent_metadata || result.assistant_message?.agent_metadata,
        };
        state.messages.push(assistant);
        appendMessageEphemeral(assistant);

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
    if (state.kbOperationInProgress || state.kbSyncInProgress) return;
    const okExt = /\.(txt|md|html|pdf|doc|docx|csv|xls|xlsx)$/i.test(file.name);
    if (!okExt) {
        toast("Supported: TXT, MD, HTML, PDF, DOC, DOCX, CSV, XLS, XLSX", { error: true });
        return;
    }
    if (!state.activeSessionId) {
        await newSession({ select: true });
    }
    beginKbUpdate(`Uploading CV to Amazon S3... (${file.name})`);
    setUploadStatus(`Uploading CV to Amazon S3... (${file.name})`, "info");
    try {
        const result = await API.uploadDocument(state.activeSessionId, file);
        setUploadStatus(result.message || "Upload complete.", "success");
        toast("Document uploaded to S3");

        if (state.awsMode && result.ingestion_job_id) {
            endKbUpdate();
            pollIngestion(result.ingestion_job_id);
        } else if (!state.awsMode) {
            endKbUpdate();
            state.engineReady = false;
            updateComposerState();
            pollEngineStatus();
        } else {
            endKbUpdate();
            await refreshKbDocuments();
        }
        setTimeout(() => setUploadStatus("", ""), 8000);
    } catch (err) {
        endKbUpdate();
        const friendly = sanitizeUserError(err.message);
        setUploadStatus(`Failed: ${friendly}`, "error");
        toast(friendly || "Upload failed", { error: true });
        if (err.partialIndexed) refreshKbDocuments();
    } finally {
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
    await loadOpeningSeasonWorkspace();
    pollEngineStatus();
    await loadSessions();
    renderMessages();
})();
