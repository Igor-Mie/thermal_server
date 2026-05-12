# PureThermal Y16 Server

Serwer WWW dla kamery termowizyjnej PureThermal / FLIR Lepton pod Ubuntu.

Projekt umożliwia:

- odczyt surowych ramek `Y16` z kamery PureThermal,
- przeliczanie wartości pikseli na temperaturę w °C,
- podgląd live w przeglądarce,
- odczyt temperatury punktu pod kursorem myszy,
- zapis ramek `Y16` do archiwum,
- przeglądanie archiwum na timeline,
- odczyt temperatury z historycznych ramek,
- wystawienie streamu MJPEG dla ZoneMindera,
- automatyczny start jako usługa `systemd`,
- watchdog sprawdzający, czy zapis ramek się nie zatrzymał.

Repozytorium:

```text
https://github.com/Igor-Mie/thermal_server.git
```

---

# 1. Co zawiera projekt

## `thermal_server.py`

Główny program.

Robi:

```text
- czyta kamerę PureThermal z /dev/video0,
- pobiera ramki Y16 160x120,
- przelicza piksele na temperaturę,
- zapisuje pliki .raw i .json do archiwum,
- udostępnia live viewer w przeglądarce,
- udostępnia archive viewer z timeline,
- pokazuje temperaturę pod kursorem,
- wystawia stream MJPEG dla ZoneMindera.
```

Adresy po uruchomieniu:

```text
/                  - live viewer
/archive           - archiwum / timeline
/frame.jpg         - aktualna ramka JPG
/temp              - temperatura punktu live
/archive_frame.jpg - historyczna ramka JPG
/archive_temp      - temperatura punktu z archiwum
/mjpeg             - stream MJPEG
```

---

## `install.sh`

Instalator.

Robi:

```text
- instaluje wymagane pakiety,
- tworzy katalog aplikacji,
- tworzy katalog archiwum,
- kopiuje thermal_server.py,
- tworzy usługę systemd purethermal-server,
- tworzy watchdog,
- tworzy timer watchdoga,
- uruchamia usługi.
```

---

## `purethermal-server.service.example`

Przykładowa usługa systemd dla głównego serwera.

Po instalacji właściwy plik znajduje się tutaj:

```text
/etc/systemd/system/purethermal-server.service
```

---

## `purethermal-watchdog.sh`

Skrypt watchdoga.

Sprawdza, czy w archiwum pojawiają się nowe pliki `.raw`.

Jeśli najnowsza ramka jest za stara, wykonuje:

```bash
systemctl restart purethermal-server
```

---

## `purethermal-watchdog.service.example`

Przykładowy service systemd dla watchdoga.

Po instalacji właściwy plik znajduje się tutaj:

```text
/etc/systemd/system/purethermal-watchdog.service
```

---

## `purethermal-watchdog.timer.example`

Przykładowy timer systemd.

Uruchamia watchdog co minutę.

Po instalacji właściwy plik znajduje się tutaj:

```text
/etc/systemd/system/purethermal-watchdog.timer
```

---

## `.gitignore`

Chroni przed przypadkowym wrzuceniem do repo plików tymczasowych i dużych danych.

Nie należy wrzucać do Gita:

```text
*.raw
thermal_archive/
thermal_old_files/
*.log
```

---

# 2. Jak działa odczyt temperatury

PureThermal udostępnia format:

```text
Y16
160x120
```

Każdy piksel jest wartością `uint16`.

Temperatura jest liczona według wzoru:

```text
°C = RAW / 100 - 273.15
```

Przykład:

```text
RAW = 29681
29681 / 100 = 296.81 K
296.81 - 273.15 = 23.66 °C
```

---

# 3. Co trzeba sprawdzić albo zmienić przy instalacji

## 3.1 Urządzenie kamery

Domyślnie kamera jest ustawiona jako:

```python
DEVICE = "/dev/video0"
```

To znajduje się w pliku:

```text
thermal_server.py
```

Sprawdzenie kamery:

```bash
v4l2-ctl --list-devices
```

Przykład poprawnego wyniku:

```text
PureThermal (fw:v1.3.0): PureTh:
        /dev/video0
        /dev/video1
        /dev/media0
```

Jeśli kamera jest jako `/dev/video2`, zmień:

```python
DEVICE = "/dev/video0"
```

na:

```python
DEVICE = "/dev/video2"
```

---

## 3.2 Format Y16

Sprawdź formaty:

