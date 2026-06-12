import cv2
import time
import os
import serial
import numpy as np
import mysql.connector
from werkzeug.utils import secure_filename
from flask import Flask, Response, jsonify, render_template, request, redirect, session, url_for
from ultralytics import YOLO

# =========================
# KONFIGURASI DASAR
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(BASE_DIR, "best.pt")

# Awal dashboard tidak memakai sample video.
# Video baru aktif setelah user upload dari dashboard.
current_source = None
current_source_name = "Belum ada video"

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}

CONF_LIMIT = 0.50
FRAME_CONFIRM = 2

COM_PORT = "COM6"      # Ganti sesuai port ESP32
BAUDRATE = 115200

LOG_INTERVAL = 3
SERIAL_INTERVAL = 0.25

STREAM_WIDTH = 640
STREAM_HEIGHT = 360

# Foto placeholder saat belum ada video.
# Simpan foto kamu di folder static dengan salah satu nama ini.
PLACEHOLDER_IMAGE_CANDIDATES = [
    os.path.join(BASE_DIR, "static", "placeholder_video.jpg"),
    os.path.join(BASE_DIR, "static", "placeholder_video.jpeg"),
    os.path.join(BASE_DIR, "static", "placeholder_video.png"),
    os.path.join(BASE_DIR, "static", "placeholder.jpg"),
    os.path.join(BASE_DIR, "static", "placeholder.jpeg"),
    os.path.join(BASE_DIR, "static", "placeholder.png"),
]

# =========================
# FLASK
# =========================
app = Flask(__name__)
app.secret_key = "deteksi_jalan_secret_key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================
# DATABASE MYSQL
# =========================
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="db_deteksi_jalan"
    )

# =========================
# LOAD MODEL YOLO
# =========================
model = YOLO(MODEL_PATH)

# =========================
# KONEKSI ESP32
# =========================
esp32 = None
esp32_connected = False

try:
    esp32 = serial.Serial(COM_PORT, BAUDRATE, timeout=1)
    time.sleep(2)
    esp32_connected = True
    print("ESP32 CONNECTED")
except Exception as e:
    print("ESP32 TIDAK TERHUBUNG:", e)
    esp32_connected = False

# =========================
# GLOBAL DASHBOARD
# =========================
status_sistem = "AMAN"
jumlah_lubang = 0
confidence_tertinggi = 0.0
buzzer_status = "OFF"
jumlah_deteksi = 0
last_update = "-"
last_log_time = 0
last_serial_command = None
last_serial_send_time = 0

