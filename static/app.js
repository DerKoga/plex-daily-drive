// State
let settings = {};
let libraries = [];
let schedules = [{ hour: 6, minute: 0 }];
let allUsers = [];
let allPodcasts = [];

// --- Init ---

document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    loadStatus();
    loadSettings();
    loadLibraries();

    // Enter key for podcast search
    const searchInput = document.getElementById("podcast-search-input");
    if (searchInput) {
        searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") searchPodcasts();
        });
    }
});

// --- Tabs ---

function initTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById("tab-" + tab.dataset.tab).classList.add("active");

            if (tab.dataset.tab === "history") loadHistory();
            if (tab.dataset.tab === "generate") { loadPlaylists(); loadGenerateUserSelect(); }
            if (tab.dataset.tab === "podcasts") loadSubscribedPodcasts();
            if (tab.dataset.tab === "users") { loadUsers(); loadPlexUsers(); }
        });
    });
}

// --- Status ---

async function loadStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();

        const plexEl = document.getElementById("plex-status");
        if (data.plex.success) {
            plexEl.textContent = data.plex.server_name + " (v" + data.plex.version + ")";
            plexEl.className = "status-value status-ok";
        } else {
            plexEl.textContent = "Nicht verbunden";
            plexEl.className = "status-value status-error";
        }

        const schedEl = document.getElementById("scheduler-status");
        schedEl.textContent = data.enabled ? "Aktiv" : "Deaktiviert";
        schedEl.className = "status-value " + (data.enabled ? "status-ok" : "status-warn");

        const nextEl = document.getElementById("next-run");
        if (data.next_runs && data.next_runs.length > 0) {
            nextEl.textContent = data.next_runs.join(", ");
        } else {
            nextEl.textContent = data.next_run || "Nicht geplant";
        }
    } catch {
        document.getElementById("plex-status").textContent = "Fehler";
        document.getElementById("plex-status").className = "status-value status-error";
    }
}

// --- Settings (server-level only) ---

async function loadSettings() {
    try {
        const res = await fetch("/api/settings");
        settings = await res.json();

        document.getElementById("plex-url").value = settings.plex_url || "";
        document.getElementById("plex-token").value = settings.plex_token || "";
        document.getElementById("podcast-download-path").value = settings.podcast_download_path || "/podcasts";
        document.getElementById("podcast-max-episodes").value = settings.podcast_max_episodes || "3";
        document.getElementById("enabled").checked = settings.enabled === "true";

        // Load schedules
        try {
            schedules = JSON.parse(settings.schedules || '[{"hour": 6, "minute": 0}]');
        } catch {
            schedules = [{ hour: 6, minute: 0 }];
        }
        renderSchedules();
    } catch (e) {
        console.error("Failed to load settings:", e);
    }
}

async function saveSettings() {
    // Collect schedules from UI
    collectSchedules();

    const data = {
        plex_url: document.getElementById("plex-url").value,
        plex_token: document.getElementById("plex-token").value,
        podcast_download_path: document.getElementById("podcast-download-path").value,
        podcast_max_episodes: document.getElementById("podcast-max-episodes").value,
        enabled: document.getElementById("enabled").checked ? "true" : "false",
        schedules: schedules,
    };

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        const result = await res.json();
        showResult("save-result", result.success, result.success ? "Einstellungen gespeichert!" : "Fehler beim Speichern");
        loadStatus();
    } catch (e) {
        showResult("save-result", false, "Fehler: " + e.message);
    }
}

// --- Schedules ---

