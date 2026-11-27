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

## Windows rendszerhang (Netflix, böngésző, filmek)

A teljes Windows-hang feldolgozásához a program az **Equalizer APO** külső,
Windows rendszerhang-feldolgozó komponensét használja. Ez nem VB-CABLE, és nem
a Kozika saját hangfájl-lejátszója: a Windows által az adott kimeneti eszközre
küldött hangot dolgozza fel.

1. Telepítsd az Equalizer APO-t a hivatalos SourceForge oldalról:
   https://sourceforge.net/projects/equalizerapo/files/
2. A telepítő Configurator ablakában jelöld be a Realtek hangszórót és azt a
   külső hangkimenetet is, amelyen hallgatni szoktál.
3. Fejezd be a telepítést, majd indítsd újra a Windows rendszert.
4. Indítsd el a Kozika Audio Studio-t, és kattints a
   **Windows teljes hangja** gombra.
5. Első bekapcsoláskor a Windows egyszer rendszergazdai jóváhagyást kér.
   Ez csak a Kozika saját szűrőfájljának engedélyezésére és a config.txt
   Include sorának beállítására szolgál. A jóváhagyás után a csúszkák
   rendszergazdai jogosultság nélkül, azonnal módosíthatók.
6. A Kozika 10 sávos EQ-, mély-, tisztaság-, magas- és hangerőbeállításai
   a felhasználói LocalAppData mappában lévő külön fájlba kerülnek,
   amelyet az APO automatikusan újratölt. Így a csúszkák állítása nem írja
   a védett Program Files mappát, és nem igényel újabb rendszergazdai jogot.
   A fájl biztonságosan, egy lépésben frissül. A térhatás csúszka jelenleg
   csak a Kozika saját fájllejátszójára vonatkozik.

Fontos: az Equalizer APO telepítése és eszközönkénti engedélyezése szükséges.
A Kozika nem telepít illesztőprogramot, és nem változtatja meg a Windows
alapértelmezett hangkimenetét. A saját fájllejátszó nagyobb Windows hangpuffert
használ a lejátszás közbeni hangkimaradások csökkentésére. Az egyszeri jóváhagyás csak a Kozika által
használt külön szűrőfájlra ad módosítási jogot; a teljes Equalizer APO
konfigurációs mappa nem válik írhatóvá. A Windows hangjavításainak
engedélyezve kell maradniuk az adott eszköz tulajdonságainál.

## Ellenőrzés

```powershell
python -m unittest -v test_audio_engine test_equalizer_apo
```
