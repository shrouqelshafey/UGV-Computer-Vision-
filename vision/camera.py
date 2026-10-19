"""Open the ESP32-CAM stream using OpenCV defaults."""

import cv2


def open_camera(url):
    # Open once without application-configured timeout or reconnection options.
    return cv2.VideoCapture(url)
