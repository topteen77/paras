const API = "/api/dashboard";

const state = {
  calls: [],
  selectedId: null,
  tasks: [],
};

const views = {
  logs: { title: "Voice Logs", subtitle: "Monitor outbound calls, recordings, and lead status" },
  recordings: { title: "Recordings", subtitle: "Listen to saved call recordings" },
  tasks: { title: "Calling Tasks", subtitle: "Scheduled and in-progress outbound campaigns" },
  campaign: { title: "New Campaign", subtitle: "Schedule calls individually or in bulk" },
  integrations: { title: "Integrations", subtitle: "API credits, connectivity, and stack switching" },
  configuration: { title: "Configuration", subtitle: "Models, phone numbers, callback URLs, and system settings" },
};

function $(id) {
  return document.getElementById(id);
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2800);
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "—";
  const s = Number(seconds);
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return mins ? `${mins}m ${secs}s` : `${secs}s`;
}

function leadBadge(temp) {
  const label = temp || "unclassified";
  return `<span class="badge ${label}">${label}</span>`;
}

function statusBadge(status) {
  const safe = (status || "unknown").toLowerCase().replace(/\s+/g, "-");
  return `<span class="badge status ${safe}">${status || "unknown"}</span>`;
}

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return response.json();
}

function recordingSrc(call) {
  if (call.recording_filename) {
    return `${API}/recordings/${encodeURIComponent(call.recording_filename)}`;
  }
  return call.recording_url || "";
}

function renderStats(stats) {
  const lead = stats.lead_counts || {};
  $("stats-row").innerHTML = `
    <div class="stat-card"><div class="label">Total calls</div><div class="value">${stats.total_calls || 0}</div></div>
    <div class="stat-card"><div class="label">Recordings</div><div class="value">${stats.with_recording || 0}</div></div>
    <div class="stat-card"><div class="label">Hot leads</div><div class="value">${lead.hot || 0}</div></div>
    <div class="stat-card"><div class="label">Warm leads</div><div class="value">${lead.warm || 0}</div></div>
    <div class="stat-card"><div class="label">Scheduled</div><div class="value">${stats.scheduled_tasks || 0}</div></div>
  `;
}