```bash
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Szukaj:

```text
'Y16 ' (16-bit Greyscale)
Size: Discrete 160x120
```

Jeśli nie ma `Y16`, ten projekt nie będzie mógł odczytać prawdziwej temperatury.

---

## 3.3 Interwał zapisu

W pliku:

```text
thermal_server.py
```

znajdź:

```python
CAPTURE_INTERVAL = 2.0
```

To oznacza zapis jednej ramki co 2 sekundy.

Przykłady:

```python
CAPTURE_INTERVAL = 1.0
```

szybszy zapis, większe zużycie dysku.

```python
CAPTURE_INTERVAL = 5.0
```

wolniejszy zapis, mniejsze zużycie dysku.

---

## 3.4 Retencja archiwum

W pliku:

```text
thermal_server.py
```

znajdź:

```python
RETENTION_DAYS = 7
```

To oznacza trzymanie archiwum przez 7 dni.

Przykłady:

```python
RETENTION_DAYS = 1
```

trzymanie około jednego dnia.

```python
RETENTION_DAYS = 30
```

trzymanie około miesiąca.

Przy `CAPTURE_INTERVAL = 2.0` zużycie dysku wynosi orientacyjnie:

```text
około 1.6 GB / dobę
około 11 GB / 7 dni
```

---

## 3.5 Zakres kolorowania obrazu

W pliku:

```text
thermal_server.py
```

znajdź:

```python
TEMP_LOW_C = 20.0
TEMP_HIGH_C = 50.0
```

To wpływa tylko na kolory obrazu, nie na prawdziwy odczyt temperatury.

Przykład dla pomieszczeń:

```python
TEMP_LOW_C = 15.0
TEMP_HIGH_C = 40.0
```

Przykład dla cieplejszych obiektów:

```python
TEMP_LOW_C = 20.0
TEMP_HIGH_C = 100.0
```

---

## 3.6 Port WWW

Na końcu `thermal_server.py` jest:

```python
app.run(host="0.0.0.0", port=8088, threaded=True)
```

Domyślny port:

```text
8088
```

Jeśli port jest zajęty, można zmienić np. na:

```python
app.run(host="0.0.0.0", port=8090, threaded=True)
```

Wtedy adres będzie:

```text
http://IP_KOMPUTERA:8090
```

---

## 3.7 Użytkownik systemowy

`install.sh` używa aktualnego użytkownika:

```bash
USER_NAME="$USER"
```

Jeśli instalujesz jako użytkownik `avena`, usługa będzie działać jako `avena`.

Jeśli chcesz wymusić innego użytkownika, zmień w `install.sh`:

```bash
USER_NAME="$USER"
```

na przykład na:

```bash
USER_NAME="avena"
```

---

## 3.8 Katalog aplikacji

Domyślnie:

```text
~/thermal_www
```

W `install.sh`:

```bash
APP_DIR="$HOME/thermal_www"
```

---

## 3.9 Katalog archiwum

Domyślnie:

```text
~/thermal_archive
```

W `install.sh`:

```bash
ARCHIVE_DIR="$HOME/thermal_archive"
```

W `thermal_server.py`:

```python
ARCHIVE_DIR = os.path.expanduser("~/thermal_archive")
```

Jeśli zmieniasz katalog archiwum, zmień go w obu miejscach.

---

## 3.10 Watchdog

Watchdog sprawdza wiek najnowszego pliku `.raw`.

W wygenerowanym skrypcie:

```text
/usr/local/bin/purethermal-watchdog.sh
```

jest:

```bash
MAX_AGE=180
```

To oznacza 180 sekund.

Jeśli najnowsza ramka jest starsza niż 180 sekund, watchdog restartuje usługę:

```text
purethermal-server
```

---

# 4. Instalacja krok po kroku od zera

## Krok 1: zainstaluj Git

```bash
sudo apt update
sudo apt install -y git
```

---

## Krok 2: pobierz repozytorium

```bash
cd ~
git clone https://github.com/Igor-Mie/thermal_server.git
cd thermal_server
```

---

## Krok 3: sprawdź, czy kamera jest widoczna

```bash
lsusb
v4l2-ctl --list-devices
```

Jeśli `v4l2-ctl` nie istnieje, możesz od razu uruchomić instalator, bo doinstaluje `v4l-utils`.

---

## Krok 4: sprawdź format Y16

Najczęściej kamera będzie jako `/dev/video0`:

```bash
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Szukaj:

