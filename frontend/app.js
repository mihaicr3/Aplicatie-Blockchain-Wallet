// ==========================================
// Frontend Application State & Configuration
// ==========================================

const CLIENTS = [
    { id: 1, name: "Client 1", port: 5001, url: "http://127.0.0.1:5001", status: "offline", height: 0 },
    { id: 2, name: "Client 2", port: 5002, url: "http://127.0.0.1:5002", status: "offline", height: 0 },
    { id: 3, name: "Client 3", port: 5003, url: "http://127.0.0.1:5003", status: "offline", height: 0 }
];

let USERS = [];

let selectedClientId = 1;
let selectedUser = null;
let balances = {};
let activeChain = [];
let transactionEdges = []; // Array of { from, to, amount }

// Zoom & Pan state
let zoom = 1.0;
let panX = 0;
let panY = 0;
let isDragging = false;
let hasDragged = false;
let dragStart = { x: 0, y: 0 };
let panStart = { x: 0, y: 0 };

// Canvas positioning
let canvas, ctx;
const userPositions = {};

// ==========================================
// Initialization
// ==========================================

document.addEventListener("DOMContentLoaded", async () => {
    initCanvas();
    setupEventListeners();
    
    // Initial data load and polling
    await refreshAll();
    setInterval(refreshAll, 2000);
    
    // Canvas animation loop
    animateCanvas();
    showToast("Dashboard initialized. Select a wallet to interact.", "success");
});

function initCanvas() {
    canvas = document.getElementById("graph-canvas");
    ctx = canvas.getContext("2d");
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
}

function resizeCanvas() {
    if (!canvas) return;
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    
    // Set display size
    canvas.style.width = rect.width + 'px';
    canvas.style.height = (rect.height || 400) + 'px';
    
    // Set actual coordinate size (scaled by DPR)
    canvas.width = rect.width * dpr;
    canvas.height = (rect.height || 400) * dpr;
    
    // Scale drawings
    ctx.resetTransform();
    ctx.scale(dpr, dpr);
    
    // Calculate positions in CSS coordinate space
    recalculateUserPositions();
}

function recalculateUserPositions() {
    if (!canvas) return;
    const rect = canvas.parentElement.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height || 400;
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(w, h) * 0.32;
    
    // Clear old positions
    for (const key in userPositions) {
        delete userPositions[key];
    }
    
    const count = USERS.length;
    USERS.forEach((user, index) => {
        // Distribute evenly around a circle starting from the top
        const angle = (index * 2 * Math.PI) / count - Math.PI / 2;
        userPositions[user] = {
            x: cx + r * Math.cos(angle),
            y: cy + r * Math.sin(angle)
        };
    });
}

// ==========================================
// Data Polling and Sync
// ==========================================

async function refreshAll() {
    await fetchClientStates();
    updateClientsBarUI();
    await fetchActiveClientData();
}

async function fetchClientStates() {
    for (const client of CLIENTS) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 3000);
            
            const res = await fetch(`${client.url}/chain`, { signal: controller.signal });
            clearTimeout(timeoutId);
            
            if (res.ok) {
                const data = await res.json();
                client.status = "online";
                client.height = data.length;
            } else {
                client.status = "offline";
                client.height = 0;
            }
        } catch (e) {
            client.status = "offline";
            client.height = 0;
        }
    }
}

function updateClientsBarUI() {
    const bar = document.getElementById("clients-status-bar");
    bar.innerHTML = "";
    
    CLIENTS.forEach(client => {
        const card = document.createElement("div");
        card.className = `client-status-card ${client.id === selectedClientId ? 'active-selected' : ''}`;
        
        card.innerHTML = `
            <div class="client-meta">
                <h4>${client.name}</h4>
                <p>Port: ${client.port}</p>
            </div>
            <span class="client-badge ${client.status}">
                ${client.status === 'online' ? `Online (${client.height} blks)` : 'Offline'}
            </span>
        `;
        
        // Switch client connection on card click
        card.addEventListener("click", () => {
            if (selectedClientId !== client.id) {
                selectedClientId = client.id;
                refreshAll();
                showToast(`Switched active connection to ${client.name}`, "info");
            }
        });
        
        bar.appendChild(card);
    });
}

