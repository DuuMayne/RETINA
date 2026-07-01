let cycles = [];
let products = [];
let currentCycleId = null;
let currentItems = [];
let pendingItemAction = null;
let currentUserEmail = null;
let currentUserRole = null;
let pollTimer = null;

document.addEventListener('DOMContentLoaded', async () => {
    const me = await api('GET', '/auth/me');
    currentUserEmail = me.email;
    currentUserRole = me.role;

    if (currentUserRole !== 'admin') {
        document.querySelectorAll('#cycle-list-view button').forEach(b => { if (b.textContent.includes('New Cycle')) b.remove(); });
    }

    try {
        products = await api('GET', '/api/products');
    } catch (e) {
        products = []; // reviewers can't list products; only needed for the admin-only "new cycle" modal
    }
    await loadCycles();
});

async function api(method, url, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Request failed');
    }
    return res.json();
}

// ── List view ──
async function loadCycles() {
    cycles = await api('GET', '/api/cycles');
    renderCycleList();
}

function renderCycleList() {
    const list = document.getElementById('cycle-list');
    if (!cycles.length) {
        list.innerHTML = '<div class="empty">No review cycles yet.</div>';
        return;
    }
    list.innerHTML = cycles.map(c => {
        const pct = c.total_items ? Math.round(((c.total_items - c.pending_items) / c.total_items) * 100) : 0;
        const isOverdue = c.status === 'active' && new Date(c.due_date) < new Date();
        const statusClass = c.status === 'closed' ? 'closed' : (isOverdue ? 'overdue' : 'active');
        const statusLabel = c.status === 'closed' ? 'Closed' : (isOverdue ? 'Overdue' : 'Active');
        return `
        <div class="card cycle-card" onclick="openCycleDetail('${c.id}')">
            <div class="cycle-header">
                <h3>${esc(c.name)}<span class="cycle-status ${statusClass}">${statusLabel}</span></h3>
                <span style="font-size:0.8rem;color:var(--text-muted)">Due ${new Date(c.due_date).toLocaleDateString()}</span>
            </div>
            <div style="font-size:0.8rem;color:var(--text-muted);margin-top:0.25rem">
                ${c.generation_status === 'generating' ? 'Generating items&hellip;' : `${c.total_items - c.pending_items} of ${c.total_items} items resolved`}
                ${c.scope_all_applications ? ' &middot; All applications' : ''}
            </div>
            <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
        </div>`;
    }).join('');
}

// ── New Cycle modal ──
function openNewCycleModal() {
    document.getElementById('cycle-name').value = '';
    document.getElementById('cycle-due-date').value = '';
    document.querySelector('input[name="cycle-scope-type"][value="all"]').checked = true;
    toggleCycleScopeType();

    const checklist = document.getElementById('cycle-product-checklist');
    checklist.innerHTML = products.map(p => `
        <label><input type="checkbox" value="${p.id}"> ${esc(p.name)}</label>
    `).join('') || '<div class="empty" style="padding:0.5rem 0">No products configured yet.</div>';

    document.getElementById('new-cycle-modal').classList.add('active');
}

function closeNewCycleModal() {
    document.getElementById('new-cycle-modal').classList.remove('active');
}

function toggleCycleScopeType() {
    const type = document.querySelector('input[name="cycle-scope-type"]:checked').value;
    document.getElementById('cycle-product-checklist').style.display = type === 'products' ? 'block' : 'none';
}

async function submitNewCycle() {
    const name = document.getElementById('cycle-name').value.trim();
    const dueDate = document.getElementById('cycle-due-date').value;
    if (!name) return alert('Name is required');
    if (!dueDate) return alert('Due date is required');

    const scopeType = document.querySelector('input[name="cycle-scope-type"]:checked').value;
    const scopeAll = scopeType === 'all';
    const productIds = scopeAll ? [] : Array.from(document.querySelectorAll('#cycle-product-checklist input:checked')).map(el => el.value);
    if (!scopeAll && !productIds.length) return alert('Select at least one product');

    try {
        const result = await api('POST', '/api/cycles', { name, due_date: dueDate, scope_all_applications: scopeAll, product_ids: productIds });
        closeNewCycleModal();
        await loadCycles();
        openCycleDetail(result.id);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ── Detail view ──
function showListView() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    document.getElementById('cycle-detail-view').style.display = 'none';
    document.getElementById('cycle-list-view').style.display = 'block';
    loadCycles();
}

async function openCycleDetail(cycleId) {
    currentCycleId = cycleId;
    document.getElementById('cycle-list-view').style.display = 'none';
    document.getElementById('cycle-detail-view').style.display = 'block';
    switchDetailTab('items', document.querySelector('#cycle-detail-view .tab'));
    await refreshCycleDetail();

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        const c = await api('GET', `/api/cycles/${currentCycleId}`);
        if (c.generation_status !== 'generating') {
            clearInterval(pollTimer);
            pollTimer = null;
            await refreshCycleDetail();
        } else {
            renderCycleHeader(c);
        }
    }, 1500);
}

