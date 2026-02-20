# Plex Daily Drive

Automatische Playlist-Erstellung für Plex - wie Spotifys "Daily Drive". Erstellt täglich eine gemischte Playlist aus Musik und Podcasts.

## Features

- Tägliche automatische Playlist-Generierung
- Mischung aus Musik-Tracks und Podcast-Episoden (wie Spotify Daily Drive)
- **Podcast-Management**: Podcasts per iTunes-Suche abonnieren, automatischer RSS-Download
- **Mehrere Zeitpläne**: z.B. morgens um 6:00 und mittags um 12:00
- Konfigurierbares Verhältnis von Musik zu Podcasts
- Web-Interface zur Steuerung und Konfiguration
- Automatische Bereinigung alter Playlists und Podcast-Episoden
- Läuft als Docker Container (Unraid-kompatibel)

## Quick Start

### 1. Plex Token ermitteln

Anleitung: https://support.plex.tv/articles/204059436/

### 2. Docker Compose konfigurieren

```yaml
services:
  plex-daily-drive:
    build: .
    container_name: plex-daily-drive
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      - PLEX_URL=http://deine-plex-ip:32400
      - PLEX_TOKEN=dein-plex-token
      - TZ=Europe/Berlin
    volumes:
      - plex-daily-drive-data:/data
      - /pfad/zu/plex/media/podcasts:/podcasts  # Muss in einer Plex-Bibliothek liegen!

volumes:
  plex-daily-drive-data:
```

### 3. Starten

```bash
docker compose up -d
```

### 4. Web-Interface öffnen

http://localhost:5000

## Podcast-Funktionalität

Da Plex keine native Podcast-Unterstützung mehr bietet, hat Plex Daily Drive ein eigenes Podcast-Management:

1. **Suchen**: Im "Podcasts"-Tab nach Podcasts suchen (nutzt iTunes-Katalog)
2. **Abonnieren**: Gewünschte Podcasts mit einem Klick abonnieren
3. **Automatischer Download**: Neue Episoden werden automatisch als MP3 heruntergeladen
4. **Plex-Integration**: Der Download-Ordner muss als Plex Musik-Bibliothek eingerichtet sein

### Einrichtung

1. Erstelle einen Ordner für Podcasts (z.B. `/mnt/user/media/podcasts`)
2. Mounte diesen Ordner in den Container als `/podcasts`
3. Erstelle in Plex eine **Musik-Bibliothek** die auf diesen Ordner zeigt
4. Im Web-Interface den Pfad unter "Podcast Download-Pfad" eintragen
5. Podcasts suchen und abonnieren

Die Episoden werden 15 Minuten vor jeder Playlist-Generierung automatisch aktualisiert.

## Konfiguration

### Umgebungsvariablen

| Variable | Beschreibung | Standard |
|---|---|---|
| `PLEX_URL` | URL des Plex Servers | `http://localhost:32400` |
| `PLEX_TOKEN` | Plex Authentifizierungs-Token | (leer) |
| `TZ` | Zeitzone | System-Standard |

**Hinweis**: PLEX_URL und PLEX_TOKEN können auch direkt im Web-Interface konfiguriert werden.

### Web-Interface Einstellungen

- **Plex URL / Token**: Plex-Server Verbindung (editierbar im UI)
- **Musik-Bibliotheken**: Welche Plex-Bibliotheken für Musik verwendet werden
- **Anzahl Musiktitel**: Zufällige Musiktitel pro Playlist (Standard: 20)
- **Anzahl Podcast-Episoden**: Podcast-Episoden pro Playlist (Standard: 3)
- **Playlist-Prefix**: Name-Prefix für Playlists (Standard: "Daily Drive")
- **Aufbewahrung**: Tage alte Playlists behalten (Standard: 7)
- **Zeitplan**: Mehrere Generierungszeiten konfigurierbar
- **Podcast Download-Pfad**: Wo Episoden gespeichert werden
- **Max. Episoden pro Podcast**: Ältere werden automatisch gelöscht

## Wie funktioniert die Mischung?

Die Playlist wird im "Daily Drive"-Stil erstellt:

1. Zufällige Musiktitel werden aus den konfigurierten Bibliotheken gezogen
2. Podcast-Episoden werden aus der Plex-Bibliothek geladen (vorher per RSS heruntergeladen)
3. Die Musik wird in Blöcke aufgeteilt, zwischen denen Podcast-Episoden eingefügt werden
4. Ergebnis: `[Musik-Block] → [Podcast] → [Musik-Block] → [Podcast] → [Musik-Block]`
