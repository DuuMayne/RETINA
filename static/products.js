let products = [];
let applications = [];

document.addEventListener('DOMContentLoaded', async () => {
    applications = await api('GET', '/api/applications');
    await loadProducts();
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

async function loadProducts() {
    products = await api('GET', '/api/products');
    const details = await Promise.all(products.map(p => api('GET', `/api/products/${p.id}`)));
    renderProducts(details);
}

function renderProducts(details) {
    const list = document.getElementById('product-list');
    if (!details.length) {
        list.innerHTML = '<div class="empty">No products yet. Add one to start scoping review cycles by team or service.</div>';
        return;
    }
    list.innerHTML = details.map(p => `
        <div class="card product-card">
            <div class="product-header">
                <div>
                    <h3>${esc(p.name)}</h3>
                    <div class="product-meta">${p.description ? esc(p.description) + ' &middot; ' : ''}${p.has_slack_webhook ? 'Slack webhook configured' : 'No Slack webhook'}</div>
                </div>
                <div class="btn-group">
                    <button class="secondary" onclick='openEditProductModal(${JSON.stringify(p)})'>Edit</button>
                    <button class="danger" onclick="deleteProduct('${p.id}')">Delete</button>
                </div>
            </div>

            <div class="section-label">Application scopes</div>
            ${p.scopes.map(s => `
                <div class="scope-row">
                    <div>
                        <strong>${esc(s.application_name)}</strong>
                        ${s.filter_field ? `<div class="scope-filter">${esc(s.filter_field)} ${esc(s.filter_match)} "${esc(s.filter_value)}"</div>` : '<div class="scope-filter">All users</div>'}
                    </div>
                    <button class="danger" onclick="deleteScope('${p.id}', '${s.id}')">Remove</button>
                </div>
            `).join('') || '<div class="empty" style="padding:0.75rem">No applications scoped yet.</div>'}
            <button class="secondary" style="margin-top:0.5rem" onclick="openScopeAddModal('${p.id}')">+ Add Scope</button>

            <div class="section-label">Reviewers</div>
            ${p.reviewers.length ? p.reviewers.map(r => `<span class="reviewer-chip">${esc(r)}</span>`).join('') : '<div class="empty" style="padding:0.5rem 0">No reviewers assigned.</div>'}
            <button class="secondary" style="margin-top:0.5rem;display:block" onclick='openReviewersModal("${p.id}", ${JSON.stringify(p.reviewers)})'>Manage Reviewers</button>
        </div>
    `).join('');
}

// ── Add/Edit Product ──
function openAddProductModal() {
    document.getElementById('product-modal-title').textContent = 'Add Product';
    document.getElementById('product-id').value = '';
    document.getElementById('product-name').value = '';
    document.getElementById('product-description').value = '';
    document.getElementById('product-webhook').value = '';
    document.getElementById('product-modal').classList.add('active');
}

function openEditProductModal(p) {
    document.getElementById('product-modal-title').textContent = 'Edit Product';
    document.getElementById('product-id').value = p.id;
    document.getElementById('product-name').value = p.name;
    document.getElementById('product-description').value = p.description || '';
    document.getElementById('product-webhook').value = '';
    document.getElementById('product-modal').classList.add('active');
}

function closeProductModal() {
    document.getElementById('product-modal').classList.remove('active');
}

async function submitProduct() {
    const id = document.getElementById('product-id').value;
    const name = document.getElementById('product-name').value.trim();
    const description = document.getElementById('product-description').value.trim();
    const webhook = document.getElementById('product-webhook').value.trim();
    if (!name) return alert('Name is required');

    try {
        if (id) {
            const body = { name, description };
            if (webhook) body.slack_webhook_url = webhook;
            await api('PUT', `/api/products/${id}`, body);
        } else {
            await api('POST', '/api/products', { name, description, slack_webhook_url: webhook || null });
        }
        closeProductModal();
        await loadProducts();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function deleteProduct(id) {
    if (!confirm('Delete this product? Its scopes and reviewer list will be removed. Any review cycles that already ran against it keep their historical data.')) return;
    await api('DELETE', `/api/products/${id}`);
    await loadProducts();
}

// ── Scopes ──
function openScopeAddModal(productId) {
    document.getElementById('scope-product-id').value = productId;
    document.getElementById('scope-filter-field').value = '';
    document.getElementById('scope-filter-match').value = 'contains';
    document.getElementById('scope-filter-value').value = '';
    document.getElementById('scope-preview-result').innerHTML = '';

    const select = document.getElementById('scope-app-select');
    select.innerHTML = applications.map(a => `<option value="${a.id}">${esc(a.name)} (${esc(a.connector_type)})</option>`).join('');

    document.getElementById('scope-modal').classList.add('active');
}

function closeScopeAddModal() {
    document.getElementById('scope-modal').classList.remove('active');
}

async function previewScope() {
    const productId = document.getElementById('scope-product-id').value;
    const applicationId = document.getElementById('scope-app-select').value;
    const filterField = document.getElementById('scope-filter-field').value.trim();
    const filterMatch = document.getElementById('scope-filter-match').value;
    const filterValue = document.getElementById('scope-filter-value').value.trim();

    const params = new URLSearchParams({ application_id: applicationId, filter_field: filterField, filter_match: filterMatch, filter_value: filterValue });
    try {
        const result = await api('GET', `/api/products/${productId}/preview-scope?${params}`);
        const box = document.getElementById('scope-preview-result');
        box.className = 'preview-result' + (result.warning ? ' warn' : '');
        box.innerHTML = `Matches <strong>${result.matched_count}</strong> of ${result.total_users} users in the latest snapshot.` +
            (result.warning ? `<br>${esc(result.warning)}` : '') +
            (result.sample.length ? `<br><span style="color:var(--text-muted)">e.g. ${result.sample.map(s => esc(s.email)).join(', ')}</span>` : '');
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function submitScope() {
    const productId = document.getElementById('scope-product-id').value;
    const body = {
        application_id: document.getElementById('scope-app-select').value,
        filter_field: document.getElementById('scope-filter-field').value.trim(),
        filter_match: document.getElementById('scope-filter-match').value,
        filter_value: document.getElementById('scope-filter-value').value.trim(),
    };
    try {
        await api('POST', `/api/products/${productId}/scopes`, body);
        closeScopeAddModal();
        await loadProducts();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function deleteScope(productId, scopeId) {
    if (!confirm('Remove this application from the product?')) return;
    await api('DELETE', `/api/products/${productId}/scopes/${scopeId}`);
    await loadProducts();
}

// ── Reviewers ──
function openReviewersModal(productId, currentReviewers) {
    document.getElementById('reviewers-product-id').value = productId;
    document.getElementById('reviewers-textarea').value = currentReviewers.join('\n');
    document.getElementById('reviewers-modal').classList.add('active');
}

function closeReviewersModal() {
    document.getElementById('reviewers-modal').classList.remove('active');
}

async function submitReviewers() {
    const productId = document.getElementById('reviewers-product-id').value;
    const emails = document.getElementById('reviewers-textarea').value
        .split('\n').map(e => e.trim()).filter(Boolean);
    try {
        await api('PUT', `/api/products/${productId}/reviewers`, { emails });
        closeReviewersModal();
        await loadProducts();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}
