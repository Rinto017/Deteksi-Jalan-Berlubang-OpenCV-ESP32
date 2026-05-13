import cv2
import serial
import time

esp32 = serial.Serial('COM6', 115200)
time.sleep(2)
cap = cv2.VideoCapture(0)

deteksiCount = 0
amanCount = 0

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    frame = cv2.resize(frame, (1280, 720))

    # fokus area bawah jalan
    roi = frame[360:720, 0:1280]

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)

    _, thresh = cv2.threshold(blur, 35, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    lubang = False

    for cnt in contours:
        area = cv2.contourArea(cnt)

        if 12000 < area < 80000:
            x, y, w, h = cv2.boundingRect(cnt)
            ratio = w / float(h)

            # bentuk lubang biasanya melebar/tidak terlalu tipis
            if 0.6 < ratio < 3.5:
                lubang = True
                cv2.rectangle(roi, (x, y), (x+w, y+h), (0, 0, 255), 3)
                cv2.putText(roi, "Lubang Terdeteksi", (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    if lubang:
        deteksiCount += 1
        amanCount = 0
    else:
        amanCount += 1
        if amanCount >= 5:
            deteksiCount = 0

    if deteksiCount >= 8:
        esp32.write(b'1')
        status = "BAHAYA"
        warna = (0, 0, 255)
    else:
        esp32.write(b'0')
        status = "AMAN"
        warna = (0, 255, 0)

    cv2.putText(frame, f"STATUS: {status}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, warna, 3)

    cv2.imshow("Deteksi Jalan", frame)
    cv2.imshow("Threshold", thresh)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
esp32.close()