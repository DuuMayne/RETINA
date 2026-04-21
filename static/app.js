const API = '';

// ── State ──
let apps = [];
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
    renderApps();
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
                    <button class="secondary" onclick="openEditModal('${a.id}')">Edit</button>
                    <button class="danger" onclick="deleteApp('${a.id}')">Remove</button>
                </div>
            </div>
            <div style="font-size:0.8rem;color:var(--text-muted)">
                ${a.last_sync ? 'Last synced: ' + new Date(a.last_sync).toLocaleString() : 'Never synced'}
                ${a.base_url ? ' &middot; ' + esc(a.base_url) : ''}
            </div>
        </div>
    `).join('');
}

// ── Add app modal ──
function openAddModal() {
    const modal = document.getElementById('add-modal');
    const typeSelect = document.getElementById('conn-type');
    typeSelect.innerHTML = Object.keys(connectorMeta).map(k =>
        `<option value="${k}">${k.charAt(0).toUpperCase() + k.slice(1)}</option>`
    ).join('');
    renderCredFields();
    modal.classList.add('active');
}

function closeAddModal() {
    document.getElementById('add-modal').classList.remove('active');
}

function renderCredFields() {
    const type = document.getElementById('conn-type').value;
    const meta = connectorMeta[type];
    const container = document.getElementById('cred-fields');
    const baseUrlInput = document.getElementById('base-url');
    baseUrlInput.value = meta.default_base_url || '';

    container.innerHTML = meta.fields.map(f => `
        <div>
            <label>${esc(f.label)}</label>
            <input type="${f.type}" name="${f.name}" placeholder="${esc(f.label)}" required>
        </div>
    `).join('');
}

async function submitAddApp() {
    const name = document.getElementById('app-name').value.trim();
    const connectorType = document.getElementById('conn-type').value;
    const baseUrl = document.getElementById('base-url').value.trim();

    const credentials = {};
    document.querySelectorAll('#cred-fields input').forEach(inp => {
        credentials[inp.name] = inp.value;
    });

    if (!name) return alert('Name is required');

    try {
        await api('POST', '/api/applications', { name, connector_type: connectorType, credentials, base_url: baseUrl || null });
        closeAddModal();
        document.getElementById('app-name').value = '';
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
        alert('Sync failed: ' + e.message);
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
