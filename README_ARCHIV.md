# Archivstand wieder aufnehmen

Stand: 16.10.2026. Dieser Ordner dient als OneDrive-Quellarchiv.

1. Diesen Projektordner samt benötigten Daten nach `%USERPROFILE%\Dev\<Projektname>` kopieren.
2. Vorhandene Git-Historie bei Bedarf weiterverwenden. Ohne Historie in der Dev-Kopie `git init` ausführen, `.gitignore` für Umgebungen/Builds ergänzen, `git status` prüfen und die ausgewählten Quellen als „Version 0“ committen.
3. Abhängigkeiten erst in Dev installieren. Archiv und aktive Arbeitskopie getrennt halten.

Vorhandene Projektanleitung: [OpenSpotter-JetValve/GETTING_STARTED.md](<OpenSpotter-JetValve/GETTING_STARTED.md>), [OpenSpotter-JetValve/README.md](<OpenSpotter-JetValve/README.md>), [OpenSpotter-JetValve/arduino_valvecontrol/gui/README.md](<OpenSpotter-JetValve/arduino_valvecontrol/gui/README.md>), [OpenSpotter-JetValve/docs/klipper_configs/README.md](<OpenSpotter-JetValve/docs/klipper_configs/README.md>), [OpenSpotter-Syringe/CAD/README.md](<OpenSpotter-Syringe/CAD/README.md>), [OpenSpotter-Syringe/Docs/README.md](<OpenSpotter-Syringe/Docs/README.md>), [OpenSpotter-Syringe/GETTING_STARTED.md](<OpenSpotter-Syringe/GETTING_STARTED.md>), [OpenSpotter-Syringe/README.md](<OpenSpotter-Syringe/README.md>).

Erfasste Python-Version: 3.13.13.
Der zusätzliche [Paketstand](requirements-environment-2026-10-16.txt) stammt aus installierten Paketmetadaten. Er enthält auch indirekte/Entwicklungsabhängigkeiten und ersetzt vorhandene Projektdefinitionen nicht. Auskommentierte lokale/VCS-Pakete benötigen ihre ursprüngliche Quelle.

Es gibt hier keine primäre `requirements.txt`. Die nachstehenden Projektdefinitionen bzw. Unterprojekte verwenden. Der Paketstand kann bei Bedarf mit `python -m pip install -r requirements-environment-2026-10-16.txt` rekonstruiert werden; seine Vollständigkeit und Plattformverträglichkeit sind nicht getestet.

Vorhandene Abhängigkeits-/Builddefinitionen:

- [OpenSpotter-JetValve/arduino_valvecontrol/gui/requirements.txt](<OpenSpotter-JetValve/arduino_valvecontrol/gui/requirements.txt>)
- [OpenSpotter-JetValve/requirements.txt](<OpenSpotter-JetValve/requirements.txt>)
- [OpenSpotter-Syringe/Spotter-Control_v3/pyproject.toml](<OpenSpotter-Syringe/Spotter-Control_v3/pyproject.toml>)
- [OpenSpotter-Syringe/Spotter-Control_v3/requirements.txt](<OpenSpotter-Syringe/Spotter-Control_v3/requirements.txt>)
- [requirements-environment-2026-10-16.txt](<requirements-environment-2026-10-16.txt>)

Start: den Einstiegspunkt in der vorhandenen Projektanleitung bzw. das gewünschte Skript/Unterprojekt wählen; ein einheitlicher Startbefehl wurde nicht überprüft.

Installation, Programmstart und Hardwarefunktionen wurden bei der Archivbereinigung nicht getestet. Quelldaten, CAD-Dateien und bestehende Git-Historien bleiben im Archiv.
