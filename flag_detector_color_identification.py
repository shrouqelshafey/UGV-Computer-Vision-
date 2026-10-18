import cv2
import json
import numpy as np
import time
# min_flag_area_ratio filters tiny blobs using a fraction of the image area.
# This is a noise filter, not a measurement of the flag's physical size.
# aspect_ratio_range can be None when the flag's proportions are unknown.

def load_settings(path="settings.json"):
    """Load and validate settings from JSON."""
    with open(path, "r", encoding="utf-8") as file:
        settings=json.load(file)
#Red wraps around in HSV, so lower/upper2 must come as a pair
    for color_name, ranges in settings["colors"].items():
        if ("lower2" in ranges) != ("upper2" in ranges):
            raise ValueError(f"Color '{color_name}' needs both lower2 and upper2")
#Gaussian blur crashes if the size is even 
#Works by sliding an odd sized square window  - center pixel and same number of neighbors on each side
    if "blur_kernel_size" in settings:
        blur_ksize= settings["blur_kernel_size"]
        if not isinstance(blur_ksize, int) or blur_ksize <= 0 or blur_ksize % 2 == 0:
            raise ValueError("'blur_kernel_size' must be a positive odd integer.")
    return settings

def build_mask(hsv_frame, color_ranges, settings):
#Builds and cleans the color mask using morphological operations
    kernel_size=settings.get("kernel_size", 5) #size of cleanup filter
#pixels inside the first HSV range become 255, everything else 0
    lower1=np.array(color_ranges["lower1"])
    upper1=np.array(color_ranges["upper1"])
    mask=cv2.inRange(hsv_frame, lower1, upper1)
#colors like red wrap around HSV so they need a second range
    if "lower2" in color_ranges and "upper2" in color_ranges:
        lower2=np.array(color_ranges["lower2"])
        upper2=np.array(color_ranges["upper2"])
        mask2=cv2.inRange(hsv_frame, lower2, upper2)
#combines both ranges: a pixel is counted when it's in either one
        mask=cv2.bitwise_or(mask, mask2)

    kernel=np.ones((kernel_size, kernel_size), np.uint8)
#OPEN removes salt (noise) and CLOSE fills small black holes inside white areas
    mask=cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask=cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    return mask #mask is cleaned and sent 

def find_largest_blob(mask, settings):
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    # Use an area ratio so the noise threshold scales with image resolution.
    image_height, image_width = mask.shape[:2]
    image_area = image_height * image_width
    min_area = settings["min_flag_area_ratio"] * image_area

    # Keep shape filtering optional because the flag proportions are unknown.
    aspect_limits = settings.get("aspect_ratio_range")

    valid_blobs = []

    for contour in contours:
        area = cv2.contourArea(contour)

        if area < min_area:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        if aspect_limits is not None:
            min_ar, max_ar = aspect_limits
            aspect_ratio = w / h

            if not (min_ar <= aspect_ratio <= max_ar):
                continue

        valid_blobs.append({
            "area": area,
            "box": (x, y, w, h)
        })

    if not valid_blobs:
        return None

    return max(valid_blobs, key=lambda blob: blob["area"])

    # Legacy fixed-pixel filtering below is unreachable after the return above.
    min_area=settings["min_flag_area"] #limits from settings
    min_ar, max_ar=settings["aspect_ratio_range"]
    valid_blobs=[] #empty list, if shape passes the checks it will be saved here

    for contour in contours: 
        #size check
        area=cv2.contourArea(contour) #for skipping shapes that are too small (probably noise)
        if area < min_area:
            continue
        
        x, y, w, h=cv2.boundingRect(contour) #shape check

#skip shapes whose width/height ratio does not look like a flag/rectangle
        aspect_ratio=w/h 
        if not(min_ar<=aspect_ratio<=max_ar):
            continue

        valid_blobs.append({"area": area,"box": (x, y, w, h)}) #passed both checks, keep it/ saves the survivors 

    if not valid_blobs:
        return None

    return max(valid_blobs, key=lambda blob: blob["area"]) #return the biggest blob/ thes survivor with the biggest area
#lambda blob: blob["area"] tells max to compare blobs by their area 

def detect_flag(frame, settings, target_color=None):
    """Detects flag color, bounding box, area, and center."""
