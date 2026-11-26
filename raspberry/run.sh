#!/bin/bash
# Uruchamia launcher i podnosi go ponownie, jeśli się wywróci.
# Normalne wyjście (przycisk PULPIT, wyłączanie) kończy pętlę.
cd "$(dirname "$0")" || exit 1
LOG="$HOME/.cache/pi-launcher.log"
mkdir -p "$(dirname "$LOG")"
for i in $(seq 1 20); do
    python3 launcher.py && exit 0
    echo "!!! launcher zakończył się błędem - restart za 2 s (próba $i)" >> "$LOG"
    sleep 2
done
