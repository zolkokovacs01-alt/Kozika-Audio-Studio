import unittest

import numpy as np

from audio_engine import AudioProcessor


class AudioProcessorTests(unittest.TestCase):
    def setUp(self):
        self.sample_rate = 48000
        time = np.arange(self.sample_rate // 2, dtype=np.float32) / self.sample_rate
        tone = 0.2 * np.sin(2 * np.pi * 1000 * time)
        self.samples = np.column_stack((tone, tone)).astype(np.float32)

    def test_equalizer_boosts_selected_frequency(self):
        flat = AudioProcessor(self.sample_rate).process(self.samples)
        processor = AudioProcessor(self.sample_rate)
        processor.set_settings({"eq_1000": 6})
        boosted = processor.process(self.samples)
        self.assertGreater(np.sqrt(np.mean(boosted ** 2)), np.sqrt(np.mean(flat ** 2)) * 1.5)

    def test_spatial_processing_changes_stereo_signal(self):
        stereo = self.samples.copy()
        stereo[:, 1] = np.sin(2 * np.pi * 1000 * np.arange(len(stereo)) / self.sample_rate + 0.4)
        processor = AudioProcessor(self.sample_rate)
        processor.set_settings({"spatial": 80})
        processed = processor.process(stereo)
        self.assertFalse(np.allclose(processed, stereo))

    def test_tone_controls_boost_their_target_ranges(self):
        time = np.arange(self.sample_rate // 2, dtype=np.float32) / self.sample_rate
        for setting, frequency in (("bass", 80), ("clarity", 3500), ("treble", 10000)):
            with self.subTest(setting=setting):
                tone = 0.1 * np.sin(2 * np.pi * frequency * time)
                samples = np.column_stack((tone, tone)).astype(np.float32)
                flat = AudioProcessor(self.sample_rate).process(samples)
                processor = AudioProcessor(self.sample_rate)
                processor.set_settings({setting: 80})
                enhanced = processor.process(samples)
                self.assertGreater(np.sqrt(np.mean(enhanced ** 2)), np.sqrt(np.mean(flat ** 2)) * 1.3)

    def test_output_level_scales_audio(self):
        processor = AudioProcessor(self.sample_rate)
        processor.set_settings({"volume": 50})
        reduced = processor.process(self.samples)
        self.assertAlmostEqual(float(np.sqrt(np.mean(reduced ** 2))),
                               float(np.sqrt(np.mean(self.samples ** 2))) * 0.5, places=4)

    def test_limiter_keeps_output_below_full_scale(self):
        processor = AudioProcessor(self.sample_rate)
        processed = processor.process(self.samples * 4)
        self.assertLessEqual(float(np.max(np.abs(processed))), 1.0)


if __name__ == "__main__":
    unittest.main()