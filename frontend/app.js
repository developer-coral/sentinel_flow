const statusEl = document.getElementById('status');
const outputEl = document.getElementById('output'); // Legacy fallback
const dashboardEl = document.getElementById('dashboardOutput');
const modal = document.getElementById('architectureModal');
const WEBHOOK_URL = "http://localhost:5678/webhook/sentinel_flow/document";

const SAMPLE_DOCUMENT = "./samples/contract.txt";

loadSampleDocument();

async function loadSampleDocument() {
  try {
    const response = await fetch(SAMPLE_DOCUMENT);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const text = await response.text();
    document.getElementById("documentText").value = text;
  } catch (err) {
    console.error("Failed to load sample document:", err);
    document.getElementById("documentText").placeholder =
      "Unable to load sample document.";
  }
}

// Elements for Dashboard Population
const dashTitle = document.getElementById('dashTitle');
const dashTypeBadge = document.getElementById('dashTypeBadge');
const dashRiskIndicator = document.getElementById('dashRiskIndicator');
const dashSummary = document.getElementById('dashSummary');
const dashFindingsList = document.getElementById('dashFindingsList');
const dashRisksList = document.getElementById('dashRisksList');
const dashActionsList = document.getElementById('dashActionsList');
const dashRoute = document.getElementById('dashRoute');
const dashConfidence = document.getElementById('dashConfidence');
const dashRiskLevel = document.getElementById('dashRiskLevel');
const dashMetricFindings = document.getElementById('dashMetricFindings');
const dashMetricRisks = document.getElementById('dashMetricRisks');
const dashMetricPlaceholders = document.getElementById('dashMetricPlaceholders');
const dashMetricAmounts = document.getElementById('dashMetricAmounts');

document.getElementById('diagramBtn').addEventListener('click', () => modal.showModal());
document.getElementById('closeModal').addEventListener('click', () => modal.close());

document.getElementById('submitBtn').addEventListener('click', async () => {
  // Check if email notification is enabled
  const enableEmail = document.getElementById('enableEmail')?.checked ?? true;
  
  const webhookUrlInput = document.getElementById('webhookUrl').value.trim();
  const finalWebhookUrl = webhookUrlInput || WEBHOOK_URL;
  
  const documentText = document.getElementById('documentText').value.trim();
  
  statusEl.className = 'status running';
  statusEl.textContent = 'Processing → n8n webhook → AI extraction → routing';
  
  // Reset views
  outputEl.style.display = 'none';
  dashboardEl.style.display = 'block';

  try {
    const response = await fetch(finalWebhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        document_text: documentText, 
        source: 'sentinel-portal', 
        submitted_at: new Date().toISOString(),
        simulate_email: enableEmail 
      })
    });

    const text = await response.text();
    let parsed;
    try { 
      parsed = JSON.parse(text); 
    } catch (e) { 
      parsed = { raw: text, error: "Failed to parse JSON response" }; 
    }

    statusEl.className = response.ok ? 'status done' : 'status error';
    statusEl.textContent = response.ok ? 'Execution Complete' : `Error ${response.status}`;

    // Check if we have the structured analysis payload
    if (parsed.ok && parsed.analysis) {
      renderDashboard(parsed);
      logToConsole("Raw Response:", parsed); // Keep raw data accessible
    } else {
      // Fallback to legacy view if structure is wrong
      console.warn("Unexpected response structure, showing raw JSON");
      dashboardEl.style.display = 'none';
      outputEl.style.display = 'block';
      outputEl.textContent = JSON.stringify(parsed, null, 2);
    }

  } catch (error) {
    statusEl.className = 'status error';
    statusEl.textContent = 'Request failed';
    console.error(error);
    
    // Show error in dashboard too if possible
    if(dashboardEl.style.display !== 'none') {
       dashSummary.textContent = "Connection failed: " + error.message;
       dashFindingsList.innerHTML = "<li>Unable to reach backend service.</li>";
    }
  }
});

function logToConsole(title, data) {
  console.group(title);
  console.log(data);
  console.groupEnd();
}

function renderDashboard(data) {
  const a = data.analysis;
  const m = data.metrics || {};
  const r = data.result || {};

  // Header
  dashTitle.textContent = a.title || "Document Analysis";
  dashTypeBadge.textContent = `Type: ${(r.document_type || 'Unknown').replace('_', ' ').toUpperCase()}`;
  
  // Risk Indicator Styling
  const riskVal = (a.risk_level || '').toLowerCase();
  dashRiskIndicator.className = `risk-indicator ${riskVal}-risk`;
  dashRiskIndicator.innerHTML = `<span class="risk-dot"></span> ${riskVal.toUpperCase()} RISK`;
  dashRiskLevel.textContent = riskVal.toUpperCase();

  // Main Content
  dashSummary.textContent = a.executive_summary || "No summary available.";
  
  // Lists
  fillList(dashFindingsList, data.findings || []);
  fillList(dashRisksList, data.risks || []);
  fillList(dashActionsList, data.recommendations || []);

  // Workflow Details
  dashRoute.textContent = (a.workflow_decision || '-').charAt(0).toUpperCase() + (a.workflow_decision || '-').slice(1);
  dashConfidence.textContent = `${Math.round((a.confidence || 0) * 100)}%`;

  // Metrics
  dashMetricFindings.textContent = m.findings_count || 0;
  dashMetricRisks.textContent = m.risks_count || 0;
  dashMetricPlaceholders.textContent = m.placeholders_found || 0;
  dashMetricAmounts.textContent = m.monetary_values_found || 0;
}

function fillList(element, items) {
  element.innerHTML = '';
  if (!items || items.length === 0) {
    element.innerHTML = '<li>No items detected.</li>';
    return;
  }
  items.forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    element.appendChild(li);
  });
}