async function fetchActiveClientData() {
    const active = CLIENTS.find(c => c.id === selectedClientId);
    
    if (active.status !== "online") {
        document.getElementById("ledger-height-badge").textContent = "Offline";
        document.getElementById("ledger-list").innerHTML = `
            <div class="network-tip" style="color:var(--color-red); padding:20px 0;">
                ⚠️ Connection failed. Client ${active.id} (Port ${active.port}) is offline.
            </div>
        `;
        balances = {};
        USERS = [];
        recalculateUserPositions();
        populateSearchableDropdown();
        activeChain = [];
        transactionEdges = [];
        return;
    }
    
    try {
        // 1. Fetch balances
        const balRes = await fetch(`${active.url}/balances`);
        if (balRes.ok) {
            const data = await balRes.json();
            balances = data.balances;
            
            const newUsers = Object.keys(balances);
            const usersChanged = JSON.stringify(newUsers.sort()) !== JSON.stringify(USERS.sort());
            if (usersChanged) {
                USERS = newUsers;
                recalculateUserPositions();
                populateSearchableDropdown();
            }
            
            if (selectedUser) {
                if (!USERS.includes(selectedUser)) {
                    deselectUserWallet();
                } else {
                    document.getElementById("wallet-balance-val").textContent = `${balances[selectedUser].toFixed(2)} Coins`;
                }
            }
        }
        
        // 2. Fetch chain and parse transaction history
        const chainRes = await fetch(`${active.url}/chain`);
        if (chainRes.ok) {
            const data = await chainRes.json();
            activeChain = data.chain;
            
            document.getElementById("ledger-height-badge").textContent = `${data.length} blocks`;
            
            // Build transaction edges for graph drawing
            const edgesMap = {};
            activeChain.forEach(block => {
                block.transactions.forEach(tx => {
                    if (tx.sender === "SYSTEM" || tx.amount === 0) return;
                    
                    const pairKey = `${tx.sender}->${tx.recipient}`;
                    if (edgesMap[pairKey]) {
                        edgesMap[pairKey] += tx.amount;
                    } else {
                        edgesMap[pairKey] = tx.amount;
                    }
                });
            });
            
            transactionEdges = Object.entries(edgesMap).map(([key, amount]) => {
                const [from, to] = key.split("->");
                return { from, to, amount };
            });
            
            renderLedgerList();
        }
    } catch (e) {
        console.error("Error fetching active client data:", e);
    }
}

function renderLedgerList() {
    const list = document.getElementById("ledger-list");
    list.innerHTML = "";
    
    if (activeChain.length === 0) {
        list.innerHTML = `<div class="network-tip">Blockchain database is empty.</div>`;
        return;
    }
    
    // Reverse order (newest first)
    for (let i = activeChain.length - 1; i >= 0; i--) {
        const block = activeChain[i];
        const isGenesis = block.index === 0;
        const entry = document.createElement("div");
        entry.className = "block-entry";
        
        let txDesc = "Genesis Block";
        if (!isGenesis && block.transactions.length > 0) {
            const tx = block.transactions[0];
            if (tx.sender === "SYSTEM") {
                txDesc = `🪙 Minted ${tx.amount.toFixed(0)} coins to ${tx.recipient}`;
            } else {
                txDesc = `💸 Sent ${tx.amount.toFixed(0)} coins from ${tx.sender} to ${tx.recipient}`;
            }
        }
        
        entry.innerHTML = `
            <div class="block-left">
                <h3>Block #${block.index}</h3>
                <p>${new Date(block.timestamp * 1000).toLocaleTimeString()}</p>
            </div>
            <div class="block-tx-details">
                <strong>${txDesc}</strong>
            </div>
            <div class="block-hashes">
                <div>Hash: <span>${block.hash.substring(0, 8)}...</span></div>
                <div style="font-size:0.6rem">Prev: ${block.previous_hash.substring(0, 8)}...</div>
            </div>
        `;
        list.appendChild(entry);
    }
}

// ==========================================
// Canvas Wallet Graph Rendering
// ==========================================

