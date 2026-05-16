/**
 * Price Tracker — Frontend Application
 *
 * Handles: API calls, DOM rendering, particles canvas, toast notifications,
 *          product CRUD, price history modal, and real-time price checks.
 */

const API = "";  // same-origin

// ─── State ───────────────────────────────────────────────────────────
let products = [];

// ─── DOM refs ────────────────────────────────────────────────────────
const $grid        = document.getElementById("products-grid");
const $empty       = document.getElementById("empty-state");
const $form        = document.getElementById("add-form");
const $btnAdd      = document.getElementById("btn-add");
const $btnCheckAll = document.getElementById("btn-check-all");
const $statTotal   = document.getElementById("stat-total-value");
const $statBelow   = document.getElementById("stat-below-value");
const $statAbove   = document.getElementById("stat-above-value");
const $modalOverlay = document.getElementById("modal-overlay");
const $modalTitle   = document.getElementById("modal-title");
const $modalBody    = document.getElementById("modal-body");
const $modalClose   = document.getElementById("modal-close");
const $toastContainer = document.getElementById("toast-container");


// =====================================================================
// PARTICLES BACKGROUND
// =====================================================================
(function initParticles() {
    const canvas = document.getElementById("particles-canvas");
    const ctx = canvas.getContext("2d");
    let particles = [];
    const COUNT = 50;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < COUNT; i++) {
        particles.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            r: Math.random() * 1.5 + 0.5,
            dx: (Math.random() - 0.5) * 0.3,
            dy: (Math.random() - 0.5) * 0.3,
            opacity: Math.random() * 0.5 + 0.1,
        });
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => {
            p.x += p.dx;
            p.y += p.dy;
            if (p.x < 0) p.x = canvas.width;
            if (p.x > canvas.width) p.x = 0;
            if (p.y < 0) p.y = canvas.height;
            if (p.y > canvas.height) p.y = 0;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(124, 92, 252, ${p.opacity})`;
            ctx.fill();
        });

        // Draw connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(124, 92, 252, ${0.06 * (1 - dist / 150)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
        requestAnimationFrame(draw);
    }
    draw();
})();


// =====================================================================
// API HELPERS
// =====================================================================
async function apiGet(path) {
    const res = await fetch(`${API}${path}`);
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `Request failed (${res.status})`);
    }
    return res.json();
}

async function apiPost(path, body = {}) {
    const res = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
}

async function apiDelete(path) {
    const res = await fetch(`${API}${path}`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
}


// =====================================================================
// TOAST NOTIFICATIONS
// =====================================================================
function showToast(message, type = "info") {
    const icons = {
        success: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
        error:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`,
        info:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`,
    };

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${message}</span>`;
    $toastContainer.appendChild(toast);

    setTimeout(() => toast.remove(), 4000);
}


// =====================================================================
// CURRENCY FORMATTING
// =====================================================================
const CURRENCY_SYMBOLS = { USD: "$", EUR: "€", GBP: "£", INR: "₹", JPY: "¥", KRW: "₩" };

