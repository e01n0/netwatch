#!/bin/bash
# Double-click handler for the netwatch sidebar.
# Called by tmux DoubleClick1Pane with #{mouse_y} as $1.
# Reads /tmp/netwatch-sidebar-map.txt and jumps to the target pane.

MOUSE_Y="${1:-}"
[ -z "$MOUSE_Y" ] && exit 0

MAP_FILE="/tmp/netwatch-sidebar-map.txt"
[ -r "$MAP_FILE" ] || exit 0

match=$(awk -F'|' -v y="$MOUSE_Y" '$1 == y {print $0; exit}' "$MAP_FILE")
[ -z "$match" ] && exit 0

pane_id=$(echo "$match" | cut -d'|' -f2)
target=$(echo "$match" | cut -d'|' -f3)

tmux select-window -t "$target" 2>/dev/null
tmux select-pane -t "$pane_id" 2>/dev/null