function drawGraph() {
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    ctx.save();
    
    // Scale by devicePixelRatio (DPR) for high-res rendering
    const dpr = window.devicePixelRatio || 1;
    ctx.scale(dpr, dpr);
    
    // Apply pan and zoom transforms
    ctx.translate(panX, panY);
    ctx.scale(zoom, zoom);
    
    // 1. Draw transaction arrows/edges
    transactionEdges.forEach(edge => {
        const pFrom = userPositions[edge.from];
        const pTo = userPositions[edge.to];
        if (pFrom && pTo) {
            drawArrow(pFrom.x, pFrom.y, pTo.x, pTo.y, edge.amount);
        }
    });
    
    // 2. Draw user nodes
    USERS.forEach(user => {
        const pos = userPositions[user];
        if (!pos) return;
        
        const isSelected = user === selectedUser;
        const balance = balances[user] || 0.0;
        
        // Selection highlight ring
        if (isSelected) {
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, 45, 0, 2 * Math.PI);
            ctx.fillStyle = "rgba(180, 100, 250, 0.08)";
            ctx.strokeStyle = "rgba(180, 100, 250, 0.3)";
            ctx.lineWidth = 3;
            ctx.fill();
            ctx.stroke();
        }
        
        // Node main circle
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 32, 0, 2 * Math.PI);
        ctx.fillStyle = isSelected ? "var(--bg-dark)" : "hsla(222, 20%, 18%, 0.9)";
        ctx.strokeStyle = isSelected ? "var(--color-purple)" : "var(--border-color)";
        ctx.lineWidth = isSelected ? 3 : 1.5;
        ctx.shadowBlur = isSelected ? 12 : 0;
        ctx.shadowColor = "var(--color-purple)";
        ctx.fill();
        ctx.stroke();
        ctx.shadowBlur = 0; // reset
        
        // User Name
        ctx.fillStyle = "white";
        ctx.font = "bold 12px Outfit, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(user, pos.x, pos.y - 4);
        
        // User Balance
        ctx.fillStyle = "var(--color-cyan)";
        ctx.font = "bold 10px 'Fira Code', monospace";
        ctx.fillText(`${balance.toFixed(0)} C`, pos.x, pos.y + 12);
    });
    
    ctx.restore();
}

