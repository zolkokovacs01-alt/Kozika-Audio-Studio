import tempfile
import unittest
from pathlib import Path

from equalizer_apo import (
    APO_FILENAME,
    INCLUDE_LINE,
    apply_system_audio,
    build_apo_config,
    disable_system_audio,
)


class EqualizerApoTests(unittest.TestCase):
    def test_build_config_includes_eq_and_tone_filters(self):
        config = build_apo_config({
            "eq_1000": 4,
            "bass": 50,
            "clarity": 50,
            "treble": 50,
            "volume": 100,
        })
        self.assertIn("Filter 1: ON PK Fc 1000 Hz Gain 4.00 dB Q 1.00", config)
        self.assertIn("LS Fc 100 Hz", config)
        self.assertIn("PK Fc 3500 Hz", config)
        self.assertIn("HS Fc 7000 Hz", config)
        self.assertIn("Preamp:", config)

    def test_apply_and_disable_preserve_existing_config(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            main = folder / "config.txt"
            main.write_text("Preamp: -2 dB\nInclude: existing.txt\n", encoding="utf-8")
            generated = apply_system_audio({"eq_1000": 3}, folder)
            self.assertTrue(generated.is_file())
            text = main.read_text(encoding="utf-8")
            self.assertIn("Include: existing.txt", text)
            self.assertIn(INCLUDE_LINE, text)
            self.assertTrue((folder / "config.txt.kozika-backup").is_file())

            disable_system_audio(folder)
            text = main.read_text(encoding="utf-8")
            self.assertIn("Include: existing.txt", text)
            self.assertNotIn(INCLUDE_LINE, text)
            self.assertTrue((folder / APO_FILENAME).is_file())


if __name__ == "__main__":
    unittest.main()