# =========================
# UTIL
# =========================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_with_padding(frame, target_width=STREAM_WIDTH, target_height=STREAM_HEIGHT):
    """
    Resize video/gambar tanpa zoom/crop.
    Landscape tetap memenuhi area 16:9.
    Portrait akan diperkecil dan diberi black bar.
    """
    h, w = frame.shape[:2]

    if w == 0 or h == 0:
        return frame

    scale = min(target_width / w, target_height / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = cv2.resize(frame, (new_w, new_h))

    canvas = cv2.copyMakeBorder(
        resized,
        top=(target_height - new_h) // 2,
        bottom=target_height - new_h - ((target_height - new_h) // 2),
        left=(target_width - new_w) // 2,
        right=target_width - new_w - ((target_width - new_w) // 2),
        borderType=cv2.BORDER_CONSTANT,
        value=(0, 0, 0)
    )

    return canvas


def buat_placeholder_frame():
    """
    Menampilkan foto placeholder dari folder static.
    Kalau gambar tidak ditemukan, baru tampil teks bawaan.
    """

    for image_path in PLACEHOLDER_IMAGE_CANDIDATES:
        if os.path.exists(image_path):
            print("Placeholder ditemukan:", image_path)

            img = cv2.imread(image_path)

            if img is not None:
                return resize_with_padding(img)
            else:
                print("Gambar ada tapi gagal dibaca:", image_path)

    print("Placeholder tidak ditemukan. Cek folder static.")

    frame = np.zeros((STREAM_HEIGHT, STREAM_WIDTH, 3), dtype=np.uint8)
    frame[:] = (20, 30, 45)

    cv2.putText(
        frame,
        "BELUM ADA VIDEO",
        (145, 145),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (255, 255, 255),
        3
    )

    cv2.putText(
        frame,
        "Upload video untuk mulai deteksi jalan berlubang",
        (65, 205),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (180, 200, 230),
        2
    )

    cv2.putText(
        frame,
        "Klik SELECT FILES atau drag & drop video",
        (105, 245),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (120, 180, 255),
        2
    )

    return frame


def simpan_log(status, jumlah, confidence, buzzer):
    try:
        db = get_db()
        cursor = db.cursor()

        sql = """
        INSERT INTO detection_logs (status, jumlah_lubang, confidence, buzzer)
        VALUES (%s, %s, %s, %s)
        """

        cursor.execute(sql, (status, jumlah, confidence, buzzer))
        db.commit()

        cursor.close()
        db.close()

        print("LOG TERSIMPAN:", status, jumlah, confidence, buzzer)

    except Exception as e:
        print("Gagal simpan log:", e)


def kirim_esp32(data, force=False):
    """
    Kirim perintah ke ESP32 tanpa membuat antrean serial menumpuk.

    b'1' = BAHAYA / buzzer ON
    b'0' = AMAN / buzzer OFF
    """
    global last_serial_command, last_serial_send_time

    if not esp32_connected:
        return

    sekarang = time.time()

    if (
        not force
        and data == last_serial_command
        and (sekarang - last_serial_send_time) < SERIAL_INTERVAL
    ):
        return

    try:
        esp32.reset_output_buffer()
        esp32.write(data)
        esp32.flush()

        last_serial_command = data
        last_serial_send_time = sekarang

    except Exception as e:
        print("Gagal kirim ke ESP32:", e)


# =========================
# LOGIN
# =========================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            cursor.execute(
                "SELECT * FROM users WHERE username=%s AND password=%s",
                (username, password)
            )

            user = cursor.fetchone()

            cursor.close()
            db.close()

            if user:
                session["login"] = True
                session["username"] = username
                return redirect(url_for("dashboard"))
            else:
                return render_template("login.html", error="Username atau password salah")

        except Exception as e:
            print("Database error:", e)
            return render_template("login.html", error="Database tidak terhubung")

    return render_template("login.html")


# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    if not session.get("login"):
        return redirect(url_for("login"))

    return render_template("dashboard.html", username=session.get("username"))


# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================
# UPLOAD VIDEO
# =========================
@app.route("/upload_video", methods=["POST"])
def upload_video():
    global current_source, current_source_name
    global status_sistem, jumlah_lubang, confidence_tertinggi
    global buzzer_status, jumlah_deteksi, last_update, last_log_time
    global last_serial_command, last_serial_send_time

    if not session.get("login"):
        return jsonify({
            "success": False,
            "message": "Belum login"
        }), 401

    if "video" not in request.files:
        return jsonify({
            "success": False,
            "message": "File video tidak ditemukan"
        })

    file = request.files["video"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "Nama file kosong"
        })

    if not allowed_file(file.filename):
        return jsonify({
            "success": False,
            "message": "Format tidak didukung. Gunakan mp4, avi, mov, atau mkv"
        })

    filename = secure_filename(file.filename)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    saved_name = f"{timestamp}_{filename}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], saved_name)

    file.save(save_path)

    current_source = save_path
    current_source_name = filename

    status_sistem = "AMAN"
    jumlah_lubang = 0
    confidence_tertinggi = 0.0
    buzzer_status = "OFF"
    jumlah_deteksi = 0
    last_update = "-"
    last_log_time = 0
    last_serial_command = None
    last_serial_send_time = 0

    kirim_esp32(b'0', force=True)

    return jsonify({
        "success": True,
        "message": "Video berhasil di-upload",
        "filename": filename
    })


# =========================
# CLEAR VIDEO
# =========================
@app.route("/clear_video", methods=["POST"])
def clear_video():
    global current_source, current_source_name
    global status_sistem, jumlah_lubang, confidence_tertinggi
    global buzzer_status, jumlah_deteksi, last_update, last_log_time
    global last_serial_command, last_serial_send_time

    if not session.get("login"):
        return jsonify({
            "success": False,
            "message": "Belum login"
        }), 401

    current_source = None
    current_source_name = "Belum ada video"

    status_sistem = "AMAN"
    jumlah_lubang = 0
    confidence_tertinggi = 0.0
    buzzer_status = "OFF"
    jumlah_deteksi = 0
    last_update = "-"
    last_log_time = 0
    last_serial_command = None
    last_serial_send_time = 0

    kirim_esp32(b'0', force=True)

    return jsonify({
        "success": True,
        "message": "Video dibersihkan. Silakan upload video untuk mulai deteksi."
    })


# =========================
# DATA REALTIME
# =========================
@app.route("/data")
def data():
    return jsonify({
        "status": status_sistem,
        "jumlah_lubang": jumlah_lubang,
        "confidence": f"{confidence_tertinggi:.2f}",
        "buzzer": buzzer_status,
        "esp32": "CONNECTED" if esp32_connected else "DISCONNECTED",
        "jumlah_deteksi": jumlah_deteksi,
        "last_update": last_update,
        "source_name": current_source_name
    })


# =========================
# AMBIL LOG DATABASE
# =========================
@app.route("/logs")
def logs():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                status, 
                jumlah_lubang, 
                confidence, 
                buzzer, 
                DATE_FORMAT(waktu, '%Y-%m-%d %H:%i:%s') AS waktu
            FROM detection_logs
            ORDER BY id DESC
            LIMIT 20
        """)

        data_log = cursor.fetchall()

        cursor.close()
        db.close()

        return jsonify(data_log)

    except Exception as e:
        print("Gagal ambil log:", e)
        return jsonify([])


# =========================
# VIDEO STREAM YOLO
# =========================
def generate_frames():
    global status_sistem, jumlah_lubang, confidence_tertinggi
    global buzzer_status, jumlah_deteksi, last_update, last_log_time
    global current_source

    cap = None
    cap_source = None
    deteksi_count = 0

    while True:
        # Kalau belum ada video, tampilkan placeholder dan matikan buzzer
        if current_source is None:
            if cap is not None:
                cap.release()
                cap = None
                cap_source = None

            status_sistem = "AMAN"
            jumlah_lubang = 0
            confidence_tertinggi = 0.0
            buzzer_status = "OFF"
            last_update = time.strftime("%H:%M:%S")
            kirim_esp32(b'0')

            frame = buat_placeholder_frame()

            _, buffer = cv2.imencode(".jpg", frame)
            frame_bytes = buffer.tobytes()

            time.sleep(0.1)

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )

            continue

        # Kalau source berubah karena upload video, buka ulang video
        if cap_source != current_source:
            if cap is not None:
                cap.release()

            cap_source = current_source
            cap = cv2.VideoCapture(cap_source)
            deteksi_count = 0

            print("Membuka source video:", cap_source)

        ret, frame = cap.read()

        if not ret:
            if isinstance(cap_source, str):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            else:
                continue

        frame = resize_with_padding(frame)

        # =========================
        # PREDIKSI YOLO
        # =========================
        results = model.predict(
            frame,
            conf=CONF_LIMIT,
            imgsz=640,
            verbose=False
        )

        result = results[0]

        jumlah_lubang_frame = 0
        conf_max = 0.0

        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = model.names[cls_id].lower()

            if class_name in ["pothole", "potholes", "lubang"]:
                jumlah_lubang_frame += 1
                conf_max = max(conf_max, conf)

                x1, y1, x2, y2 = box.xyxy[0]
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 0, 255),
                    2
                )

                cv2.putText(
                    frame,
                    f"Lubang {conf:.2f}",
                    (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2
                )

        jumlah_lubang = jumlah_lubang_frame
        confidence_tertinggi = conf_max

        if jumlah_lubang_frame > 0:
            deteksi_count += 1
        else:
            deteksi_count = 0

        sekarang = time.time()

        if deteksi_count >= FRAME_CONFIRM:
            status_sistem = "BAHAYA"
            buzzer_status = "ON"
            warna = (0, 0, 255)
            kirim_esp32(b'1')
        else:
            status_sistem = "AMAN"
            buzzer_status = "OFF"
            warna = (0, 255, 0)
            kirim_esp32(b'0')

        # Log hanya saat ada video aktif
        if sekarang - last_log_time >= LOG_INTERVAL:
            jumlah_deteksi += 1

            simpan_log(
                status_sistem,
                jumlah_lubang,
                confidence_tertinggi,
                buzzer_status
            )

            last_log_time = sekarang

        last_update = time.strftime("%H:%M:%S")

        cv2.putText(
            frame,
            f"STATUS: {status_sistem}",
            (15, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            warna,
            2
        )

        cv2.putText(
            frame,
            f"Lubang: {jumlah_lubang_frame} | Conf: {conf_max:.2f}",
            (15, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            warna,
            2
        )

        _, buffer = cv2.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )


# =========================
# ROUTE VIDEO
# =========================
@app.route("/video_feed")
def video_feed():
    if not session.get("login"):
        return redirect(url_for("login"))

    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