function drawArrow(fromx, fromy, tox, toy, amount) {
    const headlen = 10; // length of head in pixels
    const dx = tox - fromx;
    const dy = toy - fromy;
    const angle = Math.atan2(dy, dx);
    
    // Offset endpoints so arrow doesn't overlap circles
    const offset = 35;
    const startX = fromx + offset * Math.cos(angle);
    const startY = fromy + offset * Math.sin(angle);
    const endX = tox - offset * Math.cos(angle);
    const endY = toy - offset * Math.sin(angle);
    
    // Draw shaft
    ctx.beginPath();
    ctx.moveTo(startX, startY);
    ctx.lineTo(endX, endY);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
    ctx.lineWidth = 2;
    ctx.stroke();
    
    // Draw arrowhead
    ctx.beginPath();
    ctx.moveTo(endX, endY);
    ctx.lineTo(endX - headlen * Math.cos(angle - Math.PI / 6), endY - headlen * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(endX - headlen * Math.cos(angle + Math.PI / 6), endY - headlen * Math.sin(angle + Math.PI / 6));
    ctx.fillStyle = "rgba(255, 255, 255, 0.22)";
    ctx.fill();
    
    // Draw amount label in the middle of shaft
    const midX = (startX + endX) / 2;
    const midY = (startY + endY) / 2;
    ctx.fillStyle = "var(--color-orange)";
    ctx.font = "bold 9px 'Fira Code', monospace";
    ctx.textAlign = "center";
    ctx.fillText(`${amount.toFixed(0)} Coins`, midX, midY - 6);
}

function animateCanvas() {
    drawGraph();
    requestAnimationFrame(animateCanvas);
}

// ==========================================
// Event Listeners & API Actions
// ==========================================

function setupEventListeners() {
    // 1. Custom Searchable Dropdown setup for wallets/users
    populateSearchableDropdown();

    const dropdown = document.getElementById("user-search-dropdown");
    const trigger = document.getElementById("user-dropdown-trigger");
    const searchInput = document.getElementById("user-search-input");

    trigger.addEventListener("click", (e) => {
        e.stopPropagation();
        dropdown.classList.toggle("open");
        if (dropdown.classList.contains("open")) {
            searchInput.value = "";
            searchInput.focus();
            filterDropdownOptions("");
        }
    });

    searchInput.addEventListener("input", (e) => {
        filterDropdownOptions(e.target.value.toLowerCase());
    });

    searchInput.addEventListener("click", (e) => {
        e.stopPropagation();
    });

    document.addEventListener("click", (e) => {
        if (!dropdown.contains(e.target)) {
            dropdown.classList.remove("open");
        }
    });

    // 2. Canvas mouse drag and zoom controls
    canvas.addEventListener("mousedown", (e) => {
        isDragging = true;
        hasDragged = false;
        dragStart = { x: e.clientX, y: e.clientY };
        panStart = { x: panX, y: panY };
    });

    canvas.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const dx = e.clientX - dragStart.x;
        const dy = e.clientY - dragStart.y;
        
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
            hasDragged = true;
        }
        
        panX = panStart.x + dx;
        panY = panStart.y + dy;
    });

    canvas.addEventListener("mouseup", (e) => {
        if (!isDragging) return;
        isDragging = false;
        
        if (!hasDragged) {
            // Treat as a click selection
            const rect = canvas.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const clickY = e.clientY - rect.top;
            
            // Convert click from screen coordinates to transformed graph coordinates
            const graphX = (clickX - panX) / zoom;
            const graphY = (clickY - panY) / zoom;
            
            let clickedUser = null;
            for (const [user, pos] of Object.entries(userPositions)) {
                const distance = Math.sqrt((graphX - pos.x) ** 2 + (graphY - pos.y) ** 2);
                if (distance <= 32) {
                    clickedUser = user;
                    break;
                }
            }
            
            if (clickedUser) {
                selectUserWallet(clickedUser);
            }
        }
    });

    canvas.addEventListener("mouseleave", () => {
        isDragging = false;
    });

    // 3. Mouse Wheel zoom centered on mouse pointer
    canvas.addEventListener("wheel", (e) => {
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        const graphMouseX = (mouseX - panX) / zoom;
        const graphMouseY = (mouseY - panY) / zoom;
        
        const zoomIntensity = 0.08;
        let newZoom;
        if (e.deltaY < 0) {
            newZoom = zoom * (1 + zoomIntensity);
        } else {
            newZoom = zoom * (1 - zoomIntensity);
        }
        
        // Limits
        newZoom = Math.max(0.3, Math.min(newZoom, 4.0));
        
        panX = mouseX - graphMouseX * newZoom;
        panY = mouseY - graphMouseY * newZoom;
        zoom = newZoom;
    }, { passive: false });

    // 4. GUI Zoom Button Controls
    document.getElementById("zoom-in-btn").addEventListener("click", () => {
        const center = getCanvasCenterGraphCoords();
        const newZoom = Math.min(zoom * 1.2, 4.0);
        adjustPanForZoomCenter(center, newZoom);
        zoom = newZoom;
    });

    document.getElementById("zoom-out-btn").addEventListener("click", () => {
        const center = getCanvasCenterGraphCoords();
        const newZoom = Math.max(zoom / 1.2, 0.3);
        adjustPanForZoomCenter(center, newZoom);
        zoom = newZoom;
    });

    document.getElementById("zoom-reset-btn").addEventListener("click", () => {
        zoom = 1.0;
        panX = 0;
        panY = 0;
    });

    // 3. Spawn Coins Submission
    document.getElementById("spawn-coins-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const active = CLIENTS.find(c => c.id === selectedClientId);
        if (active.status !== "online") {
            showToast("Connection offline.", "error");
            return;
        }

        const amount = parseFloat(document.getElementById("spawn-amount").value);
        
        try {
            const res = await fetch(`${active.url}/mint`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ recipient: selectedUser, amount: amount })
            });
            
            if (res.ok) {
                showToast(`Successfully spawned ${amount} coins for ${selectedUser}!`, "success");
                
                // Clear consensus panel since this was a System operations (bypassed)
                document.getElementById("consensus-result-badge").textContent = "APPROVED";
                document.getElementById("consensus-result-badge").className = "badge";
                document.getElementById("voting-desc").textContent = "Minting operations are issued by SYSTEM and approved automatically.";
                document.getElementById("voting-list").innerHTML = "";
                
                await refreshAll();
            } else {
                showToast("Failed to spawn coins.", "error");
            }
        } catch (e) {
            showToast("Server connection error spawning coins.", "error");
        }
    });

    // 4. Send Coins Submission (Consensus Voting)
    document.getElementById("send-coins-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const active = CLIENTS.find(c => c.id === selectedClientId);
        if (active.status !== "online") {
            showToast("Connection offline.", "error");
            return;
        }

        const recipient = document.getElementById("send-recipient").value;
        const amount = parseFloat(document.getElementById("send-amount").value);
        
        if (selectedUser === recipient) {
            showToast("Cannot transfer to the same wallet.", "error");
            return;
        }
        
        showToast(`Broadcasting transaction for P2P consensus voting...`, "info");
        
        try {
            const res = await fetch(`${active.url}/transactions/submit`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sender: selectedUser, recipient: recipient, amount: amount })
            });
            
            const data = await res.json();
            
            // Render voting result panel
            updateVotingUI(data.approved, data.votes);
            
            if (res.ok && data.approved) {
                showToast("Transaction approved by 50%+1 clients! Block mined.", "success");
                await refreshAll();
            } else {
                showToast(`Rejected: ${data.message}`, "error");
            }
        } catch (err) {
            showToast("Server connection error during consensus voting.", "error");
        }
    });

    // 5. Reset network databases
    document.getElementById("reset-network-btn").addEventListener("click", async () => {
        if (confirm("Reset SQLite databases for Client 1, Client 2, and Client 3 back to Genesis Block?")) {
            for (const client of CLIENTS) {
                if (client.status === "online") {
                    try {
                        await fetch(`${client.url}/clear`, { method: "POST" });
                    } catch (e) {}
                }
            }
            showToast("Network databases reset.", "success");
            deselectUserWallet();
            
            // Reset voting panel
            document.getElementById("consensus-result-badge").textContent = "-";
            document.getElementById("consensus-result-badge").className = "badge";
            document.getElementById("voting-desc").textContent = "Submit a transaction to observe consensus voting in real-time.";
            document.getElementById("voting-list").innerHTML = "";
            
            await refreshAll();
        }
    });

    // 6. Register New Wallet Form Submission
    document.getElementById("register-wallet-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const active = CLIENTS.find(c => c.id === selectedClientId);
        if (active.status !== "online") {
            showToast("Connection offline.", "error");
            return;
        }

        const nameInput = document.getElementById("register-wallet-name");
        const walletName = nameInput.value.trim();
        if (!walletName) {
            showToast("Wallet name cannot be empty.", "error");
            return;
        }
        
        try {
            const res = await fetch(`${active.url}/wallets/create`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ address: walletName })
            });
            
            if (res.ok) {
                showToast(`Wallet '${walletName}' registered successfully!`, "success");
                nameInput.value = "";
                await refreshAll();
                // Select the newly created wallet
                selectUserWallet(walletName);
            } else {
                const errData = await res.json();
                showToast(errData.message || "Failed to register wallet.", "error");
            }
        } catch (err) {
            showToast("Server connection error registering wallet.", "error");
        }
    });

    // 7. Simulated Network Delay Slider inputs
    document.querySelectorAll(".delay-slider").forEach(slider => {
        slider.addEventListener("input", (e) => {
            const clientId = e.target.dataset.clientId;
            const delayVal = e.target.value;
            document.getElementById(`delay-val-${clientId}`).textContent = `${delayVal}ms`;
        });

        slider.addEventListener("change", async (e) => {
            const clientId = e.target.dataset.clientId;
            const delayVal = parseInt(e.target.value);
            const port = e.target.dataset.port;
            const clientUrl = `http://127.0.0.1:${port}`;
            
            try {
                const res = await fetch(`${clientUrl}/delay`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ delay: delayVal })
                });
                if (res.ok) {
                    showToast(`Client ${clientId} latency set to ${delayVal}ms`, "success");
                } else {
                    showToast(`Failed to set delay on Client ${clientId}`, "error");
                }
            } catch (err) {
                showToast(`Error communicating latency config to Client ${clientId}`, "error");
            }
        });
    });
}