function renderSchedules() {
    const container = document.getElementById("schedules-list");
    if (schedules.length === 0) {
        schedules = [{ hour: 6, minute: 0 }];
    }
    container.innerHTML = schedules
        .map((s, i) => `
            <div class="schedule-row" data-index="${i}">
                <input type="number" class="schedule-hour" value="${s.hour}" min="0" max="23" placeholder="Std">
                <span class="schedule-sep">:</span>
                <input type="number" class="schedule-minute" value="${s.minute}" min="0" max="59" placeholder="Min">
                <span class="schedule-label">Uhr</span>
                ${schedules.length > 1 ? `<button class="btn btn-small btn-danger" onclick="removeSchedule(${i})">&#10005;</button>` : ""}
            </div>
        `)
        .join("");
}

function addSchedule() {
    collectSchedules();
    schedules.push({ hour: 12, minute: 0 });
    renderSchedules();
}

function removeSchedule(index) {
    collectSchedules();
    schedules.splice(index, 1);
    renderSchedules();
}

function collectSchedules() {
    const rows = document.querySelectorAll(".schedule-row");
    schedules = Array.from(rows).map((row) => ({
        hour: parseInt(row.querySelector(".schedule-hour").value) || 0,
        minute: parseInt(row.querySelector(".schedule-minute").value) || 0,
    }));
}

// --- Libraries ---

async function loadLibraries() {
    try {
        const res = await fetch("/api/libraries");
        libraries = await res.json();
    } catch (e) {
        console.error("Failed to load libraries:", e);
    }
}

function renderLibraryList(containerId, libs, selectedKeys, prefix) {
    const container = document.getElementById(containerId);
    if (libs.length === 0) {
        container.innerHTML = '<p class="muted">Keine passenden Bibliotheken gefunden</p>';
        return;
    }

    // Normalize selectedKeys to strings for comparison
    const selectedStrKeys = selectedKeys.map((k) => String(k));

    container.innerHTML = libs
        .map((lib) => {
            const checked = selectedStrKeys.includes(String(lib.key)) ? "checked" : "";
            const selectedClass = checked ? "selected" : "";
            return `
                <label class="library-item ${selectedClass}">
                    <input type="checkbox" data-prefix="${prefix}" data-key="${lib.key}" ${checked}
                           onchange="this.parentElement.classList.toggle('selected', this.checked)">
                    <span>${lib.title}</span>
                </label>
            `;
        })
        .join("");
}

function getSelectedLibraries(prefix) {
    const checkboxes = document.querySelectorAll(`input[data-prefix="${prefix}"]:checked`);
    return Array.from(checkboxes).map((cb) => cb.dataset.key);
}

// --- Connection Test ---

async function testConnection() {
    const resultEl = document.getElementById("connection-result");
    resultEl.className = "result-box";
    resultEl.innerHTML = '<span class="spinner"></span> Teste Verbindung...';

    try {
        const res = await fetch("/api/test-connection", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                plex_url: document.getElementById("plex-url").value,
                plex_token: document.getElementById("plex-token").value,
            }),
        });
        const data = await res.json();
        if (data.success) {
            showResult("connection-result", true, "Verbunden mit " + data.server_name + " (v" + data.version + ")");
            loadLibraries();
            loadStatus();
        } else {
            showResult("connection-result", false, "Verbindung fehlgeschlagen: " + data.error);
        }
    } catch (e) {
        showResult("connection-result", false, "Fehler: " + e.message);
    }
}

// --- Users ---

async function loadUsers() {
    try {
        const res = await fetch("/api/users");
        allUsers = await res.json();

        // Also load all podcasts for reference
        const podRes = await fetch("/api/podcasts");
        allPodcasts = await podRes.json();

        const container = document.getElementById("users-list");

        if (allUsers.length === 0) {
            container.innerHTML = '<p class="muted">Noch keine Benutzer angelegt. Ohne Benutzer wird die Playlist global generiert.</p>';
            return;
        }

        container.innerHTML = allUsers
            .map((u) => {
                const podcastNames = allPodcasts
                    .filter((p) => u.podcasts && u.podcasts.includes(p.id))
                    .map((p) => p.name);
                const badges = podcastNames.length > 0
                    ? podcastNames.map((n) => `<span class="badge">${escapeHtml(n)}</span>`).join("")
                    : '<span class="muted" style="font-size:0.8rem">Keine Podcasts</span>';

                return `
                    <div class="user-item ${u.enabled ? "" : "disabled"}">
                        <div class="user-info">
                            <div class="user-name">${escapeHtml(u.name)}</div>
                            <div class="user-meta">
                                Plex: ${escapeHtml(u.plex_username || "\u2013")} &middot;
                                ${u.music_count} Musik &middot;
                                ${u.podcast_count} Podcasts &middot;
                                ${u.discovery_ratio}% Neuentdeckungen
                            </div>
                            <div class="user-podcasts-badges">${badges}</div>
                        </div>
                        <div class="user-actions">
                            <button class="btn btn-small btn-secondary" onclick="editUser(${u.id})">Bearbeiten</button>
                            <button class="btn btn-small btn-secondary" onclick="toggleUser(${u.id}, ${!u.enabled})">
                                ${u.enabled ? "Deaktivieren" : "Aktivieren"}
                            </button>
                            <button class="btn btn-small btn-danger" onclick="removeUser(${u.id}, '${escapeHtml(u.name)}')">Entfernen</button>
                        </div>
                    </div>
                `;
            })
            .join("");
    } catch (e) {
        document.getElementById("users-list").innerHTML = '<p class="muted">Fehler beim Laden</p>';
    }
}

async function loadPlexUsers() {
    try {
        const res = await fetch("/api/plex-users");
        const plexUsers = await res.json();
        const container = document.getElementById("plex-users-list");

        if (plexUsers.length === 0) {
            container.innerHTML = '<p class="muted">Keine Plex-Benutzer gefunden. Ist Plex verbunden?</p>';
            return;
        }

        container.innerHTML = '<div class="plex-user-chips">' +
            plexUsers.map((u) => `
                <span class="plex-user-chip ${u.is_admin ? "admin" : ""}"
                      onclick="selectPlexUser('${escapeHtml(u.username)}')"
                      title="Klicken zum Ausw\u00e4hlen">
                    ${escapeHtml(u.title)} ${u.is_admin ? "(Admin)" : ""}
                </span>
            `).join("") +
            '</div>';
    } catch {
        document.getElementById("plex-users-list").innerHTML = '<p class="muted">Fehler beim Laden der Plex-Benutzer</p>';
    }
}

function selectPlexUser(username) {
    document.getElementById("new-user-plex-username").value = username;
    if (!document.getElementById("new-user-name").value) {
        document.getElementById("new-user-name").value = username;
    }
}

async function addUser() {
    const name = document.getElementById("new-user-name").value.trim();
    const plexUsername = document.getElementById("new-user-plex-username").value.trim();
    const plexToken = document.getElementById("new-user-plex-token").value.trim();

    if (!name) {
        showResult("add-user-result", false, "Name ist erforderlich");
        return;
    }

    try {
        const res = await fetch("/api/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                plex_username: plexUsername,
                plex_token: plexToken,
            }),
        });
        const data = await res.json();
        if (data.success) {
            showResult("add-user-result", true, `Benutzer "${name}" hinzugef\u00fcgt!`);
            document.getElementById("new-user-name").value = "";
            document.getElementById("new-user-plex-username").value = "";
            document.getElementById("new-user-plex-token").value = "";
            loadUsers();
        } else {
            showResult("add-user-result", false, data.error || "Fehler beim Hinzuf\u00fcgen");
        }
    } catch (e) {
        showResult("add-user-result", false, "Fehler: " + e.message);
    }
}

async function editUser(userId) {
    const user = allUsers.find((u) => u.id === userId);
    if (!user) return;

    document.getElementById("edit-user-id").value = userId;
    document.getElementById("edit-user-name").value = user.name;
    document.getElementById("edit-user-plex-username").value = user.plex_username || "";
    document.getElementById("edit-user-plex-token").value = user.plex_token || "";
    document.getElementById("edit-user-prefix").value = user.playlist_prefix || "Daily Drive";
    document.getElementById("edit-user-music-count").value = user.music_count || 20;
    document.getElementById("edit-user-podcast-count").value = user.podcast_count || 3;
    document.getElementById("edit-user-discovery").value = user.discovery_ratio || 40;
    document.getElementById("edit-discovery-label").textContent = (user.discovery_ratio || 40) + "%";
    document.getElementById("edit-user-keep-days").value = user.keep_days || 7;
    document.getElementById("edit-user-description").value = user.playlist_description || "";

    // Render library checkboxes
    const artistLibs = libraries.filter((l) => l.type === "artist");
    let selectedLibs = [];
    try {
        selectedLibs = typeof user.music_libraries === "string"
            ? JSON.parse(user.music_libraries)
            : (user.music_libraries || []);
    } catch { /* ignore */ }
    renderLibraryList("edit-user-libraries", artistLibs, selectedLibs, "edit-user-lib");

    // Render podcast checkboxes
    const podContainer = document.getElementById("edit-user-podcasts");
    if (allPodcasts.length === 0) {
        podContainer.innerHTML = '<p class="muted">Keine Podcasts abonniert. F\u00fcge zuerst Podcasts im Podcasts-Tab hinzu.</p>';
    } else {
        const userPodIds = (user.podcasts || []).map(String);
        podContainer.innerHTML = allPodcasts
            .map((p) => {
                const checked = userPodIds.includes(String(p.id)) ? "checked" : "";
                const selectedClass = checked ? "selected" : "";
                return `
                    <label class="library-item ${selectedClass}">
                        <input type="checkbox" data-prefix="edit-user-pod" data-key="${p.id}" ${checked}
                               onchange="this.parentElement.classList.toggle('selected', this.checked)">
                        <span>${escapeHtml(p.name)}</span>
                    </label>
                `;
            })
            .join("");
    }

    // Load user cover preview
    refreshUserCoverPreview(userId);

    document.getElementById("user-edit-modal").classList.remove("hidden");
}

function closeUserModal() {
    document.getElementById("user-edit-modal").classList.add("hidden");
}

async function saveUser() {
    const userId = parseInt(document.getElementById("edit-user-id").value);
    const musicLibs = getSelectedLibraries("edit-user-lib");
    const podcastIds = getSelectedLibraries("edit-user-pod").map(Number);

    const data = {
        name: document.getElementById("edit-user-name").value,
        plex_username: document.getElementById("edit-user-plex-username").value,
        plex_token: document.getElementById("edit-user-plex-token").value,
        playlist_prefix: document.getElementById("edit-user-prefix").value,
        music_count: parseInt(document.getElementById("edit-user-music-count").value) || 20,
        podcast_count: parseInt(document.getElementById("edit-user-podcast-count").value) || 3,
        discovery_ratio: parseInt(document.getElementById("edit-user-discovery").value) || 40,
        keep_days: parseInt(document.getElementById("edit-user-keep-days").value) || 7,
        playlist_description: document.getElementById("edit-user-description").value,
        music_libraries: musicLibs,
        podcast_ids: podcastIds,
    };

    try {
        const res = await fetch(`/api/users/${userId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        const result = await res.json();
        if (result.success) {
            showResult("edit-user-result", true, "Gespeichert!");
            setTimeout(() => {
                closeUserModal();
                loadUsers();
            }, 800);
        } else {
            showResult("edit-user-result", false, result.error || "Fehler");
        }
    } catch (e) {
        showResult("edit-user-result", false, "Fehler: " + e.message);
    }
}

async function toggleUser(userId, enabled) {
    try {
        await fetch(`/api/users/${userId}/toggle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled }),
        });
        loadUsers();
    } catch (e) {
        console.error("Toggle user failed:", e);
    }
}

async function removeUser(userId, name) {
    if (!confirm(`Benutzer "${name}" wirklich entfernen?`)) return;
    try {
        await fetch(`/api/users/${userId}`, { method: "DELETE" });
        loadUsers();
    } catch (e) {
        console.error("Remove user failed:", e);
    }
}

function toggleNewUserToken() {
    const input = document.getElementById("new-user-plex-token");
    const btn = input.closest(".token-field").querySelector(".btn");
    if (input.type === "password") {
        input.type = "text";
        btn.textContent = "Verbergen";
    } else {
        input.type = "password";
        btn.textContent = "Zeigen";
    }
}

// --- User Cover ---

async function uploadUserCover(input) {
    if (!input.files || !input.files[0]) return;
    const userId = document.getElementById("edit-user-id").value;
    if (!userId) return;

    const formData = new FormData();
    formData.append("file", input.files[0]);

    try {
        const res = await fetch(`/api/users/${userId}/poster`, { method: "POST", body: formData });
        const data = await res.json();
        if (data.success) {
            showResult("edit-cover-result", true, "Cover hochgeladen!");
            refreshUserCoverPreview(userId);
        } else {
            showResult("edit-cover-result", false, "Fehler: " + (data.error || "Upload fehlgeschlagen"));
        }
    } catch (e) {
        showResult("edit-cover-result", false, "Fehler: " + e.message);
    }
    input.value = "";
}

async function deleteUserCover() {
    const userId = document.getElementById("edit-user-id").value;
    if (!userId) return;

    try {
        await fetch(`/api/users/${userId}/poster`, { method: "DELETE" });
        showResult("edit-cover-result", true, "Cover entfernt");
        refreshUserCoverPreview(userId);
    } catch (e) {
        showResult("edit-cover-result", false, "Fehler: " + e.message);
    }
}

function refreshUserCoverPreview(userId) {
    const img = document.getElementById("edit-cover-img");
    const placeholder = document.getElementById("edit-cover-placeholder");
    img.src = `/api/users/${userId}/poster?` + Date.now();
    img.style.display = "";
    placeholder.style.display = "none";
    img.onerror = () => {
        img.style.display = "none";
        placeholder.style.display = "flex";
    };
}

// --- Podcasts ---

async function searchPodcasts() {
    const query = document.getElementById("podcast-search-input").value.trim();
    if (!query) return;

    const container = document.getElementById("podcast-search-results");
    container.innerHTML = '<p class="muted"><span class="spinner"></span> Suche...</p>';

    try {
        const res = await fetch("/api/podcasts/search?q=" + encodeURIComponent(query));
        const results = await res.json();

        if (results.length === 0) {
            container.innerHTML = '<p class="muted">Keine Podcasts gefunden</p>';
            return;
        }

        container.innerHTML = results
            .map((p) => `
                <div class="podcast-result">
                    <img class="podcast-art" src="${p.artwork}" alt="" onerror="this.style.display='none'">
                    <div class="podcast-info">
                        <div class="podcast-name">${escapeHtml(p.name)}</div>
                        <div class="podcast-artist">${escapeHtml(p.artist)}</div>
                        <div class="podcast-genre">${escapeHtml(p.genre)}</div>
                    </div>
                    <button class="btn btn-primary btn-small" onclick='subscribePodcast(${JSON.stringify(p).replace(/'/g, "&#39;")})'>
                        Abonnieren
                    </button>
                </div>
            `)
            .join("");
    } catch (e) {
        container.innerHTML = '<p class="muted">Fehler bei der Suche</p>';
    }
}

async function subscribePodcast(podcast) {
    try {
        const res = await fetch("/api/podcasts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(podcast),
        });
        const data = await res.json();
        if (data.success) {
            loadSubscribedPodcasts();
            document.getElementById("podcast-search-results").innerHTML =
                '<div class="result-box success">"' + escapeHtml(podcast.name) + '" abonniert!</div>';
        }
    } catch (e) {
        console.error("Subscribe failed:", e);
    }
}

async function loadSubscribedPodcasts() {
    try {
        const res = await fetch("/api/podcasts");
        const podcasts = await res.json();
        const container = document.getElementById("subscribed-podcasts");

        if (podcasts.length === 0) {
            container.innerHTML = '<p class="muted">Noch keine Podcasts abonniert. Nutze die Suche oben!</p>';
            return;
        }

        container.innerHTML = podcasts
            .map((p) => `
                <div class="podcast-item ${p.enabled ? "" : "disabled"}">
                    <img class="podcast-art-sm" src="${p.artwork}" alt="" onerror="this.style.display='none'">
                    <div class="podcast-info">
                        <div class="podcast-name">${escapeHtml(p.name)}</div>
                        <div class="podcast-artist">${escapeHtml(p.artist)}</div>
                    </div>
                    <div class="podcast-actions">
                        <button class="btn btn-small btn-secondary" onclick="togglePodcast(${p.id}, ${!p.enabled})">
                            ${p.enabled ? "Deaktivieren" : "Aktivieren"}
                        </button>
                        <button class="btn btn-small btn-danger" onclick="removePodcast(${p.id}, '${escapeHtml(p.name)}')">
                            Entfernen
                        </button>
                    </div>
                </div>
            `)
            .join("");
    } catch {
        document.getElementById("subscribed-podcasts").innerHTML = '<p class="muted">Fehler beim Laden</p>';
    }
}

async function togglePodcast(id, enabled) {
    try {
        await fetch(`/api/podcasts/${id}/toggle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled }),
        });
        loadSubscribedPodcasts();
    } catch (e) {
        console.error("Toggle failed:", e);
    }
}

