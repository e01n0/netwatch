#!/bin/bash
# Thin bridge: reads Claude Code hook event from stdin, POSTs to netwatchd.
# Called by the plugin hook declarations with event name as $1.
# Fails silently if daemon is down — never blocks Claude.

EVENT="${1:-unknown}"
PORT_FILE="${HOME}/.config/netwatch/port"

# Read port; bail if daemon isn't running
if [ ! -r "$PORT_FILE" ]; then
    exit 0
fi
PORT=$(cat "$PORT_FILE" 2>/dev/null)
if [ -z "$PORT" ]; then
    exit 0
fi

# Read hook payload from stdin, POST to daemon
curl -s -X POST "http://127.0.0.1:${PORT}/hook/${EVENT}" \
    -H "Content-Type: application/json" \
    -d @- \
    --connect-timeout 1 \
    --max-time 3 \
    >/dev/null 2>&1 &

exit 0
