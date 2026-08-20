const state = {
  overview: null,
  files: [],
  messages: [],
  runs: [],
};

const els = {
  healthBadge: document.querySelector("#healthBadge"),
  notice: document.querySelector("#notice"),
  metrics: document.querySelector("#metrics"),
  subjectBars: document.querySelector("#subjectBars"),
  typeBars: document.querySelector("#typeBars"),
  recentFilesBody: document.querySelector("#recentFilesBody"),
  channelsBody: document.querySelector("#channelsBody"),
  subjectsBody: document.querySelector("#subjectsBody"),
  filesBody: document.querySelector("#filesBody"),
  messagesBody: document.querySelector("#messagesBody"),
  runsBody: document.querySelector("#runsBody"),
  runtimeList: document.querySelector("#runtimeList"),
  collectChannel: document.querySelector("#collectChannel"),
  stateChannel: document.querySelector("#stateChannel"),
  messageChannel: document.querySelector("#messageChannel"),
  fileStatus: document.querySelector("#fileStatus"),
  fileSubject: document.querySelector("#fileSubject"),
  fileContentType: document.querySelector("#fileContentType"),
  fileForm: document.querySelector("#fileForm"),
  messageForm: document.querySelector("#messageForm"),
  channelForm: document.querySelector("#channelForm"),
  channelStateForm: document.querySelector("#channelStateForm"),
  subjectForm: document.querySelector("#subjectForm"),
  collectForm: document.querySelector("#collectForm"),
  refreshBtn: document.querySelector("#refreshBtn"),
  seedBtn: document.querySelector("#seedBtn"),
  processBtn: document.querySelector("#processBtn"),
  reloadFilesBtn: document.querySelector("#reloadFilesBtn"),
  reloadMessagesBtn: document.querySelector("#reloadMessagesBtn"),
  reloadRunsBtn: document.querySelector("#reloadRunsBtn"),
  clearFileFormBtn: document.querySelector("#clearFileFormBtn"),
  clearMessageFormBtn: document.querySelector("#clearMessageFormBtn"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bytes(value) {
  if (!value) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function shortHash(value) {
  return value ? `${value.slice(0, 10)}...` : "-";
}

function showNotice(message, type = "info") {
  els.notice.textContent = message;
  els.notice.className = `notice ${type === "error" ? "error" : ""}`;
  window.clearTimeout(showNotice.timer);
  showNotice.timer = window.setTimeout(() => {
    els.notice.className = "notice hidden";
  }, 5000);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
}

function metric(label, value, tone) {
  return `
    <section class="metric ${tone}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </section>
  `;
}

function renderMetrics(summary) {
  els.metrics.innerHTML = [
    metric("القنوات المفعلة", summary.enabled_channels, "teal"),
    metric("المواد", summary.subjects, "blue"),
    metric("كل الملفات", summary.files, "violet"),
    metric("مصنف", summary.classified, "green"),
    metric("غير مصنف", summary.unclassified, "violet"),
    metric("مكرر", summary.duplicates, "amber"),
    metric("فشل", summary.failed, "red"),
    metric("غير مدعوم", summary.unsupported, "blue"),
  ].join("");
}

function renderBars(container, values) {
  const entries = Object.entries(values || {});
  if (!entries.length) {
    container.innerHTML = `<div class="muted">لا توجد بيانات حتى الآن</div>`;
    return;
  }
  const max = Math.max(...entries.map(([, count]) => count), 1);
  container.innerHTML = entries
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, count]) => {
      const width = Math.max(6, Math.round((count / max) * 100));
      return `
        <div class="bar-row">
          <div class="bar-label">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(count)}</strong>
          </div>
          <div class="bar-line"><div class="bar-fill" style="width:${width}%"></div></div>
        </div>
      `;
    })
    .join("");
}

function statusPill(status) {
  return `<span class="status ${escapeHtml(status)}">${escapeHtml(status || "-")}</span>`;
}

