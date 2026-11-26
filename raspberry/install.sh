#!/bin/bash
# Instalacja launchera (menu) + demona LED na Raspberry Pi OS (Bookworm / Trixie).
# Uruchom jako zwykły użytkownik (NIE przez sudo):   bash install.sh
set -e

if [ "$EUID" -eq 0 ]; then
    echo "Uruchom bez sudo:  bash install.sh   (skrypt sam poprosi o sudo, gdy trzeba)"
    exit 1
fi

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/pi-launcher"
ME="$(id -un)"

echo "==> Pakiety"
sudo apt-get update
sudo apt-get install -y python3-pygame python3-spidev python3-evdev python3-vlc vlc mpv fonts-dejavu-core fonts-dejavu-extra fonts-dseg

echo "==> Cache wtyczek VLC (szybszy start filmu)"
VCG=$(ls /usr/lib/*/vlc/vlc-cache-gen /usr/lib/vlc/vlc-cache-gen 2>/dev/null | head -n1)
if [ -n "$VCG" ]; then sudo "$VCG" "$(dirname "$VCG")/plugins" || true; fi

echo "==> Pliki -> $DEST"
mkdir -p "$DEST" "$HOME/filmy"
cp "$SRC/launcher.py" "$SRC/themes.py" "$SRC/layouts.py" "$SRC/ledd.py" "$SRC/run.sh" "$DEST/"
[ -f "$SRC/../pc/LED.py" ] && cp "$SRC/../pc/LED.py" "$DEST/" || true   # LED.py przyda się też na samym RPi
chmod +x "$DEST/"*.py "$DEST/run.sh"

echo "==> SPI (dla taśmy WS2812 na GPIO10 / pin 19)"
sudo raspi-config nonint do_spi 0
sudo usermod -aG spi,gpio,video,input "$ME"

BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

# Większy bufor SPI (potrzebny przy > ~450 diodach)
if ! grep -q "spidev.bufsiz" "$BOOT/cmdline.txt"; then
    sudo sed -i '1 s/$/ spidev.bufsiz=65536/' "$BOOT/cmdline.txt"
fi
# Pi 4: stały zegar rdzenia -> stabilny zegar SPI (inaczej diody migają/losowe kolory)
if ! grep -q "^# ledd: core_freq" "$BOOT/config.txt"; then
    printf '\n# ledd: core_freq stały dla SPI WS2812\n[pi4]\ncore_freq_min=500\n[all]\n' | sudo tee -a "$BOOT/config.txt" >/dev/null
fi

echo "==> Usługa systemd: ledd (LEDy działają od startu, niezależnie od PC)"
sudo tee /etc/systemd/system/ledd.service >/dev/null <<EOF
[Unit]
Description=WS2812 LED daemon
After=network.target

[Service]
User=$ME
SupplementaryGroups=spi gpio
ExecStart=/usr/bin/python3 $DEST/ledd.py
Restart=always
RestartSec=2
Nice=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable ledd

echo "==> Autostart menu po zalogowaniu do pulpitu"
mkdir -p "$HOME/.config/autostart" "$HOME/.local/share/applications"
DESKTOP_ENTRY="[Desktop Entry]
Type=Application
Name=Pi Launcher
Comment=Menu: Dashboard / Film / LEDy
Exec=/bin/bash $DEST/run.sh
Icon=applications-multimedia
Terminal=false
Categories=AudioVideo;"
echo "$DESKTOP_ENTRY" > "$HOME/.config/autostart/pi-launcher.desktop"
echo "$DESKTOP_ENTRY" > "$HOME/.local/share/applications/pi-launcher.desktop"   # skrót w menu pulpitu

echo "==> Automatyczne logowanie do pulpitu"
sudo raspi-config nonint do_boot_behaviour B4

# Stary dashboard (uruchamiany wcześniej przez SSH) nie jest już potrzebny
pkill -f '[d]ashboard.py' 2>/dev/null || true

echo
echo "Gotowe. Wrzuć filmy do: $HOME/filmy"
echo "Zrób restart:  sudo reboot"
echo "Logi:  ~/.cache/pi-launcher.log   oraz   journalctl -u ledd -f"
