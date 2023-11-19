#python3.7 espCapture.py 
import cv2
import time
import shutil

def capture_frame(stream_url, output_file):
    cap = cv2.VideoCapture(stream_url)
    shared_file = 'shared_frame2.jpg'
    while True:
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(output_file, frame)
            shutil.move(output_file, shared_file)  
        time.sleep(0.01)  # Adjust the frame rate as needed

if __name__ == "__main__":
    stream_url = 'http://192.168.178.47:81/stream'  # Replace with your ESP32 stream URL
    output_file = 'tempFile2.jpg'
    capture_frame(stream_url, output_file)