function emptyRow(columns, label = "لا توجد بيانات حتى الآن") {
  return `<tr><td colspan="${columns}">${label}</td></tr>`;
}

function fillSelect(select, options, placeholder = "") {
  if (!select) return;
  const previous = select.value;
  const placeholderOption = placeholder
    ? `<option value="">${escapeHtml(placeholder)}</option>`
    : "";
  select.innerHTML = `${placeholderOption}${options
    .map((option) => `<option value="${escapeHtml(option)}">${escapeHtml(option)}</option>`)
    .join("")}`;
  if ([...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  }
}

function renderOptions(data) {
  const options = data.options || {};
  fillSelect(els.fileStatus, options.file_statuses || [], "");
  fillSelect(els.fileSubject, options.subject_codes || [], "--");
  fillSelect(els.fileContentType, options.content_types || [], "--");
  fillSelect(
    els.collectChannel,
    (data.channels || []).filter((channel) => channel.enabled).map((channel) => channel.name),
    "Choose channel",
  );
  fillSelect(
    els.stateChannel,
    (data.channels || []).map((channel) => channel.name),
    "Choose channel",
  );
  fillSelect(
    els.messageChannel,
    (data.channels || []).map((channel) => channel.name),
    "Choose channel",
  );
}

function renderFiles(target, files, compact = false) {
  if (!files.length) {
    target.innerHTML = emptyRow(compact ? 6 : 9);
    return;
  }
  target.innerHTML = files
    .map((file) => `
      <tr>
        <td>${escapeHtml(file.id)}</td>
        <td class="wrap">
          <strong>${escapeHtml(file.filename)}</strong>
          <div class="muted">${escapeHtml(bytes(file.size_bytes))}</div>
        </td>
        <td>${statusPill(file.status)}</td>
        <td>${escapeHtml(file.subject_code || "-")}</td>
        <td>${escapeHtml(file.content_type || "-")}</td>
        <td>${escapeHtml(file.channel_name || "-")}</td>
        ${compact ? "" : `<td>${escapeHtml(shortHash(file.sha256))}</td>`}
        ${compact ? "" : `<td class="wrap">${escapeHtml(file.storage_path || "-")}</td>`}
        ${compact ? "" : `
          <td>
            <div class="action-cell">
              <button class="button secondary small" data-edit-file="${escapeHtml(file.id)}">Edit</button>
              <button class="button danger small" data-delete-file="${escapeHtml(file.id)}">Delete</button>
            </div>
          </td>
        `}
      </tr>
    `)
    .join("");
}

function renderChannels(channels) {
  els.channelsBody.innerHTML = channels.length
    ? channels
        .map((channel) => `
          <tr>
            <td>${escapeHtml(channel.name)}</td>
            <td>${escapeHtml(channel.username)}</td>
            <td>${channel.enabled ? "Yes" : "No"}</td>
            <td>${escapeHtml(channel.database?.last_message_id ?? "-")}</td>
            <td class="wrap">${escapeHtml(channel.database?.last_run_at ?? "-")}</td>
            <td>
              <div class="action-cell">
                <button class="button secondary small" data-edit-channel="${escapeHtml(channel.name)}">Edit</button>
                <button class="button secondary small" data-edit-channel-state="${escapeHtml(channel.name)}">State</button>
                <button class="button danger small" data-delete-channel="${escapeHtml(channel.name)}">Delete</button>
              </div>
            </td>
          </tr>
        `)
        .join("")
    : emptyRow(6);
}

function renderSubjects(subjects) {
  els.subjectsBody.innerHTML = subjects.length
    ? subjects
        .map((subject) => `
          <tr>
            <td>${escapeHtml(subject.code)}</td>
            <td>${escapeHtml(subject.name_ar)}</td>
            <td>${escapeHtml(subject.name_en)}</td>
            <td>
              <div class="action-cell">
                <button class="button secondary small" data-edit-subject="${escapeHtml(subject.code)}">Edit</button>
                <button class="button danger small" data-delete-subject="${escapeHtml(subject.code)}">Delete</button>
              </div>
            </td>
          </tr>
        `)
        .join("")
    : emptyRow(4);
}

function renderMessages(messages) {
  els.messagesBody.innerHTML = messages.length
    ? messages
        .map((message) => `
          <tr>
            <td>${escapeHtml(message.id)}</td>
            <td>${escapeHtml(message.telegram_message_id)}</td>
            <td>${escapeHtml(message.channel)}</td>
            <td class="wrap">
              <strong>${escapeHtml(message.file_name || "-")}</strong>
              <div class="muted">${escapeHtml(bytes(message.file_size))}</div>
            </td>
            <td class="wrap">${escapeHtml(message.caption || "-")}</td>
            <td class="wrap">${escapeHtml(message.message_date || "-")}</td>
            <td>
              <div class="action-cell">
                <button class="button secondary small" data-edit-message="${escapeHtml(message.id)}">Edit</button>
                ${
                  message.file_id
                    ? `<button class="button secondary small" data-edit-file="${escapeHtml(message.file_id)}">Edit File</button>`
                    : ""
                }
                <button class="button danger small" data-delete-message="${escapeHtml(message.id)}">Delete</button>
              </div>
            </td>
          </tr>
        `)
        .join("")
    : emptyRow(7);
}

function renderRuns(runs) {
  els.runsBody.innerHTML = runs.length
    ? runs
        .map((run) => `
          <tr>
            <td>${escapeHtml(run.id)}</td>
            <td>${escapeHtml(run.metadata?.command || "-")}</td>
            <td class="wrap">${escapeHtml(run.started_at || "-")}</td>
            <td class="wrap">${escapeHtml(run.finished_at || "-")}</td>
            <td>${escapeHtml(run.new_count)}</td>
            <td>${escapeHtml(run.classified_count)}</td>
            <td>${escapeHtml(run.failed_count)}</td>
            <td>
              <button class="button danger small" data-delete-run="${escapeHtml(run.id)}">Delete</button>
            </td>
          </tr>
        `)
        .join("")
    : emptyRow(8);
}

function renderRuntime(health) {
  const rows = [
    ["Database", health.database],
    ["AI Provider", health.ai_provider],
    ["OCR Language", health.ocr_language],
    ["Text Messages", health.collect_text_messages ? "Enabled" : "Disabled"],
  ];
  els.runtimeList.innerHTML = rows
    .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`)
    .join("");
}

function renderOverview(data) {
  state.overview = data;
  els.healthBadge.textContent = data.health.healthy ? "Ready" : "Error";
  els.healthBadge.className = `badge ${data.health.healthy ? "good" : "bad"}`;
  renderOptions(data);
  renderMetrics(data.summary);
  renderBars(els.subjectBars, data.report.by_subject);
  renderBars(els.typeBars, data.report.by_content_type);
  renderFiles(els.recentFilesBody, data.recent_files, true);
  renderFiles(els.filesBody, state.files.length ? state.files : data.recent_files);
  renderChannels(data.channels);
  renderSubjects(data.subjects);
  renderMessages(state.messages.length ? state.messages : data.recent_messages);
  renderRuns(state.runs.length ? state.runs : data.recent_runs);
  renderRuntime(data.health);
}

async function refreshAll() {
  const data = await api("/api/overview");
  state.files = data.recent_files;
  state.messages = data.recent_messages;
  state.runs = data.recent_runs;
  renderOverview(data);
}

async function reloadFiles() {
  const payload = await api("/api/files?limit=100");
  state.files = payload.files;
  renderFiles(els.filesBody, state.files);
}

async function reloadMessages() {
  const payload = await api("/api/messages?limit=100");
  state.messages = payload.messages;
  renderMessages(state.messages);
}

async function reloadRuns() {
  const payload = await api("/api/runs?limit=50");
  state.runs = payload.runs;
  renderRuns(state.runs);
}

function clearFileForm() {
  els.fileForm.reset();
  els.fileForm.elements.id.value = "";
}

function fillFileForm(file) {
  els.fileForm.elements.id.value = file.id;
  els.fileForm.elements.message_id.value = file.message_id || "";
  els.fileForm.elements.filename.value = file.filename || "";
  els.fileForm.elements.status.value = file.status || "";
  els.fileForm.elements.subject_code.value = file.subject_code || "";
  els.fileForm.elements.content_type.value = file.content_type || "";
  els.fileForm.elements.confidence.value = file.confidence ?? "";
  els.fileForm.elements.evidence.value = Array.isArray(file.evidence) ? file.evidence.join("\n") : "";
  els.fileForm.elements.classification_reason.value = file.classification_reason || "";
  els.fileForm.elements.error_message.value = file.error_message || "";
  els.fileForm.elements.content.value = "";
}

function clearMessageForm() {
  els.messageForm.reset();
  els.messageForm.elements.id.value = "";
}

function fillMessageForm(message) {
  els.messageForm.elements.id.value = message.id;
  els.messageForm.elements.channel.value = message.channel || "";
  els.messageForm.elements.telegram_message_id.value = message.telegram_message_id || "";
  els.messageForm.elements.media_type.value = message.media_type || "";
  els.messageForm.elements.file_name.value = message.file_name || "";
  els.messageForm.elements.file_size.value = message.file_size ?? "";
  els.messageForm.elements.caption.value = message.caption || "";
}

async function refreshAfterMutation({ files = false, messages = false, runs = false } = {}) {
  await refreshAll();
  if (files) await reloadFiles();
  if (messages) await reloadMessages();
  if (runs) await reloadRuns();
}

async function runButtonAction(button, callback) {
  setBusy(button, true);
  try {
    await callback();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#panel-${button.dataset.tab}`).classList.add("active");
  });
});