async function refreshCycleDetail() {
    const c = await api('GET', `/api/cycles/${currentCycleId}`);
    renderCycleHeader(c);
    await reloadCycleItems();
}

function renderCycleHeader(c) {
    const isOverdue = c.status === 'active' && new Date(c.due_date) < new Date();
    const statusClass = c.status === 'closed' ? 'closed' : (isOverdue ? 'overdue' : 'active');
    const statusLabel = c.status === 'closed' ? 'Closed' : (isOverdue ? 'Overdue' : 'Active');

    const warnings = (c.generation_summary && c.generation_summary.warnings) || [];

    document.getElementById('cycle-detail-header').innerHTML = `
        <div class="cycle-header" style="margin-bottom:0.5rem">
            <h2 style="margin:0">${esc(c.name)}<span class="cycle-status ${statusClass}">${statusLabel}</span></h2>
            <div class="btn-group">
                ${currentUserRole === 'admin' && c.status === 'active' ? `<button class="secondary" onclick="regenerateCycle()">Regenerate</button>` : ''}
                ${currentUserRole === 'admin' && c.status === 'active' ? `<button class="danger" onclick="closeCycle()">Close Cycle</button>` : ''}
            </div>
        </div>
        <div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:0.75rem">
            Due ${new Date(c.due_date).toLocaleDateString()} &middot;
            ${c.generation_status === 'generating' ? 'Generating items&hellip;' : `${c.total_items - c.pending_items} of ${c.total_items} resolved`}
            &middot; Created by ${esc(c.created_by)}
        </div>
        ${warnings.length ? `<div class="warning-box">${warnings.map(w => esc(w)).join('<br>')}</div>` : ''}
    `;
}

async function regenerateCycle() {
    if (!confirm('Re-sync in-scope applications and generate any missing items? Existing decisions are kept.')) return;
    await api('POST', `/api/cycles/${currentCycleId}/regenerate`);
    if (!pollTimer) {
        pollTimer = setInterval(async () => {
            const c = await api('GET', `/api/cycles/${currentCycleId}`);
            if (c.generation_status !== 'generating') {
                clearInterval(pollTimer);
                pollTimer = null;
                await refreshCycleDetail();
            } else {
                renderCycleHeader(c);
            }
        }, 1500);
    }
}

async function closeCycle() {
    if (!confirm('Close this cycle? It will stop sending reminders. This cannot be undone.')) return;
    await api('POST', `/api/cycles/${currentCycleId}/close`);
    await refreshCycleDetail();
}

