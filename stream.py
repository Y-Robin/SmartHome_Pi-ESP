import time
import picamera
import io
import numpy as np
from PIL import Image
import os
import shutil
import datetime
import cv2

RECORD_FLAG_FILE = 'record_flag.txt'
VIDEOS_FOLDER = 'static/videos'
FRAMES_BUFFER = []

temp_file = 'temp_frame.jpg'
shared_file = 'shared_frame.jpg'

def capture_and_process_frames():
    last_save_time = None  # Initialize variable to store the time of the last save
    recording = False
    global FRAMES_BUFFER
    with picamera.PiCamera() as camera:
        camera.resolution = (320, 240)
        time.sleep(2)  # Camera warm-up time

        buffer_size = camera.resolution[0] * camera.resolution[1] * 3
        stream = io.BytesIO()

        while True:
            start_time = time.time()

            # Capture
            capture_start = time.time()
            camera.capture(stream, format='rgb', use_video_port=True)
            capture_end = time.time()

            # Process
            process_start = time.time()
            stream.seek(0)
            frame = np.frombuffer(stream.read(buffer_size), dtype=np.uint8).reshape((240, 320, 3))
            processed_frame = process_frame(frame)
            process_end = time.time()

            # Save
            save_start = time.time()
            save_frame(processed_frame)
            save_end = time.time()

            # Calculate time since last save
            if last_save_time is not None:
                save_interval = save_start - last_save_time
                #print(f"Time since last save: {save_interval:.4f} s")
            last_save_time = save_start

            stream.seek(0)
            stream.truncate()

            end_time = time.time()

            #print(f"Total Time: {end_time - start_time:.4f} s, Capture: {capture_end - capture_start:.4f} s, Process: {process_end - process_start:.4f} s, Save: {save_end - save_start:.4f} s")


            if is_recording():
                if not recording:
                    # Start recording phase
                    recording = True
                    FRAMES_BUFFER = []
            
                FRAMES_BUFFER.append(frame)
            elif recording:
                # End of recording phase
                recording = False
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                video_file = os.path.join(VIDEOS_FOLDER, f"video_{timestamp}.mp4")
                print(video_file)
                save_video(FRAMES_BUFFER, video_file)
                FRAMES_BUFFER = []
                print("Current working directory:", os.getcwd())
                print("Videos will be saved in:", os.path.abspath(VIDEOS_FOLDER))
            time.sleep(0.01)  # Adjust as needed

def is_recording():
    return os.path.exists(RECORD_FLAG_FILE)

def save_video(frames, file_path, fps=30):
    height, width, layers = frames[0].shape
    size = (width, height)

    # Try H.264 codec; fall back to 'mp4v' if unavailable
    try:
        out = cv2.VideoWriter(file_path, cv2.VideoWriter_fourcc(*'X264'), fps, size)
        test_frame = np.zeros((height, width, 3), dtype=np.uint8)
        out.write(test_frame)  # Test write
    except:
        print("H.264 codec not available, falling back to mp4v")
        out = cv2.VideoWriter(file_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, size)

    for frame in frames:
        out.write(frame)
    out.release()

def process_frame(frame):
    # Process the frame as needed
    return frame

def save_frame(frame):
    # Save the frame as needed
    Image.fromarray(frame).save(temp_file)
    shutil.move(temp_file, shared_file)  

if __name__ == "__main__":
    capture_and_process_frames()