els.refreshBtn.addEventListener("click", (event) => {
  runButtonAction(event.currentTarget, async () => {
    await refreshAll();
    showNotice("تم التحديث");
  });
});

els.seedBtn.addEventListener("click", (event) => {
  runButtonAction(event.currentTarget, async () => {
    await api("/api/demo/seed", { method: "POST", body: "{}" });
    await refreshAll();
    showNotice("تم إنشاء بيانات التجربة");
  });
});

els.processBtn.addEventListener("click", (event) => {
  runButtonAction(event.currentTarget, async () => {
    await api("/api/actions/process", { method: "POST", body: "{}" });
    await refreshAfterMutation({ files: true, messages: true, runs: true });
    showNotice("تم تشغيل المعالجة");
  });
});

els.reloadFilesBtn.addEventListener("click", (event) => {
  runButtonAction(event.currentTarget, async () => {
    await reloadFiles();
    showNotice("تم تحديث الملفات");
  });
});

els.reloadMessagesBtn.addEventListener("click", (event) => {
  runButtonAction(event.currentTarget, async () => {
    await reloadMessages();
    showNotice("تم تحديث الرسائل");
  });
});

els.reloadRunsBtn.addEventListener("click", (event) => {
  runButtonAction(event.currentTarget, async () => {
    await reloadRuns();
    showNotice("تم تحديث التشغيلات");
  });
});