function renderCallsTable() {
  const tbody = $("calls-tbody");
  if (!state.calls.length) {
    tbody.innerHTML = `<tr><td colspan="8">No calls found.</td></tr>`;
    return;
  }

  tbody.innerHTML = state.calls
    .map((call) => {
      const selected = call.internal_id === state.selectedId ? "selected" : "";
      return `
        <tr class="${selected}" data-id="${call.internal_id}">
          <td>${formatDate(call.ended_at || call.started_at)}</td>
          <td>
            <div>${call.from_phone_number || "—"}</div>
            <div><strong>${call.to_phone_number || "—"}</strong></div>
            ${call.name ? `<div class="muted">${call.name}</div>` : ""}
          </td>
          <td>${call.direction || "outbound"}</td>
          <td>${statusBadge(call.telephony_status || call.status)}</td>
          <td>${leadBadge(call.lead_temperature)}</td>
          <td>
            <div>${call.hangup_cause || "—"}</div>
            <div class="muted">${call.hangup_source || ""}</div>
          </td>
          <td>${formatDuration(call.duration_seconds)}</td>
          <td>${call.cost ? `$${call.cost}` : "—"}</td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("tr[data-id]").forEach((row) => {
    row.addEventListener("click", () => selectCall(row.dataset.id));
  });
}

function renderTranscript(transcript = []) {
  if (!transcript.length) return "<p>No transcript available.</p>";
  return `<div class="transcript">${transcript
    .map((item) => {
      const role = item.role || "unknown";
      const text = item.text || item.content || "";
      return `<div class="msg ${role}"><div class="role">${role}</div>${escapeHtml(text)}</div>`;
    })
    .join("")}</div>`;
}

function renderQaPairs(qaPairs = []) {
  if (!qaPairs.length) return "";
  return `
    <div class="section-title">Q&amp;A</div>
    <div class="transcript">
      ${qaPairs
        .map(
          (qa) => `
          <div class="msg user"><div class="role">Student</div>${escapeHtml(qa.user_question || "(no question)")}</div>
          <div class="msg assistant"><div class="role">Agent</div>${escapeHtml(qa.agent_answer || "")}</div>
        `
        )
        .join("")}
    </div>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function selectCall(internalId) {
  state.selectedId = internalId;
  renderCallsTable();
  const panel = $("call-detail");
  panel.innerHTML = `<div class="detail-empty">Loading call details...</div>`;
  try {
    const call = await api(`/calls/${encodeURIComponent(internalId)}`);
    const audioSrc = recordingSrc(call);
    panel.innerHTML = `
      <div class="detail-header">
        <h2>${call.to_phone_number || "Unknown number"}</h2>
        <div class="detail-meta">${call.name || "No name"} · ${formatDate(call.ended_at || call.started_at)}</div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;">
          ${statusBadge(call.telephony_status || call.status)}
          ${leadBadge(call.lead_temperature)}
        </div>
      </div>

      ${call.conversation_flag ? `<p><strong>Lead classification:</strong> ${escapeHtml(call.conversation_flag)}</p>` : ""}
      ${call.executive_summary ? `<p><strong>Executive summary:</strong> ${escapeHtml(call.executive_summary)}</p>` : ""}
      ${call.conversation_summary ? `<p><strong>Conversation summary:</strong> ${escapeHtml(call.conversation_summary)}</p>` : ""}

      ${audioSrc ? `<audio class="audio-player" controls src="${audioSrc}"></audio>` : "<p>No recording available.</p>"}

      <div class="section-title">Transcript</div>
      ${renderTranscript(call.transcript)}

      ${renderQaPairs(call.qa_pairs)}
    `;
  } catch (error) {
    panel.innerHTML = `<div class="detail-empty">${escapeHtml(error.message)}</div>`;
  }
}

function renderRecordings() {
  const withRecording = state.calls.filter((call) => call.has_recording);
  const grid = $("recordings-grid");
  if (!withRecording.length) {
    grid.innerHTML = `<div class="recording-card"><h3>No recordings yet</h3><p>Completed calls with saved audio will appear here.</p></div>`;
    return;
  }

  grid.innerHTML = withRecording
    .map((call) => {
      const audioSrc = recordingSrc(call);
      return `
        <div class="recording-card">
          <h3>${call.to_phone_number}</h3>
          <p>${formatDate(call.ended_at || call.started_at)} · ${formatDuration(call.duration_seconds)}</p>
          <div style="margin-bottom:10px;">${leadBadge(call.lead_temperature)} ${statusBadge(call.telephony_status || call.status)}</div>
          ${audioSrc ? `<audio controls style="width:100%" src="${audioSrc}"></audio>` : ""}
          <button class="btn secondary" style="margin-top:10px" data-open="${call.internal_id}">View details</button>
        </div>
      `;
    })
    .join("");

  grid.querySelectorAll("[data-open]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchView("logs");
      selectCall(btn.dataset.open);
    });
  });
}

function renderTasks() {
  const tbody = $("tasks-tbody");
  if (!state.tasks.length) {
    tbody.innerHTML = `<tr><td colspan="6">No scheduled tasks found. Firestore may be unavailable locally.</td></tr>`;
    return;
  }

  tbody.innerHTML = state.tasks
    .map(
      (task) => `
      <tr>
        <td>${escapeHtml(task.name || "—")}</td>
        <td>${escapeHtml(task.to_phone_number || task.phone_number || "—")}</td>
        <td>${statusBadge(task.process_status)}</td>
        <td>${formatDate(task.scheduled_at)}</td>
        <td>${task.retry_count ?? 0}</td>
        <td>${escapeHtml(task.filename || "—")}</td>
      </tr>
    `
    )
    .join("");
}

async function loadCalls() {
  const params = new URLSearchParams({ limit: "100" });
  const status = $("status-filter").value;
  const lead = $("lead-filter").value;
  const search = $("search-input").value.trim();
  if (status) params.set("status", status);
  if (lead) params.set("lead", lead);
  if (search) params.set("search", search);

  const [{ calls }, stats] = await Promise.all([api(`/calls?${params}`), api("/stats")]);
  state.calls = calls;
  renderStats(stats);
  renderCallsTable();
  renderRecordings();
}

async function loadTasks() {
  const params = new URLSearchParams({ limit: "100" });
  const status = $("task-status-filter").value;
  if (status) params.set("status", status);
  const { tasks } = await api(`/tasks?${params}`);
  state.tasks = tasks;
  renderTasks();
}

function switchView(name) {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("active", section.id === `view-${name}`);
  });
  const meta = views[name];
  $("page-title").textContent = meta.title;
  $("page-subtitle").textContent = meta.subtitle;
}

