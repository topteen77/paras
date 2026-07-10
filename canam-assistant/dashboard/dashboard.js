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
  practice: {
    title: "Practice Call",
    subtitle: "Talk to Monica with headphones before placing a live call",
  },
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
    <br><span class="muted">Switching stacks updates <code>VOICE_AI_PROVIDER</code>, <code>TELEPHONY_PROVIDER</code>, and <code>STACK_NAME</code> immediately — no restart needed.</span>
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
        if (result.error) {
          showError(new Error(result.error));
          return;
        }
        const envNote = result.env_synced ? " · .env updated" : "";
        showToast(
          `${result.message || "Stack switched"}${envNote}`
        );
        await loadIntegrations();
        if (document.getElementById("view-configuration")?.classList.contains("active")) {
          await loadConfiguration();
        }
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

function renderVoiceSettingsSection(voiceSettings) {
  if (!voiceSettings) return "";
  const effective = voiceSettings.effective || {};
  const speakers = voiceSettings.speakers || [];
  const currentId = effective.speaker || "anushka";

  const speakerOptions = speakers
    .map(
      (s) => `
      <label class="voice-speaker-option ${s.id === currentId ? "selected" : ""}" data-speaker-id="${escapeHtml(s.id)}">
        <input type="radio" name="voice-speaker" value="${escapeHtml(s.id)}" ${s.id === currentId ? "checked" : ""} />
        <div>
          <strong>${escapeHtml(s.name)} · ${escapeHtml(s.gender)}</strong>
          <span>${escapeHtml(s.description)}</span>
        </div>
      </label>`
    )
    .join("");

  const langOptions = (voiceSettings.language_options || [])
    .map(
      (o) =>
        `<option value="${escapeHtml(o.code)}" ${o.code === effective.language_code ? "selected" : ""}>${escapeHtml(o.label)}</option>`
    )
    .join("");

  return `
    <div class="config-section" id="voice-settings-section">
      <h2>Voice &amp; speaker (Sarvam TTS)</h2>
      <p>
        <span class="tag ${voiceSettings.has_saved_override ? "active" : "integrated"}">
          ${voiceSettings.has_saved_override ? "Custom voice saved" : "Using .env defaults"}
        </span>
        · Applies to all new Sarvam calls. Pronunciation map runs automatically before TTS.
      </p>
      <div class="voice-settings-grid">
        <div>
          <h3>Choose speaker</h3>
          <div class="voice-speaker-list" id="voice-speaker-list">${speakerOptions}</div>
        </div>
        <div class="voice-controls">
          <h3>TTS tuning</h3>
          <label>
            Language
            <select id="voice-language">${langOptions}</select>
          </label>
          <label>
            Pace <span id="voice-pace-val">${effective.pace ?? 0.95}</span>
            <input type="range" id="voice-pace" min="0.3" max="3" step="0.05" value="${effective.pace ?? 0.95}" />
          </label>
          <label>
            Pitch <span id="voice-pitch-val">${effective.pitch ?? 0}</span>
            <input type="range" id="voice-pitch" min="-0.75" max="0.75" step="0.05" value="${effective.pitch ?? 0}" />
          </label>
          <label>
            Loudness <span id="voice-loudness-val">${effective.loudness ?? 1.1}</span>
            <input type="range" id="voice-loudness" min="0.3" max="3" step="0.05" value="${effective.loudness ?? 1.1}" />
          </label>
          <label>
            <input type="checkbox" id="voice-preprocessing" ${effective.enable_preprocessing !== false ? "checked" : ""} />
            Enable text preprocessing (numbers, mixed language)
          </label>
          <label>
            Greeting override (optional — call opening uses <strong>Call script</strong> below)
            <textarea id="voice-greeting" rows="2" placeholder="Leave blank to use Call script intro + question 1">${escapeHtml(effective.greeting || "")}</textarea>
          </label>
          <label>
            Preview text
            <textarea id="voice-preview-text" rows="2">${escapeHtml(voiceSettings.preview_sample || "")}</textarea>
          </label>
          <div class="voice-preview-row">
            <button class="btn secondary" type="button" id="preview-voice-btn">▶ Hear preview</button>
            <button class="btn primary" type="button" id="save-voice-btn">Save voice settings</button>
            <button class="btn secondary" type="button" id="reset-voice-btn" ${voiceSettings.has_saved_override ? "" : "disabled"}>Reset to .env</button>
          </div>
          <audio id="voice-preview-audio" class="voice-preview-audio" controls></audio>
        </div>
      </div>
    </div>`;
}

