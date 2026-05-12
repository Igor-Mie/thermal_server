import subprocess
import numpy as np
import cv2
import os
import time
import json
import threading
from datetime import datetime, timedelta
from flask import Flask, Response, jsonify, request

DEVICE = "/dev/video0"

WIDTH = 160
HEIGHT = 120

DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480

TEMP_LOW_C = 20.0
TEMP_HIGH_C = 50.0

CAPTURE_INTERVAL = 2.0

ARCHIVE_DIR = os.path.expanduser("~/thermal_archive")
TMP_RAW = "/tmp/purethermal_server.raw"

RETENTION_DAYS = 7

latest_frame = None
latest_jpeg = None
latest_time = 0
latest_raw_path = None

lock = threading.Lock()
app = Flask(__name__)

os.makedirs(ARCHIVE_DIR, exist_ok=True)


def temp_c(raw):
    return raw / 100.0 - 273.15


def safe_raw_path(filename):
    name = os.path.basename(filename)

    if not name.endswith(".raw"):
        raise ValueError("Nieprawidłowy plik")

    path = os.path.join(ARCHIVE_DIR, name)

    if not os.path.exists(path):
        raise FileNotFoundError("Nie ma takiej ramki")

    return path


def capture_y16():
    if os.path.exists(TMP_RAW):
        os.remove(TMP_RAW)

    cmd = [
        "timeout", "5",
        "v4l2-ctl",
        "-d", DEVICE,
        "--set-fmt-video=width=160,height=120,pixelformat=Y16 ",
        "--stream-mmap",
        "--stream-count=1",
        f"--stream-to={TMP_RAW}",
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        error = result.stderr.strip()
        if not error:
            error = f"v4l2-ctl zakończył się kodem {result.returncode}"
        raise RuntimeError(error)

    expected_size = WIDTH * HEIGHT * 2

    if not os.path.exists(TMP_RAW):
        raise RuntimeError("Nie powstał plik RAW")

    actual_size = os.path.getsize(TMP_RAW)

    if actual_size != expected_size:
        raise RuntimeError(
            f"Zły rozmiar RAW: {actual_size} bajtów, oczekiwano {expected_size}"
        )

    data = np.fromfile(TMP_RAW, dtype=np.uint16)

    if data.size != WIDTH * HEIGHT:
        raise RuntimeError(
            f"Zły rozmiar ramki: {data.size}, oczekiwano {WIDTH * HEIGHT}"
        )

    return data.reshape((HEIGHT, WIDTH))


def save_raw_frame(frame):
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    raw_path = os.path.join(ARCHIVE_DIR, f"{stamp}.raw")
    json_path = os.path.join(ARCHIVE_DIR, f"{stamp}.json")

    frame.astype(np.uint16).tofile(raw_path)

    meta = {
        "timestamp": now.isoformat(timespec="seconds"),
        "device": DEVICE,
        "width": WIDTH,
        "height": HEIGHT,
        "format": "Y16",
        "dtype": "uint16",
        "byte_order": "little_endian",
        "temperature_formula_c": "raw / 100.0 - 273.15",
        "raw_file": os.path.basename(raw_path),
        "min_c": round(temp_c(int(frame.min())), 2),
        "max_c": round(temp_c(int(frame.max())), 2),
        "mean_c": round(temp_c(float(frame.mean())), 2),
        "center_c": round(temp_c(int(frame[HEIGHT // 2, WIDTH // 2])), 2)
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return raw_path


def load_raw_frame(path):
    data = np.fromfile(path, dtype=np.uint16)

    if data.size != WIDTH * HEIGHT:
        raise RuntimeError(
            f"Zły rozmiar ramki: {data.size}, oczekiwano {WIDTH * HEIGHT}"
        )

    return data.reshape((HEIGHT, WIDTH))


def frame_to_jpeg(frame, mark_x=None, mark_y=None):
    low_raw = int((TEMP_LOW_C + 273.15) * 100)
    high_raw = int((TEMP_HIGH_C + 273.15) * 100)

    clipped = np.clip(frame, low_raw, high_raw)
    img8 = ((clipped - low_raw) * 255.0 / (high_raw - low_raw)).astype(np.uint8)

    img = cv2.resize(
        img8,
        (DISPLAY_WIDTH, DISPLAY_HEIGHT),
        interpolation=cv2.INTER_NEAREST
    )

    img_color = cv2.applyColorMap(img, cv2.COLORMAP_INFERNO)

    t_min = temp_c(int(frame.min()))
    t_max = temp_c(int(frame.max()))
    t_mean = temp_c(float(frame.mean()))
    t_center = temp_c(int(frame[HEIGHT // 2, WIDTH // 2]))

    overlay = img_color.copy()
    cv2.rectangle(overlay, (0, 0), (DISPLAY_WIDTH, 96), (0, 0, 0), -1)
    img_color = cv2.addWeighted(overlay, 0.55, img_color, 0.45, 0)

    cv2.putText(img_color, f"CENTER: {t_center:.2f} C", (15, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    cv2.putText(img_color, f"MIN: {t_min:.2f} C   MAX: {t_max:.2f} C", (15, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)

    cv2.putText(img_color, f"MEAN: {t_mean:.2f} C", (15, 86),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    if mark_x is not None and mark_y is not None:
        dx = int(mark_x * 4 + 2)
        dy = int(mark_y * 4 + 2)
        cv2.drawMarker(
            img_color,
            (dx, dy),
            (255, 255, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=28,
            thickness=2
        )

    ok, jpg = cv2.imencode(
        ".jpg",
        img_color,
        [int(cv2.IMWRITE_JPEG_QUALITY), 85]
    )

    if not ok:
        raise RuntimeError("Nie udało się zakodować JPG")

    return jpg.tobytes()


def cleanup_old_files():
    if RETENTION_DAYS <= 0:
        return

    cutoff = time.time() - RETENTION_DAYS * 24 * 3600

    for name in os.listdir(ARCHIVE_DIR):
        if not (name.endswith(".raw") or name.endswith(".json")):
            continue

        path = os.path.join(ARCHIVE_DIR, name)

        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


def capture_loop():
    global latest_frame, latest_jpeg, latest_time, latest_raw_path

    last_cleanup = 0

    while True:
        try:
            frame = capture_y16()
            raw_path = save_raw_frame(frame)
            jpeg = frame_to_jpeg(frame)

            with lock:
                latest_frame = frame.copy()
                latest_jpeg = jpeg
                latest_time = time.time()
                latest_raw_path = raw_path

            print(
                "Ramka OK",
                time.strftime("%H:%M:%S"),
                os.path.basename(raw_path),
                f"MAX={temp_c(int(frame.max())):.2f}C"
            )

            if time.time() - last_cleanup > 3600:
                cleanup_old_files()
                last_cleanup = time.time()

        except Exception as e:
            print(f"Błąd przechwytywania: {e}")

        time.sleep(CAPTURE_INTERVAL)


@app.route("/")
def index():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>PureThermal Live</title>
  <style>
    body { background:#111; color:#eee; font-family:Arial,sans-serif; margin:20px; }
    a { color:#8cc8ff; }
    .wrap { display:flex; gap:20px; align-items:flex-start; }
    #thermal { width:640px; height:480px; image-rendering:pixelated; border:1px solid #555; cursor:crosshair; }
    .panel { font-size:22px; line-height:1.6; min-width:320px; }
    .value { color:#fff; font-weight:bold; }
    .small { color:#aaa; font-size:14px; margin-top:20px; }
    .status { margin-top:15px; font-size:14px; color:#aaa; }
  </style>
</head>
<body>
  <h2>PureThermal — LIVE</h2>
  <p><a href="/archive">Przejdź do archiwum / timeline</a></p>

  <div class="wrap">
    <img id="thermal" src="/frame.jpg">
    <div class="panel">
      <div>X kamera: <span id="x" class="value">-</span></div>
      <div>Y kamera: <span id="y" class="value">-</span></div>
      <div>Temperatura: <span id="temp" class="value">-</span> °C</div>
      <div>RAW: <span id="raw" class="value">-</span></div>
      <div class="small">
        Obraz kamery: 160×120<br>
        Podgląd: 640×480<br>
        Zapis Y16 działa w tle.
      </div>
      <div class="status">Status: <span id="status">czekam...</span></div>
    </div>
  </div>

<script>
const img = document.getElementById("thermal");
const statusEl = document.getElementById("status");

function refreshImage() {
  img.src = "/frame.jpg?t=" + Date.now();
}
setInterval(refreshImage, 2000);

img.onload = () => statusEl.textContent = "obraz odebrany";
img.onerror = () => statusEl.textContent = "brak obrazu";

img.addEventListener("mousemove", async function(e) {
  const rect = img.getBoundingClientRect();
  const px = e.clientX - rect.left;
  const py = e.clientY - rect.top;

  const displayX = Math.floor(px * 640 / rect.width);
  const displayY = Math.floor(py * 480 / rect.height);

  const camX = Math.floor(displayX / 4);
  const camY = Math.floor(displayY / 4);

  if (camX < 0 || camX >= 160 || camY < 0 || camY >= 120) return;

  try {
    const r = await fetch(`/temp?x=${camX}&y=${camY}&t=${Date.now()}`);
    const data = await r.json();

    if (data.error) {
      statusEl.textContent = data.error;
      return;
    }

    document.getElementById("x").textContent = data.x;
    document.getElementById("y").textContent = data.y;
    document.getElementById("temp").textContent = data.temp_c.toFixed(2);
    document.getElementById("raw").textContent = data.raw;
    statusEl.textContent = "temperatura live odczytana";
  } catch(err) {
    statusEl.textContent = "błąd odczytu";
  }
});
</script>
</body>
</html>
"""


@app.route("/archive")
def archive_page():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>PureThermal Archiwum</title>
  <style>
    body { background:#111; color:#eee; font-family:Arial,sans-serif; margin:20px; }
    a { color:#8cc8ff; }
    .wrap { display:flex; gap:20px; align-items:flex-start; }
    #thermal { width:640px; height:480px; image-rendering:pixelated; border:1px solid #555; cursor:crosshair; }
    .panel { font-size:20px; line-height:1.6; min-width:360px; }
    .value { color:#fff; font-weight:bold; }
    .small { color:#aaa; font-size:14px; margin-top:20px; }
    input[type=range] { width:640px; }
    button { padding:8px 12px; margin-right:8px; }
  </style>
</head>
<body>
  <h2>PureThermal — archiwum Y16 / timeline</h2>
  <p><a href="/">Powrót do LIVE</a></p>

  <div>
    <button onclick="loadArchive()">Odśwież listę</button>
    <button onclick="stepFrame(-1)">Poprzednia</button>
    <button onclick="stepFrame(1)">Następna</button>
  </div>

  <p>
    Timeline:<br>
    <input id="slider" type="range" min="0" max="0" value="0">
  </p>

  <p>
    Ramka: <span id="idx">-</span> /
    <span id="count">-</span><br>
    Czas: <span id="stamp" class="value">-</span><br>
    Plik: <span id="file" class="value">-</span>
  </p>

  <div class="wrap">
    <img id="thermal" src="">
    <div class="panel">
      <div>X kamera: <span id="x" class="value">-</span></div>
      <div>Y kamera: <span id="y" class="value">-</span></div>
      <div>Temperatura: <span id="temp" class="value">-</span> °C</div>
      <div>RAW: <span id="raw" class="value">-</span></div>
      <div class="small">
        To jest odczyt z zapisanej ramki Y16.<br>
        Możesz przewijać timeline i najeżdżać myszką na obraz.
      </div>
    </div>
  </div>

<script>
let frames = [];
let current = 0;

const slider = document.getElementById("slider");
const img = document.getElementById("thermal");

async function loadArchive() {
  const r = await fetch("/api/archive?t=" + Date.now());
  const data = await r.json();

  frames = data.frames || [];

  document.getElementById("count").textContent = frames.length;

  if (frames.length === 0) {
    document.getElementById("stamp").textContent = "brak ramek";
    return;
  }

  slider.min = 0;
  slider.max = frames.length - 1;

  current = frames.length - 1;
  slider.value = current;

  showFrame(current);
}

function showFrame(i) {
  if (frames.length === 0) return;

  if (i < 0) i = 0;
  if (i >= frames.length) i = frames.length - 1;

  current = i;
  slider.value = current;

  const f = frames[current];

  document.getElementById("idx").textContent = current + 1;
  document.getElementById("count").textContent = frames.length;
  document.getElementById("stamp").textContent = f.timestamp;
  document.getElementById("file").textContent = f.file;

  img.src = "/archive_frame.jpg?file=" + encodeURIComponent(f.file) + "&t=" + Date.now();
}

function stepFrame(delta) {
  showFrame(current + delta);
}

slider.addEventListener("input", function() {
  showFrame(parseInt(slider.value));
});

img.addEventListener("mousemove", async function(e) {
  if (frames.length === 0) return;

  const rect = img.getBoundingClientRect();
  const px = e.clientX - rect.left;
  const py = e.clientY - rect.top;

  const displayX = Math.floor(px * 640 / rect.width);
  const displayY = Math.floor(py * 480 / rect.height);

  const camX = Math.floor(displayX / 4);
  const camY = Math.floor(displayY / 4);

  if (camX < 0 || camX >= 160 || camY < 0 || camY >= 120) return;

  const f = frames[current];

  const r = await fetch(
    `/archive_temp?file=${encodeURIComponent(f.file)}&x=${camX}&y=${camY}&t=${Date.now()}`
  );

  const data = await r.json();

  if (data.error) return;

  document.getElementById("x").textContent = data.x;
  document.getElementById("y").textContent = data.y;
  document.getElementById("temp").textContent = data.temp_c.toFixed(2);
  document.getElementById("raw").textContent = data.raw;
});

loadArchive();
</script>
</body>
</html>
"""


@app.route("/frame.jpg")
def frame_jpg():
    with lock:
        jpeg = latest_jpeg

    if jpeg is None:
        return Response("Brak ramki", status=503)

    return Response(jpeg, mimetype="image/jpeg")


@app.route("/temp")
def temp_at_point():
    try:
        x = int(request.args.get("x", "-1"))
        y = int(request.args.get("y", "-1"))
    except ValueError:
        return jsonify({"error": "Nieprawidłowe x/y"}), 400

    if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
        return jsonify({"error": "Punkt poza obrazem"}), 400

    with lock:
        frame = None if latest_frame is None else latest_frame.copy()

    if frame is None:
        return jsonify({"error": "Brak ramki"}), 503

    raw = int(frame[y, x])

    return jsonify({
        "x": x,
        "y": y,
        "raw": raw,
        "temp_c": temp_c(raw),
        "frame_age_s": round(time.time() - latest_time, 2)
    })


@app.route("/api/archive")
def api_archive():
    files = []

    for name in os.listdir(ARCHIVE_DIR):
        if not name.endswith(".raw"):
            continue

        raw_path = os.path.join(ARCHIVE_DIR, name)
        json_path = os.path.join(ARCHIVE_DIR, name.replace(".raw", ".json"))

        timestamp = name.replace(".raw", "")

        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    timestamp = meta.get("timestamp", timestamp)
            except Exception:
                pass

        files.append({
            "file": name,
            "timestamp": timestamp,
            "mtime": os.path.getmtime(raw_path)
        })

    files.sort(key=lambda x: x["mtime"])

    return jsonify({
        "count": len(files),
        "frames": files
    })


@app.route("/archive_frame.jpg")
def archive_frame():
    try:
        filename = request.args.get("file", "")
        path = safe_raw_path(filename)
        frame = load_raw_frame(path)

        mark_x = request.args.get("x")
        mark_y = request.args.get("y")

        if mark_x is not None and mark_y is not None:
            mark_x = int(mark_x)
            mark_y = int(mark_y)
        else:
            mark_x = None
            mark_y = None

        jpeg = frame_to_jpeg(frame, mark_x, mark_y)
        return Response(jpeg, mimetype="image/jpeg")

    except Exception as e:
        return Response(str(e), status=400)


@app.route("/archive_temp")
def archive_temp():
    try:
        filename = request.args.get("file", "")
        x = int(request.args.get("x", "-1"))
        y = int(request.args.get("y", "-1"))

        if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
            return jsonify({"error": "Punkt poza obrazem"}), 400

        path = safe_raw_path(filename)
        frame = load_raw_frame(path)

        raw = int(frame[y, x])

        return jsonify({
            "file": os.path.basename(path),
            "x": x,
            "y": y,
            "raw": raw,
            "temp_c": temp_c(raw)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400


def mjpeg_generator():
    last_jpeg = None

    while True:
        with lock:
            jpeg = latest_jpeg

        if jpeg is not None and jpeg != last_jpeg:
            last_jpeg = jpeg

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                jpeg +
                b"\r\n"
            )

        time.sleep(0.2)


@app.route("/mjpeg")
def mjpeg():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    thread = threading.Thread(target=capture_loop, daemon=True)
    thread.start()

    print("PureThermal server start")
    print("LIVE:     http://10.3.14.87:8088")
    print("ARCHIVE:  http://10.3.14.87:8088/archive")
    print(f"Archive dir: {ARCHIVE_DIR}")
    print(f"Retention: {RETENTION_DAYS} days")
    print("Przerwij: Ctrl+C")

    app.run(host="0.0.0.0", port=8088, threaded=True)