async function removePodcast(id, name) {
    if (!confirm(`Podcast "${name}" wirklich entfernen?`)) return;
    try {
        await fetch(`/api/podcasts/${id}`, { method: "DELETE" });
        loadSubscribedPodcasts();
    } catch (e) {
        console.error("Remove failed:", e);
    }
}

async function refreshPodcasts() {
    const btn = document.getElementById("refresh-podcasts-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Lade Episoden...';

    try {
        const res = await fetch("/api/podcasts/refresh", { method: "POST" });
        const data = await res.json();
        showResult("refresh-result", true, `${data.downloaded} neue Episoden heruntergeladen`);
    } catch (e) {
        showResult("refresh-result", false, "Fehler: " + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Jetzt neue Episoden laden";
    }
}

// --- Generate ---

async function loadGenerateUserSelect() {
    try {
        const res = await fetch("/api/users");
        const users = await res.json();
        const select = document.getElementById("generate-user-select");

        select.innerHTML = '<option value="">Alle Benutzer / Global</option>';
        users.filter((u) => u.enabled).forEach((u) => {
            select.innerHTML += `<option value="${u.id}">${escapeHtml(u.name)}</option>`;
        });
    } catch {
        // ignore
    }
}

async function generateNow() {
    const btn = document.getElementById("generate-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Generiere...';

    const userId = document.getElementById("generate-user-select").value;

    try {
        const body = userId ? { user_id: parseInt(userId) } : {};
        const res = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (data.success) {
            const p = data.playlist;
            if (Array.isArray(p)) {
                const summaries = p.map((pl) =>
                    `"${pl.name}"${pl.user ? " (" + pl.user + ")" : ""}: ${pl.music} Musik + ${pl.podcasts} Podcasts`
                );
                showResult("generate-result", true, summaries.join("\n"));
            } else {
                showResult(
                    "generate-result",
                    true,
                    `Playlist "${p.name}" erstellt: ${p.music} Musik + ${p.podcasts} Podcasts = ${p.total} Titel` +
                    (p.user ? ` (${p.user})` : "")
                );
            }
            loadPlaylists();
        } else {
            showResult("generate-result", false, "Fehler: " + (data.error || "Unbekannter Fehler"));
        }
    } catch (e) {
        showResult("generate-result", false, "Fehler: " + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Jetzt generieren";
    }
}

// --- Playlists ---

async function loadPlaylists() {
    try {
        const res = await fetch("/api/playlists");
        const playlists = await res.json();
        const container = document.getElementById("active-playlists");

        if (playlists.length === 0) {
            container.innerHTML = '<p class="muted">Keine Daily Drive Playlists gefunden</p>';
            return;
        }

        container.innerHTML = playlists
            .map(
                (p) => `
                <div class="playlist-item">
                    <span class="name">${escapeHtml(p.title)}</span>
                    <span class="meta">${p.item_count} Titel</span>
                </div>
            `
            )
            .join("");
    } catch {
        document.getElementById("active-playlists").innerHTML = '<p class="muted">Fehler beim Laden</p>';
    }
}

// --- History ---

async function loadHistory() {
    try {
        const res = await fetch("/api/history");
        const history = await res.json();
        const container = document.getElementById("history-list");

        if (history.length === 0) {
            container.innerHTML = '<p class="muted">Noch keine Playlists generiert</p>';
            return;
        }

        container.innerHTML = `
            <table class="history-table">
                <thead>
                    <tr>
                        <th>Playlist</th>
                        <th>Musik</th>
                        <th>Podcasts</th>
                        <th>Gesamt</th>
                        <th>Erstellt</th>
                    </tr>
                </thead>
                <tbody>
                    ${history
                        .map(
                            (h) => `
                        <tr>
                            <td>${escapeHtml(h.name)}</td>
                            <td>${h.music_count}</td>
                            <td>${h.podcast_count}</td>
                            <td>${h.track_count}</td>
                            <td>${escapeHtml(h.created_at)}</td>
                        </tr>
                    `
                        )
                        .join("")}
                </tbody>
            </table>
        `;
    } catch {
        document.getElementById("history-list").innerHTML = '<p class="muted">Fehler beim Laden</p>';
    }
}

// --- Helpers ---

function toggleToken() {
    const input = document.getElementById("plex-token");
    const btn = input.nextElementSibling;
    if (input.type === "password") {
        input.type = "text";
        btn.textContent = "Verbergen";
    } else {
        input.type = "password";
        btn.textContent = "Zeigen";
    }
}

function showResult(elementId, success, message) {
    const el = document.getElementById(elementId);
    el.className = "result-box " + (success ? "success" : "error");
    el.textContent = message;
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
