"""
LED.py - sterowanie taśmą WS2812 na Raspberry Pi z linii komend (PC lub samo RPi).

Przykłady:
  python LED.py rainbow
  python LED.py static --color ff0000 --brightness 0.4
  python LED.py comet --color 0,120,255 --speed 2
  python LED.py off
  python LED.py --brightness 0.2            # tylko zmiana jasności
  python LED.py status                      # pokaż aktualne ustawienia
  python LED.py rainbow --ip 127.0.0.1      # uruchomione na samym RPi

Tryby: off, static, breathe, rainbow, cycle, comet, sparkle, fire, police, shift
"""
import argparse
import json
import socket

RPI_IP = "192.168.50.2"
LED_PORT = 5006
MODES = ("off", "static", "breathe", "rainbow", "cycle",
         "comet", "sparkle", "fire", "police", "shift")


def parse_color(text):
    text = text.strip().lstrip("#")
    if "," in text:
        parts = [int(p) for p in text.split(",")]
    elif len(text) == 6:
        parts = [int(text[i:i + 2], 16) for i in (0, 2, 4)]
    else:
        raise argparse.ArgumentTypeError("kolor: ff8800 albo 255,136,0")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("kolor musi mieć 3 składowe")
    return [max(0, min(255, p)) for p in parts]


def main():
    ap = argparse.ArgumentParser(description="Sterowanie LED na Raspberry Pi")
    ap.add_argument("mode", nargs="?", choices=MODES + ("status",))
    ap.add_argument("--color", type=parse_color)
    ap.add_argument("--brightness", type=float, help="0.0 - 1.0")
    ap.add_argument("--speed", type=float, help="0.1 - 5.0")
    ap.add_argument("--ip", default=RPI_IP)
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)

    if args.mode == "status":
        msg = {"cmd": "get"}
    else:
        msg = {"cmd": "set"}
        if args.mode:
            msg["mode"] = args.mode
        if args.color is not None:
            msg["color"] = args.color
        if args.brightness is not None:
            msg["brightness"] = args.brightness
        if args.speed is not None:
            msg["speed"] = args.speed
        if len(msg) == 1:
            ap.error("podaj tryb albo --color / --brightness / --speed")

    sock.sendto(json.dumps(msg).encode("utf-8"), (args.ip, LED_PORT))
    try:
        data, _ = sock.recvfrom(2048)
        print("Stan LED:", json.loads(data.decode("utf-8")).get("state"))
    except socket.timeout:
        print(f"Brak odpowiedzi z {args.ip}:{LED_PORT} - czy usługa ledd działa na RPi?")


if __name__ == "__main__":
    main()