```text
Y16
160x120
```

Jeśli kamera jest pod innym numerem, np. `/dev/video2`, sprawdź:

```bash
v4l2-ctl -d /dev/video2 --list-formats-ext
```

i potem zmień `DEVICE` w `thermal_server.py`.

---

## Krok 5: dostosuj ustawienia, jeśli trzeba

Edytuj:

```bash
nano thermal_server.py
```

Najważniejsze rzeczy do zmiany:

```python
DEVICE = "/dev/video0"
CAPTURE_INTERVAL = 2.0
RETENTION_DAYS = 7
TEMP_LOW_C = 20.0
TEMP_HIGH_C = 50.0
```

Zapis w nano:

```text
Ctrl + O
Enter
Ctrl + X
```

---

## Krok 6: uruchom instalator

```bash
./install.sh
```

Instalator wykona:

```text
- instalację pakietów,
- utworzenie ~/thermal_www,
- utworzenie ~/thermal_archive,
- skopiowanie thermal_server.py,
- utworzenie purethermal-server.service,
- utworzenie purethermal-watchdog.service,
- utworzenie purethermal-watchdog.timer,
- włączenie i uruchomienie usług.
```

---

## Krok 7: sprawdź status usługi

```bash
sudo systemctl status purethermal-server --no-pager
```

Powinno być:

```text
Active: active (running)
```

---

## Krok 8: sprawdź watchdog

```bash
systemctl list-timers | grep purethermal
```

Powinieneś zobaczyć:

```text
purethermal-watchdog.timer
```

---

## Krok 9: sprawdź IP komputera

```bash
hostname -I
```

Przykład:

```text
10.3.14.87
```

---

## Krok 10: otwórz live viewer

W przeglądarce:

```text
http://IP_KOMPUTERA:8088
```

Przykład:

```text
http://10.3.14.87:8088
```

---

## Krok 11: otwórz archiwum / timeline

```text
http://IP_KOMPUTERA:8088/archive
```

Przykład:

```text
http://10.3.14.87:8088/archive
```

---

## Krok 12: sprawdź odczyt temperatury z terminala

```bash
curl -s "http://127.0.0.1:8088/temp?x=80&y=60"
```

Poprawny wynik wygląda podobnie:

```json
{
  "frame_age_s": 1.38,
  "raw": 29681,
  "temp_c": 23.66,
  "x": 80,
  "y": 60
}
```

Najważniejsze:

```text
frame_age_s
```

Jeśli `frame_age_s` jest małe, np. `0–5`, live działa poprawnie.

---

# 5. Adresy po instalacji

Live:

```text
http://IP_KOMPUTERA:8088
```

Archiwum:

```text
http://IP_KOMPUTERA:8088/archive
```

Stream MJPEG:

```text
http://IP_KOMPUTERA:8088/mjpeg
```

Lokalnie:

```text
http://127.0.0.1:8088
http://127.0.0.1:8088/archive
http://127.0.0.1:8088/mjpeg
```

---

# 6. Archiwum Y16

Pliki zapisują się w:

```text
~/thermal_archive
```

Każda ramka tworzy parę plików:

```text
2026-05-12_12-07-58.raw
2026-05-12_12-07-58.json
```

Plik `.raw`:

```text
surowa ramka Y16
160 x 120
uint16
38400 bajtów
```

Plik `.json` zawiera:

```text
- czas,
- rozmiar,
- format,
- min temperatura,
- max temperatura,
- średnia temperatura,
- temperatura środka.
```

Sprawdzenie najnowszych ramek:

```bash
ls -lt ~/thermal_archive/*.raw | head -5
```

Sprawdzenie rozmiaru archiwum:

```bash
du -sh ~/thermal_archive
```

---

# 7. ZoneMinder

Najbezpieczniejszy układ:

```text
PureThermal USB
        ↓
thermal_server.py
        ↓
MJPEG / HTTP
        ↓
ZoneMinder
```

Dzięki temu tylko `thermal_server.py` używa `/dev/video0`.

Adres dla ZoneMindera, jeśli ZoneMinder działa na tym samym komputerze:

```text
http://127.0.0.1:8088/mjpeg
```

Uwaga:

```text
ZoneMinder nie odczyta temperatury pod kursorem.
Do temperatury używaj strony live albo archiwum.
```

---

# 8. Najważniejsze komendy administracyjne

Status serwera:

```bash
sudo systemctl status purethermal-server --no-pager
```

