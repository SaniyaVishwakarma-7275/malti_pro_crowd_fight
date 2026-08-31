import cv2

url = "rtsp://admin:Msspl%401234@122.162.237.4:2001/video/live?channel=1&subtype=0"

cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

print("Opened:", cap.isOpened())

while True:
    ret, frame = cap.read()

    if not ret:
        print("Frame read failed")
        break

    cv2.imshow("Camera", frame)

    if cv2.waitKey(1) == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
