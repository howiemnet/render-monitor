#!/bin/sh

# Render node "broadcaster" - linux, nVidia GPUs

UDP_PORT=43217
BROADCAST_ADDR="10.0.1.255"  # Change this if your network requires a specific subnet
HOSTN=$(hostname -s)

while true; do
    CPU=$(top -bn1 | awk '/Cpu/ { print $2}')
    GPU=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits)
    MEM=$(free -m | awk '/Mem/{print $3}')

    STATUS_MSG="${HOSTN} | CPU: ${CPU}% | GPU: ${GPU}% | MEM: ${MEM}MB"

    # Send over network via UDP broadcast
    echo "$STATUS_MSG"
    printf "%s\n" "$STATUS_MSG" | nc -u -q0 -b $BROADCAST_ADDR $UDP_PORT

    sleep 0.25
done