function switchDetailTab(name, btn) {
    document.querySelectorAll('#cycle-detail-view .tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('detail-tab-items').style.display = name === 'items' ? '' : 'none';
    document.getElementById('detail-tab-audit').style.display = name === 'audit' ? '' : 'none';
    if (name === 'audit') loadCycleAuditLog();
}

// ── Items ──
async function reloadCycleItems() {
    const scope = document.getElementById('item-scope-toggle').value;
    currentItems = await api('GET', `/api/cycles/${currentCycleId}/items?scope=${scope}`);
    applyItemFilters();
}

function applyItemFilters() {
    const q = document.getElementById('item-search').value.toLowerCase();
    const status = document.getElementById('item-status-filter').value;
    const filtered = currentItems.filter(i =>
        (!q || i.user_email.includes(q) || (i.user_name || '').toLowerCase().includes(q)) &&
        (!status || i.status === status)
    );
    renderItemTable(filtered);
}

function renderItemTable(items) {
    const wrap = document.getElementById('item-table-wrap');
    if (!items.length) {
        wrap.innerHTML = '<div class="empty">No items match your filters.</div>';
        return;
    }
    const productsById = Object.fromEntries(products.map(p => [p.id, p.name]));
    wrap.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Product</th>
                    <th>Application</th>
                    <th>Email</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Notes</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${items.map(i => `
                    <tr>
                        <td>${i.product_id ? `<span class="tag">${esc(productsById[i.product_id] || '—')}</span>` : '—'}</td>
                        <td>${esc(i.application_name)}</td>
                        <td>${esc(i.user_email)}</td>
                        <td>${esc(i.user_name || '')}</td>
                        <td><span class="review-status ${i.status}">${esc(i.status)}</span></td>
                        <td class="notes-cell" title="${esc(i.notes)}">${esc(i.notes) || '—'}</td>
                        <td>
                            ${i.can_act ? `
                                <div class="action-btns">
                                    <button class="danger" onclick='openItemActionModal("flag", ${JSON.stringify(i)})'>Flag</button>
                                    <button onclick='openItemActionModal("approve", ${JSON.stringify(i)})'>Approve</button>
                                    ${i.status === 'flagged' ? `<button class="secondary" onclick='openItemActionModal("resolve", ${JSON.stringify(i)})'>Resolve</button>` : ''}
                                </div>
                            ` : '<span style="font-size:0.75rem;color:var(--text-muted)">Not assigned to you</span>'}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        <div style="margin-top:0.75rem;font-size:0.8rem;color:var(--text-muted)">${items.length} item${items.length !== 1 ? 's' : ''}</div>
    `;
}

function openItemActionModal(action, item) {
    pendingItemAction = { action, item };
    const titles = { flag: 'Flag for Removal', approve: 'Approve Access', resolve: 'Mark as Resolved' };
    const confirms = { flag: 'Flag', approve: 'Approve', resolve: 'Resolve' };
    const btnColors = { flag: 'danger', approve: '', resolve: 'secondary' };

    document.getElementById('item-modal-title').textContent = titles[action];
    document.getElementById('item-modal-sub').textContent = `${item.user_email} · ${item.application_name}`;
    document.getElementById('item-modal-notes').value = item.notes || '';
    const btn = document.getElementById('item-modal-confirm');
    btn.textContent = confirms[action];
    btn.className = btnColors[action] || '';
    document.getElementById('item-action-modal').classList.add('active');
}

function closeItemActionModal() {
    document.getElementById('item-action-modal').classList.remove('active');
    pendingItemAction = null;
}

async function submitItemAction() {
    if (!pendingItemAction) return;
    const { action, item } = pendingItemAction;
    const notes = document.getElementById('item-modal-notes').value.trim();
    try {
        await api('POST', `/api/cycles/${currentCycleId}/items/${item.id}/action`, { action, notes });
        closeItemActionModal();
        await refreshCycleDetail();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ── Audit log ──
async function loadCycleAuditLog() {
    const wrap = document.getElementById('audit-table-wrap');
    wrap.innerHTML = '<div class="empty"><span class="spinner"></span> Loading...</div>';
    const logs = await api('GET', `/api/cycles/${currentCycleId}/audit-log`);
    if (!logs.length) {
        wrap.innerHTML = '<div class="empty">No audit entries yet.</div>';
        return;
    }
    wrap.innerHTML = `
        <table>
            <thead>
                <tr><th>When</th><th>Action</th><th>By</th><th>User/Product</th><th>Details</th></tr>
            </thead>
            <tbody>
                ${logs.map(l => `
                    <tr>
                        <td style="font-size:0.8rem;color:var(--text-muted)">${new Date(l.created_at).toLocaleString()}</td>
                        <td><span class="audit-action ${l.action}">${esc(l.action)}</span></td>
                        <td>${esc(l.actor_email)}</td>
                        <td>${esc(l.target_email || l.application_name || '—')}</td>
                        <td style="font-size:0.8rem;color:var(--text-muted)">${esc(l.details || '—')}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// ── Export ──
function exportCycleCSV() {
    window.location.href = `/api/cycles/${currentCycleId}/export`;
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}
