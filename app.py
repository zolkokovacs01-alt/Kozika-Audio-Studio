"""Kozika Audio Studio desktop player and audio enhancer."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from audio_engine import BANDS, DEFAULTS, PRESETS, AudioProcessor

try:
    import sounddevice as sd
    SOUNDDEVICE_ERROR = ""
except (ImportError, OSError) as error:
    sd = None
    SOUNDDEVICE_ERROR = str(error)


BG = "#101311"
PANEL = "#191e1b"
PANEL_LIGHT = "#222a25"
TEXT = "#f1f3ed"
MUTED = "#9ba79e"
ACCENT = "#b8ef54"
ACCENT_DARK = "#31451c"
LINE = "#303a33"


class KozikaAudioStudio:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Kozika Audio Studio")
        self.root.configure(bg=BG)
        self.root.minsize(1000, 850)
        self.root.geometry("1180x940")

        self.samples: np.ndarray | None = None
        self.source_rate = 0
        self.play_cursor = 0
        self.processor: AudioProcessor | None = None
        self.stream: sd.OutputStream | None = None
        self.playing = False
        self.track_title = tk.StringVar(value="Nincs betöltött hangfájl")
        self.status = tk.StringVar(value="Válasszon hangkimenetet, majd töltsön be egy zenét vagy filmet.")
        self.preset = tk.StringVar(value="Egyéni")
        self.device = tk.StringVar()
        self.device_names: dict[str, int] = {}
        self.setting_vars: dict[str, tk.DoubleVar] = {}
        self.slider_labels: dict[str, tk.StringVar] = {}
        self.eq_labels: dict[str, ttk.Label] = {}
        self._loading_preset = False
        self._end_of_track = threading.Event()

        self._style()
        self._build()
        self._refresh_devices()
        self.root.after(120, self._watch_playback)

    def _style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 27))
        style.configure("Section.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 14))
        style.configure("TButton", background=PANEL_LIGHT, foreground=TEXT, borderwidth=0,
                        padding=(15, 11), font=("Segoe UI Semibold", 10))
        style.map("TButton", background=[("active", "#303a33"), ("disabled", PANEL)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#17200c")
        style.map("Accent.TButton", background=[("active", "#cafa78")])
        style.configure("TCombobox", fieldbackground=PANEL_LIGHT, background=PANEL_LIGHT,
                        foreground=TEXT, arrowcolor=ACCENT, padding=9)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_LIGHT)],
                  foreground=[("readonly", TEXT)])
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL_LIGHT,
                        background=ACCENT, bordercolor=PANEL_LIGHT, lightcolor=ACCENT, darkcolor=ACCENT)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=(30, 22))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="KOZIKA  /  AUDIO STUDIO", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(header, text="Kozika Audio Studio", style="Title.TLabel").pack(anchor="w", pady=(4, 1))
        ttk.Label(header, text="Hangzásvezérlés külső hangszórókhoz", style="Muted.TLabel").pack(anchor="w")

        player = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        player.pack(fill="x", pady=(0, 18))
        player.columnconfigure(1, weight=1)
        ttk.Button(player, text="＋  Hangfájl megnyitása", style="Accent.TButton",
                   command=self._open_file).grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 18))
        ttk.Label(player, textvariable=self.track_title, style="Panel.TLabel",
                  font=("Segoe UI Semibold", 12)).grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.progress = ttk.Progressbar(player, mode="determinate", maximum=100, style="Horizontal.TProgressbar")
        self.progress.grid(row=1, column=1, sticky="ew", padx=(0, 18))
        controls = ttk.Frame(player, style="Panel.TFrame")
        controls.grid(row=0, column=2, rowspan=2, sticky="e")
        self.play_button = ttk.Button(controls, text="▶  Lejátszás", style="Accent.TButton", command=self._toggle_play)
        self.play_button.pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="■  Leállítás", command=self._stop).pack(side="left")

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(0, 18))
        device_box = ttk.Frame(options)
        device_box.pack(side="left", fill="x", expand=True, padx=(0, 14))
        ttk.Label(device_box, text="HANGKIMENET", style="Muted.TLabel").pack(anchor="w", pady=(0, 7))
        self.device_combo = ttk.Combobox(device_box, textvariable=self.device, state="readonly")
        self.device_combo.pack(fill="x")
        self.device_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_settings())
        preset_box = ttk.Frame(options)
        preset_box.pack(side="left", fill="x", expand=True)
        ttk.Label(preset_box, text="HANGPROFIL", style="Muted.TLabel").pack(anchor="w", pady=(0, 7))
        self.preset_combo = ttk.Combobox(preset_box, textvariable=self.preset,
                                         values=("Egyéni", *PRESETS.keys()), state="readonly")
        self.preset_combo.pack(fill="x")
        self.preset_combo.bind("<<ComboboxSelected>>", self._select_preset)

        eq_header = ttk.Frame(outer)
        eq_header.pack(fill="x", pady=(0, 8))
        ttk.Label(eq_header, text="10 sávos hangszínszabályzó", style="Section.TLabel").pack(side="left")
        ttk.Label(eq_header, text="Finomhangolás  ·  −12 – +12 dB", style="Muted.TLabel").pack(side="right")
        eq_panel = ttk.Frame(outer, style="Panel.TFrame", padding=(13, 14, 13, 10))
        eq_panel.pack(fill="x", pady=(0, 17))
        for column, frequency in enumerate(BANDS):
            eq_panel.columnconfigure(column, weight=1, uniform="eq")
            key = f"eq_{frequency}"
            variable = tk.DoubleVar(value=DEFAULTS[key])
            self.setting_vars[key] = variable
            value_label = ttk.Label(eq_panel, text="0 dB", style="PanelMuted.TLabel", width=6,
                                    anchor="center")
            value_label.grid(row=0, column=column, pady=(0, 3))
            self.eq_labels[key] = value_label
            slider = tk.Scale(eq_panel, variable=variable, from_=12, to=-12, resolution=0.5,
                              orient="vertical", showvalue=False, length=142, width=20,
                              sliderlength=20, bg=PANEL, fg=TEXT, troughcolor="#38433b",
                              activebackground=ACCENT, highlightthickness=0, bd=0,
                              command=lambda value, name=key: self._slider_changed(name, value))
            slider.grid(row=1, column=column, sticky="ns")
            ttk.Label(eq_panel, text=self._frequency_label(frequency), style="PanelMuted.TLabel",
                      anchor="center").grid(row=2, column=column, pady=(5, 0))

        controls_header = ttk.Frame(outer)
        controls_header.pack(fill="x", pady=(0, 8))
        ttk.Label(controls_header, text="Hangzásvezérlés", style="Section.TLabel").pack(side="left")
        ttk.Label(controls_header, text="A beállítások lejátszás közben is változtathatók", style="Muted.TLabel").pack(side="right")
        controls_panel = ttk.Frame(outer, style="Panel.TFrame", padding=(16, 14, 16, 15))
        controls_panel.pack(fill="x")
        for column in range(5):
            controls_panel.columnconfigure(column, weight=1, uniform="tone")
        control_specs = (
            ("bass", "Mélyhang", "Erőteljes, állítható basszus", 0, 100),
            ("clarity", "Tisztaság", "Beszéd és részletek kiemelése", 0, 100),
            ("treble", "Magas hangok", "Részletgazdagabb hangzás", 0, 100),
            ("spatial", "Térhatás", "Szélesebb sztereó tér", 0, 100),
            ("volume", "Kimeneti szint", "Biztonságos jelszint-szabályozás", 0, 150),
        )
        for column, (key, title, hint, minimum, maximum) in enumerate(control_specs):
            block = ttk.Frame(controls_panel, style="Panel.TFrame")
            block.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 8 if column < 4 else 0))
            variable = tk.DoubleVar(value=DEFAULTS[key])
            self.setting_vars[key] = variable
            value_label = tk.StringVar(value=self._format_value(key, DEFAULTS[key]))
            self.slider_labels[key] = value_label
            line = ttk.Frame(block, style="Panel.TFrame")
            line.pack(fill="x")
            ttk.Label(line, text=title, style="Panel.TLabel",
                      font=("Segoe UI Semibold", 10)).pack(side="left")
            ttk.Label(line, textvariable=value_label, style="Panel.TLabel",
                      foreground=ACCENT).pack(side="right")
            ttk.Label(block, text=hint, style="PanelMuted.TLabel", wraplength=185).pack(anchor="w", pady=(4, 7))
            tk.Scale(block, variable=variable, from_=minimum, to=maximum, resolution=1,
                     orient="horizontal", showvalue=False, length=145, width=18,
                     sliderlength=20, bg=PANEL, fg=TEXT, troughcolor="#38433b",
                     activebackground=ACCENT, highlightthickness=0, bd=0,
                     command=lambda value, name=key: self._slider_changed(name, value)).pack(fill="x")

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(14, 0))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=1070).pack(anchor="w")

    @staticmethod
    def _frequency_label(frequency: int) -> str:
        return f"{frequency // 1000} kHz" if frequency >= 1000 else f"{frequency} Hz"

    @staticmethod
    def _format_value(key: str, value: float) -> str:
        return f"{value:.0f}%" if key != "volume" else f"{value:.0f}%"

    def _refresh_devices(self) -> None:
        if sd is None:
            self.status.set(f"A hangkimenet nem érhető el ezen a rendszeren: {SOUNDDEVICE_ERROR}")
            return
        try:
            devices = sd.query_devices()
            self.device_names = {
                f"{item['name']}  ·  {index}": index
                for index, item in enumerate(devices) if item["max_output_channels"] >= 2
            }
            names = list(self.device_names)
            self.device_combo.configure(values=names)
            default_output = sd.default.device[1]
            default_name = next((name for name, index in self.device_names.items() if index == default_output), "")
            if names:
                self.device.set(default_name or names[0])
                self.status.set("Hangkimenet kész. A lejátszóban kiválasztott hangfájlon működik a hangfeldolgozás.")
            else:
                self.status.set("Nem található sztereó hangkimenet. Ellenőrizze a Windows hangbeállításait.")
        except Exception as error:
            self.status.set(f"A hangkimenetek nem érhetők el: {error}")

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Hangfájl kiválasztása",
            filetypes=(("Hangfájlok", "*.wav *.flac *.ogg *.aiff *.aif *.mp3"), ("Minden fájl", "*.*")),
        )
        if not path:
            return
        try:
            audio, rate = sf.read(path, dtype="float32", always_2d=True)
            if audio.shape[1] == 1:
                audio = np.repeat(audio, 2, axis=1)
            elif audio.shape[1] > 2:
                audio = audio[:, :2]
            audio = np.ascontiguousarray(audio)
            was_playing = self.playing
            if was_playing:
                self._stop()
            self.samples = audio
            self.source_rate = int(rate)
            self.play_cursor = 0
            self.track_title.set(Path(path).name)
            self.progress.configure(value=0)
            self.status.set(f"Betöltve: {len(audio) / rate:.0f} másodperc · {rate} Hz · sztereó feldolgozás.")
            if was_playing:
                self._toggle_play()
        except Exception as error:
            messagebox.showerror("Nem sikerült megnyitni", f"A hangfájl nem olvasható:\n{error}")

    def _toggle_play(self) -> None:
        if self.playing:
            self._pause()
            return
        if sd is None:
            messagebox.showerror("A hangkimenet nem érhető el", SOUNDDEVICE_ERROR)
            return
        if self.samples is None:
            self._open_file()
            if self.samples is None:
                return
        if not self.device.get() or self.device.get() not in self.device_names:
            messagebox.showwarning("Nincs hangkimenet", "Válasszon elérhető sztereó hangkimenetet.")
            return
        try:
            device_index = self.device_names[self.device.get()]
            device_info = sd.query_devices(device_index)
            rate = int(device_info["default_samplerate"])
            if rate != self.source_rate:
                from math import gcd
                divisor = gcd(rate, self.source_rate)
                audio = resample_poly(self.samples, rate // divisor, self.source_rate // divisor, axis=0).astype(np.float32)
            else:
                audio = self.samples
            if self.play_cursor >= len(audio):
                self.play_cursor = 0
            self._playback_samples = audio
            self.processor = AudioProcessor(rate)
            self._apply_settings()
            self._end_of_track.clear()
            self.stream = sd.OutputStream(device=device_index, samplerate=rate, channels=2,
                                          dtype="float32", blocksize=1024, callback=self._audio_callback)
            self.stream.start()
            self.playing = True
            self.play_button.configure(text="Ⅱ  Szünet")
            self.status.set("Lejátszás és valós idejű hangfeldolgozás aktív.")
        except Exception as error:
            self.playing = False
            self.stream = None
            messagebox.showerror("Nem sikerült elindítani", f"Ellenőrizze a hangkimenetet és annak beállításait.\n\n{error}")

    def _audio_callback(self, output: np.ndarray, frames: int, _time, _status) -> None:
        audio = self._playback_samples
        end = min(self.play_cursor + frames, len(audio))
        count = end - self.play_cursor
        output.fill(0)
        if count:
            output[:count] = self.processor.process(audio[self.play_cursor:end])
            self.play_cursor = end
        if count < frames:
            self._end_of_track.set()
            raise sd.CallbackStop

    def _pause(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.playing = False
        self.play_button.configure(text="▶  Folytatás")
        self.status.set("Lejátszás szüneteltetve. A hangbeállítások módosíthatók.")

    def _stop(self) -> None:
        self._pause()
        self.play_cursor = 0
        self.progress.configure(value=0)
        self.play_button.configure(text="▶  Lejátszás")
        self._end_of_track.clear()

    def _watch_playback(self) -> None:
        if self.samples is not None and self.playing:
            self.progress.configure(value=100 * self.play_cursor / max(1, len(self._playback_samples)))
        if self._end_of_track.is_set():
            self._stop()
            self.status.set("A lejátszás véget ért.")
        self.root.after(120, self._watch_playback)

    def _slider_changed(self, key: str, value: str) -> None:
        number = float(value)
        if key in self.slider_labels:
            self.slider_labels[key].set(self._format_value(key, number))
        elif key.startswith("eq_"):
            self.eq_labels[key].configure(text=f"{number:+.1f} dB" if number else "0 dB")
        if not self._loading_preset:
            self.preset.set("Egyéni")
        self._apply_settings()

    def _apply_settings(self) -> None:
        if self.processor:
            self.processor.set_settings({key: variable.get() for key, variable in self.setting_vars.items()})

    def _select_preset(self, _event=None) -> None:
        values = PRESETS.get(self.preset.get())
        if values is None:
            return
        self._loading_preset = True
        for frequency, gain in zip(BANDS, values["eq"]):
            self.setting_vars[f"eq_{frequency}"].set(gain)
        for key in ("bass", "clarity", "treble", "spatial", "volume"):
            self.setting_vars[key].set(values[key])
            self.slider_labels[key].set(self._format_value(key, values[key]))
        for frequency, gain in zip(BANDS, values["eq"]):
            self.eq_labels[f"eq_{frequency}"].configure(text=f"{gain:+.1f} dB" if gain else "0 dB")
        self._loading_preset = False
        self._apply_settings()
        self.status.set(f"A(z) „{self.preset.get()}” hangprofil aktív.")

    def close(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = KozikaAudioStudio(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()