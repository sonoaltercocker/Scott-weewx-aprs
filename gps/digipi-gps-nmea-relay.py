#!/usr/bin/env python3
"""
digipi-gps-nmea-relay.py  -  GPS data for Winlink Express on the LAN

Version 1.6  -  part of the DigiPi GPS Position Updater, Scott Sheppard, KJ4ZZB
Based on the GPSD-to-NMEA relay by Scott Curie, NS7C.

Winlink Express (and other programs) can take their position from a GPS over
TCP, but they expect raw NMEA sentences ($GPRMC, $GPGGA ...).  gpsd speaks its
own protocol, so this relay asks gpsd on this Pi for NMEA and passes on only
the lines that start with '$', to every computer that connects to port 2948.

gpsd itself stays reachable only from the Pi; only port 2948 is open to the
network.  Anyone on that network can read the station's position from it.

Turned on and off with:
  sudo digipi-gps-position.py --enable lan-nmea
  sudo digipi-gps-position.py --disable lan-nmea
"""

import socket
import socketserver

GPSD_HOST, GPSD_PORT = "127.0.0.1", 2947
LISTEN_HOST, LISTEN_PORT = "0.0.0.0", 2948


class NMEAHandler(socketserver.BaseRequestHandler):
    """One gpsd connection per client; only NMEA sentences are passed on."""

    def handle(self):
        gps = None
        try:
            gps = socket.create_connection((GPSD_HOST, GPSD_PORT), timeout=5)
            gps.settimeout(None)
            gps.sendall(b'?WATCH={"enable":true,"json":false,"nmea":true};\n')
            for raw in gps.makefile("rb"):
                line = raw.strip()
                if line.startswith(b"$"):
                    self.request.sendall(line + b"\r\n")
        except OSError as exc:          # client went away, or gpsd not running
            print(f"Client {self.client_address[0]}: {exc}", flush=True)
        finally:
            if gps:
                gps.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server((LISTEN_HOST, LISTEN_PORT), NMEAHandler) as server:
        print(f"NMEA relay listening on port {LISTEN_PORT}", flush=True)
        server.serve_forever()
