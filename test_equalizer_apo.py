import tempfile
import unittest
from pathlib import Path

from equalizer_apo import (
    APO_FILENAME,
    DISABLED_CONFIG,
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

    def test_many_eq_boosts_cannot_attenuate_to_silence(self):
        settings = {f"eq_{frequency}": 12 for frequency in
                    (31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)}
        config = build_apo_config(settings)
        self.assertIn("Preamp: -18.00 dB", config)

    def test_system_preamp_never_adds_unlimited_gain(self):
        config = build_apo_config({"volume": 150})
        self.assertIn("Preamp: 0.00 dB", config)

    def test_apply_and_disable_preserve_existing_config(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            main = folder / "config.txt"
            main.write_text("Preamp: -2 dB\nInclude: existing.txt\n", encoding="utf-8")
            generated = apply_system_audio({"eq_1000": 3}, folder)
            self.assertEqual(generated, folder / APO_FILENAME)
            self.assertTrue(generated.is_file())
            text = main.read_text(encoding="utf-8")
            self.assertIn("Include: existing.txt", text)
            self.assertIn(INCLUDE_LINE, text)
            self.assertTrue((folder / "config.txt.kozika-backup").is_file())

            # Subsequent slider changes update only the Kozika-owned file.
            main_before = main.read_bytes()
            apply_system_audio({"bass": 35, "volume": 100}, folder)
            self.assertEqual(main.read_bytes(), main_before)

            disable_system_audio(folder)
            self.assertEqual(main.read_bytes(), main_before)
            self.assertEqual(generated.read_text(encoding="utf-8"), DISABLED_CONFIG)


if __name__ == "__main__":
    unittest.main()
