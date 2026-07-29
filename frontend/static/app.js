(() => {
  "use strict";

  const messagesEl = document.getElementById("messages");
  const emptyStateEl = document.getElementById("emptyState");
  const scrollBottomBtn = document.getElementById("scrollBottomBtn");
  const conversationListEl = document.getElementById("conversationList");
  const chatTitleEl = document.getElementById("chatTitle");
  const chatForm = document.getElementById("chatForm");
  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const newChatBtn = document.getElementById("newChatBtn");
  const menuBtn = document.getElementById("menuBtn");
  const sidebar = document.getElementById("sidebar");
  const sidebarBackdrop = document.getElementById("sidebarBackdrop");
  const themeToggle = document.getElementById("themeToggle");
  const themeIcon = document.getElementById("themeIcon");

  const SUN_ICON = '<path d="M12 4V2M12 22v-2M4.93 4.93 3.51 3.51M20.49 20.49l-1.42-1.42M4 12H2M22 12h-2M4.93 19.07l-1.42 1.42M20.49 3.51l-1.42 1.42M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
  const MOON_ICON = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>';
  const SEND_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const STOP_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="3"/></svg>';
  const COPY_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="12" height="12" rx="2" stroke="currentColor" stroke-width="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10" stroke="currentColor" stroke-width="2"/></svg>';
  const CHECK_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M20 6 9 17l-5-5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const EDIT_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const NEAR_BOTTOM_PX = 96;

  let currentConversationId = null;
  let activeAbortController = null;
  let autoFollow = true;
  const rawContentByElement = new WeakMap();
  const pendingRenders = new Map();

  // ---------------- Markdown rendering ----------------

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Code block placeholders use \x01 (a control character) as a delimiter
  // instead of plain spaces. A code block that forms its own paragraph
  // (blank line before/after -- the normal case) gets run through
  // block.trim() by the paragraph-splitting step below; a space-delimited
  // placeholder would have its delimiters silently eaten by that trim(),
  // permanently breaking the restore regex further down. \x01 survives
  // .trim() and escapeHtml() untouched.
  const CB_OPEN = "\x01CB";
  const CB_CLOSE = "\x01";

  function renderMarkdown(raw) {
    const codeBlocks = [];
    let text = raw.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      const idx = codeBlocks.length;
      codeBlocks.push({ lang, code: code.replace(/\n$/, "") });
      return `${CB_OPEN}${idx}${CB_CLOSE}`;
    });

    text = escapeHtml(text);

    const inlineCodes = [];
    text = text.replace(/`([^`\n]+)`/g, (_, code) => {
      const idx = inlineCodes.length;
      inlineCodes.push(code);
      return `IC${idx}`;
    });

    // tables
    text = text.replace(
      /^\|(.+)\|[ \t]*\n\|[ \t:|-]+\|[ \t]*\n((?:\|.*\|[ \t]*\n?)*)/gm,
      (match, header, body) => {
        const headers = header.split("|").map((c) => c.trim()).filter((c) => c.length);
        const rows = body
          .trim()
          .split("\n")
          .filter((r) => r.trim())
          .map((row) => row.split("|").map((c) => c.trim()).filter((c, i, arr) => !(i === 0 && c === "") && !(i === arr.length - 1 && c === "")));
        let html = "<table><thead><tr>";
        headers.forEach((h) => (html += `<th>${h}</th>`));
        html += "</tr></thead><tbody>";
        rows.forEach((row) => {
          html += "<tr>";
          row.forEach((cell) => (html += `<td>${cell}</td>`));
          html += "</tr>";
        });
        html += "</tbody></table>\n";
        return html;
      }
    );

    // headers
    text = text
      .replace(/^### (.*)$/gm, "<h3>$1</h3>")
      .replace(/^## (.*)$/gm, "<h2>$1</h2>")
      .replace(/^# (.*)$/gm, "<h1>$1</h1>");

    // bold then italic
    text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    text = text.replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>");

    // links
    text = text.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );

    // unordered lists
    text = text.replace(/(^|\n)((?:[*-] .*(?:\n|$))+)/g, (m, lead, block) => {
      const items = block
        .trim()
        .split("\n")
        .map((l) => `<li>${l.replace(/^[*-]\s+/, "")}</li>`)
        .join("");
      return `${lead}<ul>${items}</ul>\n`;
    });

    // ordered lists
    text = text.replace(/(^|\n)((?:\d+\. .*(?:\n|$))+)/g, (m, lead, block) => {
      const items = block
        .trim()
        .split("\n")
        .map((l) => `<li>${l.replace(/^\d+\.\s+/, "")}</li>`)
        .join("");
      return `${lead}<ol>${items}</ol>\n`;
    });

    // paragraphs
    text = text
      .split(/\n{2,}/)
      .map((block) => {
        const trimmed = block.trim();
        if (!trimmed) return "";
        if (/^<(h1|h2|h3|ul|ol|table)/.test(trimmed)) return trimmed;
        if (/^\x01CB\d+\x01$/.test(trimmed)) return trimmed;
        return `<p>${trimmed.replace(/\n/g, "<br>")}</p>`;
      })
      .join("\n");

    text = text.replace(/IC(\d+)/g, (_, i) => `<code>${inlineCodes[+i]}</code>`);
    text = text.replace(/\x01CB(\d+)\x01/g, (_, i) => {
      const block = codeBlocks[+i];
      const langClass = block.lang ? ` class="language-${escapeHtml(block.lang)}"` : "";
      return `<pre><code${langClass}>${escapeHtml(block.code)}</code></pre>`;
    });

    return text;
  }

  // ---------------- Clipboard ----------------

  function copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      const original = btn.innerHTML;
      btn.innerHTML = CHECK_ICON;
      btn.classList.add("copied");
      setTimeout(() => {
        btn.innerHTML = original;
        btn.classList.remove("copied");
      }, 1500);
    });
  }

  function attachCodeCopyButtons(body) {
    body.querySelectorAll("pre").forEach((pre) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "code-copy-btn";
      btn.innerHTML = `${COPY_ICON}<span>Copy</span>`;
      btn.addEventListener("click", () => {
        const code = pre.querySelector("code");
        copyToClipboard(code ? code.textContent : pre.textContent, btn);
      });
      pre.appendChild(btn);
    });
  }

  // ---------------- Scrolling ----------------

  function isNearBottom() {
    return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < NEAR_BOTTOM_PX;
  }

  function updateScrollBottomVisibility() {
    scrollBottomBtn.hidden = autoFollow;
  }

  function scrollToBottomImmediate() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
    updateScrollBottomVisibility();
  }

  function maybeAutoScroll() {
    if (autoFollow) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    updateScrollBottomVisibility();
  }

  messagesEl.addEventListener("scroll", () => {
    autoFollow = isNearBottom();
    updateScrollBottomVisibility();
  });

  scrollBottomBtn.addEventListener("click", () => {
    autoFollow = true;
    scrollToBottomImmediate();
  });

  // ---------------- Rendering ----------------

  function hideEmptyState() {
    if (emptyStateEl) emptyStateEl.style.display = "none";
  }

  function clearMessages() {
    messagesEl.innerHTML = "";
  }

  function showEmptyState() {
    clearMessages();
    messagesEl.appendChild(emptyStateEl);
    emptyStateEl.style.display = "";
  }

  function setMessageBodyContent(row, role, content) {
    const body = row.querySelector(".message-body");
    body.innerHTML =
      role === "assistant"
        ? renderMarkdown(content)
        : `<p>${escapeHtml(content).replace(/\n/g, "<br>")}</p>`;
    if (role === "assistant") attachCodeCopyButtons(body);
    rawContentByElement.set(row, content);
  }

  function attachMessageActions(row, role) {
    const actions = row.querySelector(".message-actions");
    actions.innerHTML = "";

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "message-action-btn";
    copyBtn.title = "Copy message";
    copyBtn.setAttribute("aria-label", "Copy message");
    copyBtn.innerHTML = COPY_ICON;
    copyBtn.addEventListener("click", () => copyToClipboard(rawContentByElement.get(row) || "", copyBtn));
    actions.appendChild(copyBtn);

    if (role === "user") {
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "message-action-btn";
      editBtn.title = "Edit message";
      editBtn.setAttribute("aria-label", "Edit message");
      editBtn.innerHTML = EDIT_ICON;
      editBtn.addEventListener("click", () => {
        if (activeAbortController) return;
        enterEditMode(row);
      });
      actions.appendChild(editBtn);
    }
  }

  function appendMessage(role, content, { id } = {}) {
    hideEmptyState();
    const row = document.createElement("div");
    row.className = `message-row ${role}`;
    if (id !== undefined && id !== null) row.dataset.messageId = id;

    const inner = document.createElement("div");
    inner.className = "message-inner";

    const avatar = document.createElement("div");
    avatar.className = `avatar ${role}`;
    avatar.textContent = role === "user" ? "U" : "AI";

    const col = document.createElement("div");
    col.className = "message-content-col";
    col.innerHTML = '<div class="message-body"></div><div class="message-actions"></div>';

    inner.appendChild(avatar);
    inner.appendChild(col);
    row.appendChild(inner);
    messagesEl.appendChild(row);

    setMessageBodyContent(row, role, content);
    attachMessageActions(row, role);

    if (role === "user") {
      autoFollow = true;
      scrollToBottomImmediate();
    } else {
      maybeAutoScroll();
    }
    return row;
  }

  function scheduleStreamingRender(row, text, isError) {
    pendingRenders.set(row, { text, isError });
    if (row.dataset.renderScheduled) return;
    row.dataset.renderScheduled = "1";
    requestAnimationFrame(() => {
      const pending = pendingRenders.get(row);
      pendingRenders.delete(row);
      delete row.dataset.renderScheduled;
      if (!pending) return;
      const body = row.querySelector(".message-body");
      body.innerHTML = pending.isError
        ? `<p class="error-text">${escapeHtml(pending.text)}</p>`
        : renderMarkdown(pending.text);
      if (!pending.isError) attachCodeCopyButtons(body);
      maybeAutoScroll();
    });
  }

  function finalizeStreamingMessage(row, text) {
    setMessageBodyContent(row, "assistant", text);
    attachMessageActions(row, "assistant");
    maybeAutoScroll();
  }

  function appendTypingIndicator() {
    hideEmptyState();
    const row = document.createElement("div");
    row.className = "message-row assistant";
    row.id = "typingRow";

    row.innerHTML = `
      <div class="message-inner">
        <div class="avatar assistant">AI</div>
        <div class="message-body">
          <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>
      </div>
    `;
    messagesEl.appendChild(row);
    maybeAutoScroll();
  }

  function removeTypingIndicator() {
    const row = document.getElementById("typingRow");
    if (row) row.remove();
  }

  function removeMessagesAfter(row) {
    let next = row.nextElementSibling;
    while (next) {
      const toRemove = next;
      next = next.nextElementSibling;
      toRemove.remove();
    }
  }

  // ---------------- Edit-in-place ----------------

  function enterEditMode(row) {
    if (row.classList.contains("editing")) return; // don't clobber an in-progress edit
    const rawText = rawContentByElement.get(row) || "";
    row.classList.add("editing");
    const body = row.querySelector(".message-body");
    const originalHTML = body.innerHTML;
    body.innerHTML = "";

    const textarea = document.createElement("textarea");
    textarea.className = "edit-textarea";
    textarea.value = rawText;
    body.appendChild(textarea);

    const actionsRow = document.createElement("div");
    actionsRow.className = "edit-actions";
    actionsRow.innerHTML =
      '<button type="button" class="edit-save-btn">Save &amp; Submit</button>' +
      '<button type="button" class="edit-cancel-btn">Cancel</button>';
    body.appendChild(actionsRow);

    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    const cancel = () => {
      row.classList.remove("editing");
      body.innerHTML = originalHTML;
    };

    const submit = () => {
      const newText = textarea.value.trim();
      if (!newText) return;
      const messageId = Number(row.dataset.messageId);
      row.classList.remove("editing");
      removeMessagesAfter(row);
      streamAssistantReply(newText, { editMessageId: messageId, editingRow: row });
    };

    actionsRow.querySelector(".edit-cancel-btn").addEventListener("click", cancel);
    actionsRow.querySelector(".edit-save-btn").addEventListener("click", submit);
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      } else if (e.key === "Escape") {
        cancel();
      }
    });
  }

  // ---------------- Conversations ----------------

  async function fetchConversations() {
    const res = await fetch("/api/conversations");
    return res.json();
  }

  async function loadConversation(id) {
    const res = await fetch(`/api/conversations/${id}`);
    if (!res.ok) return;
    const conv = await res.json();
    currentConversationId = conv.id;
    localStorage.setItem("lastConversationId", conv.id);
    chatTitleEl.textContent = conv.title || "New chat";
    clearMessages();
    autoFollow = true;
    if (!conv.messages.length) {
      showEmptyState();
    } else {
      conv.messages.forEach((m) => appendMessage(m.role, m.content, { id: m.id }));
    }
    scrollToBottomImmediate();
    closeSidebarOnMobile();
    highlightActiveConversation();
    messageInput.focus();
  }

  function startNewChat() {
    currentConversationId = null;
    localStorage.removeItem("lastConversationId");
    chatTitleEl.textContent = "New chat";
    autoFollow = true;
    showEmptyState();
    updateScrollBottomVisibility();
    highlightActiveConversation();
    closeSidebarOnMobile();
    messageInput.focus();
  }

  function highlightActiveConversation() {
    document.querySelectorAll(".conversation-item").forEach((el) => {
      el.classList.toggle("active", el.dataset.id === currentConversationId);
    });
  }

  async function refreshSidebar() {
    const conversations = await fetchConversations();
    conversationListEl.innerHTML = "";
    conversations.forEach((conv) => {
      const item = document.createElement("div");
      item.className = "conversation-item";
      item.dataset.id = conv.id;
      item.innerHTML = `
        <span class="title">${escapeHtml(conv.title || "New chat")}</span>
        <button class="rename-btn" aria-label="Rename conversation" title="Rename">${EDIT_ICON}</button>
        <button class="delete-btn" aria-label="Delete conversation" title="Delete">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      `;
      item.addEventListener("click", () => loadConversation(conv.id));
      item.querySelector(".delete-btn").addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("Delete this chat?")) return;
        await fetch(`/api/conversations/${conv.id}`, { method: "DELETE" });
        if (currentConversationId === conv.id) startNewChat();
        refreshSidebar();
      });
      item.querySelector(".rename-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        startRenaming(item, conv);
      });
      conversationListEl.appendChild(item);
    });
    highlightActiveConversation();
  }

  function startRenaming(item, conv) {
    const titleSpan = item.querySelector(".title");
    const currentTitle = conv.title || "New chat";
    const input = document.createElement("input");
    input.className = "rename-input";
    input.value = currentTitle;
    titleSpan.replaceWith(input);
    input.focus();
    input.select();

    let settled = false;
    const restore = () => {
      if (settled) return;
      settled = true;
      input.replaceWith(titleSpan);
    };
    const save = async () => {
      if (settled) return;
      settled = true;
      const newTitle = input.value.trim();
      if (!newTitle || newTitle === currentTitle) {
        input.replaceWith(titleSpan);
        return;
      }
      const res = await fetch(`/api/conversations/${conv.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle }),
      });
      if (res.ok) {
        const updated = await res.json();
        titleSpan.textContent = updated.title;
        if (conv.id === currentConversationId) chatTitleEl.textContent = updated.title;
      }
      input.replaceWith(titleSpan);
    };

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        save();
      } else if (e.key === "Escape") {
        restore();
      }
    });
    input.addEventListener("blur", save);
    input.addEventListener("click", (e) => e.stopPropagation());
  }

  // ---------------- Streaming send / stop / regenerate ----------------

  function setStreamingUI(isStreaming) {
    messageInput.disabled = isStreaming;
    if (isStreaming) {
      sendBtn.disabled = false;
      sendBtn.innerHTML = STOP_ICON;
      sendBtn.setAttribute("aria-label", "Stop generating");
    } else {
      sendBtn.innerHTML = SEND_ICON;
      sendBtn.setAttribute("aria-label", "Send message");
      updateSendButtonState();
    }
  }

  async function streamAssistantReply(text, opts = {}) {
    const { editMessageId, editingRow } = opts;

    let userRow;
    if (editingRow) {
      userRow = editingRow;
      setMessageBodyContent(userRow, "user", text);
      autoFollow = true;
      scrollToBottomImmediate();
    } else {
      userRow = appendMessage("user", text);
    }

    appendTypingIndicator();
    const controller = new AbortController();
    activeAbortController = controller;
    setStreamingUI(true);

    let assistantRow = null;
    let assembled = "";

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: currentConversationId,
          message: text,
          edit_message_id: editMessageId ?? null,
        }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || res.statusText || "Request failed");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);

          if (event.type === "start") {
            currentConversationId = event.conversation_id;
            localStorage.setItem("lastConversationId", currentConversationId);
            userRow.dataset.messageId = event.message_id;
          } else if (event.type === "delta") {
            if (!assistantRow) {
              removeTypingIndicator();
              assistantRow = appendMessage("assistant", "");
            }
            assembled += event.content;
            scheduleStreamingRender(assistantRow, assembled, false);
          } else if (event.type === "error") {
            if (!assistantRow) {
              removeTypingIndicator();
              assistantRow = appendMessage("assistant", "");
            }
            assembled = event.content;
            scheduleStreamingRender(assistantRow, assembled, true);
          }
        }
      }
    } catch (err) {
      removeTypingIndicator();
      if (err.name !== "AbortError") {
        if (!assistantRow) assistantRow = appendMessage("assistant", "");
        assembled = `Sorry, something went wrong: ${err.message}`;
        scheduleStreamingRender(assistantRow, assembled, true);
      }
    } finally {
      activeAbortController = null;
      setStreamingUI(false);
      if (assistantRow) {
        if (assembled) {
          finalizeStreamingMessage(assistantRow, assembled);
        } else {
          assistantRow.remove();
        }
      }
      await refreshSidebar();
      const activeItem = conversationListEl.querySelector(`[data-id="${currentConversationId}"]`);
      if (activeItem) chatTitleEl.textContent = activeItem.querySelector(".title").textContent;
      messageInput.focus();
    }
  }

  function updateSendButtonState() {
    sendBtn.disabled = messageInput.value.trim().length === 0;
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (activeAbortController) {
      activeAbortController.abort();
      return;
    }
    const text = messageInput.value.trim();
    if (!text) return;
    messageInput.value = "";
    messageInput.style.height = "auto";
    updateSendButtonState();
    streamAssistantReply(text);
  });

  messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 200)}px`;
    updateSendButtonState();
  });

  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  document.querySelectorAll(".suggestion-card").forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.dataset.prompt;
      messageInput.value = prompt;
      updateSendButtonState();
      chatForm.requestSubmit();
    });
  });

  newChatBtn.addEventListener("click", startNewChat);

  // ---------------- Mobile sidebar ----------------

  function openSidebarOnMobile() {
    sidebar.classList.add("open");
    sidebarBackdrop.classList.add("visible");
  }

  function closeSidebarOnMobile() {
    sidebar.classList.remove("open");
    sidebarBackdrop.classList.remove("visible");
  }

  menuBtn.addEventListener("click", () => {
    sidebar.classList.contains("open") ? closeSidebarOnMobile() : openSidebarOnMobile();
  });
  sidebarBackdrop.addEventListener("click", closeSidebarOnMobile);

  // ---------------- Theme ----------------

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeIcon.innerHTML = theme === "dark" ? SUN_ICON : MOON_ICON;
    localStorage.setItem("theme", theme);
  }

  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    applyTheme(current === "dark" ? "light" : "dark");
  });

  // ---------------- Init ----------------

  (async function init() {
    const storedTheme = localStorage.getItem("theme");
    if (storedTheme) applyTheme(storedTheme);
    else themeIcon.innerHTML = window.matchMedia("(prefers-color-scheme: dark)").matches ? SUN_ICON : MOON_ICON;

    await refreshSidebar();

    const lastId = localStorage.getItem("lastConversationId");
    if (lastId) {
      const conversations = await fetchConversations();
      if (conversations.some((c) => c.id === lastId)) {
        await loadConversation(lastId);
        return;
      }
    }
    startNewChat();
  })();
})();
