import cv2

for i in range(5):

    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)

    if cap.isOpened():

        print(f"Kamera ditemukan di index {i}")

        ret, frame = cap.read()

        if ret:
            cv2.imshow(f"Kamera {i}", frame)
            cv2.waitKey(3000)

        cap.release()

cv2.destroyAllWindows()