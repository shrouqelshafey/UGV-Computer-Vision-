"""Choose a target color from a clean, unannotated camera frame."""

import cv2

from .detector import detect_flag


def select_target_color(calibration_frame, settings, target_color=None):
    """Keep the previous target when selection is cancelled or unrecognized."""
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
        # Count pixels directly; detection already converts the sample to HSV.
        sample_pixel_count = sample.shape[0] * sample.shape[1]
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
            f"{sample_pixel_count} calibration pixels."
        )
    else:
        print("[INFO] Calibration cancelled.")

    # Return the chosen profile name; the caller resets confirmation.
    return target_color
