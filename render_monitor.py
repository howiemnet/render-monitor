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



#!/usr/bin/env python3

import socket
import json
import time
import threading
import shutil
import subprocess
import os
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pysnmp.hlapi import *

# Settings
UDP_PORT = 43217
HTTP_PORT = 80
SERVE_DIR = "/mnt/raid001/render_monitor_web/web"
JSON_OUTPUT_FILE = os.path.join(SERVE_DIR, "render_status2.json")
HISTORY_LENGTH = 120

MOUNT_POINTS = ["/mnt/lib", "/mnt/raid002", "/mnt/renders", "/mnt/renders_b"]
INTERNAL_HOSTS = {"RENDER_NAS": "10.0.1.99", "RENDER003": "render003.local", "RENDER005": "render005.local"}
EXTERNAL_HOSTS = {"G_DNS": "8.8.8.8", "DROPBOX": "dropbox.com", "HOWIEM.NET": "howiem.net",}

# SNMP WAN interface index (as per your ifIn/ifOut commands)
WAN_IF_INDEX = 2

# traffic_info holds the latest in/out MB/s plus history lists
traffic_info = {"in": 0.0, "out": 0.0, "history": {"in": [], "out": []}}
prev_in_octets = None
prev_out_octets = None

# Shared data
node_stats = {}
disk_info = {}
network_info = {}
lock = threading.Lock()

# up near your globals
MAX32 = 2**32

def delta_counter(prev, curr, maxval=MAX32):
    """Compute correct octet delta even if counter has rolled."""
    d = curr - prev
    if d < 0:
        d += maxval
    return d
    
def get_snmp_counter(oid):
    # oid e.g. f"IF-MIB::ifInOctets.{WAN_IF_INDEX}"
    raw = subprocess.check_output(
        ["snmpwalk", "-v", "2c", "-c", "public", "10.0.1.1", oid],
        universal_newlines=True
    )
    # output: IF-MIB::ifInOctets.2 = Counter32: 12345678
    return int(raw.strip().split()[-1])

def get_in():
    eI,eS,eII,varBinds = next(getCmd(
        SnmpEngine(),
        CommunityData('public', mpModel=1),  # SNMPv2c
        UdpTransportTarget(('10.0.1.1', 161)),
        ContextData(),
        ObjectType(ObjectIdentity('IF-MIB', 'ifInOctets', 2))
    ))
    return(int(varBinds[0][1]))

def get_out():
    eI,eS,eII,varBinds = next(getCmd(
        SnmpEngine(),
        CommunityData('public', mpModel=1),  # SNMPv2c
        UdpTransportTarget(('10.0.1.1', 161)),
        ContextData(),
        ObjectType(ObjectIdentity('IF-MIB', 'ifOutOctets', 2))
    ))
    return(int(varBinds[0][1]))




def get_disk_usage():
    disks = {}
    for mount in MOUNT_POINTS:
        try:
            usage = shutil.disk_usage(mount)
            total_gb = round(usage.total / (1024**3), 1)
            used_gb = round((usage.total - usage.free) / (1024**3), 1)
            used_percent = round(used_gb / total_gb * 100, 1)
            disks[mount] = {
                "totalGb": total_gb,
                "usedGb": used_gb,
                "usedPercent": used_percent
            }
        except FileNotFoundError:
            disks[mount] = {
                "totalGb": None,
                "usedGb": None,
                "usedPercent": None
            }
    return disks

def ping_host(host):
    import platform
    try:
        cmd = ["ping", "-c", "1", host] if platform.system() != "Windows" else ["ping", "-n", "1", host]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if result.returncode == 0 and "time=" in result.stdout:
            latency_line = next((line for line in result.stdout.splitlines() if "time=" in line), "")
            latency_str = latency_line.split("time=")[1].split(" ")[0]
            return {"address": host, "reachable": True, "latencyMs": round(float(latency_str), 2)}
        else:
            return {"address": host, "reachable": False, "latencyMs": None}
    except Exception as e:
        return {"address": host, "reachable": False, "latencyMs": None}

def background_updater():
    global disk_info, network_info
    while True:
        disks = get_disk_usage()
        network = {
            "internal": {name: ping_host(addr) for name, addr in INTERNAL_HOSTS.items()},
            "external": {name: ping_host(addr) for name, addr in EXTERNAL_HOSTS.items()}
        }
        with lock:
            disk_info = disks
            network_info = network
        time.sleep(15)

