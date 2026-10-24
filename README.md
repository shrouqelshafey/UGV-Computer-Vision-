# Computer Vision System Documentation

UGV Project - Colored Flag Detection, Identification, and Frame Stabilization

## 1. Introduction

The UGV is designed to operate autonomously. It must search for a flag, identify its color, and then use the detected flag's position to help the control system guide the robot toward it.

The Computer Vision module is responsible for:

- Detecting colored regions that could represent the flag.
- Identifying the detected flag's color.
- Filtering small regions and image noise.
- Confirming detections across consecutive frames to reduce unstable results.
- Calculating the flag's bounding box, center, and horizontal position relative to the center of the image.
- Sending confirmed detection information to the announcement module so that the flag's color can be displayed on the LCD.

## 2. Approach Selection: Classical Computer Vision Instead of Model Training

### Why I chose this approach?

I chose a classical computer vision approach using OpenCV and HSV color thresholding. The main idea is to detect the flag based on its color instead of training a model to recognize it from a dataset.

The system follows these steps:

1. Capture a frame from the ESP32-CAM.
2. Apply Gaussian blur to reduce small image variations and noise.
3. Convert the frame from BGR to HSV color space.
4. Apply color thresholds using cv2.inRange() to create binary masks.
5. Clean the masks using morphological operations.
6. Find contours and filter them according to their area and, optionally, their aspect ratio.
7. Select the largest valid blob across the configured colors.
8. Confirm the detected color across consecutive frames.
9. Calculate the bounding box, center, and normalized horizontal position.
10. Pass the confirmed detection to the announcement module.

This approach was more suitable for our current problem because the competition requirements make color-based detection a reasonable starting point. The target is expected to be a single, solid-color rectangular fabric flag attached to a vertical pole. The flag's color and size will be announced on competition day, so the system needs to support different colors without requiring a new trained model for each one.

Classical computer vision offers several advantages for this situation:

- No training dataset is required. I do not need to collect and label hundreds or thousands of images of the flag before the system can start detecting it.
- The color thresholds are adjustable. When the actual flag color is known, the HSV ranges can be modified in the configuration file without changing the main detection algorithm.
- The processing is relatively lightweight. The system uses basic image-processing operations instead of a computationally heavier deep learning model. This is useful when working with limited hardware and a low-cost camera.

Training a model such as a YOLO detector could be useful if the system needed to recognize flags based on their shape, pole, context, or appearance under more complicated conditions.

However, that would introduce additional requirements, including collecting representative training data, labeling images, training and evaluating the model, and determining whether the selected hardware can run the model efficiently.

For the current project, I considered a configurable, classical approach more appropriate because it is simpler to implement, easier to modify on competition day, and better aligned with the available hardware and the expected target.

This does not mean classical computer vision is always better than deep learning. The choice depends on the target, environment, computational resources, and required reliability. As my mentor, Fares, always says, it’s not a matter of right or wrong; it’s about what makes the most sense for what you’re working on right now.

## 3. Main application

The overall processing flow is:

Camera frame → Gaussian blur → BGR-to-HSV conversion → Color segmentation → Morphological filtering → Contour detection → Blob filtering → Largest valid candidate → Consecutive-frame confirmation → Position calculation and announcement.

## 4. Color Detection Using HSV and cv2.inRange()

### Why HSV was used instead of BGR

A major decision in the implementation was to perform color segmentation in HSV rather than directly in BGR.

BGR represents each pixel using blue, green, and red intensity values. Although it is the default color format used by OpenCV when reading most color images, setting color thresholds directly in BGR can be difficult because the three channels change together as the lighting conditions change.

HSV represents a pixel using three different properties:

- Hue (H): Represents the type of color, such as red, green, blue, or yellow.
- Saturation (S): Represents how strong or pure the color is.
- Value (V): Represents brightness.

Separating these properties makes it more convenient to define color ranges.

HSV does not make color detection completely independent of lighting. Strong sunlight, shadows, camera exposure, reflections, and white balance can still change the measured values. However, it provides a more convenient representation for defining adjustable color thresholds.

### How cv2.inRange() works