#blur first to smooth out camera noise
    blur_ksize=settings.get("blur_kernel_size", 5)
    blurred_frame=cv2.GaussianBlur(frame, (blur_ksize, blur_ksize), 0)

#convert from BGR to HSV, better for color detection
    hsv=cv2.cvtColor(blurred_frame, cv2.COLOR_BGR2HSV)
#variables that will hold the winning color and its blob
    best_color=None
    best_blob=None
    # None searches all profiles; a selected target skips the other colors.
    for color_name, ranges in settings["colors"].items():
        if target_color is not None and color_name != target_color:
            continue
        mask = build_mask(hsv, ranges, settings)
        blob=find_largest_blob(mask, settings)
#mask is made first  to find the best flag shaped blob in that mask

        if blob is not None:
            if best_blob is None or blob["area"]>best_blob["area"]:
                best_blob=blob
                best_color=color_name

    if best_color is None:
        return {"detected": False}

    x, y, w, h= best_blob["box"] #center
    center_x=x+w//2
    center_y=y+h//2

    return {
        "detected": True,
        "color": best_color,
        "area": best_blob["area"],
        "box": best_blob["box"],
        "center": (center_x, center_y)
    }

class FlagStabilizer:
#Handles consecutive frame confirmation to ensure reliable detection
    def __init__(self, required_consecutive_frames=4): #4 frames in a row must show the same color before we trust it
        self.required_frames=required_consecutive_frames
        self.current_color=None
        self.consecutive_count=0

    def update(self, detection_result):
        if detection_result["detected"]:
            detected_color=detection_result["color"]

            if detected_color==self.current_color:
                self.consecutive_count+=1
            else:
                self.current_color=detected_color #different color
                self.consecutive_count = 1
        else:
            self.current_color=None
            self.consecutive_count=0
            return {"confirmed": False}

        if self.consecutive_count >= self.required_frames: #confirm and pass the detection data 
            return {
                "confirmed": True,
                "color": self.current_color,
                "center": detection_result["center"],
                "box": detection_result["box"],
                "area": detection_result["area"]
            }
        return {"confirmed": False}

def open_camera(url):
    # Set timeouts here because these options apply when opening the stream.
    # Allow 5 seconds to connect and 8 seconds for slow video reads.
    return cv2.VideoCapture(
        url,
        cv2.CAP_FFMPEG,  # This backend supports the timeout options below.
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000,
        ],
    )

def reconnect_camera(url, max_attempts=5):
    # Limit attempts for each recovery cycle instead of retrying forever.
    for attempt in range(1, max_attempts + 1):
        # Check q between attempts; opening or reading can still wait for a timeout.
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return None

        print(f"[INFO] Reconnecting ({attempt}/{max_attempts})...")
        cap = open_camera(url)

        # A stream must provide a frame before we call the recovery successful.
        if cap.isOpened():
            ok, first_frame = cap.read()
            if ok and first_frame is not None:
                print("[INFO] Camera reconnected.")
                return cap

        # Close failed captures before trying another connection.
        cap.release()

        if attempt < max_attempts:
            # Pause between attempts while allowing q to cancel.
            if cv2.waitKey(2000) & 0xFF == ord('q'):
                return None

    print("[ERROR] Reconnection attempts exhausted.")
    # None tells main that no working capture was recovered.
    return None


