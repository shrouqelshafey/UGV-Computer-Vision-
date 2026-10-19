"""Load the shared JSON settings when the application starts."""

import json
from pathlib import Path


def load_settings(path=None):
    """Load and validate settings from JSON."""
    # Resolve the default file from the project, not the terminal directory.
    if path is None:
        path = Path(__file__).resolve().parent.parent / "settings.json"
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