The cv2.inRange() function is the main operation used to separate a target color from the rest of the image.

It compares every pixel in the HSV image with a lower and an upper threshold. If all three HSV components fall within their corresponding ranges, the pixel is assigned a value of 255 (white).

Otherwise, it is assigned a value of 0 (black).

For example:

```python
lower = np.array([100, 150, 50])
upper = np.array([140, 255, 255])
mask = cv2.inRange(hsv_frame, lower, upper)
```

This example creates a mask for pixels whose Hue, Saturation, and Value fall within the specified ranges. These values are an example of a blue-color profile and may need adjustment for the actual camera and flag.

The resulting mask is a binary image. White pixels represent areas that satisfy the color conditions, while black pixels represent areas that do not. This representation makes it easier to find the connected regions that could correspond to the flag.

## 5. Configuration Using settings.json

Instead of hard-coding every threshold inside the detection functions, I placed the main adjustable parameters in settings.json.

This makes the system easier to maintain and test. I can adjust/add the corresponding HSV thresholds. The configuration also allows the minimum area ratio, aspect-ratio limits, blur kernel size, and morphology kernel size to be changed independently.

This separation between the algorithm and its configuration makes the implementation more flexible and helps avoid unnecessary changes to the source code during testing.

### Explanation of the settings

#### min_flag_area_ratio: 0.001

The minimum accepted contour area is calculated as a fraction of the total image area. The value 0.001 corresponds to 0.1% of the image area. A contour smaller than this threshold is rejected.

Using an area ratio rather than a fixed number of pixels makes the threshold scale with the image resolution. For example, a 320 × 240 frame and a 640 × 480 frame will have different minimum contour areas even when the configured ratio is the same.

This is useful because the camera resolution may change. However, it does not guarantee that the same physical flag will occupy the same proportion of the image at different distances.

#### aspect_ratio_range: [0.5, 2.0]

The aspect ratio is calculated as: width / height The candidate is accepted only when its aspect ratio is between 0.5 and 2.0, inclusive. This is an optional shape filter intended to reject some elongated or unusually shaped regions.

#### kernel_size: 3

This determines the size of the square kernel used for morphological filtering. A 3 × 3 kernel is used in the current configuration. A smaller kernel generally preserves more detail but may remove less noise. A larger kernel can clean larger imperfections, but it may also remove small parts of the flag or merge nearby regions.

#### blur_kernel_size: 3

This determines the size of the Gaussian blur kernel applied before color segmentation. A 3 × 3 kernel provides mild smoothing. Larger odd-sized kernels can suppress more noise but may also blur edges and small details.

#### colors

This section contains the HSV thresholds for every supported color. Each color has a first lower and upper bound. Colors that need two separate Hue intervals can also have lower2 and upper2 (like red).

The detector checks all configured color profiles automatically.

## 6. Functions and Methods Used in the Implementation

### `build_mask(hsv_frame, color_ranges, settings)`

This function creates a cleaned binary mask for a particular color.

It first retrieves the morphology kernel size from the settings file and converts the lower and upper HSV bounds into NumPy arrays. It then calls cv2.inRange() to identify the pixels that belong to the configured color range. If a second range exists, the function creates a second mask and combines both masks using cv2.bitwise_or().

Finally, it applies two morphological operations:

#### Morphological opening

```python
mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
```

It helps remove small isolated white regions that may have been incorrectly classified as the target color. For example, small colored specks caused by image noise may disappear after opening.

#### Morphological closing

```python
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
```

It helps fill small black gaps and holes inside white regions. This is useful when the flag surface contains small imperfections.

The function returns the cleaned mask for use by the contour detection stage.

### `find_largest_blob(mask, settings)`

This function identifies the largest valid connected contour in a binary mask. It begins with cv2.findContours(), which extracts the boundaries of white regions in the mask.

The selected parameters are:

- cv2.RETR_EXTERNAL: Retrieves only the outermost contours. This is appropriate because the system is interested in the external boundary of each candidate rather than nested internal contours.
- cv2.CHAIN_APPROX_SIMPLE: Reduces redundant points along straight contour segments, making the contour representation more compact.