Logi serwera:

```bash
journalctl -u purethermal-server -f
```

Restart serwera:

```bash
sudo systemctl restart purethermal-server
```

Status watchdoga:

```bash
systemctl list-timers | grep purethermal
```

Logi watchdoga:

```bash
journalctl -t purethermal-watchdog -n 50 --no-pager
```

Sprawdzenie live:

```bash
curl -s "http://127.0.0.1:8088/temp?x=80&y=60"
```

Sprawdzenie archiwum:

```bash
ls -lt ~/thermal_archive/*.raw | head -5
du -sh ~/thermal_archive
```

---

# 9. Problem: obraz live się zaciął

Sprawdź wiek ramki:

```bash
curl -s "http://127.0.0.1:8088/temp?x=80&y=60"
```

Sprawdź, czy archiwum się aktualizuje:

```bash
date
ls -lt ~/thermal_archive/*.raw | head -5
```

Sprawdź procesy kamery:

```bash
ps -o pid,etimes,cmd -C v4l2-ctl -C timeout
sudo fuser -v /dev/video0
```

Jeśli nowe pliki `.raw` się nie pojawiają i `frame_age_s` rośnie, odczyt z kamery się zatrzymał.

Spróbuj:

```bash
sudo systemctl restart purethermal-server
```

Jeśli nie pomoże:

```text
1. odłącz kamerę USB-C,
2. poczekaj 5 sekund,
3. podłącz ponownie,
4. zrestartuj usługę.
```

```bash
sudo systemctl restart purethermal-server
```

---

# 10. Watchdog

Watchdog co minutę sprawdza wiek najnowszej ramki `.raw`.

Jeśli najnowsza ramka ma więcej niż 180 sekund, restartuje usługę:

```text
purethermal-server
```

Sprawdzenie:

```bash
systemctl list-timers | grep purethermal
journalctl -t purethermal-watchdog -n 20 --no-pager
```

Przykład poprawnego logu:

```text
purethermal-watchdog: OK, najnowsza ramka ma 2s
```

Przykład restartu:

```text
purethermal-watchdog: Najnowsza ramka ma 240s, restartuję purethermal-server
```

Uwaga:

```text
Jeśli kamera zawiesi się sprzętowo, restart usługi może nie wystarczyć.
Wtedy trzeba odłączyć/podłączyć kamerę albo dodać programowy reset USB.
```

---

# 11. Aktualizacja z Gita

```bash
cd ~/thermal_server
git pull
./install.sh
```

Po aktualizacji sprawdź:

```bash
sudo systemctl status purethermal-server --no-pager
curl -s "http://127.0.0.1:8088/temp?x=80&y=60"
```

---

# 12. Deinstalacja

Zatrzymanie usług:

```bash
sudo systemctl stop purethermal-server
sudo systemctl disable purethermal-server

sudo systemctl stop purethermal-watchdog.timer
sudo systemctl disable purethermal-watchdog.timer
```

Usunięcie usług:

```bash
sudo rm -f /etc/systemd/system/purethermal-server.service
sudo rm -f /etc/systemd/system/purethermal-watchdog.service
sudo rm -f /etc/systemd/system/purethermal-watchdog.timer
sudo rm -f /usr/local/bin/purethermal-watchdog.sh
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

Usunięcie aplikacji:

```bash
rm -rf ~/thermal_www
rm -rf ~/thermal_server
```

Usunięcie archiwum, tylko jeśli nie potrzebujesz zapisanych ramek:

```bash
rm -rf ~/thermal_archive
```

---

# 13. Szybka instalacja na nowym komputerze

```bash
sudo apt update
sudo apt install -y git

cd ~
git clone https://github.com/Igor-Mie/thermal_server.git
cd thermal_server

v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext

./install.sh

hostname -I
```

Potem otwórz:

```text
http://IP_KOMPUTERA:8088
http://IP_KOMPUTERA:8088/archive
```

---

# 14. Minimalny test poprawnego działania

```bash
sudo systemctl status purethermal-server --no-pager
systemctl list-timers | grep purethermal
curl -s "http://127.0.0.1:8088/temp?x=80&y=60"
ls -lt ~/thermal_archive/*.raw | head -5
```

Poprawnie:

```text
- purethermal-server jest active/running,
- purethermal-watchdog.timer jest aktywny,
- curl pokazuje temp_c i małe frame_age_s,
- w ~/thermal_archive pojawiają się nowe pliki .raw.
```
