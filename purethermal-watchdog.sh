#!/usr/bin/env bash

ARCHIVE_DIR="/home/avena/thermal_archive"
SERVICE="purethermal-server"
MAX_AGE=180

LATEST=$(ls -t "$ARCHIVE_DIR"/*.raw 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    logger -t purethermal-watchdog "Brak plików RAW, restartuję $SERVICE"
    systemctl restart "$SERVICE"
    exit 0
fi

NOW=$(date +%s)
MTIME=$(stat -c %Y "$LATEST")
AGE=$((NOW - MTIME))

if [ "$AGE" -gt "$MAX_AGE" ]; then
    logger -t purethermal-watchdog "Najnowsza ramka ma ${AGE}s, restartuję $SERVICE"
    systemctl restart "$SERVICE"
else
    logger -t purethermal-watchdog "OK, najnowsza ramka ma ${AGE}s"
fi