function selectUserWallet(user) {
    selectedUser = user;
    
    document.getElementById("wallet-panel-title").textContent = user;
    document.getElementById("wallet-panel-addr").textContent = "Wallet Node";
    document.getElementById("wallet-balance-val").textContent = `${(balances[user] || 0.0).toFixed(2)} Coins`;
    document.getElementById("selected-user-display").textContent = user;
    
    document.getElementById("wallet-actions").style.display = "block";
    
    // Populate recipient dropdown excluding selected sender
    const recipSelect = document.getElementById("send-recipient");
    recipSelect.innerHTML = "";
    USERS.forEach(u => {
        if (u !== user) {
            const opt = document.createElement("option");
            opt.value = u;
            opt.textContent = u;
            recipSelect.appendChild(opt);
        }
    });

    // Mark corresponding option as selected in dropdown menu
    document.querySelectorAll("#user-dropdown-options .dropdown-option").forEach(el => {
        if (el.textContent === user) {
            el.classList.add("selected");
        } else {
            el.classList.remove("selected");
        }
    });
}

function deselectUserWallet() {
    selectedUser = null;
    document.getElementById("wallet-actions").style.display = "none";
    document.getElementById("wallet-panel-title").textContent = "Select a Wallet";
    document.getElementById("wallet-panel-addr").textContent = "-";
    document.getElementById("wallet-balance-val").textContent = "0.00 Coins";
    document.getElementById("selected-user-display").textContent = "Select Wallet...";
}