The function then calculates the image area and derives the minimum allowed contour area from min_flag_area_ratio. Each contour is checked against the minimum area threshold. If it is too small, it is rejected.

For the remaining contours, cv2.boundingRect() calculates the smallest upright rectangle that encloses the contour. The width and height of this rectangle are used to calculate its aspect ratio. If aspect_ratio_range is configured, contours outside the allowed interval are rejected.

Every remaining candidate is stored with its area and bounding box. The function then returns the candidate with the largest contour area. If no candidate passes the filters, it returns None.

Selecting the largest valid blob is a simple way to prioritize the most prominent colored region in the frame. It is not a guarantee that the selected region is the flag. A larger object of a similar color could still be selected.

### `detect_flag(frame, settings)`

This is the main detection function. It combines the preprocessing, color segmentation, contour filtering, and candidate selection stages.

#### Step 1: Gaussian blur

```python
blurred_frame = cv2.GaussianBlur(
    frame, (blur_ksize, blur_ksize), 0
)
```

Gaussian blur smooths the image by replacing each pixel with a weighted average of nearby pixels. Nearby pixels closer to the center of the kernel receive greater weight.

I included this step because the ESP32-CAM image may contain noise and small variations in pixel values. Without smoothing, these variations can create isolated pixels that fall inside a color threshold.

The kernel size is configurable, allowing the amount of smoothing to be adjusted. Blurring is a compromise: too little smoothing may leave noise, while too much can weaken the boundaries of the flag.

#### Step 2: Convert BGR to HSV

```python
hsv = cv2.cvtColor(blurred_frame, cv2.COLOR_BGR2HSV)
```

OpenCV provides the camera frame in BGR format. The frame is converted to HSV because HSV makes it more convenient to define color thresholds independently of brightness.

#### Step 3: Search the configured colors

The function iterates through every color in settings["colors"]. For each color, it calls build_mask() to create the mask and find_largest_blob() to identify its largest valid candidate.

The detector compares the areas of the candidates found for different colors. It keeps the candidate with the largest contour area as the overall result. This design allows the system to identify a color automatically without requiring the operator to select a color before processing begins.

#### Step 4: Handle missing detections

If no valid candidate is found for any color, the function returns:

```python
{"detected": False}
```

This tells the main application that the current frame does not contain an accepted detection.

#### Step 5: Calculate the bounding box and center

When a candidate is found, the function extracts its bounding box coordinates (x, y, w, h) and calculates the center:

```python
center_x = x + w // 2
center_y = y + h // 2
```

### FlagStabilizer class

The FlagStabilizer class was introduced to reduce the effect of unstable detections between frames.

A camera processes a continuous sequence of images. A single frame may contain noise, a temporary lighting change, or an incorrectly classified region. If the system announces every individual detection, the output may change unnecessarily.

The stabilizer checks whether the same color appears in consecutive frames.

#### `__init__(required_consecutive_frames=4)`

This method initializes the stabilizer.

- required_frames stores the number of consecutive detections required for confirmation.
- current_color stores the color being tracked.
- consecutive_count stores the number of consecutive frames in which that color has been detected.

The current setting requires four consecutive detections.

#### `update(detection_result)`

This method processes the detection result from each frame. If a detection exists and its color matches current_color, the consecutive count is increased. If a different color is detected, the current color is replaced and the counter is reset to one because the current frame is the first detection of the new color. If no detection is found, the color and counter are reset, and the function returns {"confirmed": False}.

Once the counter reaches the required number of frames, the method returns a confirmed result containing the color, center, bounding box, and area from the current detection.

This approach reduces false announcements caused by isolated detections and short interruptions. However, it does not completely eliminate false positives.

### `main()`

The main() function connects the different components and manages the complete application loop.

## 7. Problems Faced During Development

### Limited image quality of the ESP32-CAM

One of the main challenges is the quality of the ESP32-CAM. Compared with a better camera, its image can be less reliable under difficult lighting conditions and may contain noise, blur, or inconsistent color reproduction.

This directly affects HSV thresholding. The detector operates on the pixels provided by the camera, so inaccurate color information can lead to missing detections or incorrect color classification.

