#!/bin/zsh
cd "/Users/Jonah/Documents/antigravity/cool-pythagoras"
echo "=========================================================="
echo " 🫀 Polar H10 -> Unity 6.3 BLE-Bridge"
echo "=========================================================="
echo ""
.venv/bin/python polar-ble-bridge/polar_udp_bridge.py
read -k1 "?Drücke eine beliebige Taste zum Schließen..."
