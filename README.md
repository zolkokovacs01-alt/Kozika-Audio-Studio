# Kozika Audio Studio

Magyar nyelvű, Windows 11-es asztali lejátszó 10 sávos hangszínszabályzóval,
állítható mélyhang- és magashang-kiemeléssel, sztereó térhatással és kimeneti
szintszabályozással. A hangfeldolgozás valós időben, a lejátszó hangjára működik;
nem telepít hangillesztőprogramot, és nem módosítja más alkalmazások hangját.

## Indítás Windows 11 rendszeren

1. Telepítse a 64 bites Python 3.11 vagy újabb verziót a python.org oldalról.
2. A projekt mappájában futtassa:

	```powershell
	py -m venv .venv
	.venv\Scripts\Activate.ps1
	python -m pip install -r requirements.txt
	python app.py
	```

3. Válasszon hangkimenetet, nyisson meg egy hangfájlt, majd indítsa el a lejátszást.

WAV, FLAC, OGG, AIFF és MP3 fájlokat támogat. A kimenet sztereó; többcsatornás
forrásból az első két csatornát használja. Az alkalmazás a teljes megnyitott
hangfájlt memóriába tölti, ezért nagy fájloknál számoljon ennek megfelelő memóriaigénnyel.

## Ellenőrzés

```powershell
python -m unittest -v test_audio_engine
```
