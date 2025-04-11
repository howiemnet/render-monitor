#!/usr/bin/env python3

# Monitor script. Run this on a machine on the network. It:
#
# - listens out for UDB messages fromt the nodes, and keeps
#   track of each node's current state
# - starts up a simple webserver, serving two things:
#    - a JSON file with the render nodes' current activity data
#    - a webpage, index.html, which displays it nicely.
#
#      
# The webserver port is coded to port 80 here, so the page
# can be accessed from the lan at http://10.0.1.50 - which 
# means this script needs to be run with sudo. The script can be
# run without sudo if you're happy to specfy a higher port, but that
# means you'll need to direct your browser specifically to is - eg
# http://10.0.1.50:8000
#



import socket
import threading
import time
import json
import os
from http.server import SimpleHTTPRequestHandler, HTTPServer

UDP_PORT = 43217
HTTP_PORT = 80
node_data = {}
data_lock = threading.Lock()  # 👈 protect shared state

# Serve from ./web directory
WEB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

class CustomHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/render_status.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with data_lock:
                json_bytes = json.dumps(list(node_data.values())).encode("utf-8")
            self.wfile.write(json_bytes)
        else:
            super().do_GET()

    def log_message(self, format, *args):
        return  # suppress default logging

def listen_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', UDP_PORT))
    print(f"🔊 Listening for UDP on port {UDP_PORT}...")

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode().strip()
            print(f"📡 {msg}")
            parts = msg.split('|')
            if len(parts) >= 2:
                name = parts[0].strip()
                fields = {k.strip(): v.strip() for k, v in (s.split(':') for s in parts[1:])}
                cpu = float(fields.get("CPU", "0").strip('%'))
                gpu = float(fields.get("GPU", "0").strip('%'))
                mem = int(fields.get("MEM", "0").strip('MB'))

                with data_lock:
                    node_data[name] = {
                        "name": name,
                        "cpu": cpu,
                        "gpu": gpu,
                        "mem": mem,
                        "lastSeen": int(time.time())
                    }

        except Exception as e:
            print(f"⚠️ Error: {e}")

def serve_http():
    os.chdir(WEB_ROOT)
    server = HTTPServer(('', HTTP_PORT), CustomHandler)
    print(f"🌍 Serving HTTP from {WEB_ROOT} on port {HTTP_PORT}...")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=listen_udp, daemon=True).start()
    serve_http()
