#!/bin/bash
# install-gps-position.sh - install or upgrade the DigiPi GPS Position Updater
# Version 1.6  -  Scott Sheppard, KJ4ZZB
# RMS start hook and LAN NMEA relay based on work by Scott Curie, NS7C
#
# Run on the DigiPi, from the folder holding the files:
#   sudo bash install-gps-position.sh
#
# Run it AFTER DigiPi's normal Initialize. From then on, every boot reads the
# GPS and updates the position everywhere DigiPi and WeeWX keep it, and the
# position is updated again whenever the station settles at a new place.
#
# Upgrading: run the new installer the same way. Your settings and the
# optional features you turned on are kept.

set -e
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo:  sudo bash $0"
  exit 1
fi

for f in digipi-gps-position.py digipi-gps-position.service \
         digipi-gps-nmea-relay.py digipi-gps-nmea-relay.service; do
  [ -f "$f" ] || { echo "Missing $f - run this from the unzipped digipi-gps-position folder."; exit 1; }
done

mount -o remount,rw /

install -m 755 digipi-gps-position.py         /usr/local/bin/digipi-gps-position.py
install -m 755 digipi-gps-nmea-relay.py       /usr/local/bin/digipi-gps-nmea-relay.py
install -m 644 digipi-gps-position.service    /etc/systemd/system/digipi-gps-position.service
install -m 644 digipi-gps-nmea-relay.service  /etc/systemd/system/digipi-gps-nmea-relay.service

# Update the position each time the Winlink RMS gateway mode starts, so the
# gateway always registers with the current grid square. A drop-in adds a step
# to DigiPi's winlinkrms.service without editing DigiPi's own file.
# "-" = RMS starts even if this step fails; "+" = runs as root.
mkdir -p /etc/systemd/system/winlinkrms.service.d
cat > /etc/systemd/system/winlinkrms.service.d/gps-position.conf <<'DROPIN'
# Added by install-gps-position.sh (DigiPi GPS Position Updater)
[Unit]
After=gpsd.service gpsd.socket

[Service]
ExecStartPre=-+/usr/bin/python3 /usr/local/bin/digipi-gps-position.py --rms-start
DROPIN

systemctl daemon-reload
systemctl enable digipi-gps-position.service
systemctl enable gpsd.service 2>/dev/null || true

# The LAN NMEA feed is installed but stays off unless it was turned on before
SETTINGS=/etc/digipi-gps-position.conf
if [ -f "$SETTINGS" ] && grep -q '^lan-nmea *= *on' "$SETTINGS"; then
  systemctl enable digipi-gps-nmea-relay.service
  systemctl restart digipi-gps-nmea-relay.service || true
else
  systemctl disable digipi-gps-nmea-relay.service 2>/dev/null || true
fi

# An upgrade: restart a running watcher so it uses the new program
if systemctl is-active --quiet digipi-gps-position.service; then
  systemctl restart digipi-gps-position.service
fi

# Point gpsd at the GPS by its permanent /dev/serial/by-id name, so it can't be
# swapped with a radio cable (both can show up as ttyACM0/ttyACM1). Only done
# when gpsd confirms which device is the GPS; otherwise nothing is changed.
echo
/usr/bin/python3 /usr/local/bin/digipi-gps-position.py --set-gps-device || true

# Position history: where DigiPi thinks it is right now
/usr/bin/python3 /usr/local/bin/digipi-gps-position.py --record-install >/dev/null

echo
echo "Installed DigiPi GPS Position Updater $(/usr/bin/python3 /usr/local/bin/digipi-gps-position.py --version | awk '{print $2}')."
echo "gpsd is set to read:"
grep '^DEVICES' /etc/default/gpsd || echo "  (no DEVICES line in /etc/default/gpsd!)"
echo
if [ -f /etc/weewx/weewx.conf ] || [ -f /home/pi/weewx-data/weewx.conf ]; then
  echo "WeeWX found: its [Station] position will be kept up to date too."
else
  echo "WeeWX not installed: only DigiPi settings will be updated."
  echo "(If you install WeeWX later, it is picked up automatically at the next boot.)"
fi
echo
if systemctl is-active --quiet digipi-gps-position.service; then
  echo "The position watcher is running."
else
  echo "The position watcher starts at the next boot. To start it now:"
  echo "  sudo systemctl start digipi-gps-position"
fi
echo
echo "Optional features and settings:"
echo "  sudo digipi-gps-position.py --status"
echo
echo "Test now without changing anything:"
echo "  sudo digipi-gps-position.py --dry-run --force"
echo
echo "Position history (one line per change):"
echo "  cat /home/pi/gps-position-history.txt"
echo
echo "After a reboot, see what it did with:"
echo "  journalctl -u digipi-gps-position -b"