function fmtCurrency(amount, currency = "USD") {
    if (amount == null) return "N/A";
    const sym = CURRENCY_SYMBOLS[currency] || "$";
    return `${sym}${Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}


// =====================================================================
// RENDER PRODUCTS
// =====================================================================
function updateStats() {
    const total = products.length;
    let below = 0, above = 0;
    products.forEach(p => {
        if (p.last_price != null && p.last_price <= p.threshold) below++;
        else if (p.last_price != null) above++;
    });
    animateNumber($statTotal, total);
    animateNumber($statBelow, below);
    animateNumber($statAbove, above);
}

function animateNumber(el, target) {
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;
    el.textContent = target;
    el.style.transform = "scale(1.2)";
    el.style.transition = "transform 0.25s ease";
    setTimeout(() => { el.style.transform = "scale(1)"; }, 250);
}

function renderProducts() {
    if (products.length === 0) {
        $grid.innerHTML = "";
        $empty.style.display = "block";
        updateStats();
        return;
    }

    $empty.style.display = "none";

    $grid.innerHTML = products.map((p, i) => {
        const hasPrice = p.last_price != null;
        const belowThreshold = hasPrice && p.last_price <= p.threshold;
        const diff = hasPrice ? p.last_price - p.threshold : null;

        let statusClass, statusText;
        if (!hasPrice) {
            statusClass = "status-unknown";
            statusText = "No price data";
        } else if (belowThreshold) {
            statusClass = "status-below";
            statusText = `${fmtCurrency(Math.abs(diff), p.currency)} below target`;
        } else {
            statusClass = "status-above";
            statusText = `${fmtCurrency(diff, p.currency)} above target`;
        }

        const priceClass = belowThreshold ? "below" : (hasPrice ? "current" : "no-data");

        return `
        <div class="product-card ${belowThreshold ? 'below-threshold' : ''}" style="animation-delay: ${i * 0.06}s" data-id="${p.id}">
            <div class="card-header">
                <span class="card-name" title="${escHtml(p.name || 'Unknown Product')}">${escHtml(p.name || "Unknown Product")}</span>
                <div class="card-actions">
                    <button class="btn btn-ghost btn-icon btn-sm" onclick="checkProduct(${p.id})" title="Check price now">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                    </button>
                    <button class="btn btn-danger btn-icon btn-sm" onclick="deleteProduct(${p.id})" title="Remove">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                </div>
            </div>

            <div class="card-status ${statusClass}">
                <span class="card-status-dot"></span>
                ${statusText}
            </div>

            <div class="card-prices">
                <div class="price-block">
                    <div class="price-block-label">Current Price</div>
                    <div class="price-block-value ${priceClass}">
                        ${hasPrice ? fmtCurrency(p.last_price, p.currency) : "—"}
                    </div>
                </div>
                <div class="price-block">
                    <div class="price-block-label">Target Price</div>
                    <div class="price-block-value threshold">${fmtCurrency(p.threshold, p.currency)}</div>
                </div>
            </div>

            <a class="card-url" href="${escHtml(p.url)}" target="_blank" rel="noopener" title="${escHtml(p.url)}">
                ${escHtml(truncateUrl(p.url))}
            </a>

            <div class="card-footer">
                <button class="btn btn-ghost btn-sm" onclick="showHistory(${p.id})">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                    History
                </button>
                <a class="btn btn-ghost btn-sm" href="${escHtml(p.url)}" target="_blank" rel="noopener" style="justify-content:center; text-decoration:none;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                    Visit Page
                </a>
            </div>
        </div>`;
    }).join("");

    updateStats();
}


// =====================================================================
// HELPERS
// =====================================================================
function escHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
}

function truncateUrl(url) {
    try {
        const u = new URL(url);
        const path = u.pathname.length > 40 ? u.pathname.slice(0, 37) + "..." : u.pathname;
        return u.hostname + path;
    } catch {
        return url;
    }
}


// =====================================================================
// ACTIONS
// =====================================================================

// Fetch and render products
async function loadProducts() {
    try {
        const data = await apiGet("/api/products");
        products = data.products || [];
        renderProducts();
    } catch (err) {
        showToast(`Failed to load products: ${err.message}`, "error");
    }
}

// Add a product
$form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = document.getElementById("input-url").value.trim();
    const threshold = document.getElementById("input-threshold").value;
    const email = document.getElementById("input-email").value.trim();

    if (!url || !threshold) return;

    // Show loading state
    const btnSpan = $btnAdd.querySelector("span");
    const btnLoader = $btnAdd.querySelector(".btn-loader");
    const btnSvg = $btnAdd.querySelector("svg");
    btnSpan.textContent = "Scraping...";
    btnLoader.style.display = "block";
    btnSvg.style.display = "none";
    $btnAdd.disabled = true;

    try {
        const data = await apiPost("/api/products", { url, threshold: parseFloat(threshold), email });
        showToast(`Now tracking: ${data.product?.name || "Product"}`, "success");

        if (data.alert_triggered) {
            showToast("Price is already below your target! 🎉", "success");
        }

        $form.reset();
        await loadProducts();
    } catch (err) {
        showToast(err.message, "error");
    } finally {
        btnSpan.textContent = "Start Tracking";
        btnLoader.style.display = "none";
        btnSvg.style.display = "";
        $btnAdd.disabled = false;
    }
});

// Check a single product
async function checkProduct(id) {
    const card = document.querySelector(`.product-card[data-id="${id}"]`);
    if (card) card.style.opacity = "0.6";

    try {
        const data = await apiPost(`/api/products/${id}/check`);
        if (data.error && !data.price) {
            showToast(`${data.product?.name}: ${data.error}`, "error");
        } else {
            const name = data.product?.name || "Product";
            showToast(`${name}: ${fmtCurrency(data.price, data.product?.currency)}`, "info");

            if (data.alert_triggered) {
                showToast(`${name} is below your target! 🎉`, "success");
            }
        }
        await loadProducts();
    } catch (err) {
        showToast(err.message, "error");
    } finally {
        if (card) card.style.opacity = "";
    }
}

// Check all products
$btnCheckAll.addEventListener("click", async () => {
    $btnCheckAll.disabled = true;
    $btnCheckAll.querySelector("span").textContent = "Checking...";
    showToast("Checking all products...", "info");

    try {
        const data = await apiPost("/api/products/check-all");
        const results = data.results || [];
        const success = results.filter(r => r.status === "success").length;
        const alerts = results.filter(r => r.alert_triggered).length;
        showToast(`Checked ${success}/${results.length} products. ${alerts} alert(s).`, "success");
        await loadProducts();
    } catch (err) {
        showToast(err.message, "error");
    } finally {
        $btnCheckAll.disabled = false;
        $btnCheckAll.querySelector("span").textContent = "Check All";
    }
});

// Delete a product
async function deleteProduct(id) {
    const prod = products.find(p => p.id === id);
    const name = prod?.name || "this product";
    if (!confirm(`Remove "${name}"?`)) return;

    try {
        await apiDelete(`/api/products/${id}`);
        showToast(`Removed: ${name}`, "success");
        await loadProducts();
    } catch (err) {
        showToast(err.message, "error");
    }
}

// Show price history modal
async function showHistory(id) {
    $modalOverlay.classList.add("open");
    $modalBody.innerHTML = `<div style="text-align:center; padding:30px; color: var(--text-muted);">Loading...</div>`;

    try {
        const data = await apiGet(`/api/products/${id}/history`);
        const product = data.product;
        const history = data.history || [];

        $modalTitle.textContent = `${product.name || "Product"} — Price History`;

        if (history.length === 0) {
            $modalBody.innerHTML = `
                <div style="text-align:center; padding:40px; color: var(--text-muted);">
                    <p>No price records yet.</p>
                    <p style="font-size:0.85rem; margin-top:8px;">Run a price check to start recording history.</p>
                </div>`;
            return;
        }

        // Build mini chart
        const chartHtml = buildMiniChart(history, product);

        // Build table
        const currency = product.currency || "USD";
        const rowsHtml = history.map(h => {
            const date = new Date(h.checked_at).toLocaleString();
            const diff = h.price - product.threshold;
            const badge = diff <= 0
                ? `<span class="history-badge below">↓ ${fmtCurrency(Math.abs(diff), currency)} below</span>`
                : `<span class="history-badge above">↑ ${fmtCurrency(diff, currency)} above</span>`;
            return `<tr>
                <td>${date}</td>
                <td class="history-price">${fmtCurrency(h.price, currency)}</td>
                <td>${badge}</td>
            </tr>`;
        }).join("");

        $modalBody.innerHTML = `
            ${chartHtml}
            <table class="history-table">
                <thead>
                    <tr><th>Date</th><th>Price</th><th>vs Target</th></tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>`;

    } catch (err) {
        $modalBody.innerHTML = `<div style="text-align:center; padding:30px; color: var(--red);">Error: ${escHtml(err.message)}</div>`;
    }
}

// Build a simple SVG mini chart
function buildMiniChart(history, product) {
    if (history.length < 2) return "";

    const reversed = [...history].reverse(); // oldest first
    const prices = reversed.map(h => h.price);
    const minP = Math.min(...prices, product.threshold) * 0.95;
    const maxP = Math.max(...prices, product.threshold) * 1.05;
    const range = maxP - minP || 1;

    const W = 560, H = 160, PAD = 20;
    const plotW = W - PAD * 2;
    const plotH = H - PAD * 2;

    const points = prices.map((p, i) => {
        const x = PAD + (i / (prices.length - 1)) * plotW;
        const y = PAD + plotH - ((p - minP) / range) * plotH;
        return `${x},${y}`;
    });

    const thresholdY = PAD + plotH - ((product.threshold - minP) / range) * plotH;

    // Gradient area
    const areaPoints = `${PAD},${PAD + plotH} ${points.join(" ")} ${PAD + plotW},${PAD + plotH}`;

    const currency = product.currency || "USD";

    return `
    <div class="history-chart-container">
        <svg viewBox="0 0 ${W} ${H}" style="width:100%; height:auto;">
            <defs>
                <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="rgba(124,92,252,0.3)"/>
                    <stop offset="100%" stop-color="rgba(124,92,252,0)"/>
                </linearGradient>
            </defs>
            <!-- Area fill -->
            <polygon points="${areaPoints}" fill="url(#chartGrad)"/>
            <!-- Price line -->
            <polyline points="${points.join(" ")}" fill="none" stroke="#7c5cfc" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            <!-- Threshold line -->
            <line x1="${PAD}" y1="${thresholdY}" x2="${W - PAD}" y2="${thresholdY}" stroke="#34d399" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.6"/>
            <text x="${W - PAD - 4}" y="${thresholdY - 6}" fill="#34d399" font-size="10" text-anchor="end" font-family="Inter, sans-serif">Target: ${fmtCurrency(product.threshold, currency)}</text>
            <!-- Data points -->
            ${prices.map((p, i) => {
                const x = PAD + (i / (prices.length - 1)) * plotW;
                const y = PAD + plotH - ((p - minP) / range) * plotH;
                return `<circle cx="${x}" cy="${y}" r="3.5" fill="#7c5cfc" stroke="#0a0a0f" stroke-width="1.5"/>`;
            }).join("")}
        </svg>
    </div>`;
}

// Close modal
$modalClose.addEventListener("click", () => $modalOverlay.classList.remove("open"));
$modalOverlay.addEventListener("click", (e) => {
    if (e.target === $modalOverlay) $modalOverlay.classList.remove("open");
});
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $modalOverlay.classList.remove("open");
});


// =====================================================================
// INIT
// =====================================================================
loadProducts();