def main():
    try:
        settings = load_settings()
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    # Update this IP if the camera reports a new address in Serial Monitor.
    camera_url = "http://192.168.1.100:81/stream"
    cap = open_camera(camera_url)

    if not cap.isOpened():
        print("[ERROR] Could not open camera.")
        cap.release()
        return
    stabilizer=FlagStabilizer(required_consecutive_frames=4) #onlu trust a detection after 4 frames in a row
    print("[INFO] Pure Flag Vision Module Running. Press 'q' to Quit.")

    max_consecutive_failures=30 # Failed-read count before reopening, not seconds.
    failure_count=0
    # c sets this name; keep it during recovery so the target color stays selected.
    target_color = None
    # Default status-image size; use the real frame shape once video arrives.
    last_frame_shape = (240, 320, 3)

    while True: # One iteration per attempted camera read.
        ret, frame=cap.read() #ret=true if a frame was grabbed 
        if not ret:
            # A failed read breaks the sequence: require four new detections.
            stabilizer = FlagStabilizer(required_consecutive_frames=4)
            failure_count+=1
            print(f"[WARN] Failed to grab frame ({failure_count}/{max_consecutive_failures}). Retrying...")

            # Clear the old detection while the stream is unavailable.
            offline_frame = np.zeros(last_frame_shape, dtype=np.uint8)
            cv2.putText(
                offline_frame, "Camera unavailable", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2
            )
            cv2.imshow("Flag Vision Module", offline_frame)
            if cv2.waitKey(100) & 0xFF == ord('q'):
                break

            if failure_count >= max_consecutive_failures:
                print("[WARN] Camera reads failed. Reconnecting...")
                # Release the old stream before opening its replacement.
                cap.release()
                recovered_cap = reconnect_camera(camera_url)
                if recovered_cap is None:
                    # Recovery failed or q was pressed; stop without using None.
                    print("[INFO] Camera recovery stopped. Exiting.")
                    break
                cap = recovered_cap
                # Resume with a fresh failure count and reset confirmation.
                failure_count = 0
            continue
        
        failure_count=0
        last_frame_shape = frame.shape
        # Keep a clean copy so calibration does not sample drawn boxes or text.
        calibration_frame = frame.copy()  
        raw_detection=detect_flag(frame, settings , target_color)
#confirm if it was seen several frames in a row
        stable_result=stabilizer.update(raw_detection)

        if stable_result["confirmed"]: #drawing the results
            color=stable_result["color"]
            x, y, w, h=stable_result["box"]
            cx, cy=stable_result["center"]
            area=stable_result["area"]
#green box around the falg, red dot at the center
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
#text showing the color,size and center position
            cv2.putText(frame, f"Flag: {color} | Area: {int(area)}", (20, 40), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Center: ({cx}, {cy})", (20, 75), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        else:
            cv2.putText(frame, "Status: Searching / Stabilizing...", (20, 40), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
#show the frame in a window
        cv2.imshow("Flag Vision Module", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('c'):
            # Select a sample from a still image using the existing color profiles.
            # This shortcut does not calculate new HSV limits or save settings.
            roi = cv2.selectROI(
                "Calibration sample",
                calibration_frame,
                showCrosshair=True,
                fromCenter=False
            )

            cv2.destroyWindow("Calibration sample")

            x, y, w, h = map(int, roi)

            if w > 0 and h > 0:
                # Only the selected region should decide the target color.
                sample = calibration_frame[y:y+h, x:x+w]
                sample_hsv = cv2.cvtColor(
                    sample, cv2.COLOR_BGR2HSV
                )

                # Prepare HSV pixels for the count; range estimation is still pending.
                calibration_pixels = sample_hsv.reshape(-1, 3)
                # Search all profiles here so c can replace an earlier color choice.
                sample_result = detect_flag(sample, settings)

                if sample_result["detected"]:
                    # Later frames are checked only against this color profile.
                    target_color = sample_result["color"]
                    print(f"[INFO] Target color locked: {target_color}")
                else:
                    print(
                        "[WARN] Sample color not recognized. "
                        "Previous target kept."
                    )

                print(
                    f"[INFO] Selected "
                    f"{len(calibration_pixels)} calibration pixels."
                )
            else:
                print("[INFO] Calibration cancelled.")

            # Reset confirmation after selecting, rejecting, or cancelling a sample.
            stabilizer = FlagStabilizer(
                required_consecutive_frames=4
            )

        elif key == ord('r'):
            # Reload saved JSON settings without restarting the program.
            try:
                updated_settings = load_settings()

                if "min_flag_area_ratio" not in updated_settings:
                    raise ValueError(
                        "Missing 'min_flag_area_ratio' in settings.json"
                    )

                # Replace settings only after loading and the current checks succeed.
                settings = updated_settings

                # Require new detections using the reloaded settings.
                stabilizer = FlagStabilizer(
                    required_consecutive_frames=4
                )

                print("[INFO] Settings reloaded. Confirmation reset.")

            except Exception as e:
                print(
                    f"[WARN] Reload failed; keeping previous settings: {e}"
                )

    # Close the active capture and preview windows when the loop ends.
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