els.clearFileFormBtn.addEventListener("click", clearFileForm);
els.clearMessageFormBtn.addEventListener("click", clearMessageForm);

els.channelForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api("/api/channels", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        username: form.get("username"),
        enabled: form.get("enabled") === "on",
      }),
    });
    event.currentTarget.reset();
    event.currentTarget.elements.enabled.checked = true;
    await refreshAll();
    showNotice("تم حفظ القناة");
  } catch (error) {
    showNotice(error.message, "error");
  }
});

els.channelStateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api("/api/channels/state", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        last_message_id: Number(form.get("last_message_id") || 0),
        status: form.get("status") || "active",
      }),
    });
    await refreshAll();
    showNotice("تم حفظ حالة القناة");
  } catch (error) {
    showNotice(error.message, "error");
  }
});

els.subjectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api("/api/subjects", {
      method: "POST",
      body: JSON.stringify({
        code: form.get("code"),
        name_ar: form.get("name_ar"),
        name_en: form.get("name_en"),
      }),
    });
    event.currentTarget.reset();
    await refreshAll();
    showNotice("تم حفظ المادة");
  } catch (error) {
    showNotice(error.message, "error");
  }
});

els.fileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const id = form.get("id");
  const path = id ? `/api/files/${encodeURIComponent(id)}` : "/api/files";
  const method = id ? "PATCH" : "POST";

  try {
    await api(path, {
      method,
      body: JSON.stringify({
        message_id: Number(form.get("message_id") || 0),
        filename: form.get("filename"),
        status: form.get("status"),
        subject_code: form.get("subject_code") || "",
        content_type: form.get("content_type") || "",
        confidence: form.get("confidence") === "" ? "" : Number(form.get("confidence")),
        evidence: form.get("evidence") || "",
        classification_reason: form.get("classification_reason") || "",
        error_message: form.get("error_message") || "",
        content: form.get("content") || "",
      }),
    });
    await refreshAfterMutation({ files: true, messages: true });
    showNotice("تم حفظ الملف والتصنيف");
  } catch (error) {
    showNotice(error.message, "error");
  }
});