function formatCredits(credits) {
  if (!credits) return "";
  const rows = [];
  if (credits.total != null) rows.push(["Total", formatCreditValue(credits.total, credits.unit)]);
  if (credits.used != null) rows.push(["Used", formatCreditValue(credits.used, credits.unit)]);
  if (credits.balance != null) rows.push(["Balance", formatCreditValue(credits.balance, credits.unit)]);

  const percent =
    credits.total && credits.used != null
      ? Math.min(100, Math.round((credits.used / credits.total) * 100))
      : null;

  return `
    <div class="credit-meter">
      <div class="credit-row"><strong>${escapeHtml(credits.label || "Credits")}</strong></div>
      ${rows
        .map(([label, value]) => `<div class="credit-row"><span>${label}</span><span>${value}</span></div>`)
        .join("")}
      ${percent != null ? `<div class="credit-bar"><span style="width:${percent}%"></span></div>` : ""}
      ${credits.note ? `<div class="credit-note">${escapeHtml(credits.note)}</div>` : ""}
    </div>
  `;
}

function formatCreditValue(value, unit) {
  const num = Number(value);
  const formatted = Number.isFinite(num) ? num.toLocaleString(undefined, { maximumFractionDigits: 4 }) : value;
  return unit ? `${formatted} ${unit}` : formatted;
}

function connectivityLabel(status) {
  return (status || "unknown").replaceAll("_", " ");
}

function renderIntegrations(data) {
  const active = data.active_stack || {};
  $("active-stack-summary").innerHTML = `
    <strong>${escapeHtml(active.stack_name || "Unknown")}</strong>
    · Telephony: <code>${escapeHtml(active.telephony || "-")}</code>
    · Voice AI: <code>${escapeHtml(active.voice_ai || "-")}</code>
    · Source: ${escapeHtml(active.source || "env")}
  `;

  $("stack-grid").innerHTML = (data.stacks || [])
    .map((stack) => {
      const tags = [
        `<span class="tag ${stack.status}">${stack.status}</span>`,
        stack.active ? `<span class="tag active">Active</span>` : "",
      ].join("");
      const warnings = [];
      if (stack.missing_credentials?.length) {
        warnings.push(`Missing: ${stack.missing_credentials.join(", ")}`);
      }
      if (stack.not_working?.length) {
        warnings.push(`Not working: ${stack.not_working.join(", ")}`);
      }
      const canSwitch = stack.status === "integrated";
      return `
        <div class="stack-card ${stack.active ? "active" : ""}">
          <h3>${escapeHtml(stack.name)}</h3>
          <div>${tags}</div>
          <p>${escapeHtml(stack.description || "")}</p>
          <p><code>${escapeHtml(stack.telephony)}</code> + <code>${escapeHtml(stack.voice_ai)}</code></p>
          ${warnings.length ? `<p class="credit-note">${escapeHtml(warnings.join(" · "))}</p>` : ""}
          <div class="stack-actions">
            ${
              canSwitch
                ? `<button class="btn ${stack.active ? "secondary" : "primary"}" data-stack="${stack.id}" ${stack.active ? "disabled" : ""}>
                    ${stack.active ? "Current stack" : "Switch to this stack"}
                  </button>`
                : `<button class="btn secondary" disabled>Coming soon</button>`
            }
          </div>
        </div>
      `;
    })
    .join("");

  $("stack-grid").querySelectorAll("[data-stack]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const result = await api("/stack", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stack_id: btn.dataset.stack }),
        });
        showToast(result.message || "Stack switched");
        await loadIntegrations();
      } catch (error) {
        showError(error);
      }
    });
  });

  $("provider-grid").innerHTML = (data.providers || [])
    .map((provider) => {
      return `
        <div class="provider-card">
          <div class="connectivity ${provider.connectivity}">${connectivityLabel(provider.connectivity)}</div>
          <h3>${escapeHtml(provider.name)} ${provider.active ? '<span class="tag active">In use</span>' : ""}</h3>
          <p>${escapeHtml(provider.message || provider.category)}</p>
          ${formatCredits(provider.credits)}
          ${
            provider.dashboard_url
              ? `<div class="provider-links"><a href="${provider.dashboard_url}" target="_blank" rel="noopener">Open provider dashboard</a></div>`
              : ""
          }
        </div>
      `;
    })
    .join("");
}

