#!/usr/bin/env bash
set -e

APP_NAME="purethermal-server"
WATCHDOG_NAME="purethermal-watchdog"

APP_DIR="$HOME/thermal_www"
ARCHIVE_DIR="$HOME/thermal_archive"
APP_FILE="$APP_DIR/thermal_server.py"

USER_NAME="$USER"
GROUP_NAME="video"

echo "======================================"
echo " PureThermal Y16 Server installer"
echo "======================================"
echo
echo "User:        $USER_NAME"
echo "App dir:     $APP_DIR"
echo "Archive dir: $ARCHIVE_DIR"
echo

if [ ! -f "thermal_server.py" ]; then
    echo "Błąd: nie znaleziono thermal_server.py w bieżącym katalogu."
    echo "Uruchom install.sh z katalogu repozytorium."
    exit 1
fi

echo "Instaluję zależności..."
sudo apt update
sudo apt install -y python3 python3-flask python3-opencv python3-numpy v4l-utils

echo
echo "Tworzę katalogi..."
mkdir -p "$APP_DIR"
mkdir -p "$ARCHIVE_DIR"

echo
echo "Kopiuję thermal_server.py..."
cp thermal_server.py "$APP_FILE"

echo
echo "Dodaję użytkownika do grupy video..."
sudo usermod -aG video "$USER_NAME"

echo
echo "Zatrzymuję stare usługi, jeśli istnieją..."
sudo systemctl stop "$APP_NAME" 2>/dev/null || true
sudo systemctl stop "$WATCHDOG_NAME.timer" 2>/dev/null || true
sudo systemctl stop "$WATCHDOG_NAME.service" 2>/dev/null || true

echo
echo "Instaluję usługę $APP_NAME..."
sudo tee /etc/systemd/system/${APP_NAME}.service >/dev/null <<SERVICEEOF
[Unit]
Description=PureThermal Y16 recorder and web viewer
After=network.target

[Service]
Type=simple
User=${USER_NAME}
Group=${GROUP_NAME}
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_FILE}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF

echo
echo "Instaluję watchdog..."
sudo tee /usr/local/bin/${WATCHDOG_NAME}.sh >/dev/null <<WATCHDOGEOF
#!/usr/bin/env bash

ARCHIVE_DIR="${ARCHIVE_DIR}"
SERVICE="${APP_NAME}"
MAX_AGE=180

LATEST=\$(ls -t "\$ARCHIVE_DIR"/*.raw 2>/dev/null | head -1)

if [ -z "\$LATEST" ]; then
    logger -t ${WATCHDOG_NAME} "Brak plików RAW, restartuję \$SERVICE"
    systemctl restart "\$SERVICE"
    exit 0
fi

NOW=\$(date +%s)
MTIME=\$(stat -c %Y "\$LATEST")
AGE=\$((NOW - MTIME))

if [ "\$AGE" -gt "\$MAX_AGE" ]; then
    logger -t ${WATCHDOG_NAME} "Najnowsza ramka ma \${AGE}s, restartuję \$SERVICE"
    systemctl restart "\$SERVICE"
else
    logger -t ${WATCHDOG_NAME} "OK, najnowsza ramka ma \${AGE}s"
fi
WATCHDOGEOF

sudo chmod +x /usr/local/bin/${WATCHDOG_NAME}.sh

echo
echo "Instaluję usługę watchdoga..."
sudo tee /etc/systemd/system/${WATCHDOG_NAME}.service >/dev/null <<WATCHDOGSERVICEEOF
[Unit]
Description=PureThermal frame watchdog

[Service]
Type=oneshot
ExecStart=/usr/local/bin/${WATCHDOG_NAME}.sh
WATCHDOGSERVICEEOF

echo
echo "Instaluję timer watchdoga..."
sudo tee /etc/systemd/system/${WATCHDOG_NAME}.timer >/dev/null <<WATCHDOGTIMEREOF
[Unit]
Description=Run PureThermal watchdog every minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
Unit=${WATCHDOG_NAME}.service

[Install]
WantedBy=timers.target
WATCHDOGTIMEREOF

echo
echo "Przeładowuję systemd..."
sudo systemctl daemon-reload

echo
echo "Włączam i uruchamiam usługi..."
sudo systemctl enable "$APP_NAME"
sudo systemctl restart "$APP_NAME"

sudo systemctl enable --now "${WATCHDOG_NAME}.timer"

echo
echo "======================================"
echo " Instalacja zakończona"
echo "======================================"
echo
echo "Status serwera:"
sudo systemctl --no-pager --lines=5 status "$APP_NAME" || true

echo
echo "Timer watchdoga:"
systemctl list-timers | grep purethermal || true

echo
echo "Adresy:"
echo "LIVE:     http://IP_KOMPUTERA:8088"
echo "ARCHIVE:  http://IP_KOMPUTERA:8088/archive"
echo "MJPEG:    http://IP_KOMPUTERA:8088/mjpeg"
echo
echo "Sprawdź IP komputera:"
echo "hostname -I"
echo
echo "Uwaga: jeśli użytkownik nie miał wcześniej dostępu do grupy video,"
echo "może być potrzebne wylogowanie/zalogowanie albo restart systemu."
