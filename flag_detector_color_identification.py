import cv2
import json
import numpy as np
import time
#min_flag_area->the smallest size a shape can be to count as a flag 
#(man3mlhash too low 3ashan el specks dont get treated as a flag wala too high so that the real flag doesn't get rejected)\
#aspect_ratio_range->how wide the shape is compared to its height, removes things that are the wrong shape

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
#Find the largest contour that passes area and shape checks
#Find the outlines of the white areas in the mask
    contours, _= cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL, #keeps only outer outlines 
        cv2.CHAIN_APPROX_SIMPLE
    )

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

def detect_flag(frame,settings):
    """Detects flag color, bounding box, area, and center."""
#blur first to smooth out camera noise
    blur_ksize=settings.get("blur_kernel_size", 5)
    blurred_frame=cv2.GaussianBlur(frame, (blur_ksize, blur_ksize), 0)

#convert from BGR to HSV, better for color detection
    hsv=cv2.cvtColor(blurred_frame, cv2.COLOR_BGR2HSV)
#variables that will hold the winning color and its blob
    best_color=None
    best_blob=None
#try every color from settings file 
    for color_name, ranges in settings["colors"].items():
        mask=build_mask(hsv, ranges, settings) 
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

def main():
    try:
        settings = load_settings()
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    cap=cv2.VideoCapture("http://192.168.1.103:81/stream") # we should put the URI of straming adress here ex:"http://192.168.1.107:81/stream"
    if not cap.isOpened():
        print("[ERROR] Could not open camera.")
        return

    stabilizer=FlagStabilizer(required_consecutive_frames=4) #onlu trust a detection after 4 frames in a row
    print("[INFO] Pure Flag Vision Module Running. Press 'q' to Quit.")

    max_consecutive_failures=30 #30 failed frame max
    failure_count=0

    while True: #runs oncer per camera frame
        ret, frame=cap.read() #ret=true if a frame was grabbed 
        if not ret:
            failure_count+=1
            print(f"[WARN] Failed to grab frame ({failure_count}/{max_consecutive_failures}). Retrying...")
            if failure_count >= max_consecutive_failures:
                print("[ERROR] Camera feed lost permanently. Exiting program.")
                break
            #wait a moment
            time.sleep(0.1)
            continue
        
        failure_count=0
#look for a flag in this single frame
        raw_detection=detect_flag(frame, settings)
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

        if cv2.waitKey(1) & 0xFF == ord('q'): #press q exists the camera
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()