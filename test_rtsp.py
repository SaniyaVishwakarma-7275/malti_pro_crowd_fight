import cv2

url = "rtsp://admin:Multi%40421@122.162.237.4:1030/mode=real&idc=1&ids=2"

cap = cv2.VideoCapture(url)

if cap.isOpened():
    print("RTSP OPEN SUCCESS")

    ret, frame = cap.read()

    if ret:
        print("FRAME RECEIVED:", frame.shape)
        cv2.imwrite("test.jpg", frame)
    else:
        print("RTSP OPEN BUT NO FRAME")

else:
    print("RTSP FAILED")

cap.release()
