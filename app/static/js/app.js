(() => {
  const statusClass = (status) => {
    const map = {
      APPROVED: "status-approved",
      REJECTED: "status-rejected",
      PAUSED: "status-paused",
      RUNNING: "status-running",
      PENDING: "status-pending",
      COMPLETED: "status-approved",
      FAILED: "status-rejected",
    };
    return map[status] || "status-pending";
  };

  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const renderRuns = (rows) => {
    const tbody = document.querySelector("[data-run-rows]");
    if (!tbody) return;
    if (!Array.isArray(rows) || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No workflows available.</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map((run) => {
        const id = escapeHtml(run.id || "");
        const idShort = escapeHtml((run.id || "").slice(0, 8));
        const type = escapeHtml((run.workflow_type || "").replaceAll("_", " "));
        const stage = escapeHtml((run.current_stage || "-").replaceAll("_", " "));
        const created = escapeHtml(run.created_at || "");
        const status = escapeHtml(run.status || "PENDING");
        const badge = statusClass(status);
        return [
          "<tr>",
          `<td class="mono">${idShort}</td>`,
          `<td>${type}</td>`,
          `<td><span class="status-badge ${badge}">${status}</span></td>`,
          `<td>${stage}</td>`,
          `<td>${created}</td>`,
          '<td class="actions-cell">',
          `<a href="/review/${id}" class="link-btn">Review</a>`,
          `<a href="/audit/${id}" class="link-btn">Audit</a>`,
          "</td>",
          "</tr>",
        ].join("");
      })
      .join("");
  };

  const pollDashboard = async () => {
    const hasRunTable = document.querySelector("[data-run-table]");
    if (!hasRunTable) return;
    try {
      const response = await fetch("/api/workflows", { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const payload = await response.json();
      if (payload && payload.success && Array.isArray(payload.data)) renderRuns(payload.data);
    } catch (_) {
      return;
    }
  };

  const bindDecisionForm = () => {
    const form = document.querySelector("#decision-form");
    if (!form) return;
    const message = document.querySelector("#decision-message");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const workflowId = form.getAttribute("data-workflow-id");
      const checked = form.querySelector('input[name="decision"]:checked');
      const notesField = form.querySelector("#decision-notes");
      if (!workflowId || !checked || !notesField || !message) return;
      const body = {
        actor: "HUMAN",
        decision: checked.value,
        notes: notesField.value,
      };
      message.className = "decision-message";
      message.textContent = "Submitting decision...";
      try {
        const response = await fetch(`/api/workflows/${workflowId}/decide`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok || !payload.success) {
          message.classList.add("error");
          message.textContent = payload.error || "Failed to submit decision.";
          return;
        }
        message.classList.add("success");
        message.textContent = "Decision submitted successfully.";
        setTimeout(() => {
          window.location.href = `/audit/${workflowId}`;
        }, 900);
      } catch (_) {
        message.classList.add("error");
        message.textContent = "Network error while submitting decision.";
      }
    });
  };

  bindDecisionForm();
  pollDashboard();
  setInterval(pollDashboard, 10000);
})();
