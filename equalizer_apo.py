"""Windows system-audio integration through Equalizer APO.

The generated live filter file is stored in the user's LocalAppData folder.
Only the one-time Include entry in Equalizer APO's protected config.txt needs
administrator approval; ordinary slider changes never write to Program Files.
"""
from __future__ import annotations

import ctypes
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Mapping

APO_DIRS = (
    Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "EqualizerAPO" / "config",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")) / "EqualizerAPO" / "config",
)
APO_FILENAME = "KozikaAudioStudio.txt"
LEGACY_INCLUDE_LINE = f"Include: {APO_FILENAME}"


def user_config_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / "AppData" / "Local"
    return root / "KozikaAudioStudio" / "EqualizerAPO"


def include_line(user_dir: Path | None = None) -> str:
    target = (user_dir or user_config_dir()) / APO_FILENAME
    # Equalizer APO accepts quoted file paths; use a full local path so the
    # generated file can live outside the protected Program Files directory.
    return f'Include: "{target.resolve()}"'


def find_config_dir() -> Path | None:
    for folder in APO_DIRS:
        if (folder / "config.txt").is_file():
            return folder
    return None


def build_apo_config(settings: Mapping[str, float]) -> str:
    """Convert Kozika controls into Equalizer APO filters with safe headroom."""
    frequencies = (31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
    eq = [float(settings.get(f"eq_{f}", 0.0)) for f in frequencies]
    bass = float(settings.get("bass", 0.0)) * 0.12
    clarity = float(settings.get("clarity", 0.0)) * 0.08
    treble = float(settings.get("treble", 0.0)) * 0.12
    volume = min(150.0, max(0.0, float(settings.get("volume", 100.0))))
    volume_db = 20.0 * math.log10(max(volume, 0.1) / 100.0)

    # A long sum of every positive EQ slider can attenuate the whole signal
    # almost to silence. Cap EQ headroom compensation; the APO output remains
    # protected from clipping without making ordinary slider changes inaudible.
    requested_boost = (
        sum(max(0.0, gain) for gain in eq)
        + max(0.0, bass) + max(0.0, clarity) + max(0.0, treble)
    )
    preamp = volume_db - min(requested_boost, 18.0)

    lines = [
        "# Kozika Audio Studio - generated settings",
        "# Managed by Kozika Audio Studio; edit the app controls instead.",
        f"Preamp: {preamp:.2f} dB",
    ]
    number = 1
    for frequency, gain in zip(frequencies, eq):
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
    return "\\n".join(lines) + "\\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\\n", dir=path.parent, delete=False
        ) as handle:
            handle.write(text)
            temp_name = handle.name
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def _needs_include_update(main_config: Path, line: str) -> bool:
    text = main_config.read_text(encoding="utf-8-sig")
    return line.casefold() not in text.casefold()


def request_admin_install(config_dir: Path | None = None,
                          user_dir: Path | None = None) -> bool:
    """Ask Windows for one-time elevation to add the APO Include directive."""
    folder = config_dir or find_config_dir()
    if folder is None or os.name != "nt":
        return False
    main_config = folder / "config.txt"
    target_dir = user_dir or user_config_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    wanted = include_line(target_dir)

    def ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    script = f"""$ErrorActionPreference = 'Stop'
$configPath = {ps_quote(str(main_config))}
$includeLine = {ps_quote(wanted)}
$backupPath = $configPath + '.kozika-backup'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {{ throw 'Equalizer APO config.txt not found.' }}
$raw = [System.IO.File]::ReadAllText($configPath)
$lines = @($raw -split "\\r?\\n")
$kept = New-Object System.Collections.Generic.List[string]
foreach ($line in $lines) {{
    if ($line -match '^\\s*Include:\\s*"?KozikaAudioStudio\\.txt"?\\s*$') {{ continue }}
    if ($line -eq $includeLine) {{ continue }}
    [void]$kept.Add($line)
}}
[void]$kept.Add($includeLine)
if (-not (Test-Path -LiteralPath $backupPath)) {{ Copy-Item -LiteralPath $configPath -Destination $backupPath }}
$body = ($kept -join [Environment]::NewLine).TrimEnd() + [Environment]::NewLine
[System.IO.File]::WriteAllText($configPath, $body, [System.Text.UTF8Encoding]::new($false))
"""
    script_path = target_dir / "install_equalizer_apo_include.ps1"
    _atomic_write(script_path, script)
    parameters = f'-NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", parameters, None, 1
        )
        return int(result) > 32
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def apply_system_audio(settings: Mapping[str, float],
                       config_dir: Path | None = None,
                       user_dir: Path | None = None) -> Path:
    """Write live filters to LocalAppData and ensure config.txt includes them."""
    folder = config_dir or find_config_dir()
    if folder is None:
        raise FileNotFoundError(
            "Nem található az Equalizer APO. Telepítsd, majd a Configuratorban "
            "jelöld be a Realtek és a külső hangszóró kimenetét."
        )
    main_config = folder / "config.txt"
    if not main_config.is_file():
        raise FileNotFoundError(f"Nem található: {main_config}")

    target_dir = user_dir or user_config_dir()
    generated = target_dir / APO_FILENAME
    _atomic_write(generated, build_apo_config(settings))

    wanted = include_line(target_dir)
    main_text = main_config.read_text(encoding="utf-8-sig")
    if wanted.casefold() not in main_text.casefold():
        # Migrate the previous version's relative Include instead of leaving
        # two active Kozika filter files in the Equalizer APO chain.
        lines = [
            line for line in main_text.splitlines()
            if not re.match(r'^\\s*Include:\\s*"?KozikaAudioStudio\\.txt"?\\s*$',
                            line, flags=re.IGNORECASE)
            and line.strip().casefold() != wanted.casefold()
        ]
        lines.append(wanted)
        backup = folder / "config.txt.kozika-backup"
        if not backup.exists():
            shutil.copy2(main_config, backup)
        _atomic_write(main_config, "\\n".join(lines).rstrip() + "\\n")
    return generated


def disable_system_audio(config_dir: Path | None = None,
                         user_dir: Path | None = None) -> None:
    """Disable only Kozika filters without editing protected config.txt."""
    target = (user_dir or user_config_dir()) / APO_FILENAME
    # Keep the one-time Include installed, but make its file neutral. This
    # avoids requiring administrator rights merely to turn Kozika off.
    _atomic_write(target, "# Kozika Audio Studio - processing disabled\\nPreamp: 0 dB\\n")