### Adjusting HSV ranges

The initial HSV thresholds cannot be assumed to work perfectly with the actual ESP32-CAM.

They must be checked against images captured by the camera. Different cameras can produce different pixel values for the same physical color because of exposure, white balance, sensor characteristics, and image processing.

As a result, the ranges in settings.json need to be adjusted based on the actual flag and the camera's output. This is especially important when the competition flag's color is announced and the system must be configured for that target.

Lighting was another important challenge.

For this reason, the camera was tested under different lighting conditions. The HSV thresholds were checked in each condition rather than selected from one image and assumed to work everywhere.

### Choosing a suitable candidate

The system selects the largest valid contour for each color and then chooses the largest candidate across all configured colors. This is a practical rule for a simple environment with one prominent flag, but it introduces a limitation. If a different object of a configured color occupies more image area than the flag, the system may select that object instead.

The area filter and aspect-ratio filter reduce some unwanted candidates, but neither can prove that a region is a flag.

### Unstable frame-by-frame detections

A candidate may appear in one frame and disappear in the next because of motion. To reduce this instability, I implemented the FlagStabilizer class, which requires four consecutive detections of the same color before confirmation.

This improves consistency but introduces a small delay. It can also fail if the camera repeatedly loses the target or if a false detection persists for the required number of frames.

## 8. Limitations and Cases Where the Approach May Fail

Although the developed approach is appropriate for the current requirements, it has several limitations that must be considered before deployment.

### Objects with similar colors

The detector relies primarily on color. If another object in the background has a color within one of the configured HSV ranges, it may be detected as a candidate. This is particularly problematic if the object is large enough to pass the area filter and has an acceptable bounding-box aspect ratio.

The system does not currently use a trained classifier to distinguish a flag from every other object with a similar color.

### Severe lighting changes

Strong shadows, overexposure, reflections, or automatic camera adjustments can move the flag's pixels outside the configured HSV ranges. The result may be a fragmented mask, an incorrect color classification, or no detection at all.

HSV reduces some of the difficulty associated with defining color thresholds, but it does not eliminate lighting sensitivity.

### Small or distant flags

The minimum area ratio rejects candidates that occupy too little of the image. If the flag is far away or appears very small, its contour may fall below the threshold. A distant flag may also contain too few pixels to preserve its color accurately. Lowering the area threshold may help detect smaller targets, but it also allows more noise and background objects to pass the filter.

### Incorrect aspect-ratio assumptions

The current aspect-ratio interval is broad, but it still rejects contours outside the configured limits. If the flag appears at an unusual angle, is partially hidden, or has proportions outside the selected interval, it may be rejected even when its color is correct.

Because the actual flag dimensions are not yet known, the current limits should be treated as initial values rather than final competition parameters.

### Overlapping color ranges

The HSV profiles are configured independently. If two color ranges overlap, a pixel or region may satisfy more than one profile. For example, the boundaries between red, orange, and yellow may be difficult to separate under certain lighting conditions. If different color profiles identify similar regions, the detector selects the candidate with the largest contour area rather than applying a separate color-confidence score.

This means the selected color may be wrong even if the system detects the physical flag region correctly.

### Delay during confirmation

The detector must observe four consecutive frames with the same color before returning a confirmed result. This delay depends on the camera frame rate. If frames arrive slowly or the camera stream is unstable, confirmation may take longer than expected. The current stabilizer also resets its counter when a frame contains no accepted detection. Repeated interruptions can therefore prevent confirmation even when the flag is visible most of the time.

## 9. Conclusion

The Computer Vision module was developed using classical image-processing techniques in OpenCV to detect and identify a colored flag. The approach uses HSV thresholding, binary masks, morphological filtering, contour extraction, geometric filtering, largest-blob selection, and consecutive-frame confirmation.

We selected this approach because it matches the current project requirements, avoids the need for a labeled training dataset, and allows the detection parameters to be adjusted easily when the actual competition flag is known. It also provides a relatively lightweight and interpretable solution for the ESP32-CAM-based system.

Our GitHub repo https://github.com/shrouqelshafey/UGV-Computer-Vision-.git