// Update the Consensus Voting panel with the YES/NO statuses
function updateVotingUI(approved, votes) {
    const badge = document.getElementById("consensus-result-badge");
    const desc = document.getElementById("voting-desc");
    const list = document.getElementById("voting-list");
    
    list.innerHTML = "";
    
    if (approved) {
        badge.textContent = "APPROVED";
        badge.className = "badge";
        badge.style.background = "var(--color-green-glow)";
        badge.style.color = "var(--color-green)";
        badge.style.borderColor = "hsla(145, 80%, 45%, 0.3)";
        desc.textContent = "Consensus achieved: Transaction met the 50%+1 approval criteria and was written to SQLite.";
    } else {
        badge.textContent = "REJECTED";
        badge.className = "badge";
        badge.style.background = "var(--color-red-glow)";
        badge.style.color = "var(--color-red)";
        badge.style.borderColor = "hsla(354, 85%, 55%, 0.3)";
        desc.textContent = "Consensus failed: Transaction was rejected due to insufficient approvals or balance.";
    }
    
    // Sort votes by port/url
    Object.entries(votes).forEach(([peerUrl, detail]) => {
        const port = peerUrl.split(":").pop();
        const row = document.createElement("div");
        row.className = "voting-row";
        
        const isYes = detail.vote === "yes";
        row.innerHTML = `
            <span><strong>Client :${port}</strong></span>
            <span class="vote-badge ${isYes ? 'yes' : 'no'}">${detail.vote}</span>
        `;
        list.appendChild(row);
    });
}

// ==========================================
// Toast Alerts
// ==========================================

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    
    let icon = "ℹ️";
    if (type === "success") icon = "✅";
    if (type === "error") icon = "🚨";
    
    toast.innerHTML = `
        <span style="margin-right: 8px;">${icon}</span>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add("fade-out");
        toast.addEventListener("animationend", () => {
            toast.remove();
        });
    }, 3500);
}

// ==========================================
// Searchable Dropdown Helpers
// ==========================================

function populateSearchableDropdown() {
    const container = document.getElementById("user-dropdown-options");
    if (!container) return;
    container.innerHTML = "";
    
    USERS.forEach(user => {
        const opt = document.createElement("div");
        opt.className = `dropdown-option ${user === selectedUser ? 'selected' : ''}`;
        opt.textContent = user;
        opt.dataset.value = user;
        
        opt.addEventListener("click", () => {
            selectUserWallet(user);
            document.getElementById("user-search-dropdown").classList.remove("open");
            showToast(`Selected wallet: ${user}`, "info");
        });
        
        container.appendChild(opt);
    });
}

function filterDropdownOptions(query) {
    const options = document.querySelectorAll("#user-dropdown-options .dropdown-option");
    options.forEach(opt => {
        const text = opt.textContent.toLowerCase();
        if (text.includes(query)) {
            opt.style.display = "block";
        } else {
            opt.style.display = "none";
        }
    });
}

function getCanvasCenterGraphCoords() {
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    return {
        x: (centerX - panX) / zoom,
        y: (centerY - panY) / zoom
    };
}

function adjustPanForZoomCenter(center, newZoom) {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    panX = centerX - center.x * newZoom;
    panY = centerY - center.y * newZoom;
}
