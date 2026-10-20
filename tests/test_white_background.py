"""Detect non-white flags automatically on the competition's white background."""

import unittest

import numpy as np

from vision.detector import FlagStabilizer, detect_flag
from vision.settings import load_settings


class WhiteBackgroundTests(unittest.TestCase):
    def setUp(self):
        # Use the real project settings so restoring white exposes the regression.
        self.settings = load_settings()

    def test_each_supported_flag_color_on_white_sheet(self):
        colors = {
            "red": (0, 0, 255),
            "blue": (255, 0, 0),
            "green": (0, 255, 0),
            "yellow": (0, 255, 255),
            "orange": (0, 128, 255),
            "purple": (255, 0, 128),
        }
        for color, bgr in colors.items():
            with self.subTest(color=color):
                image = np.full((240, 320, 3), 255, dtype=np.uint8)
                image[70:150, 110:210] = bgr
                # Every frame searches all six configured colors automatically.
                result = detect_flag(image, self.settings)
                self.assertTrue(result["detected"])
                self.assertEqual(result["color"], color)
                x, y, width, height = result["box"]
                self.assertLess(width * height, image.shape[0] * image.shape[1] / 2)
                self.assertTrue(x <= 160 < x + width)
                self.assertTrue(y <= 110 < y + height)

    def test_blank_white_sheet_never_confirms_a_flag(self):
        image = np.full((240, 320, 3), 255, dtype=np.uint8)
        stabilizer = FlagStabilizer()
        for _ in range(8):
            detection = detect_flag(image, self.settings)
            self.assertFalse(detection["detected"])
            self.assertFalse(stabilizer.update(detection)["confirmed"])

    def test_removing_confirmed_flag_clears_confirmation(self):
        blank = np.full((240, 320, 3), 255, dtype=np.uint8)
        image = blank.copy()
        image[70:150, 110:210] = (0, 0, 255)
        stabilizer = FlagStabilizer()
        for index in range(4):
            result = stabilizer.update(detect_flag(image, self.settings))
            self.assertEqual(result["confirmed"], index == 3)
        # The sheet alone must not replace the removed red flag with white.
        self.assertFalse(
            stabilizer.update(detect_flag(blank, self.settings))["confirmed"]
        )


if __name__ == "__main__":
    unittest.main()
