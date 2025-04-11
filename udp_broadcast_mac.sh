#!/bin/sh

# Render node broadcaster - Mac, Apple Silicon.
#
# Relies on macmon, a utility installable with brew (brew install macmon)


UDP_PORT=43217
BROADCAST_ADDR="10.0.1.255"
HOSTN=$(hostname -s)

# Check dependencies
command -v macmon >/dev/null 2>&1 || { echo >&2 "macmon not installed. Aborting."; exit 1; }
command -v jq >/dev/null 2>&1 || { echo >&2 "jq not installed. Aborting."; exit 1; }
command -v socat >/dev/null 2>&1 || { echo >&2 "socat not installed. Aborting."; exit 1; }

# Start monitoring loop
macmon pipe -i 250 | while read -r line; do

ECPU_USAGE=$(echo "$line" | jq '.ecpu_usage[1]')
PCPU_USAGE=$(echo "$line" | jq '.pcpu_usage[1]')
GPU=$(echo "$line" | jq '.gpu_usage[1]')
MEM=$(echo "$line" | jq '.memory.ram_usage')

CPU_TOTAL=$(echo "($ECPU_USAGE * 8 + $PCPU_USAGE * 16) / 24 * 100" | bc -l)
CPU_PCT=$(printf "%.0f" "$CPU_TOTAL")
GPU_PCT=$(printf "%.0f" "$(echo "$GPU * 100" | bc)")
MEM_MB=$(printf "%.0f" "$(echo "$MEM / 1024 / 1024" | bc)")


    STATUS_MSG="${HOSTN} | CPU: ${CPU_PCT}% | GPU: ${GPU_PCT}% | MEM: ${MEM_MB}MB"

    echo "$STATUS_MSG"
    printf "%s\n" "$STATUS_MSG" | socat - UDP-DATAGRAM:$BROADCAST_ADDR:$UDP_PORT,broadcast
done