els.messageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const id = form.get("id");
  const path = id ? `/api/messages/${encodeURIComponent(id)}` : "/api/messages";
  const method = id ? "PATCH" : "POST";
  try {
    await api(path, {
      method,
      body: JSON.stringify({
        channel: form.get("channel"),
        telegram_message_id: Number(form.get("telegram_message_id") || 0),
        media_type: form.get("media_type") || "",
        file_name: form.get("file_name") || "",
        file_size: form.get("file_size") === "" ? "" : Number(form.get("file_size")),
        caption: form.get("caption") || "",
      }),
    });
    await refreshAfterMutation({ messages: true });
    showNotice("تم حفظ الرسالة");
  } catch (error) {
    showNotice(error.message, "error");
  }
});

els.collectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api("/api/actions/collect", {
      method: "POST",
      body: JSON.stringify({
        channel: form.get("channel"),
        limit: Number(form.get("limit") || 5),
      }),
    });
    await refreshAfterMutation({ files: true, messages: true, runs: true });
    showNotice("تم تشغيل الجمع");
  } catch (error) {
    showNotice(error.message, "error");
  }
});

document.addEventListener("click", async (event) => {
  const editChannel = event.target.closest("[data-edit-channel]");
  const editChannelState = event.target.closest("[data-edit-channel-state]");
  const deleteChannelButton = event.target.closest("[data-delete-channel]");
  const editSubject = event.target.closest("[data-edit-subject]");
  const deleteSubjectButton = event.target.closest("[data-delete-subject]");
  const editMessage = event.target.closest("[data-edit-message]");
  const editFile = event.target.closest("[data-edit-file]");
  const deleteFileButton = event.target.closest("[data-delete-file]");
  const deleteMessageButton = event.target.closest("[data-delete-message]");
  const deleteRunButton = event.target.closest("[data-delete-run]");

  if (editChannel) {
    const channel = (state.overview?.channels || []).find((item) => item.name === editChannel.dataset.editChannel);
    if (!channel) return;
    els.channelForm.name.value = channel.name;
    els.channelForm.username.value = channel.username;
    els.channelForm.enabled.checked = channel.enabled;
    showNotice("جاهز لتعديل القناة");
    return;
  }

  if (editChannelState) {
    const channel = (state.overview?.channels || []).find(
      (item) => item.name === editChannelState.dataset.editChannelState,
    );
    if (!channel) return;
    els.channelStateForm.name.value = channel.name;
    els.channelStateForm.last_message_id.value = channel.database?.last_message_id ?? 0;
    els.channelStateForm.status.value = channel.database?.status || "active";
    showNotice("جاهز لتعديل حالة القناة");
    return;
  }

  if (deleteChannelButton) {
    if (!window.confirm("Delete this channel from config?")) return;
    try {
      await api(`/api/channels/${encodeURIComponent(deleteChannelButton.dataset.deleteChannel)}`, {
        method: "DELETE",
      });
      await refreshAll();
      showNotice("تم حذف القناة من الإعدادات");
    } catch (error) {
      showNotice(error.message, "error");
    }
    return;
  }

  if (editSubject) {
    const subject = (state.overview?.subjects || []).find((item) => item.code === editSubject.dataset.editSubject);
    if (!subject) return;
    els.subjectForm.code.value = subject.code;
    els.subjectForm.name_ar.value = subject.name_ar;
    els.subjectForm.name_en.value = subject.name_en;
    showNotice("جاهز لتعديل المادة");
    return;
  }

  if (deleteSubjectButton) {
    if (!window.confirm("Delete this subject from config?")) return;
    try {
      await api(`/api/subjects/${encodeURIComponent(deleteSubjectButton.dataset.deleteSubject)}`, {
        method: "DELETE",
      });
      await refreshAll();
      showNotice("تم حذف المادة من الإعدادات");
    } catch (error) {
      showNotice(error.message, "error");
    }
    return;
  }

  if (editMessage) {
    let message = state.messages.find((item) => String(item.id) === String(editMessage.dataset.editMessage));
    if (!message) {
      await reloadMessages();
      message = state.messages.find((item) => String(item.id) === String(editMessage.dataset.editMessage));
    }
    if (!message) return;
    fillMessageForm(message);
    document.querySelector('[data-tab="messages"]').click();
    showNotice("جاهز لتعديل الرسالة");
    return;
  }

  if (editFile) {
    let file = state.files.find((item) => String(item.id) === String(editFile.dataset.editFile));
    if (!file) {
      await reloadFiles();
      file = state.files.find((item) => String(item.id) === String(editFile.dataset.editFile));
    }
    if (!file) return;
    fillFileForm(file);
    document.querySelector('[data-tab="files"]').click();
    showNotice("جاهز لتعديل الملف");
    return;
  }

  if (deleteFileButton) {
    if (!window.confirm("Delete this file record and stored file?")) return;
    try {
      await api(`/api/files/${encodeURIComponent(deleteFileButton.dataset.deleteFile)}`, {
        method: "DELETE",
      });
      clearFileForm();
      await refreshAfterMutation({ files: true, messages: true });
      showNotice("تم حذف الملف");
    } catch (error) {
      showNotice(error.message, "error");
    }
    return;
  }

  if (deleteMessageButton) {
    if (!window.confirm("Delete this message and its file, if any?")) return;
    try {
      await api(`/api/messages/${encodeURIComponent(deleteMessageButton.dataset.deleteMessage)}`, {
        method: "DELETE",
      });
      clearFileForm();
      await refreshAfterMutation({ files: true, messages: true });
      showNotice("تم حذف الرسالة");
    } catch (error) {
      showNotice(error.message, "error");
    }
    return;
  }

  if (deleteRunButton) {
    if (!window.confirm("Delete this processing run?")) return;
    try {
      await api(`/api/runs/${encodeURIComponent(deleteRunButton.dataset.deleteRun)}`, {
        method: "DELETE",
      });
      await refreshAfterMutation({ runs: true });
      showNotice("تم حذف التشغيل");
    } catch (error) {
      showNotice(error.message, "error");
    }
  }
});

refreshAll().catch((error) => {
  els.healthBadge.textContent = "Error";
  els.healthBadge.className = "badge bad";
  showNotice(error.message, "error");
});
