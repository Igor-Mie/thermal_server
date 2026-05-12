#!/usr/bin/env bash
set -e

APP_DIR="$HOME/thermal_www"
ARCHIVE_DIR="$HOME/thermal_archive"

echo "Instaluję zależności..."
sudo apt update
sudo apt install -y python3 python3-flask python3-opencv python3-numpy v4l-utils

echo "Tworzę katalogi..."
mkdir -p "$APP_DIR"
mkdir -p "$ARCHIVE_DIR"

echo "Kopiuję thermal_server.py..."
cp thermal_server.py "$APP_DIR/thermal_server.py"

echo "Dodaję użytkownika do grupy video..."
sudo usermod -aG video "$USER"

echo
echo "Gotowe."
echo "Test ręczny:"
echo "python3 $APP_DIR/thermal_server.py"
echo
echo "Potem otwórz:"
echo "http://IP_KOMPUTERA:8088"
echo "http://IP_KOMPUTERA:8088/archive"
echo
echo "Uwaga: po dodaniu do grupy video może być potrzebne wylogowanie/zalogowanie."