async function loadIntegrations() {
  const data = await api("/integrations");
  renderIntegrations(data);
}

function copyText(value) {
  navigator.clipboard.writeText(value).then(() => showToast("Copied to clipboard"));
}

function renderKvGrid(items) {
  return `<div class="kv-grid">${items
    .map(
      ([key, value]) => `
      <div class="kv-item">
        <div class="key">${escapeHtml(key)}</div>
        <div class="value">${value == null || value === "" ? "—" : escapeHtml(String(value))}</div>
      </div>`
    )
    .join("")}</div>`;
}

function renderUrlGroup(group) {
  if (!group) return "";
  const urls = group.urls || {};
  const rows = Object.entries(urls)
    .map(
      ([label, url]) => `
      <div class="url-row">
        <div class="url-label">${escapeHtml(label.replaceAll("_", " "))}</div>
        <div class="url-value">${escapeHtml(url)}</div>
        <button class="btn secondary copy-url-btn" type="button">Copy</button>
      </div>`
    )
    .join("");
  return `
    <div class="config-section">
      <h2>${escapeHtml(group.title || "URLs")}</h2>
      ${group.note ? `<p>${escapeHtml(group.note)}</p>` : ""}
      <div class="url-list">${rows}</div>
    </div>
  `;
}

function renderPhoneTable(numbers, provider) {
  if (!numbers?.length) {
    return `<p>No ${provider} numbers returned from API. Check credentials or configure <code>${provider.toUpperCase()}_PHONE_NUMBER</code> in .env.</p>`;
  }
  const headers =
    provider === "plivo"
      ? ["Number", "Alias", "Region", "Voice", "Application", "Outbound"]
      : ["Number", "Name", "Voice URL", "Outbound"];
  const rows = numbers
    .map((n) => {
      if (provider === "plivo") {
        return `
          <tr>
            <td><strong>${escapeHtml(n.number || "—")}</strong></td>
            <td>${escapeHtml(n.alias || "—")}</td>
            <td>${escapeHtml(n.region || "—")}</td>
            <td>${n.voice_enabled ? "Yes" : "No"}</td>
            <td>${escapeHtml(n.application || "—")}</td>
            <td>${n.configured_outbound ? '<span class="tag active">Active</span>' : "—"}</td>
          </tr>`;
      }
      return `
        <tr>
          <td><strong>${escapeHtml(n.number || "—")}</strong></td>
          <td>${escapeHtml(n.friendly_name || "—")}</td>
          <td class="url-value">${escapeHtml(n.voice_url || "—")}</td>
          <td>${n.configured_outbound ? '<span class="tag active">Active</span>' : "—"}</td>
        </tr>`;
    })
    .join("");
  return `
    <table class="phone-table">
      <thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderConfiguration(config) {
  const root = $("configuration-root");
  const callbacks = config.callbacks || {};
  const models = config.models || {};
  const phones = config.phone_numbers || {};
  const prompts = config.prompts || {};
  const sarvam = models.sarvam || {};
  const eleven = models.elevenlabs || {};

  const publicAlert = callbacks.public_url_ok
    ? `<div class="alert ok">Public URL is set: <code>${escapeHtml(callbacks.public_base_url)}</code></div>`
    : `<div class="alert warn">WEB_SERVER_URL is localhost — Plivo/Twilio cannot reach callbacks until ngrok is configured.</div>`;

  const modelItems = [];
  if (models.voice_ai_provider === "sarvam") {
    modelItems.push(
      ["LLM model", sarvam.chat_model],
      ["STT model", sarvam.stt_model],
      ["TTS model", sarvam.tts_model],
      ["TTS speaker", sarvam.tts_speaker],
      ["Language", sarvam.language_code],
      ["System prompt", sarvam.system_prompt_path],
      ["Prompt file exists", sarvam.system_prompt_exists ? "Yes" : "No"]
    );
  } else if (models.voice_ai_provider === "elevenlabs") {
    modelItems.push(
      ["Cold calling agent", eleven.cold_calling_agent_id || "Not set"],
      ["After-visit agent", eleven.after_visit_feedback_agent_id || "Not set"]
    );
  }
  modelItems.unshift(
    ["Telephony", models.telephony_provider],
    ["Voice AI", models.voice_ai_provider]
  );

  const usingPrompt = prompts.using === "user" ? "Your custom prompt" : "Default prompt";
  const promptSection =
    models.voice_ai_provider === "sarvam"
      ? `
    <div class="config-section" id="prompt-section">
      <h2>System prompts</h2>
      <p>
        <span class="tag ${prompts.using === "user" ? "active" : "integrated"}">Active: ${escapeHtml(usingPrompt)}</span>
        · User prompt overrides default for all new Sarvam calls.
      </p>
      <div class="prompt-panels">
        <div class="prompt-panel">
          <h3>${escapeHtml(prompts.default?.label || "Default prompt")}</h3>
          <div class="prompt-meta">
            ${escapeHtml(prompts.default?.path || "")} · ${prompts.default?.char_count || 0} chars
          </div>
          <textarea readonly id="default-prompt-text">${escapeHtml(prompts.default?.content || "")}</textarea>
        </div>
        <div class="prompt-panel">
          <h3>${escapeHtml(prompts.user?.label || "Your custom prompt")}</h3>
          <div class="prompt-meta">
            ${prompts.user?.has_override ? `${escapeHtml(prompts.user.path)} · modified ${escapeHtml(prompts.user.modified_at || "")}` : "Not saved yet — edit below and click Save"}
          </div>
          <textarea id="user-prompt-text" placeholder="Write your custom system prompt here. When saved, this fully replaces the default for outbound Sarvam calls.">${escapeHtml(prompts.user?.content || "")}</textarea>
          <div class="prompt-actions">
            <button class="btn primary" type="button" id="save-prompt-btn">Save custom prompt</button>
            <button class="btn secondary" type="button" id="reset-prompt-btn" ${prompts.user?.has_override ? "" : "disabled"}>Reset to default</button>
            <button class="btn secondary" type="button" id="copy-default-prompt-btn">Copy default into editor</button>
          </div>
        </div>
      </div>
    </div>`
      : "";

  root.innerHTML = `
    ${publicAlert}

    <div class="config-section">
      <h2>Active stack</h2>
      <p>${escapeHtml(config.active_stack?.stack_name || "")} · source: ${escapeHtml(config.active_stack?.source || "env")}</p>
      ${renderKvGrid([
        ["Stack ID", config.active_stack?.stack_id],
        ["Telephony provider", config.active_stack?.telephony],
        ["Voice AI provider", config.active_stack?.voice_ai],
      ])}
    </div>

    <div class="config-section">
      <h2>Models &amp; agents</h2>
      <p>AI models and agent IDs used for the active voice stack.</p>
      ${renderKvGrid(modelItems)}
    </div>

    ${promptSection}

    <div class="config-section">
      <h2>Phone numbers</h2>
      <p>Outbound caller ID from .env and numbers on your telephony account.</p>
      ${renderKvGrid([
        ["Active telephony", phones.active_telephony],
        ["Outbound number (.env)", phones.active_outbound_number || "Not set"],
        ["Outbound configured", phones.outbound_configured ? "Yes" : "No"],
        ["Number on account", phones.active_number_on_account == null ? "—" : phones.active_number_on_account ? "Yes" : "No"],
        ["Plivo .env", phones.configured_outbound?.plivo || "Not set"],
        ["Twilio .env", phones.configured_outbound?.twilio || "Not set"],
      ])}
      <div class="section-title">Plivo account numbers</div>
      ${renderPhoneTable(phones.plivo_account_numbers, "plivo")}
      <div class="section-title">Twilio account numbers</div>
      ${renderPhoneTable(phones.twilio_account_numbers, "twilio")}
    </div>

    ${renderUrlGroup(callbacks.inbound_plivo_console)}
    ${renderUrlGroup(callbacks.outbound_per_call)}
    ${renderUrlGroup(callbacks.example_outbound)}
    ${renderUrlGroup(callbacks.scheduler_and_reports)}

    <div class="config-section">
      <h2>Call tuning</h2>
      ${renderKvGrid([
        ["Max parallel calls", config.tuning?.max_parallel_requests_to_agent],
        ["Default call duration (s)", config.tuning?.default_call_duration_seconds],
        ["Max retry count", config.tuning?.max_call_retry_count],
        ["Status complete delay (s)", config.tuning?.status_complete_task_delay_seconds],
      ])}
    </div>

    <div class="config-section">
      <h2>Infrastructure &amp; webhooks</h2>
      ${renderKvGrid([
        ["WEB_SERVER_URL", config.infrastructure?.web_server_url],
        ["NGROK_URL", config.infrastructure?.ngrok_url],
        ["Recordings folder", config.infrastructure?.call_recordings_dir],
        ["GCP project", config.infrastructure?.project_id],
        ["GCP region", config.infrastructure?.region],
        ["Cloud Tasks queue", config.infrastructure?.queue_name],
        ["BigQuery dataset", config.infrastructure?.bigquery_dataset],
        ["Post-call webhook", config.webhooks?.post_call_webhook_url || "Not set"],
        ["Plivo auth ID", config.credentials?.plivo_auth_id],
        ["Twilio account SID", config.credentials?.twilio_account_sid],
      ])}
    </div>
  `;

  root.querySelectorAll(".copy-url-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const value = btn.parentElement?.querySelector(".url-value")?.textContent;
      if (value) copyText(value);
    });
  });

  const savePromptBtn = $("save-prompt-btn");
  const resetPromptBtn = $("reset-prompt-btn");
  const copyDefaultBtn = $("copy-default-prompt-btn");

  savePromptBtn?.addEventListener("click", async () => {
    const content = $("user-prompt-text")?.value || "";
    try {
      const result = await api("/prompts", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      showToast(result.message || "Prompt saved");
      await loadConfiguration();
    } catch (error) {
      showError(error);
    }
  });

  resetPromptBtn?.addEventListener("click", async () => {
    try {
      const result = await api("/prompts", { method: "DELETE" });
      showToast(result.message || "Reset to default");
      await loadConfiguration();
    } catch (error) {
      showError(error);
    }
  });

  copyDefaultBtn?.addEventListener("click", () => {
    const defaultText = $("default-prompt-text")?.value || "";
    const editor = $("user-prompt-text");
    if (editor) {
      editor.value = defaultText;
      showToast("Default prompt copied to editor — click Save to apply");
    }
  });
}

async function loadConfiguration() {
  const config = await api("/configuration");
  renderConfiguration(config);
}

function bindNavigation() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchView(btn.dataset.view);
      if (btn.dataset.view === "tasks") loadTasks();
      if (btn.dataset.view === "integrations") loadIntegrations().catch(showError);
      if (btn.dataset.view === "configuration") loadConfiguration().catch(showError);
    });
  });
}

function bindFilters() {
  $("refresh-btn").addEventListener("click", () => loadCalls().catch(showError));
  $("status-filter").addEventListener("change", () => loadCalls().catch(showError));
  $("lead-filter").addEventListener("change", () => loadCalls().catch(showError));
  $("search-input").addEventListener("input", debounce(() => loadCalls().catch(showError), 300));
  $("refresh-tasks-btn").addEventListener("click", () => loadTasks().catch(showError));
  $("task-status-filter").addEventListener("change", () => loadTasks().catch(showError));
  $("refresh-integrations-btn")?.addEventListener("click", () => loadIntegrations().catch(showError));
  $("refresh-config-btn")?.addEventListener("click", () => loadConfiguration().catch(showError));
}

function bindCampaignForms() {
  $("single-call-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    try {
      const result = await api("/schedule-call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      $("single-call-result").textContent = `Scheduled ${result.to_phone_number} (${result.internal_id})`;
      showToast("Call scheduled");
      form.reset();
      loadTasks().catch(() => {});
    } catch (error) {
      showError(error);
    }
  });

  $("direct-call-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    try {
      const result = await api("/run-direct-call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      $("direct-call-result").textContent = `Dialing ${payload.to} (${result.internal_id || "pending"})`;
      showToast("Direct call initiated");
      form.reset();
      setTimeout(() => loadCalls().catch(showError), 3000);
    } catch (error) {
      showError(error);
    }
  });

  $("batch-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    try {
      const result = await api("/schedule-batch", {
        method: "POST",
        body: formData,
      });
      $("batch-result").textContent = result.message || "Batch scheduled";
      showToast("Batch uploaded");
      form.reset();
      loadTasks().catch(() => {});
    } catch (error) {
      showError(error);
    }
  });

  $("run-batch-btn").addEventListener("click", async () => {
    try {
      const result = await api("/run-batch", { method: "POST" });
      showToast(result.message || "Batch started");
      loadTasks().catch(() => {});
    } catch (error) {
      showError(error);
    }
  });
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function showError(error) {
  showToast(error.message || "Something went wrong");
}

async function init() {
  bindNavigation();
  bindFilters();
  bindCampaignForms();
  try {
    await loadCalls();
  } catch (error) {
    showError(error);
  }
}

init();
