"""
FILM.py (PC) - OPCJONALNY pilot: uruchamia film na Raspberry Pi z komputera.

Film działa też bez PC - wystarczy wybrać FILM w menu na ekranie RPi.
Ten skrypt tylko wysyła komendę do launchera (UDP, bez SSH).
Zamknięcie okna (X) lub Ctrl+C zatrzymuje film i wraca RPi do menu.
"""
import ctypes
import json
import socket
import threading
import time

RPI_IP = "192.168.50.2"
RPI_PORT = 5005
FILE = ""                 # nazwa pliku w ~/filmy na RPi, np. "film.mp4"; puste = lista / jedyny film
STOP_ON_EXIT = True       # False = film gra dalej po zamknięciu tego okna

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
cleanup_lock = threading.Lock()
cleanup_done = False


def send_cmd(obj, repeat=3):
    data = json.dumps(obj).encode("utf-8")
    for _ in range(repeat):
        try:
            sock.sendto(data, (RPI_IP, RPI_PORT))
        except OSError:
            pass
        time.sleep(0.02)


def cleanup():
    global cleanup_done
    with cleanup_lock:
        if cleanup_done:
            return
        cleanup_done = True
    if STOP_ON_EXIT:
        print("\nZatrzymywanie filmu na Raspberry Pi...")
        send_cmd({"cmd": "stop", "mode": "film"})
    sock.close()


HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)


def _win_ctrl_handler(ctrl_type):
    if ctrl_type in (2, 5, 6):  # zamknięcie okna / wylogowanie / shutdown
        cleanup()
    return False


_console_handler = HANDLER_ROUTINE(_win_ctrl_handler)
ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler, True)


def main():
    cmd = {"cmd": "mode", "mode": "film"}
    if FILE:
        cmd["file"] = FILE
    print(f"Uruchamianie filmu na {RPI_IP} ({FILE or 'wybór na ekranie RPi'})...")
    print("Naciśnij Ctrl+C lub zamknij to okno (X), aby wyłączyć film.")
    try:
        send_cmd(cmd)
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
