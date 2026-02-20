# Plex Daily Drive

Automatische Playlist-Erstellung für Plex - wie Spotifys "Daily Drive". Erstellt täglich eine gemischte Playlist aus Musik und Podcasts.

## Features

- Tägliche automatische Playlist-Generierung
- Mischung aus Musik-Tracks und Podcast-Episoden (wie Spotify Daily Drive)
- Konfigurierbares Verhältnis von Musik zu Podcasts
- Web-Interface zur Steuerung und Konfiguration
- Automatische Bereinigung alter Playlists
- Option: nur ungespielte / neueste Podcast-Episoden
- Läuft als Docker Container

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
      - SCHEDULE_HOUR=6
      - SCHEDULE_MINUTE=0
      - TZ=Europe/Berlin
    volumes:
      - plex-daily-drive-data:/data

volumes:
  plex-daily-drive-data:
```

### 3. Starten

```bash
docker compose up -d
```

### 4. Web-Interface öffnen

http://localhost:5000

## Konfiguration

### Umgebungsvariablen

| Variable | Beschreibung | Standard |
|---|---|---|
| `PLEX_URL` | URL des Plex Servers | `http://localhost:32400` |
| `PLEX_TOKEN` | Plex Authentifizierungs-Token | (leer) |
| `SCHEDULE_HOUR` | Stunde der täglichen Generierung (0-23) | `6` |
| `SCHEDULE_MINUTE` | Minute der täglichen Generierung (0-59) | `0` |
| `TZ` | Zeitzone | System-Standard |

### Web-Interface Einstellungen

- **Musik-Bibliotheken**: Welche Plex-Bibliotheken für Musik verwendet werden
- **Podcast-Bibliotheken**: Welche Plex-Bibliotheken für Podcasts verwendet werden
- **Anzahl Musiktitel**: Wie viele zufällige Musiktitel pro Playlist (Standard: 20)
- **Anzahl Podcast-Episoden**: Wie viele Podcast-Episoden pro Playlist (Standard: 3)
- **Playlist-Prefix**: Name-Prefix für generierte Playlists (Standard: "Daily Drive")
- **Aufbewahrung**: Wie viele Tage alte Playlists behalten werden (Standard: 7)
- **Nur neueste Podcasts**: Bevorzugt kürzlich hinzugefügte Episoden
- **Nur ungespielte Podcasts**: Filtert bereits gehörte Episoden aus

## Wie funktioniert die Mischung?

Die Playlist wird im "Daily Drive"-Stil erstellt:

1. Zufällige Musiktitel werden aus den konfigurierten Bibliotheken gezogen
2. Podcast-Episoden werden nach den Filterkriterien ausgewählt
3. Die Musik wird in Blöcke aufgeteilt, zwischen denen Podcast-Episoden eingefügt werden
4. Ergebnis: `[Musik-Block] → [Podcast] → [Musik-Block] → [Podcast] → [Musik-Block]`
