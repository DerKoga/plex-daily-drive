// State
let settings = {};
let libraries = [];

// --- Init ---

document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    loadStatus();
    loadSettings();
    loadLibraries();
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
            if (tab.dataset.tab === "generate") loadPlaylists();
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
        nextEl.textContent = data.next_run || "Nicht geplant";
    } catch {
        document.getElementById("plex-status").textContent = "Fehler";
        document.getElementById("plex-status").className = "status-value status-error";
    }
}

// --- Settings ---

async function loadSettings() {
    try {
        const res = await fetch("/api/settings");
        settings = await res.json();

        document.getElementById("playlist-prefix").value = settings.playlist_prefix || "Daily Drive";
        document.getElementById("keep-days").value = settings.keep_days || "7";
        document.getElementById("music-count").value = settings.music_count || "20";
        document.getElementById("podcast-count").value = settings.podcast_count || "3";
        document.getElementById("schedule-hour").value = settings.schedule_hour || "6";
        document.getElementById("schedule-minute").value = settings.schedule_minute || "0";
        document.getElementById("enabled").checked = settings.enabled === "true";
        document.getElementById("podcast-recent-only").checked = settings.podcast_recent_only === "true";
        document.getElementById("podcast-unplayed-only").checked = settings.podcast_unplayed_only === "true";
    } catch (e) {
        console.error("Failed to load settings:", e);
    }
}

async function saveSettings() {
    const musicLibs = getSelectedLibraries("music");
    const podcastLibs = getSelectedLibraries("podcast");

    const data = {
        playlist_prefix: document.getElementById("playlist-prefix").value,
        keep_days: document.getElementById("keep-days").value,
        music_count: document.getElementById("music-count").value,
        podcast_count: document.getElementById("podcast-count").value,
        schedule_hour: document.getElementById("schedule-hour").value,
        schedule_minute: document.getElementById("schedule-minute").value,
        enabled: document.getElementById("enabled").checked ? "true" : "false",
        podcast_recent_only: document.getElementById("podcast-recent-only").checked ? "true" : "false",
        podcast_unplayed_only: document.getElementById("podcast-unplayed-only").checked ? "true" : "false",
        music_libraries: musicLibs,
        podcast_libraries: podcastLibs,
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

// --- Libraries ---

async function loadLibraries() {
    try {
        const res = await fetch("/api/libraries");
        libraries = await res.json();

        const settingsRes = await fetch("/api/settings");
        const currentSettings = await settingsRes.json();

        let selectedMusic = [];
        let selectedPodcasts = [];
        try {
            selectedMusic = JSON.parse(currentSettings.music_libraries || "[]");
            selectedPodcasts = JSON.parse(currentSettings.podcast_libraries || "[]");
        } catch { /* ignore */ }

        const artistLibs = libraries.filter((l) => l.type === "artist");

        renderLibraryList("music-libraries", artistLibs, selectedMusic, "music");
        renderLibraryList("podcast-libraries", artistLibs, selectedPodcasts, "podcast");
    } catch (e) {
        document.getElementById("music-libraries").innerHTML = '<p class="muted">Fehler beim Laden der Bibliotheken. Ist Plex verbunden?</p>';
        document.getElementById("podcast-libraries").innerHTML = '<p class="muted">Fehler beim Laden der Bibliotheken.</p>';
    }
}

function renderLibraryList(containerId, libs, selectedKeys, prefix) {
    const container = document.getElementById(containerId);
    if (libs.length === 0) {
        container.innerHTML = '<p class="muted">Keine passenden Bibliotheken gefunden</p>';
        return;
    }

    container.innerHTML = libs
        .map((lib) => {
            const checked = selectedKeys.includes(lib.key) ? "checked" : "";
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
        const res = await fetch("/api/test-connection", { method: "POST" });
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

// --- Generate ---

async function generateNow() {
    const btn = document.getElementById("generate-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Generiere...';

    try {
        const res = await fetch("/api/generate", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            const p = data.playlist;
            showResult(
                "generate-result",
                true,
                `Playlist "${p.name}" erstellt: ${p.music} Musik + ${p.podcasts} Podcasts = ${p.total} Titel`
            );
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
                    <span class="name">${p.title}</span>
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
                            <td>${h.name}</td>
                            <td>${h.music_count}</td>
                            <td>${h.podcast_count}</td>
                            <td>${h.track_count}</td>
                            <td>${h.created_at}</td>
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

function showResult(elementId, success, message) {
    const el = document.getElementById(elementId);
    el.className = "result-box " + (success ? "success" : "error");
    el.textContent = message;
}
