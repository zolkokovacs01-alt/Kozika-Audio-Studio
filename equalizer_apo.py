"""Windows system-audio integration through Equalizer APO.

The live filter file stays inside Equalizer APO's config directory so APO can
watch and reload it immediately. A one-time UAC helper grants the current
Windows user Modify rights to this single Kozika-owned file; slider changes
then never need administrator rights or rewrite config.txt.
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
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "EqualizerAPO" / "config",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "EqualizerAPO" / "config",
)
APO_FILENAME = "KozikaAudioStudio.txt"
INCLUDE_LINE = f"Include: {APO_FILENAME}"
DISABLED_CONFIG = "# Kozika Audio Studio - processing disabled\nPreamp: 0 dB\n"


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
    requested_boost = (
        sum(max(0.0, gain) for gain in eq)
        + max(0.0, bass) + max(0.0, clarity) + max(0.0, treble)
    )
    # Avoid attenuating the whole signal into near-silence when several EQ
    # bands are raised. The limiter remains the final peak-safety stage.
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
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    """Atomic write for config.txt (used only during one-time installation)."""
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as handle:
            handle.write(text)
            temp_name = handle.name
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def request_admin_install(config_dir: Path | None = None) -> bool:
    """Ask for one-time elevation to install Include and grant file-only access."""
    folder = config_dir or find_config_dir()
    if folder is None or os.name != "nt":
        return False
    main_config = folder / "config.txt"
    generated = folder / APO_FILENAME

    def ps_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    script = f"""$ErrorActionPreference = 'Stop'
$configPath = {ps_quote(str(main_config))}
$generatedPath = {ps_quote(str(generated))}
$includeLine = {ps_quote(INCLUDE_LINE)}
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
if (-not (Test-Path -LiteralPath $generatedPath)) {{
    [System.IO.File]::WriteAllText($generatedPath, {ps_quote(DISABLED_CONFIG)}, [System.Text.UTF8Encoding]::new($false))
}}
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $generatedPath /grant ($account + ':(M)') | Out-Null
if ($LASTEXITCODE -ne 0) {{ throw 'Could not grant Modify permission to the Kozika filter file.' }}
"""
    script_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "KozikaAudioStudio"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / "install_equalizer_apo_include.ps1"
    script_path.write_text(script, encoding="utf-8")
    parameters = f'-NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
    try:
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int,
        ]
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        result = shell32.ShellExecuteW(
            None, "runas", "powershell.exe", parameters, None, 1
        )
        return result is not None and int(result) > 32
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def apply_system_audio(settings: Mapping[str, float],
                       config_dir: Path | None = None) -> Path:
    """Update the single user-writable filter file; install Include once."""
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
    # The file receives a one-time Modify ACL during setup. Write to the
    # existing file in place: replacing it atomically would require directory
    # permissions that Program Files intentionally does not grant.
    generated.write_bytes(build_apo_config(settings).encode("utf-8"))

    main_text = main_config.read_text(encoding="utf-8-sig")
    if INCLUDE_LINE.casefold() not in main_text.casefold():
        # This is a one-time protected-file change. The app catches
        # PermissionError and offers the UAC setup helper.
        lines = [
            line for line in main_text.splitlines()
            if not re.match(r'^\s*Include:\s*"?KozikaAudioStudio\.txt"?\s*$',
                            line, flags=re.IGNORECASE)
            and line.strip().casefold() != INCLUDE_LINE.casefold()
        ]
        lines.append(INCLUDE_LINE)
        backup = folder / "config.txt.kozika-backup"
        if not backup.exists():
            shutil.copy2(main_config, backup)
        _atomic_write(main_config, "\n".join(lines).rstrip() + "\n")
    return generated


def disable_system_audio(config_dir: Path | None = None) -> None:
    """Disable only Kozika filters without editing protected config.txt."""
    folder = config_dir or find_config_dir()
    if folder is None:
        return
    generated = folder / APO_FILENAME
    generated.write_bytes(DISABLED_CONFIG.encode("utf-8"))
