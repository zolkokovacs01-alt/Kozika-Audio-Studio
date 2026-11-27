"""Real-time stereo audio processing for Kozika Audio Studio."""

from __future__ import annotations

import threading

import numpy as np
from scipy.signal import lfilter, sosfilt


BANDS = (31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
DEFAULTS = {
    **{f"eq_{frequency}": 0.0 for frequency in BANDS},
    "bass": 0.0,
    "clarity": 0.0,
    "treble": 0.0,
    "spatial": 0.0,
    "volume": 100.0,
}
PRESETS = {
    "Kiegyensúlyozott": {"eq": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "bass": 0, "clarity": 0, "treble": 0, "spatial": 18, "volume": 100},
    "Zene": {"eq": [2, 3, 2, 0, -1, 0, 1, 2, 2, 1], "bass": 24, "clarity": 18, "treble": 18, "spatial": 30, "volume": 100},
    "Film": {"eq": [3, 3, 1, 0, 1, 2, 3, 2, 1, 0], "bass": 30, "clarity": 25, "treble": 10, "spatial": 55, "volume": 100},
    "Mély basszus": {"eq": [4, 5, 4, 2, 0, 0, 0, 0, 0, 0], "bass": 60, "clarity": 0, "treble": 0, "spatial": 12, "volume": 100},
    "Tiszta beszéd": {"eq": [-2, -1, 0, 1, 2, 3, 3, 2, 1, 0], "bass": 0, "clarity": 45, "treble": 18, "spatial": 15, "volume": 100},
}


def _peaking_eq(frequency: float, gain_db: float, sample_rate: int, q: float) -> list[float]:
    frequency = min(frequency, sample_rate * 0.45)
    amplitude = 10 ** (gain_db / 40)
    omega = 2 * np.pi * frequency / sample_rate
    alpha = np.sin(omega) / (2 * q)
    cosine = np.cos(omega)
    return _normalize_sos(
        [1 + alpha * amplitude, -2 * cosine, 1 - alpha * amplitude,
         1 + alpha / amplitude, -2 * cosine, 1 - alpha / amplitude]
    )


def _shelf(frequency: float, gain_db: float, sample_rate: int, high: bool = False) -> list[float]:
    frequency = min(frequency, sample_rate * 0.45)
    amplitude = 10 ** (gain_db / 40)
    omega = 2 * np.pi * frequency / sample_rate
    cosine = np.cos(omega)
    alpha = np.sin(omega) / np.sqrt(2)
    root = 2 * np.sqrt(amplitude) * alpha

    if high:
        coefficients = [
            amplitude * ((amplitude + 1) + (amplitude - 1) * cosine + root),
            -2 * amplitude * ((amplitude - 1) + (amplitude + 1) * cosine),
            amplitude * ((amplitude + 1) + (amplitude - 1) * cosine - root),
            (amplitude + 1) - (amplitude - 1) * cosine + root,
            2 * ((amplitude - 1) - (amplitude + 1) * cosine),
            (amplitude + 1) - (amplitude - 1) * cosine - root,
        ]
    else:
        coefficients = [
            amplitude * ((amplitude + 1) - (amplitude - 1) * cosine + root),
            2 * amplitude * ((amplitude - 1) - (amplitude + 1) * cosine),
            amplitude * ((amplitude + 1) - (amplitude - 1) * cosine - root),
            (amplitude + 1) + (amplitude - 1) * cosine + root,
            -2 * ((amplitude - 1) + (amplitude + 1) * cosine),
            (amplitude + 1) + (amplitude - 1) * cosine - root,
        ]
    return _normalize_sos(coefficients)


def _normalize_sos(coefficients: list[float]) -> list[float]:
    b0, b1, b2, a0, a1, a2 = coefficients
    return [b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]


class AudioProcessor:
    """Block-based EQ, tone shaping, stereo widening, and output limiting."""

    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self._settings = DEFAULTS.copy()
        self._lock = threading.Lock()
        self._sos = self._build_sos(self._settings)
        self._filter_state = np.zeros((13, 2, 2), dtype=np.float64)
        self._delay_samples = max(1, int(sample_rate * 0.012))
        self._delay_state = np.zeros((2, self._delay_samples), dtype=np.float64)
        self._delay_filter = np.zeros(self._delay_samples + 1)
        self._delay_filter[-1] = 1.0

    def _build_sos(self, settings: dict[str, float]) -> np.ndarray:
        gains = [settings[f"eq_{frequency}"] for frequency in BANDS]
        sections = [
            _peaking_eq(frequency, gain, self.sample_rate, 1.0)
            for frequency, gain in zip(BANDS, gains)
        ]
        sections.extend((
            _shelf(100, settings["bass"] * 0.12, self.sample_rate),
            _peaking_eq(3500, settings["clarity"] * 0.08, self.sample_rate, 0.8),
            _shelf(7000, settings["treble"] * 0.12, self.sample_rate, high=True),
        ))
        return np.asarray(sections, dtype=np.float64)

    def set_settings(self, values: dict[str, float]) -> None:
        # Build coefficients outside the audio callback.  The callback only
        # swaps an already prepared immutable array, so moving a slider never
        # makes the real-time audio thread calculate filter coefficients.
        with self._lock:
            updated = self._settings.copy()
        for name, value in values.items():
            if name not in updated:
                continue
            number = float(value)
            if not np.isfinite(number):
                continue
            if name.startswith("eq_"):
                number = min(12.0, max(-12.0, number))
            elif name == "volume":
                number = min(150.0, max(0.0, number))
            else:
                number = min(100.0, max(0.0, number))
            updated[name] = number
        coefficients = self._build_sos(updated)
        with self._lock:
            self._settings = updated
            self._sos = coefficients

    def process(self, samples: np.ndarray) -> np.ndarray:
        if samples.ndim != 2 or samples.shape[1] != 2:
            raise ValueError("A hangfeldolgozó kétcsatornás mintákat vár.")
        if samples.size == 0:
            return samples.astype(np.float32, copy=True)

        with self._lock:
            settings = self._settings.copy()
            sos = self._sos

        output, self._filter_state = sosfilt(
            sos, samples.astype(np.float64, copy=False), axis=0, zi=self._filter_state
        )

        spatial = settings["spatial"] / 100.0
        if spatial:
            mid = (output[:, 0] + output[:, 1]) * 0.5
            side = (output[:, 0] - output[:, 1]) * 0.5
            delayed_left, self._delay_state[0] = lfilter(
                self._delay_filter, [1.0], output[:, 1], zi=self._delay_state[0]
            )
            delayed_right, self._delay_state[1] = lfilter(
                self._delay_filter, [1.0], output[:, 0], zi=self._delay_state[1]
            )
            reflection = np.column_stack((delayed_left, delayed_right)) * (spatial * 0.16)
            widened_side = side * (1.0 + spatial * 0.8)
            output = np.column_stack((mid + widened_side, mid - widened_side)) + reflection

        output *= settings["volume"] / 100.0
        output = np.nan_to_num(output, copy=False, nan=0.0, posinf=1.0, neginf=-1.0)
        magnitude = np.abs(output)
        over_limit = magnitude > 0.95
        output[over_limit] = np.sign(output[over_limit]) * (
            0.95 + 0.05 * np.tanh((magnitude[over_limit] - 0.95) / 0.05)
        )
        return output.astype(np.float32)