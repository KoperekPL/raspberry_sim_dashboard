# raspberry_sim_dashboard

Raspberry Pi z ekranem jako deska rozdzielcza do symulatora HydroSim, odtwarzacz filmów i sterownik taśmy LED WS2812.

Po włączeniu RPi pokazuje się menu: **DASHBOARD / FILM / LEDY**. Filmy i LEDy działają bez komputera. PC jest potrzebny tylko do dashboardu, bo stamtąd przychodzi telemetria.

![menu](docs/menu.png)

## Co gdzie działa

| | Raspberry Pi (`raspberry/`) | PC z Windows (`pc/`) |
|---|---|---|
| Menu startowe | `launcher.py` (autostart po zalogowaniu) | – |
| Dashboard | rysowany w `launcher.py`, dane UDP :5005 | `DASHBOARD.py` czyta HydroSim i wysyła telemetrię |
| Film | `launcher.py` + `mpv`, pliki z `~/filmy` | `FILM.py` – opcjonalny pilot |
| LEDy | `ledd.py` – usługa systemd, działa od startu | `LED.py` – opcjonalne sterowanie z konsoli |

```
 PC (Windows)                         Raspberry Pi
 ┌──────────────┐  UDP 5005   ┌───────────────────────┐  UDP 5006  ┌─────────┐
 │ DASHBOARD.py ├────────────►│ launcher.py (pygame)  ├───────────►│ ledd.py ├─► SPI ─► WS2812
 │ FILM.py      │ telemetria  │ menu/dashboard/film   │ ustawienia │ (systemd)│
 └──────────────┘ + komendy   └───────────┬───────────┘ + RPM      └─────────┘
 ┌──────────────┐  UDP 5006                │ uruchamia                  ▲
 │ LED.py       ├──────────────────────────┼────────────────────────────┘
 └──────────────┘                          ▼
                                          mpv (~/filmy)
```

SSH nie jest już potrzebne. PC przełącza RPi w tryb dashboardu komendą UDP, a po zamknięciu `DASHBOARD.py` RPi wraca do menu.

## Instalacja na Raspberry Pi

```bash
git clone https://github.com/KoperekPL/raspberry_sim_dashboard.git
cd raspberry_sim_dashboard/raspberry
bash install.sh        # bez sudo
sudo reboot
```

Skrypt instalacyjny:
- instaluje `python3-pygame`, `python3-spidev` i `mpv`,
- włącza SPI i ustawia stały zegar rdzenia na Pi 4 (bez tego taśma LED migałaby),
- tworzy usługę `ledd` i dodaje menu do autostartu pulpitu,
- włącza automatyczne logowanie do pulpitu.

Filmy wrzucasz do `~/filmy` (`.mp4 .mkv .mov .avi .webm .m4v`). Jeśli jest tylko jeden film, odpali się od razu. Przy kilku pokaże się lista. Film zamykasz podwójnym dotknięciem albo klawiszem ESC.

Konfiguracja jest na górze plików:
- `launcher.py`: `FILM_LOOP`, `FILM_MUTE`, `AUTO_DASHBOARD` (sam przechodzi do dashboardu, gdy przyjdą dane z PC)
- `ledd.py`: `NUM_LEDS`, `COLOR_ORDER`, `MAX_BRIGHTNESS`

Po zmianie konfiguracji skopiuj pliki do `~/pi-launcher/` (albo uruchom `install.sh` jeszcze raz) i wykonaj `sudo systemctl restart ledd`.

## Podłączenie taśmy WS2812

| RPi | Taśma |
|---|---|
| GPIO10 / MOSI (pin 19) → konwerter 3.3→5 V (np. 74AHCT125) → rezystor 330 Ω | DIN |
| GND (np. pin 20) | GND (wspólna masa z zasilaczem!) |
| – | +5 V z **osobnego** zasilacza (≈60 mA na diodę przy pełnej bieli) |

Przy taśmie warto dać kondensator 1000 µF między +5 V a GND. `MAX_BRIGHTNESS` w `ledd.py` ogranicza maksymalny prąd.

Działa na Pi 3, 4 i 5. Używa SPI, więc nie potrzebuje roota i nie koliduje z dźwiękiem, inaczej niż biblioteka `rpi_ws281x`, która na Pi 5 nie działa.

## Na PC

- `DASHBOARD.py`: tak jak wcześniej (potrzebny `hydrosim_sdk`). Przy starcie przełącza RPi na dashboard, przy zamknięciu wraca do menu.
- `FILM.py`: opcjonalny. Odpala film na RPi z komputera (`FILE = "nazwa.mp4"` lub puste).
- `LED.py`: np. `python LED.py rainbow`, `python LED.py static --color ff0000 --brightness 0.3`, `python LED.py status`.

W każdym skrypcie ustaw `RPI_IP`. Zapora Windows musi przepuszczać wychodzące UDP (zwykle przepuszcza).

## Tryby LED

`WYŁĄCZ`, `STAŁY`, `ODDECH`, `TĘCZA`, `CYKL KOLORÓW`, `KOMETA`, `ISKRY`, `OGIEŃ`, `POLICJA` oraz **`OBROTY (RPM)`**. Ten ostatni to shift-light: w trybie dashboardu pasek rośnie z obrotami (zielony → żółty → czerwony) i miga na niebiesko przy redline. Bez danych z PC delikatnie świeci wybranym kolorem.

Ustawienia zapisują się w `~/.config/ledd/state.json` i są przywracane po restarcie.

## Protokół (JSON po UDP)

Launcher, port **5005**:
```json
{"rpm": 6500, "max_rpm": 9000, "speed": 87, "unit": "MPH", "current_lap": 42.3, "last_lap": 61.2, "best_lap": 60.9}
{"cmd": "mode", "mode": "dashboard"}            // też "film" (+ opcjonalnie "file") i "menu"
{"cmd": "stop", "mode": "dashboard"}            // wraca do menu tylko, jeśli ten tryb jest aktywny
```
ledd, port **5006**:
```json
{"cmd": "set", "mode": "comet", "color": [0,120,255], "brightness": 0.5, "speed": 1.0}
{"cmd": "rpm", "rpm": 7200, "redline": 9000}
{"cmd": "get"}                                  // odpowiedź: {"state": {...}}
```

## Diagnostyka

- Logi menu: `~/.cache/pi-launcher.log`
- Logi LED: `journalctl -u ledd -f`
- Test menu w oknie na zwykłym komputerze: `LAUNCHER_WINDOW=800x480 python3 raspberry/launcher.py`
- Kolory zamienione (np. czerwony świeci na zielono): zmień `COLOR_ORDER` w `ledd.py`.
- Diody migają losowo: sprawdź konwerter poziomów, wspólną masę i to, czy wykonano reboot po instalacji (wymaga tego zmiana zegara SPI).
- Wyjście z menu na pulpit: przycisk **PULPIT**. Menu można potem uruchomić ponownie ze skrótu „Pi Launcher” w menu systemu.