import time

def monitor_snmp():
    global prev_in_octets, prev_out_octets, traffic_info

    try:
        prev_in_octets  = get_in()
        prev_out_octets = get_out()
    except Exception as e:
        print("Failed to bootstrap SNMP counters:", e)
        prev_in_octets = prev_out_octets = 0
    last_time = time.monotonic()
    time.sleep(1)

    while True:
        try:
            raw_in  = get_in()
            raw_out = get_out()

            # compute deltas accounting for wrap
            diff_in  = delta_counter(prev_in_octets,  raw_in)
            diff_out = delta_counter(prev_out_octets, raw_out)

            now     = time.monotonic()
            elapsed = now - last_time
            last_time = now

            # convert to MB delta
            mb_in  = diff_in  / (1024**2)
            mb_out = diff_out / (1024**2)

            # actual MB/s
            rate_in  = mb_in  / elapsed
            rate_out = mb_out / elapsed

            prev_in_octets, prev_out_octets = raw_in, raw_out

            with lock:
                hin = traffic_info["history"]["in"]
                hout = traffic_info["history"]["out"]
                hin.append(round(rate_in,  2))
                hout.append(round(rate_out, 2))
                if len(hin)  > HISTORY_LENGTH: hin.pop(0)
                if len(hout) > HISTORY_LENGTH: hout.pop(0)
                traffic_info.update({
                    "in": round(rate_in,  2),
                    "out": round(rate_out, 2),
                    "history": {"in": hin, "out": hout}
                })

            write_json()

        except subprocess.CalledProcessError as e:
            print("SNMP command failed:", e)
        except BrokenPipeError as e:
            print("Pipe to snmpwalk broke:", e)
        except Exception as e:
            print("Unexpected SNMP error:", e)

        time.sleep(0.5)


def write_json():
    with lock:
        output = {
            "nodes": node_stats,
            "disks": disk_info,
            "network": network_info,
            "traffic": traffic_info
        }
        with open(JSON_OUTPUT_FILE, "w") as f:
            json.dump(output, f, indent=2)

def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", UDP_PORT))
    while True:
        data, addr = sock.recvfrom(1024)
        try:
            message = data.decode("utf-8")
            name, cpu, gpu, mem, app = parse_message(message)
            timestamp = int(time.time())
            with lock:
                if name not in node_stats:
                    node_stats[name] = {
                        "cpu": 0.0,
                        "gpu": 0.0,
                        "mem": 0,
                        "app": app,
                        "lastSeen": timestamp,
                        "history": {"cpu": [], "gpu": []},
                        "ping": {"latencyMs": None, "reachable": False}
                    }
                node_stats[name]["cpu"] = cpu
                node_stats[name]["gpu"] = gpu
                node_stats[name]["mem"] = mem
                node_stats[name]["app"] = app
                node_stats[name]["lastSeen"] = timestamp
                node_stats[name]["history"]["cpu"].append(cpu)
                node_stats[name]["history"]["gpu"].append(gpu)
                if len(node_stats[name]["history"]["cpu"]) > HISTORY_LENGTH:
                    node_stats[name]["history"]["cpu"].pop(0)
                    node_stats[name]["history"]["gpu"].pop(0)
            write_json()
        except Exception as e:
            print("Error processing UDP message:", e)

def parse_message(msg):
    parts = msg.split("|")
    name = parts[0].strip()
    cpu = float(parts[1].split(":")[1].strip().replace("%", ""))
    gpu = float(parts[2].split(":")[1].strip().replace("%", ""))
    mem = int(parts[3].split(":")[1].strip().replace("MB", ""))
    app = parts[4].split(":", 1)[1].strip()
    return name, cpu, gpu, mem, app

def run_http_server():
    os.chdir(SERVE_DIR)
    server = HTTPServer(("", HTTP_PORT), SimpleHTTPRequestHandler)
    print(f"Serving on port {HTTP_PORT}...")
    server.serve_forever()

# Start threads
threading.Thread(target=background_updater, daemon=True).start()
threading.Thread(target=udp_listener, daemon=True).start()
threading.Thread(target=monitor_snmp, daemon=True).start() 
threading.Thread(target=run_http_server, daemon=True).start()

# Keep main thread alive
while True:
    time.sleep(1)
