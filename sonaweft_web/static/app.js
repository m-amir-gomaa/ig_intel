"use strict";
const $ = (id) => document.getElementById(id);
let config,
  csrf = "",
  upload = null,
  current = null,
  selected = null,
  timer = null,
  pollDelay = 4000,
  dirty = false;
const money = (u) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4,
  }).format(u / 10000);
function status(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}
async function api(path, options = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...options });
  let v;
  try {
    v = await r.json();
  } catch {
    throw new Error(
      "The service returned an unreadable response. Retry shortly.",
    );
  }
  if (!r.ok)
    throw new Error(
      typeof v.detail === "string"
        ? v.detail
        : "The request could not be completed.",
    );
  return v;
}
const post = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(body),
  });
async function busy(button, action) {
  button.disabled = true;
  try {
    await action();
  } catch (e) {
    status(e.message, true);
  } finally {
    button.disabled = false;
  }
}
function safeLeave() {
  return (
    !dirty || confirm("Your correction is not saved. Leave without saving?")
  );
}
function updateQuote() {
  if (!upload) return;
  const mode = $("review-mode").value;
  const q = upload.quotes[mode];
  $("price").textContent = money(q.units) + " for the complete selected result";
  $("ai-consent-label").hidden = mode === "none";
  $("trial-button").disabled = mode !== "none" || !config.hosted_enabled;
  $("run-button").disabled = !config.billing_enabled;
}
async function refreshSession() {
  config = await api("/api/session");
  csrf = config.csrf;
  $("balance").textContent =
    money(config.account.available) +
    " available · " +
    money(config.account.reserved) +
    " reserved";
  $("inspect-button").disabled = !config.hosted_enabled;
  $("pack5").disabled = $("pack10").disabled = !config.billing_enabled;
  $("billing-note").textContent = config.billing_enabled
    ? "One-time packs; no subscription. Save your private recovery key before buying."
    : "Paddle merchant review and payment testing are pending. Paid packs are closed.";
  if (upload) updateQuote();
}
function action(label, handler, secondary = true) {
  const b = document.createElement("button");
  b.textContent = label;
  if (secondary) b.className = "secondary";
  b.addEventListener("click", () => busy(b, handler));
  return b;
}
async function refreshJobs() {
  const values = await api("/api/jobs");
  $("jobs").replaceChildren();
  if (!values.length) {
    const p = document.createElement("p");
    p.textContent = "Your jobs appear here after confirmation.";
    $("jobs").append(p);
  }
  for (const j of values) {
    const card = document.createElement("article"),
      title = document.createElement("h4"),
      state = document.createElement("p"),
      controls = document.createElement("div");
    title.textContent = j.filename;
    state.textContent =
      j.stage + (j.trial ? " · first 30 seconds" : " · " + money(j.units));
    controls.className = "actions";
    card.append(title, state);
    if (j.error) {
      const e = document.createElement("p");
      e.textContent = j.error;
      card.append(e);
    }
    if (j.status === "done")
      controls.append(action("Review & export", () => openJob(j.id)));
    if (j.status === "queued")
      controls.append(
        action("Cancel queued job", async () => {
          await post("/api/jobs/" + j.id + "/cancel", {});
          await refreshJobs();
          await refreshSession();
        }),
      );
    if (j.status === "error" && !j.trial)
      controls.append(
        action("Review retry quote", async () => {
          const q = {
            none: 1500 + Math.ceil(j.seconds / 60) * 150,
            standard: 2500 + Math.ceil(j.seconds / 60) * 200,
            advanced: 3500 + Math.ceil(j.seconds / 60) * 250,
          };
          upload = {
            upload: j.upload,
            filename: j.filename,
            duration: j.seconds,
            quotes: Object.fromEntries(
              Object.entries(q).map(([k, units]) => [k, { units }]),
            ),
          };
          $("filename").textContent = j.filename;
          $("duration").textContent =
            "Explicit retry; retained ASR may be reused. Review the quote and confirm below.";
          $("quote").hidden = false;
          $("review-mode").value = j.review;
          updateQuote();
          $("quote").scrollIntoView({ behavior: "smooth", block: "start" });
        }),
      );
    card.append(controls);
    $("jobs").append(card);
  }
  clearTimeout(timer);
  if (
    values.some((j) => ["queued", "running"].includes(j.status)) &&
    !document.hidden
  ) {
    timer = setTimeout(
      () => refreshJobs().catch((e) => status(e.message, true)),
      pollDelay,
    );
    pollDelay = Math.min(20000, pollDelay + 2000);
  } else pollDelay = 4000;
}
$("upload-form").addEventListener("submit", (e) => {
  e.preventDefault();
  busy($("inspect-button"), async () => {
    const file = $("media-file").files[0];
    if (!file) throw new Error("Choose a recording.");
    if (file.size > config.max_bytes)
      throw new Error("Choose a recording within the size limit.");
    const form = new FormData();
    form.append("file", file);
    form.append("request_id", crypto.randomUUID());
    status("Inspecting the recording. No transcription has started.");
    upload = await api("/api/uploads", {
      method: "POST",
      headers: { "X-CSRF-Token": csrf },
      body: form,
    });
    $("quote").hidden = false;
    $("filename").textContent = upload.filename;
    $("duration").textContent =
      (upload.duration / 60).toFixed(2) + " minutes · original timing retained";
    updateQuote();
    status(
      "Inspection complete. Choose the complete result you want and confirm the quote.",
    );
  });
});
$("review-mode").addEventListener("change", updateQuote);
async function startJob(trial) {
  if (!upload) throw new Error("Inspect a recording first.");
  const mode = trial ? "none" : $("review-mode").value;
  if (!$("rights").checked)
    throw new Error("Confirm that you may process this media.");
  if (mode !== "none" && !$("ai-consent").checked)
    throw new Error("Confirm whether transcript text may be sent to DeepSeek.");
  const job = await post("/api/jobs", {
    upload: upload.upload,
    request_id: crypto.randomUUID(),
    review: mode,
    trial,
    expected_units: trial ? 0 : upload.quotes[mode].units,
    authorized_media: $("rights").checked,
    ai_consent: $("ai-consent").checked,
  });
  status(
    job.submission_uncertain
      ? "Submission is uncertain. Check the existing job; do not start another paid job."
      : "Job queued. You can follow its stage below.",
  );
  await refreshSession();
  await refreshJobs();
}
$("trial-button").addEventListener("click", () =>
  busy($("trial-button"), () => startJob(true)),
);
$("run-button").addEventListener("click", () =>
  busy($("run-button"), () => startJob(false)),
);
function drawSegments() {
  const filter = $("segment-search").value.toLowerCase();
  $("segments").replaceChildren();
  for (const s of current.segments) {
    if (
      !(current.corrections[s.segment_id] || s.text)
        .toLowerCase()
        .includes(filter)
    )
      continue;
    const b = document.createElement("button"),
      t = document.createElement("time"),
      text = document.createElement("span");
    t.textContent = s.start.toFixed(2) + " – " + s.end.toFixed(2) + " s";
    text.textContent = current.corrections[s.segment_id] ?? s.text;
    b.classList.toggle("active", s.segment_id === selected?.segment_id);
    b.append(t, text);
    b.addEventListener("click", () => {
      if (!safeLeave()) return;
      selectSegment(s);
      $("audio").currentTime = s.start;
    });
    $("segments").append(b);
  }
}
function selectSegment(s) {
  selected = s;
  dirty = false;
  $("selected-time").textContent =
    "Source segment " +
    s.segment_id +
    " · " +
    s.start.toFixed(2) +
    "–" +
    s.end.toFixed(2) +
    " s";
  $("original").textContent = s.text;
  $("editor").value = current.corrections[s.segment_id] ?? s.text;
  $("suggestions").replaceChildren();
  for (const suggestion of current.review_data?.corrections || []) {
    if (suggestion.segment_id !== s.segment_id) continue;
    const p = document.createElement("p");
    p.textContent =
      "AI suggestion: “" +
      suggestion.quote +
      "” → “" +
      suggestion.replacement +
      "”";
    const apply = action("Apply to draft", async () => {
      if (!$("editor").value.includes(suggestion.quote))
        throw new Error(
          "This draft differs from the suggested source text. Review it manually.",
        );
      $("editor").value = $("editor").value.replace(
        suggestion.quote,
        suggestion.replacement,
      );
      dirty = true;
      status("Suggestion applied to the draft. Review and save it explicitly.");
    });
    $("suggestions").append(p, apply);
  }
  drawSegments();
}
async function openJob(id) {
  if (!safeLeave()) return;
  current = await api("/api/jobs/" + id);
  $("review-panel").hidden = false;
  $("segment-search").value = "";
  $("audio").src = "/api/jobs/" + id + "/audio";
  for (const [element, format] of [
    ["bundle-link", "bundle"],
    ["md-link", "md"],
    ["srt-link", "srt"],
    ["vtt-link", "vtt"],
    ["json-link", "json"],
  ])
    $(element).href = "/api/jobs/" + id + "/export?format=" + format;
  $("ai-notes").hidden = !current.review_data;
  $("summary").textContent = current.review_data?.summary_md || "";
  $("claims").replaceChildren();
  for (const c of current.review_data?.claims || []) {
    const p = document.createElement("p"),
      b = action("Hear source " + c.segment_id, async () => {
        const s = current.segments.find((s) => s.segment_id === c.segment_id);
        if (s && safeLeave()) {
          selectSegment(s);
          $("audio").currentTime = s.start;
        }
      });
    p.textContent = "“" + c.quote + "” — " + c.question;
    const lookup = action("Find source candidates", async () => {
      if (!$("research-consent").checked)
        throw new Error("Confirm whether this claim may be sent to Crossref.");
      const found = await post("/api/jobs/" + current.id + "/sources", {
        claim_index: current.review_data.claims.indexOf(c),
        research_consent: true,
      });
      const list = document.createElement("ul");
      for (const source of found.sources) {
        const li = document.createElement("li"),
          a = document.createElement("a");
        a.href = source.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = source.title + " · " + source.doi;
        li.append(a);
        list.append(li);
      }
      const note = document.createElement("p");
      note.textContent = found.notice;
      if (!found.sources.length)
        note.textContent =
          "No candidates returned. That does not establish that this claim is true or false.";
      lookup.after(note, list);
      lookup.disabled = true;
    });
    $("claims").append(p, b, lookup);
  }
  if (current.segments[0]) selectSegment(current.segments[0]);
  $("review-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  $("review-title").setAttribute("tabindex", "-1");
  $("review-title").focus();
}
$("segment-search").addEventListener("input", () => {
  if (current) drawSegments();
});
$("editor").addEventListener("input", () => {
  dirty = true;
});
$("save-edit").addEventListener("click", () =>
  busy($("save-edit"), async () => {
    if (!current || !selected) return;
    const corrections = {
      ...current.corrections,
      [selected.segment_id]: $("editor").value,
    };
    const r = await post("/api/jobs/" + current.id + "/edit", {
      revision: current.revision,
      corrections,
    });
    current.revision = r.revision;
    current.corrections = corrections;
    dirty = false;
    drawSegments();
    status(
      "Correction saved separately. The original machine transcript is unchanged.",
    );
  }),
);
$("close-review").addEventListener("click", () => {
  if (safeLeave()) {
    $("review-panel").hidden = true;
    $("audio").pause();
    dirty = false;
    $("refresh-jobs").focus();
  }
});
$("make-key").addEventListener("click", () =>
  busy($("make-key"), async () => {
    const r = await post("/api/recovery", {});
    $("recovery-key").value = r.recovery_key;
    $("key-box").hidden = false;
    $("recovery-key").focus();
    $("recovery-key").select();
    status(r.notice);
  }),
);
$("hide-key").addEventListener("click", () => {
  $("key-box").hidden = true;
  $("recovery-key").value = "";
});
$("restore-form").addEventListener("submit", (e) => {
  e.preventDefault();
  if (!safeLeave()) return;
  busy(e.currentTarget.querySelector("button"), async () => {
    await post("/api/restore", { recovery_key: $("restore-key").value });
    $("restore-key").value = "";
    $("review-panel").hidden = true;
    current = null;
    dirty = false;
    await refreshSession();
    await refreshJobs();
    status("Your workspace was restored.");
  });
});
for (const pack of [5, 10])
  $("pack" + pack).addEventListener("click", () =>
    busy($("pack" + pack), async () => {
      const r = await post("/api/checkout", {
        pack,
        terms_accepted: $("purchase-consent").checked,
      });
      location.assign(r.url);
    }),
  );
$("refresh-jobs").addEventListener("click", () =>
  busy($("refresh-jobs"), async () => {
    await refreshSession();
    await refreshJobs();
  }),
);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) clearTimeout(timer);
  else if (config) refreshJobs().catch((e) => status(e.message, true));
});
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
(async () => {
  try {
    await refreshSession();
    await refreshJobs();
    status(
      config.hosted_enabled
        ? "Your private workspace is ready. Inspect a recording to start."
        : "Hosted processing is being verified. The local CLI is available; paid packs remain closed.",
    );
  } catch (e) {
    status(e.message, true);
  }
})();
