const API = '';

// ── State ──
let apps = [];
let schedules = {};
let connectorMeta = {};
let currentAppId = null;
let currentUsers = [];

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
    connectorMeta = await api('GET', '/api/connectors');
    await loadApps();
});

// ── API helper ──
async function api(method, url, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API + url, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Request failed');
    }
    return res.json();
}

// ── Load apps ──
async function loadApps() {
    apps = await api('GET', '/api/applications');
    const scheduleList = await api('GET', '/api/schedules');
    schedules = Object.fromEntries(scheduleList.map(s => [s.app_id, s]));
    renderApps();
}

function scheduleLabel(appId) {
    const s = schedules[appId];
    if (!s || !s.sync_enabled || !s.sync_schedule) return 'Manual sync only';
    const labels = { hourly: 'Hourly', every_6_hours: 'Every 6 hours', daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly' };
    return 'Scheduled: ' + (labels[s.sync_schedule] || s.sync_schedule);
}

function renderApps() {
    const list = document.getElementById('app-list');
    if (!apps.length) {
        list.innerHTML = '<div class="empty">No applications configured. Add one above.</div>';
        return;
    }
    list.innerHTML = apps.map(a => `
        <div class="card">
            <div class="card-header">
                <h3>${esc(a.name)} <span class="tag">${esc(a.connector_type)}</span></h3>
                <div class="btn-group">
                    <button onclick="syncApp('${a.id}', this)">Pull Access</button>
                    <button class="secondary" onclick="viewSnapshots('${a.id}')">History</button>
                    <button class="secondary" onclick="openScheduleModal('${a.id}')">Schedule</button>
                    <button class="secondary" onclick="openEditModal('${a.id}')">Edit</button>
                    <button class="danger" onclick="deleteApp('${a.id}')">Remove</button>
                </div>
            </div>
            <div style="font-size:0.8rem;color:var(--text-muted)">
                ${a.last_sync ? 'Last synced: ' + new Date(a.last_sync).toLocaleString() : 'Never synced'}
                &middot; ${scheduleLabel(a.id)}
                ${a.base_url ? ' &middot; ' + esc(a.base_url) : ''}
            </div>
        </div>
    `).join('');
}

// ── Schedule modal ──
function openScheduleModal(appId) {
    const app = apps.find(a => a.id === appId);
    const current = schedules[appId];
    document.getElementById('schedule-app-id').value = appId;
    document.getElementById('schedule-app-name').textContent = app ? app.name : '';
    document.getElementById('schedule-preset').value = (current && current.sync_enabled) ? (current.sync_schedule || '') : '';
    document.getElementById('schedule-modal').classList.add('active');
}

function closeScheduleModal() {
    document.getElementById('schedule-modal').classList.remove('active');
}

async function submitSchedule() {
    const appId = document.getElementById('schedule-app-id').value;
    const preset = document.getElementById('schedule-preset').value;
    try {
        await api('PUT', `/api/applications/${appId}/schedule`, {
            schedule: preset,
            enabled: !!preset,
        });
        closeScheduleModal();
        await loadApps();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ── Connector categories ──
const CONNECTOR_CATEGORIES = {
    'Identity & Access': ['okta', 'entra_id', 'google_workspace', 'jumpcloud', 'duo', 'onepassword'],
    'MDM & Endpoint': ['jamf', 'kandji', 'sentinelone', 'crowdstrike', 'unifi'],
    'Cloud & Infrastructure': ['aws', 'cloudflare', 'snowflake', 'mongodb_atlas', 'terraform_cloud'],
    'DevOps & Engineering': ['github', 'gitlab', 'docker_hub', 'npm', 'snyk', 'airflow'],
    'Collaboration': ['slack', 'atlassian', 'zendesk', 'zoom', 'webex', 'figma'],
    'Business & CRM': ['salesforce', 'hubspot', 'docusign', 'servicenow'],
    'HR': ['workday', 'bamboohr'],
    'Security & Compliance': ['vanta', 'splunk', 'lacework', 'hackerone', 'cisco_umbrella'],
    'Observability': ['datadog', 'newrelic', 'pagerduty', 'looker'],
    'File Storage': ['box', 'dropbox', 'files_com'],
    'Other': ['sendgrid', 'segment', 'hellosign', 'namecheap', 'experian'],
};

function connectorDisplayName(key) {
    const names = {
        aws: 'AWS IAM', entra_id: 'Microsoft Entra ID', google_workspace: 'Google Workspace',
        crowdstrike: 'CrowdStrike', sentinelone: 'SentinelOne', pagerduty: 'PagerDuty',
        newrelic: 'New Relic', hackerone: 'HackerOne', cisco_umbrella: 'Cisco Umbrella',
        docker_hub: 'Docker Hub', mongodb_atlas: 'MongoDB Atlas', terraform_cloud: 'Terraform Cloud',
        sendgrid: 'SendGrid', hellosign: 'HelloSign', files_com: 'Files.com',
        bamboohr: 'BambooHR', hubspot: 'HubSpot', servicenow: 'ServiceNow',
        jumpcloud: 'JumpCloud', onepassword: '1Password', docusign: 'DocuSign',
        npm: 'npm', gitlab: 'GitLab',
    };
    return names[key] || key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
}

let selectedConnectorType = null;

// ── Add app modal ──
function openAddModal() {
    const modal = document.getElementById('add-modal');
    selectedConnectorType = null;
    document.getElementById('app-name').value = '';
    document.getElementById('base-url').value = '';
    document.getElementById('cred-fields').innerHTML = '';
    document.getElementById('conn-config').style.display = 'none';
    renderConnectorPicker('');
    modal.classList.add('active');
    setTimeout(() => document.getElementById('conn-search').focus(), 100);
}

function closeAddModal() {
    document.getElementById('add-modal').classList.remove('active');
}

function renderConnectorPicker(query) {
    const grid = document.getElementById('conn-picker-grid');
    const q = query.toLowerCase();
    const available = Object.keys(connectorMeta);

    // Build categorized list, filtering by search
    let html = '';
    const categorized = new Set();

    for (const [category, keys] of Object.entries(CONNECTOR_CATEGORIES)) {
        const matches = keys.filter(k => available.includes(k) && (
            !q || k.includes(q) || connectorDisplayName(k).toLowerCase().includes(q) || category.toLowerCase().includes(q)
        ));
        if (!matches.length) continue;
        matches.forEach(k => categorized.add(k));

        html += `<div class="picker-category">${esc(category)}</div>`;
        html += '<div class="picker-row">';
        html += matches.map(k => `
            <button type="button" class="picker-item ${selectedConnectorType === k ? 'selected' : ''}"
                    onclick="selectConnector('${k}')">
                ${esc(connectorDisplayName(k))}
            </button>
        `).join('');
        html += '</div>';
    }

    // Uncategorized connectors
    const uncategorized = available.filter(k => !categorized.has(k) && (
        !q || k.includes(q) || connectorDisplayName(k).toLowerCase().includes(q)
    ));
    if (uncategorized.length) {
        html += '<div class="picker-category">Other</div>';
        html += '<div class="picker-row">';
        html += uncategorized.map(k => `
            <button type="button" class="picker-item ${selectedConnectorType === k ? 'selected' : ''}"
                    onclick="selectConnector('${k}')">
                ${esc(connectorDisplayName(k))}
            </button>
        `).join('');
        html += '</div>';
    }

    if (!html) {
        html = '<div class="empty" style="padding:1rem">No connectors match your search.</div>';
    }

    grid.innerHTML = html;
}

function selectConnector(type) {
    selectedConnectorType = type;
    const meta = connectorMeta[type];

    // Update picker selection state
    document.querySelectorAll('.picker-item').forEach(el => el.classList.remove('selected'));
    event.target.classList.add('selected');

    // Show config section
    const config = document.getElementById('conn-config');
    config.style.display = 'block';
    document.getElementById('selected-conn-name').textContent = connectorDisplayName(type);
    document.getElementById('base-url').value = meta.default_base_url || '';

    const container = document.getElementById('cred-fields');
    container.innerHTML = meta.fields.map(f => `
        <div>
            <label>${esc(f.label)}</label>
            <input type="${f.type}" name="${f.name}" placeholder="${esc(f.label)}" required>
        </div>
    `).join('');

    // Scroll config into view within modal
    config.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function testConnection() {
    if (!selectedConnectorType) return alert('Select a connector first');

    const baseUrl = document.getElementById('base-url').value.trim();
    const credentials = {};
    document.querySelectorAll('#cred-fields input').forEach(inp => {
        credentials[inp.name] = inp.value;
    });

    const testBtn = document.querySelector('#conn-config .test-btn');
    const resultDiv = document.getElementById('test-result');

    testBtn.disabled = true;
    testBtn.innerHTML = '<span class="spinner"></span>Testing...';
    resultDiv.innerHTML = '';
    resultDiv.className = 'test-result';

    try {
        const resp = await fetch(API + '/api/connectors/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                connector_type: selectedConnectorType,
                credentials,
                base_url: baseUrl || null,
            })
        });
        const result = await resp.json();

        if (result.success) {
            resultDiv.className = 'test-result success';
            resultDiv.innerHTML = `
                <strong>✓ ${esc(result.message)}</strong>
                ${result.sample_user ? `<div style="font-size:0.85rem;margin-top:0.25rem">Sample: ${esc(result.sample_user.name || result.sample_user.email || result.sample_user.id)}</div>` : ''}
            `;
        } else {
            resultDiv.className = 'test-result error';
            resultDiv.innerHTML = `
                <strong>✗ ${esc(result.title)}</strong>
                <div style="margin-top:0.5rem">${esc(result.message)}</div>
                ${result.suggestions && result.suggestions.length ? `
                    <div style="margin-top:0.5rem;font-size:0.85rem">
                        <strong>Suggestions:</strong>
                        <ul style="margin:0.25rem 0 0 1.25rem;padding:0">
                            ${result.suggestions.map(s => `<li>${esc(s)}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
                <details style="margin-top:0.5rem;font-size:0.75rem">
                    <summary style="cursor:pointer;color:var(--text-muted)">Technical details</summary>
                    <pre style="margin-top:0.25rem;padding:0.5rem;background:var(--bg-secondary);border-radius:4px;overflow-x:auto">${esc(result.raw_error)}</pre>
                </details>
            `;
        }
    } catch (e) {
        resultDiv.className = 'test-result error';
        resultDiv.innerHTML = `<strong>✗ Test Failed</strong><div style="margin-top:0.5rem">${esc(e.message)}</div>`;
    } finally {
        testBtn.disabled = false;
        testBtn.textContent = 'Test Connection';
    }
}

async function submitAddApp() {
    const name = document.getElementById('app-name').value.trim();
    const baseUrl = document.getElementById('base-url').value.trim();

    if (!selectedConnectorType) return alert('Select a connector first');
    if (!name) return alert('Name is required');

    const credentials = {};
    document.querySelectorAll('#cred-fields input').forEach(inp => {
        credentials[inp.name] = inp.value;
    });

    try {
        await api('POST', '/api/applications', { name, connector_type: selectedConnectorType, credentials, base_url: baseUrl || null });
        closeAddModal();
        await loadApps();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ── Sync ──
async function syncApp(appId, btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Syncing...';
    try {
        const result = await api('POST', `/api/applications/${appId}/sync`);
        currentAppId = appId;
        currentUsers = result.users;
        showUsersPanel(apps.find(a => a.id === appId)?.name || 'App');
        await loadApps();
    } catch (e) {
        // Try to extract diagnosis from error detail
        let message = e.message;
        try {
            const resp = await fetch(API + `/api/applications/${appId}/sync`, { method: 'POST' });
            if (!resp.ok) {
                const detail = await resp.json().catch(() => null);
                if (detail && detail.detail && detail.detail.diagnosis) {
                    const diag = detail.detail.diagnosis;
                    message = `${diag.title}\n\n${diag.message}`;
                    if (diag.suggestions && diag.suggestions.length) {
                        message += '\n\nSuggestions:\n' + diag.suggestions.map(s => '• ' + s).join('\n');
                    }
                }
            }
        } catch {}
        alert('Sync failed:\n\n' + message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Pull Access';
    }
}

// ── View snapshots ──
async function viewSnapshots(appId) {
    currentAppId = appId;
    const snaps = await api('GET', `/api/applications/${appId}/snapshots`);
    if (!snaps.length) return alert('No snapshots yet. Pull access first.');

    // Load the latest snapshot
    const snap = await api('GET', `/api/snapshots/${snaps[0].id}`);
    currentUsers = snap.users;

    const appName = apps.find(a => a.id === appId)?.name || 'App';
    showUsersPanel(appName, snaps);
}

// ── Users panel ──
function showUsersPanel(appName, snapshots) {
    const panel = document.getElementById('users-panel');
    const snapBar = snapshots ? `
        <div class="snapshot-bar">
            <h2>${esc(appName)} - Entitlement Review</h2>
            <select class="snapshot-select" onchange="loadSnapshot(this.value)">
                ${snapshots.map(s => `<option value="${s.id}">${new Date(s.synced_at).toLocaleString()} (${s.user_count} users)</option>`).join('')}
            </select>
        </div>
    ` : `<h2>${esc(appName)} - Entitlement Review</h2>`;

    panel.innerHTML = `
        ${snapBar}
        <input type="text" class="search-input" placeholder="Search by name, email, or role..." oninput="filterUsers(this.value)">
        <div id="users-table-wrap"></div>
    `;
    panel.style.display = 'block';
    renderUsersTable(currentUsers);
}

async function loadSnapshot(snapId) {
    const snap = await api('GET', `/api/snapshots/${snapId}`);
    currentUsers = snap.users;
    renderUsersTable(currentUsers);
}

function filterUsers(query) {
    const q = query.toLowerCase();
    const filtered = currentUsers.filter(u =>
        u.name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        u.roles.some(r => r.toLowerCase().includes(q))
    );
    renderUsersTable(filtered);
}

function renderUsersTable(users) {
    const wrap = document.getElementById('users-table-wrap');
    if (!users.length) {
        wrap.innerHTML = '<div class="empty">No users found.</div>';
        return;
    }
    wrap.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Roles</th>
                    <th>Last Login</th>
                </tr>
            </thead>
            <tbody>
                ${users.map(u => `
                    <tr>
                        <td>${esc(u.name)}</td>
                        <td>${esc(u.email)}</td>
                        <td><span class="status-${u.status === 'active' ? 'active' : 'inactive'}">${esc(u.status)}</span></td>
                        <td>${u.roles.map(r => `<span class="tag">${esc(r)}</span>`).join(' ')}</td>
                        <td>${u.last_login ? new Date(u.last_login).toLocaleDateString() : '—'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        <div style="margin-top:0.75rem;font-size:0.8rem;color:var(--text-muted)">${users.length} user${users.length !== 1 ? 's' : ''}</div>
    `;
}

// ── Edit app modal ──
async function openEditModal(appId) {
    const appData = await api('GET', `/api/applications/${appId}`);
    const meta = connectorMeta[appData.connector_type];
    const modal = document.getElementById('edit-modal');

    document.getElementById('edit-app-id').value = appId;
    document.getElementById('edit-app-name').value = appData.name;
    document.getElementById('edit-base-url').value = appData.base_url || '';
    document.getElementById('edit-conn-type').textContent = appData.connector_type.charAt(0).toUpperCase() + appData.connector_type.slice(1);

    const container = document.getElementById('edit-cred-fields');
    container.innerHTML = meta.fields.map(f => `
        <div>
            <label>${esc(f.label)}</label>
            <input type="${f.type}" name="${f.name}" placeholder="Leave unchanged" value="${esc(appData.credentials[f.name] || '')}">
        </div>
    `).join('');

    modal.classList.add('active');
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.remove('active');
}

async function testEditConnection() {
    const appId = document.getElementById('edit-app-id').value;
    const app = apps.find(a => a.id === appId);
    if (!app) return alert('Application not found');

    const baseUrl = document.getElementById('edit-base-url').value.trim();
    const credentials = {};
    document.querySelectorAll('#edit-cred-fields input').forEach(inp => {
        credentials[inp.name] = inp.value;
    });

    const testBtn = document.querySelector('#edit-modal .test-btn');
    const resultDiv = document.getElementById('edit-test-result');

    testBtn.disabled = true;
    testBtn.innerHTML = '<span class="spinner"></span>Testing...';
    resultDiv.innerHTML = '';
    resultDiv.className = 'test-result';

    try {
        const resp = await fetch(API + '/api/connectors/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                connector_type: app.connector_type,
                credentials,
                base_url: baseUrl || null,
            })
        });
        const result = await resp.json();

        if (result.success) {
            resultDiv.className = 'test-result success';
            resultDiv.innerHTML = `
                <strong>✓ ${esc(result.message)}</strong>
                ${result.sample_user ? `<div style="font-size:0.85rem;margin-top:0.25rem">Sample: ${esc(result.sample_user.name || result.sample_user.email || result.sample_user.id)}</div>` : ''}
            `;
        } else {
            resultDiv.className = 'test-result error';
            resultDiv.innerHTML = `
                <strong>✗ ${esc(result.title)}</strong>
                <div style="margin-top:0.5rem">${esc(result.message)}</div>
                ${result.suggestions && result.suggestions.length ? `
                    <div style="margin-top:0.5rem;font-size:0.85rem">
                        <strong>Suggestions:</strong>
                        <ul style="margin:0.25rem 0 0 1.25rem;padding:0">
                            ${result.suggestions.map(s => `<li>${esc(s)}</li>`).join('')}
                        </ul>
                    </div>
                ` : ''}
                <details style="margin-top:0.5rem;font-size:0.75rem">
                    <summary style="cursor:pointer;color:var(--text-muted)">Technical details</summary>
                    <pre style="margin-top:0.25rem;padding:0.5rem;background:var(--bg-secondary);border-radius:4px;overflow-x:auto">${esc(result.raw_error)}</pre>
                </details>
            `;
        }
    } catch (e) {
        resultDiv.className = 'test-result error';
        resultDiv.innerHTML = `<strong>✗ Test Failed</strong><div style="margin-top:0.5rem">${esc(e.message)}</div>`;
    } finally {
        testBtn.disabled = false;
        testBtn.textContent = 'Test Connection';
    }
}

async function submitEditApp() {
    const appId = document.getElementById('edit-app-id').value;
    const name = document.getElementById('edit-app-name').value.trim();
    const baseUrl = document.getElementById('edit-base-url').value.trim();

    const credentials = {};
    document.querySelectorAll('#edit-cred-fields input').forEach(inp => {
        credentials[inp.name] = inp.value;
    });

    if (!name) return alert('Name is required');

    try {
        await api('PUT', `/api/applications/${appId}`, { name, base_url: baseUrl || null, credentials });
        closeEditModal();
        await loadApps();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ── Delete ──
async function deleteApp(appId) {
    if (!confirm('Remove this application and all its snapshots?')) return;
    await api('DELETE', `/api/applications/${appId}`);
    await loadApps();
    document.getElementById('users-panel').style.display = 'none';
}

// ── CSV Export ──
function exportCSV() {
    if (!currentUsers.length) return;
    const headers = ['Name', 'Email', 'Status', 'Roles', 'Last Login', 'Created At'];
    const rows = currentUsers.map(u => [
        u.name, u.email, u.status,
        u.roles.join('; '),
        u.last_login || '', u.created_at || ''
    ]);
    const csv = [headers, ...rows].map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `retina_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
}

// ── Cross-Reference View ──
async function showCrossRef() {
    const panel = document.getElementById('crossref-panel');
    const usersPanel = document.getElementById('users-panel');
    usersPanel.style.display = 'none';

    panel.style.display = 'block';
    panel.innerHTML = '<div class="empty"><span class="spinner"></span> Running cross-reference against Okta...</div>';

    try {
        const data = await api('GET', '/api/cross-reference');
        renderCrossRef(data);
    } catch (e) {
        panel.innerHTML = `<div class="card"><p style="color:var(--danger)">${esc(e.message)}</p><p style="font-size:0.85rem;color:var(--text-muted)">Make sure you have an Okta connector configured and synced.</p></div>`;
    }
}

function renderCrossRef(data) {
    const panel = document.getElementById('crossref-panel');
    const { flags_summary: flags } = data;

    panel.innerHTML = `
        <div class="card">
            <h2>Cross-Reference: Okta Identity Baseline</h2>
            <p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:1rem">
                Comparing ${data.total_entitlements} entitlements across ${data.apps_reviewed} applications against ${data.okta_user_count} Okta identities.
            </p>

            <div class="crossref-summary">
                <div class="crossref-stat">
                    <span class="crossref-num ${flags.not_in_okta > 0 ? 'danger' : ''}">${flags.not_in_okta}</span>
                    <span class="crossref-label">Not in Okta</span>
                </div>
                <div class="crossref-stat">
                    <span class="crossref-num ${flags.okta_inactive > 0 ? 'danger' : ''}">${flags.okta_inactive}</span>
                    <span class="crossref-label">Okta Inactive</span>
                </div>
                <div class="crossref-stat">
                    <span class="crossref-num ${flags.stale_access > 0 ? 'warning' : ''}">${flags.stale_access}</span>
                    <span class="crossref-label">Stale (90+ days)</span>
                </div>
                <div class="crossref-stat">
                    <span class="crossref-num ${flags.mfa_disabled > 0 ? 'warning' : ''}">${flags.mfa_disabled}</span>
                    <span class="crossref-label">MFA Disabled</span>
                </div>
            </div>
        </div>

        ${data.applications.map(app => `
            <div class="card" style="margin-top:1rem">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
                    <h3>${esc(app.app_name)} <span class="tag">${esc(app.connector_type)}</span></h3>
                    <span style="font-size:0.8rem;color:var(--text-muted)">
                        ${app.total_users} users &middot; <span style="color:var(--danger)">${app.flagged_users} flagged</span>
                    </span>
                </div>
                ${app.flagged_users > 0 ? `
                    <table>
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Email</th>
                                <th>App Status</th>
                                <th>Okta Status</th>
                                <th>Roles</th>
                                <th>Last Login</th>
                                <th>Flags</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${app.users.filter(u => u.flags.length > 0).map(u => `
                                <tr>
                                    <td>${esc(u.name)}</td>
                                    <td>${esc(u.email)}</td>
                                    <td><span class="status-${u.app_status === 'active' ? 'active' : 'inactive'}">${esc(u.app_status)}</span></td>
                                    <td><span class="status-${u.okta_status === 'ACTIVE' || u.okta_status === 'active' ? 'active' : 'inactive'}">${esc(u.okta_status)}</span></td>
                                    <td>${u.roles.slice(0, 3).map(r => `<span class="tag">${esc(r)}</span>`).join(' ')}${u.roles.length > 3 ? ` <span class="tag">+${u.roles.length - 3}</span>` : ''}</td>
                                    <td>${u.last_login ? new Date(u.last_login).toLocaleDateString() : '—'}</td>
                                    <td>${u.flags.map(f => `<span class="flag flag-${f.startsWith('stale') || f === 'mfa_disabled' || f === 'no_login_data' ? 'warning' : 'danger'}">${esc(formatFlag(f))}</span>`).join(' ')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                ` : `<p style="font-size:0.85rem;color:var(--text-muted)">No flagged users. All entitlements match Okta.</p>`}
            </div>
        `).join('')}
    `;
}

function formatFlag(flag) {
    if (flag === 'not_in_okta') return 'Not in Okta';
    if (flag === 'okta_inactive') return 'Okta Inactive';
    if (flag === 'mfa_disabled') return 'No MFA';
    if (flag === 'no_login_data') return 'No login data';
    if (flag === 'no_email') return 'No email';
    if (flag.startsWith('stale_')) return `Stale (${flag.replace('stale_', '').replace('d', '')} days)`;
    return flag;
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}
