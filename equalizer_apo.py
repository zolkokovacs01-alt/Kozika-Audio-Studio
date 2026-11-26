"""System-wide Windows audio integration through Equalizer APO.

Equalizer APO is an external, signed Windows Audio Processing Object. This
module writes Kozika's tone controls to an included APO configuration file;
it does not install drivers or change Windows audio endpoints.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Mapping

APO_DIRS = (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "EqualizerAPO" / "config",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "EqualizerAPO" / "config",
)
APO_FILENAME = "KozikaAudioStudio.txt"
INCLUDE_LINE = f"Include: {APO_FILENAME}"


def find_config_dir() -> Path | None:
    for folder in APO_DIRS:
        if (folder / "config.txt").is_file():
            return folder
    return None


def build_apo_config(settings: Mapping[str, float]) -> str:
    """Convert Kozika controls into Equalizer APO filter commands."""
    eq = [float(settings.get(f"eq_{f}", 0.0)) for f in
          (31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)]
    bass = float(settings.get("bass", 0.0)) * 0.12
    clarity = float(settings.get("clarity", 0.0)) * 0.08
    treble = float(settings.get("treble", 0.0)) * 0.12
    volume = max(0.0, float(settings.get("volume", 100.0)))
    volume_db = 20.0 * math.log10(max(volume, 0.1) / 100.0)
    # Conservative headroom prevents the combined positive filters clipping.
    boost = sum(max(0.0, gain) for gain in eq) + max(0.0, bass) + max(0.0, clarity) + max(0.0, treble)
    preamp = min(0.0, volume_db - boost)

    lines = [
        "# Kozika Audio Studio - generated settings",
        "# Managed by Kozika Audio Studio; edit the app controls instead.",
        f"Preamp: {preamp:.2f} dB",
    ]
    number = 1
    for frequency, gain in zip((31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000), eq):
        if abs(gain) >= 0.05:
            lines.append(f"Filter {number}: ON PK Fc {frequency} Hz Gain {gain:.2f} dB Q 1.00")
            number += 1
    if abs(bass) >= 0.05:
        lines.append(f"Filter {number}: ON LS Fc 100 Hz Gain {bass:.2f} dB")
        number += 1
    if abs(clarity) >= 0.05:
        lines.append(f"Filter {number}: ON PK Fc 3500 Hz Gain {clarity:.2f} dB Q 0.80")
        number += 1
    if abs(treble) >= 0.05:
        lines.append(f"Filter {number}: ON HS Fc 7000 Hz Gain {treble:.2f} dB")
    return "\n".join(lines) + "\n"


def apply_system_audio(settings: Mapping[str, float], config_dir: Path | None = None) -> Path:
    """Safely include Kozika's generated filters in Equalizer APO config.txt."""
    folder = config_dir or find_config_dir()
    if folder is None:
        raise FileNotFoundError(
            "Nem található az Equalizer APO. Telepítsd, majd a Configuratorban "
            "jelöld be a Realtek és a külső hangszóró kimenetét."
        )
    main_config = folder / "config.txt"
    if not main_config.is_file():
        raise FileNotFoundError(f"Nem található: {main_config}")

    generated = folder / APO_FILENAME
    main_text = main_config.read_text(encoding="utf-8-sig")
    if INCLUDE_LINE.casefold() not in main_text.casefold():
        backup = folder / "config.txt.kozika-backup"
        if not backup.exists():
            shutil.copy2(main_config, backup)
        updated = main_text.rstrip() + "\n\n# Kozika Audio Studio system-wide processing\n" + INCLUDE_LINE + "\n"
        # Write via a temporary file in the same directory, then replace atomically.
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                         dir=folder, delete=False) as handle:
            handle.write(updated)
            temp_name = handle.name
        os.replace(temp_name, main_config)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                     dir=folder, delete=False) as handle:
        handle.write(build_apo_config(settings))
        temp_name = handle.name
    os.replace(temp_name, generated)
    return generated
