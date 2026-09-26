content = '''// FIDDS - frontend logic

const uploadForm = document.getElementById("uploadForm");
const submitBtn = document.getElementById("submitBtn");
const progressBox = document.getElementById("progressBox");
const progressBar = document.getElementById("progressBar");
const progressStage = document.getElementById("progressStage");
const resultRoot = document.getElementById("resultRoot");

const STAGES = [
    { id: "document", label: "Document received", pct: 15 },
    { id: "ocr", label: "Running OCR + MRZ extraction", pct: 35 },
    { id: "validation", label: "Validating fields", pct: 55 },
    { id: "tampering", label: "Analyzing image forensics", pct: 75 },
    { id: "face", label: "Face verification", pct: 88 },
    { id: "risk", label: "Computing risk score", pct: 98 },
];

function setStage(idx) {
    STAGES.forEach((s, i) => {
        const el = document.getElementById("stage-" + s.id);
        if (!el) return;
        el.classList.remove("text-info", "fw-bold", "text-muted");
        if (i < idx) el.classList.add("text-muted");
        else if (i === idx) el.classList.add("text-info", "fw-bold");
        else el.classList.add("text-muted");
    });
}

function tickProgress(idx) {
    if (idx >= STAGES.length) return;
    const s = STAGES[idx];
    progressBar.style.width = s.pct + "%";
    progressBar.textContent = s.pct + "%";
    progressStage.textContent = s.label;
    setStage(idx);
}

function riskColor(level) {
    if (level === "LOW") return "success";
    if (level === "MEDIUM") return "warning";
    if (level === "HIGH") return "danger";
    return "secondary";
}

function sevColor(sev) {
    if (sev === "critical") return "danger";
    if (sev === "warning") return "warning";
    return "info";
}

function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function renderResult(data) {
    const risk = data.risk || {};
    const components = risk.components || {};
    const reasons = risk.reasons || [];
    const fields = data.fields || {};
    const color = riskColor(risk.risk_level);

    const fieldsRows = [
        ["Passport number", fields.passport_number],
        ["Surname", fields.surname],
        ["Given names", fields.given_names],
        ["Nationality", fields.nationality],
        ["Date of birth", fields.date_of_birth],
        ["Date of expiry", fields.date_of_expiry],
        ["DOB source", fields.dob_source],
        ["Expiry source", fields.expiry_source],
    ]
        .filter(([_, v]) => v)
        .map(([k, v]) => `<tr><td class="text-muted">${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`)
        .join("");

    const componentRows = Object.keys(components)
        .map(k => {
            const v = components[k];
            const barColor = v < 30 ? "success" : v < 60 ? "warning" : "danger";
            return `<tr>
                <td class="text-muted">${escapeHtml(k)}</td>
                <td style="width:50%">
                    <div class="progress" style="height:10px;">
                        <div class="progress-bar bg-${barColor}" style="width:${v}%"></div>
                    </div>
                </td>
                <td class="text-end">${v}</td>
            </tr>`;
        })
        .join("");

    const reasonItems = reasons
        .map(r => {
            const c = sevColor(r.severity);
            return `<li class="list-group-item d-flex align-items-start">
                <span class="badge bg-${c} me-2">${escapeHtml(r.severity)}</span>
                <div>
                    <div class="small text-muted">${escapeHtml(r.source)}</div>
                    <div>${escapeHtml(r.text)}</div>
                </div>
            </li>`;
        })
        .join("");

    resultRoot.innerHTML = `
        <div class="card shadow-sm border-0 mb-3">
            <div class="card-body text-center">
                <div class="small text-muted mb-1">Overall Risk Indicator</div>
                <div class="display-1 fw-bold text-${color}">${risk.risk_score ?? "-"}</div>
                <div class="h4 text-${color} mb-2">${escapeHtml(risk.risk_level || "UNKNOWN")}</div>
                <div class="badge bg-${color} fs-6 py-2 px-3">${escapeHtml(risk.recommendation || "")}</div>
            </div>
        </div>

        <div class="card shadow-sm border-0 mb-3">
            <div class="card-header bg-dark text-white"><strong>Component Scores</strong></div>
            <div class="card-body p-0">
                <table class="table table-sm mb-0 align-middle">
                    <tbody>${componentRows || '<tr><td class="text-muted p-3">No components.</td></tr>'}</tbody>
                </table>
            </div>
        </div>

        <div class="card shadow-sm border-0 mb-3">
            <div class="card-header bg-dark text-white"><strong>Why This Result?</strong></div>
            <ul class="list-group list-group-flush">
                ${reasonItems || '<li class="list-group-item text-muted">No explanatory reasons.</li>'}
            </ul>
        </div>

        <div class="card shadow-sm border-0 mb-3">
            <div class="card-header bg-dark text-white"><strong>Extracted Fields</strong></div>
            <div class="card-body p-0">
                <table class="table table-sm mb-0">
                    <tbody>${fieldsRows || '<tr><td class="text-muted p-3">No fields extracted.</td></tr>'}</tbody>
                </table>
            </div>
        </div>

        <div class="alert alert-secondary small mb-0">
            ${escapeHtml(risk.disclaimer || "Assistive signal only. Manual review required.")}
            <hr class="my-2">
            <div class="text-muted">
                Session: ${escapeHtml(data.session_id || "")} &middot;
                OCR confidence: ${data.ocr_confidence ?? "-"}% &middot;
                MRZ source: ${escapeHtml(data.mrz_source || "-")}
            </div>
        </div>
    `;
}

uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const docFile = document.getElementById("documentFile").files[0];
    if (!docFile) {
        alert("Please select a document.");
        return;
    }
    const selfieFile = document.getElementById("selfieFile").files[0];

    const fd = new FormData();
    fd.append("file", docFile);
    if (selfieFile) fd.append("selfie", selfieFile);

    submitBtn.disabled = true;
    submitBtn.textContent = "Processing...";
    progressBox.style.display = "block";
    tickProgress(0);
    resultRoot.innerHTML = '<div class="card shadow-sm border-0"><div class="card-body text-center py-5 text-muted">Analyzing...</div></div>';

    // animate through the stages while waiting
    let stageIdx = 1;
    const stageTimer = setInterval(() => {
        if (stageIdx < STAGES.length) {
            tickProgress(stageIdx);
            stageIdx++;
        }
    }, 900);

    try {
        const res = await fetch("/api/analyze", { method: "POST", body: fd });
        clearInterval(stageTimer);
        progressBar.style.width = "100%";
        progressBar.textContent = "100%";
        progressStage.textContent = "Complete";

        const data = await res.json();
        if (!res.ok) {
            resultRoot.innerHTML = `<div class="alert alert-danger"><strong>Error ${res.status}</strong><br>${escapeHtml(data.detail || "Unknown error")}</div>`;
            return;
        }
        renderResult(data);
    } catch (err) {
        clearInterval(stageTimer);
        resultRoot.innerHTML = `<div class="alert alert-danger">Network error: ${escapeHtml(err.message)}</div>`;
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Run Screening Pipeline";
    }
});
'''

with open("static/js/app.js", "w", encoding="utf-8") as f:
    f.write(content)

print("written app.js:", len(content), "chars")
