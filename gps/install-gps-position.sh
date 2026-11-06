#!/bin/bash
# install-gps-position.sh - install the DigiPi GPS position updater
# Version 1.3  -  Scott Sheppard, KJ4ZZB
#
# Run on the DigiPi, from the folder holding the files:
#   sudo bash install-gps-position.sh
#
# Run it AFTER DigiPi's normal Initialize. From then on, every boot reads the
# GPS and updates the position everywhere DigiPi and WeeWX keep it.

set -e
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo:  sudo bash $0"
  exit 1
fi

mount -o remount,rw /

install -m 755 digipi-gps-position.py      /usr/local/bin/digipi-gps-position.py
install -m 644 digipi-gps-position.service /etc/systemd/system/digipi-gps-position.service

systemctl daemon-reload
systemctl enable digipi-gps-position.service
systemctl enable gpsd.service 2>/dev/null || true

# First line of the position history: where DigiPi thinks it is right now
/usr/bin/python3 /usr/local/bin/digipi-gps-position.py --record-install >/dev/null

echo
echo "Installed DigiPi GPS Position Updater $(/usr/bin/python3 /usr/local/bin/digipi-gps-position.py --version | awk '{print $2}')."
echo "gpsd is set to read:"
grep '^DEVICES' /etc/default/gpsd || echo "  (no DEVICES line in /etc/default/gpsd!)"
echo
echo "Make sure that is your GPS. A by-id name is safest, for example:"
ls /dev/serial/by-id/ 2>/dev/null | sed 's|^|  /dev/serial/by-id/|' || echo "  (no USB serial devices found)"
echo
if [ -f /etc/weewx/weewx.conf ] || [ -f /home/pi/weewx-data/weewx.conf ]; then
  echo "WeeWX found: its [Station] position will be kept up to date too."
else
  echo "WeeWX not installed: only DigiPi settings will be updated."
  echo "(If you install WeeWX later, it is picked up automatically at the next boot.)"
fi
echo
echo "Test now without changing anything:"
echo "  sudo /usr/local/bin/digipi-gps-position.py --dry-run --force"
echo
echo "Position history (one line per change):"
echo "  cat /home/pi/gps-position-history.txt"
echo
echo "After a reboot, see what it did with:"
echo "  journalctl -u digipi-gps-position -b"