function bindVoiceSettings(voiceSettings) {
  const getPayload = () => ({
    speaker: document.querySelector('input[name="voice-speaker"]:checked')?.value,
    language_code: $("voice-language")?.value,
    pace: parseFloat($("voice-pace")?.value || "0.95"),
    pitch: parseFloat($("voice-pitch")?.value || "0"),
    loudness: parseFloat($("voice-loudness")?.value || "1.1"),
    enable_preprocessing: $("voice-preprocessing")?.checked ?? true,
    greeting: $("voice-greeting")?.value || "",
    tts_model: voiceSettings?.effective?.tts_model || "bulbul:v2",
  });

  const syncRangeLabel = (inputId, labelId) => {
    const input = $(inputId);
    const label = $(labelId);
    if (input && label) {
      input.addEventListener("input", () => {
        label.textContent = input.value;
      });
    }
  };
  syncRangeLabel("voice-pace", "voice-pace-val");
  syncRangeLabel("voice-pitch", "voice-pitch-val");
  syncRangeLabel("voice-loudness", "voice-loudness-val");

  document.querySelectorAll(".voice-speaker-option").forEach((el) => {
    el.addEventListener("click", () => {
      document.querySelectorAll(".voice-speaker-option").forEach((n) => n.classList.remove("selected"));
      el.classList.add("selected");
      const radio = el.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
    });
  });

  $("preview-voice-btn")?.addEventListener("click", async () => {
    const payload = {
      ...getPayload(),
      text: $("voice-preview-text")?.value || "",
    };
    try {
      const response = await fetch(`${API}/voice-settings/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || err.error || `Preview failed (${response.status})`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const audio = $("voice-preview-audio");
      if (audio) {
        audio.src = url;
        audio.play().catch(() => {});
      }
      showToast("Playing voice preview");
    } catch (error) {
      showError(error);
    }
  });

  $("save-voice-btn")?.addEventListener("click", async () => {
    try {
      const result = await api("/voice-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getPayload()),
      });
      showToast(result.message || "Voice settings saved");
      await loadConfiguration();
    } catch (error) {
      showError(error);
    }
  });

  $("reset-voice-btn")?.addEventListener("click", async () => {
    try {
      const result = await api("/voice-settings", { method: "DELETE" });
      showToast(result.message || "Voice settings reset");
      await loadConfiguration();
    } catch (error) {
      showError(error);
    }
  });
}

const CALL_SCRIPT_SAMPLES = ["Canada", "none", "Masters", "next year", "Mumbai", "Monday at 4 PM"];
const CALL_SCRIPT_ACKS = ["Certainly.", "Got it.", "Thank you.", "Understood.", "Noted.", "Perfect."];

function buildCallPreviewLocal(intro, questions, closingTemplate) {
  const qs = (questions || []).map((q) => (q || "").trim());
  while (qs.length < 6) qs.push(`[question ${qs.length + 1}]`);
  const lines = ["--- CALL PREVIEW (sample answers) ---"];
  lines.push(`Monica: ${(intro || "").trim()} ${qs[0]}`);
  for (let i = 0; i < 6; i++) {
    lines.push(`You: ${CALL_SCRIPT_SAMPLES[i]}`);
    if (i < 5) {
      lines.push(`Monica: ${CALL_SCRIPT_ACKS[i]} ${qs[i + 1]}`);
    } else {
      const closing = (closingTemplate || "")
        .replace("{country}", CALL_SCRIPT_SAMPLES[0])
        .replace("{other}", CALL_SCRIPT_SAMPLES[1])
        .replace("{other_part}", "")
        .replace("{level}", CALL_SCRIPT_SAMPLES[2])
        .replace("{timeline}", CALL_SCRIPT_SAMPLES[3])
        .replace("{location}", CALL_SCRIPT_SAMPLES[4])
        .replace("{callback}", CALL_SCRIPT_SAMPLES[5]);
      lines.push(`Monica: ${closing || "[confirmation summary] Goodbye."}`);
    }
  }
  lines.push("--- END ---");
  return lines.join("\n");
}

function updateCallScriptPreview() {
  const intro = $("call-script-intro")?.value || "";
  const questions = [];
  for (let i = 0; i < 6; i++) {
    questions.push($(`call-script-q-${i}`)?.value || "");
  }
  const closing = $("call-script-closing")?.value || "";
  const preview = $("call-script-preview");
  if (preview) {
    preview.value = buildCallPreviewLocal(intro, questions, closing);
  }
}

function renderCallScriptSection(callScript) {
  if (!callScript) return "";
  const cs = callScript.effective || callScript;
  const intro = cs.intro || "";
  const questions = cs.questions || [];
  const labels = cs.topic_labels || [];
  const closing = cs.closing_template || "";
  const preview = callScript.call_preview || buildCallPreviewLocal(intro, questions, closing);

  const questionFields = Array.from({ length: 6 }, (_, i) => {
    const label = labels[i] || `Question ${i + 1}`;
    return `
      <label class="call-script-question">
        <span class="call-script-q-label">${i + 1}. ${escapeHtml(label)}</span>
        <input type="text" id="call-script-q-${i}" data-label="${escapeHtml(label)}" value="${escapeHtml(questions[i] || "")}" />
      </label>`;
  }).join("");

  return `
    <div class="config-section" id="call-script-section">
      <h2>Call script</h2>
      <p>
        <span class="tag ${callScript.has_saved_override ? "active" : "integrated"}">
          ${callScript.has_saved_override ? "Custom script saved" : "Using defaults"}
        </span>
        · Intro and questions used in live calls, practice mode, and the system prompt.
      </p>
      <div class="call-script-grid">
        <div class="call-script-editor">
          <label>
            Intro (spoken once at call start)
            <textarea id="call-script-intro" rows="3" placeholder="Hello, thank you for calling...">${escapeHtml(intro)}</textarea>
          </label>
          <h3>Questions (one per turn, in order)</h3>
          <div class="call-script-questions">${questionFields}</div>
          <label>
            Closing template
            <textarea id="call-script-closing" rows="2">${escapeHtml(closing)}</textarea>
            <span class="muted small">Placeholders: {country}, {other}, {other_part}, {level}, {timeline}, {location}, {callback}</span>
          </label>
          <div class="prompt-actions">
            <button class="btn primary" type="button" id="save-call-script-btn">Save call script</button>
            <button class="btn secondary" type="button" id="reset-call-script-btn" ${callScript.has_saved_override ? "" : "disabled"}>Reset to defaults</button>
          </div>
        </div>
        <div class="call-script-preview-panel">
          <h3>Call preview</h3>
          <p class="muted small">Sample walkthrough with example answers — updates as you edit.</p>
          <textarea id="call-script-preview" readonly rows="18">${escapeHtml(preview)}</textarea>
        </div>
      </div>
    </div>`;
}

function bindCallScript() {
  ["call-script-intro", "call-script-closing"].forEach((id) => {
    $(id)?.addEventListener("input", updateCallScriptPreview);
  });
  for (let i = 0; i < 6; i++) {
    $(`call-script-q-${i}`)?.addEventListener("input", updateCallScriptPreview);
  }

  $("save-call-script-btn")?.addEventListener("click", async () => {
    const questions = [];
    const topic_labels = [];
    for (let i = 0; i < 6; i++) {
      questions.push($(`call-script-q-${i}`)?.value || "");
      topic_labels.push($(`call-script-q-${i}`)?.dataset?.label || `Question ${i + 1}`);
    }
    try {
      const result = await api("/call-script", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intro: $("call-script-intro")?.value || "",
          questions,
          topic_labels,
          closing_template: $("call-script-closing")?.value || "",
        }),
      });
      if (result.error) throw new Error(result.error);
      showToast(result.message || "Call script saved");
      await loadConfiguration();
    } catch (error) {
      showError(error);
    }
  });

  $("reset-call-script-btn")?.addEventListener("click", async () => {
    try {
      const result = await api("/call-script", { method: "DELETE" });
      showToast(result.message || "Reset to defaults");
      await loadConfiguration();
    } catch (error) {
      showError(error);
    }
  });
}

function renderConfiguration(config) {
  const root = $("configuration-root");
  const callbacks = config.callbacks || {};
  const models = config.models || {};
  const phones = config.phone_numbers || {};
  const prompts = config.prompts || {};
  const callScript = config.call_script || {};
  const voiceSettings = config.voice_settings || {};
  const sarvam = models.sarvam || {};
  const eleven = models.elevenlabs || {};
  const gemini = models.gemini || {};
  const voiceAi = models.voice_ai_provider;

  const publicAlert = callbacks.public_url_ok
    ? `<div class="alert ok">Public URL is set: <code>${escapeHtml(callbacks.public_base_url)}</code></div>`
    : `<div class="alert warn">WEB_SERVER_URL is localhost — Plivo/Twilio cannot reach callbacks until ngrok is configured.</div>`;

  const modelItems = [];
  if (voiceAi === "sarvam") {
    modelItems.push(
      ["LLM model", sarvam.chat_model],
      ["STT model", sarvam.stt_model],
      ["TTS model", sarvam.tts_model],
      ["TTS speaker", sarvam.tts_speaker],
      ["Language", sarvam.language_code],
      ["System prompt", sarvam.system_prompt_path],
      ["Prompt file exists", sarvam.system_prompt_exists ? "Yes" : "No"]
    );
  } else if (voiceAi === "gemini") {
    modelItems.push(
      ["Live model", gemini.live_model],
      ["Language", gemini.language_code],
      ["Voice name", gemini.voice_name || "Default"],
      ["API key configured", gemini.api_key_configured ? "Yes" : "No"],
      ["System prompt", gemini.system_prompt_path],
      ["Prompt file exists", gemini.system_prompt_exists ? "Yes" : "No"]
    );
  } else if (voiceAi === "elevenlabs") {
    modelItems.push(
      ["Cold calling agent", eleven.cold_calling_agent_id || "Not set"],
      ["After-visit agent", eleven.after_visit_feedback_agent_id || "Not set"]
    );
  }
  modelItems.unshift(
    ["Telephony", models.telephony_provider],
    ["Voice AI", models.voice_ai_provider]
  );

  const voiceSection = voiceAi === "sarvam" ? renderVoiceSettingsSection(voiceSettings) : "";

  const promptVoiceStacks = ["sarvam", "gemini"];
  const callScriptSection = promptVoiceStacks.includes(voiceAi) ? renderCallScriptSection(callScript) : "";
  const usingPrompt = prompts.using === "user" ? "Your custom prompt" : "Default prompt";
  const promptSection = promptVoiceStacks.includes(voiceAi)
    ? `
    <div class="config-section" id="prompt-section">
      <h2>System prompts</h2>
      <p>
        <span class="tag ${prompts.using === "user" ? "active" : "integrated"}">Active: ${escapeHtml(usingPrompt)}</span>
        · User prompt overrides default for all new ${escapeHtml(voiceAi)} calls.
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
          <textarea id="user-prompt-text" placeholder="Write your custom system prompt here. When saved, this replaces the default for outbound calls.">${escapeHtml(prompts.user?.content || "")}</textarea>
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

    ${voiceSection || (voiceAi !== "sarvam"
      ? `<div class="config-section"><h2>Voice &amp; speaker</h2><p class="muted">Speaker selection is available when the active stack uses <strong>Sarvam TTS</strong>. For Gemini, switch stack under <strong>Integrations</strong> → Plivo + Gemini.</p></div>`
      : "")}

    <div class="config-section">
      <h2>Active stack</h2>
      <p>${escapeHtml(config.active_stack?.stack_name || "")} · source: ${escapeHtml(config.active_stack?.source || "env")}</p>
      <p class="muted">Change stack under <strong>Integrations</strong> — updates telephony + voice AI for the next call.</p>
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

    ${callScriptSection}

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

  if (models.voice_ai_provider === "sarvam" && voiceSettings) {
    bindVoiceSettings(voiceSettings);
  }
  if (promptVoiceStacks.includes(voiceAi) && callScript) {
    bindCallScript();
  }
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
      if (btn.dataset.view === "practice") ensureTextPracticeSession().catch(showError);
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
  $("jump-voice-btn")?.addEventListener("click", () => {
    const el = document.getElementById("voice-settings-section");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      showToast("Voice & speaker settings");
    } else {
      showToast("Voice settings require Sarvam stack — check Integrations");
    }
  });
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

const practiceState = {
  ws: null,
  audioContext: null,
  micStream: null,
  processor: null,
  playbackContext: null,
  nextPlayTime: 0,
  micPaused: false,
  micPauseTimer: null,
  textSessionId: null,
  textEnded: false,
};

function practiceWsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/simulate`;
}

function setPracticeStatus(text, extraClass = "") {
  const el = $("practice-status");
  if (!el) return;
  el.textContent = text;
  el.className = `practice-status ${extraClass}`.trim();
}

function renderPracticeProgress(flow) {
  const el = $("practice-progress");
  if (!el || !flow) return;
  const n = flow.turn_index || 0;
  const total = flow.total_questions || 6;
  const next = flow.next_question ? `Next: ${flow.next_question}` : "Closing";
  el.textContent = `Progress: ${n}/${total} answered · ${next}`;
}

function appendPracticeLine(role, text) {
  const root = $("practice-transcript");
  if (!root || !text) return;
  if (root.querySelector(".detail-empty")) {
    root.innerHTML = "";
  }
  const line = document.createElement("div");
  line.className = `practice-line ${role}`;
  line.innerHTML = `<div class="role">${role === "user" ? "You" : "Monica"}</div>${escapeHtml(text)}`;
  root.appendChild(line);
  root.scrollTop = root.scrollHeight;
}

function floatTo16BitPCM(float32) {
  const buffer = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

function downsampleBuffer(buffer, inputRate, outputRate) {
  if (inputRate === outputRate) return buffer;
  const ratio = inputRate / outputRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    result[i] = buffer[Math.floor(i * ratio)];
  }
  return result;
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function playPracticePcm(pcmBytes) {
  if (!practiceState.playbackContext) {
    practiceState.playbackContext = new AudioContext({ sampleRate: 8000 });
    practiceState.nextPlayTime = practiceState.playbackContext.currentTime;
  }
  const ctx = practiceState.playbackContext;
  const samples = pcmBytes.length / 2;
  const audioBuffer = ctx.createBuffer(1, samples, 8000);
  const channel = audioBuffer.getChannelData(0);
  const view = new DataView(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.byteLength);
  for (let i = 0; i < samples; i++) {
    channel[i] = view.getInt16(i * 2, true) / 32768;
  }
  const source = ctx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(ctx.destination);
  const startAt = Math.max(ctx.currentTime, practiceState.nextPlayTime);
  source.start(startAt);
  practiceState.nextPlayTime = startAt + audioBuffer.duration;
}

async function startVoicePractice() {
  if (practiceState.ws) {
    showToast("Practice already running");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    practiceState.micStream = stream;
    const ws = new WebSocket(practiceWsUrl());
    practiceState.ws = ws;

    ws.onopen = () => {
      setPracticeStatus("Connected — listening", "live");
      $("practice-start-btn").disabled = true;
      $("practice-stop-btn").disabled = false;
      $("practice-transcript").innerHTML = "";
      startMicCapture(stream, ws);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.event === "transcript" && data.text) {
        appendPracticeLine(data.role, data.text);
      }
      if (data.event === "flow") {
        renderPracticeProgress(data);
      }
      if (data.event === "playAudio" && data.media?.payload) {
        setPracticeStatus("Monica speaking — wait", "speaking");
        const durationSec = Number(data.duration) || 3;
        practiceState.micPaused = true;
        if (practiceState.micPauseTimer) clearTimeout(practiceState.micPauseTimer);
        practiceState.micPauseTimer = setTimeout(() => {
          practiceState.micPaused = false;
          setPracticeStatus("Your turn — speak now", "live");
        }, durationSec * 1000 + 450);
        const raw = atob(data.media.payload);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
        playPracticePcm(bytes);
      }
      if (data.event === "clearAudio") {
        practiceState.nextPlayTime = practiceState.playbackContext?.currentTime || 0;
        practiceState.micPaused = false;
        if (practiceState.micPauseTimer) clearTimeout(practiceState.micPauseTimer);
      }
      if (data.event === "started") {
        showToast("Practice call started");
      }
      if (data.event === "flow" && data.all_collected) {
        setPracticeStatus("Call complete — ending", "");
      }
      if (data.event === "ended") {
        setPracticeStatus("Call ended", "");
        stopVoicePractice();
      }
      if (data.event === "error") {
        showError(new Error(data.message || "Practice error"));
        stopVoicePractice();
      }
    };

    ws.onerror = () => showError(new Error("WebSocket error"));
    ws.onclose = () => {
      if (practiceState.ws === ws) {
        stopVoicePractice();
      }
    };
  } catch (error) {
    showError(error);
    stopVoicePractice();
  }
}

function startMicCapture(stream, ws) {
  const audioContext = new AudioContext();
  practiceState.audioContext = audioContext;
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  practiceState.processor = processor;
  processor.onaudioprocess = (e) => {
    if (practiceState.micPaused) return;
    if (!practiceState.ws || practiceState.ws.readyState !== WebSocket.OPEN) return;
    const input = e.inputBuffer.getChannelData(0);
    const downsampled = downsampleBuffer(input, audioContext.sampleRate, 8000);
    const pcm = floatTo16BitPCM(downsampled);
    ws.send(
      JSON.stringify({
        event: "media",
        media: { payload: bytesToBase64(pcm), sampleRate: 8000 },
      })
    );
  };
  source.connect(processor);
  processor.connect(audioContext.destination);
}

function stopVoicePractice() {
  if (practiceState.ws) {
    try {
      practiceState.ws.send(JSON.stringify({ event: "stop" }));
      practiceState.ws.close();
    } catch (_) {
      /* ignore */
    }
    practiceState.ws = null;
  }
  if (practiceState.processor) {
    practiceState.processor.disconnect();
    practiceState.processor = null;
  }
  if (practiceState.audioContext) {
    practiceState.audioContext.close().catch(() => {});
    practiceState.audioContext = null;
  }
  if (practiceState.micStream) {
    practiceState.micStream.getTracks().forEach((t) => t.stop());
    practiceState.micStream = null;
  }
  if (practiceState.playbackContext) {
    practiceState.playbackContext.close().catch(() => {});
    practiceState.playbackContext = null;
    practiceState.nextPlayTime = 0;
  }
  if (practiceState.micPauseTimer) {
    clearTimeout(practiceState.micPauseTimer);
    practiceState.micPauseTimer = null;
  }
  practiceState.micPaused = false;
  $("practice-start-btn").disabled = false;
  $("practice-stop-btn").disabled = true;
  setPracticeStatus("Idle", "");
}

async function ensureTextPracticeSession() {
  if (practiceState.textSessionId && !practiceState.textEnded) return;
  await startTextPracticeSession();
}

async function startTextPracticeSession() {
  const result = await api("/simulate/start", { method: "POST" });
  practiceState.textSessionId = result.session_id;
  practiceState.textEnded = false;
  $("practice-text-input").disabled = false;
  $("practice-text-send").disabled = false;
  $("practice-transcript").innerHTML = "";
  appendPracticeLine("assistant", result.greeting);
  renderPracticeProgress(result.flow);
  setPracticeStatus("Text session ready", "live");
}

async function sendTextPracticeTurn(message) {
  if (!practiceState.textSessionId) {
    await startTextPracticeSession();
  }
  appendPracticeLine("user", message);
  const result = await api("/simulate/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: practiceState.textSessionId, message }),
  });
  if (result.error) throw new Error(result.error);
  appendPracticeLine("assistant", result.reply);
  renderPracticeProgress(result.flow);
  if (result.ended) {
    practiceState.textEnded = true;
    practiceState.textSessionId = null;
    $("practice-text-input").disabled = true;
    setPracticeStatus("Session ended", "");
  }
}

function bindPracticeForms() {
  $("practice-start-btn")?.addEventListener("click", () => startVoicePractice().catch(showError));
  $("practice-stop-btn")?.addEventListener("click", () => stopVoicePractice());
  $("practice-text-reset")?.addEventListener("click", () => {
    practiceState.textSessionId = null;
    practiceState.textEnded = true;
    startTextPracticeSession().catch(showError);
  });
  $("practice-text-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("practice-text-input");
    const text = (input?.value || "").trim();
    if (!text) return;
    try {
      await sendTextPracticeTurn(text);
      input.value = "";
    } catch (error) {
      showError(error);
    }
  });
}

async function init() {
  bindNavigation();
  bindFilters();
  bindCampaignForms();
  bindPracticeForms();
  try {
    await loadCalls();
  } catch (error) {
    showError(error);
  }
}

init();
