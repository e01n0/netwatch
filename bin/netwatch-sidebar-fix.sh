#!/bin/bash
# Enforce sidebar layout after any split/resize/pane-exit.
# Finds the NETWATCH pane in the current window and forces it to:
#   - 32 columns wide
#   - Full window height (by being the leftmost pane)
# If a rogue split created a pane below/above the sidebar, kill it.

SIDEBAR=$(tmux list-panes -F '#{pane_id} #{pane_title} #{pane_width} #{pane_height}' \
    | awk '$2 == "NETWATCH" {print $1; exit}')

[ -z "$SIDEBAR" ] && exit 0

# Get the window height for comparison
WIN_HEIGHT=$(tmux display-message -p '#{window_height}')
SIDEBAR_HEIGHT=$(tmux display-message -t "$SIDEBAR" -p '#{pane_height}')
SIDEBAR_WIDTH=$(tmux display-message -t "$SIDEBAR" -p '#{pane_width}')

# Fix width if it drifted
if [ "$SIDEBAR_WIDTH" -ne 32 ] 2>/dev/null; then
    tmux resize-pane -t "$SIDEBAR" -x 32 2>/dev/null
fi

# If sidebar isn't full height, something split it vertically.
# Resize it back to full height.
if [ "$SIDEBAR_HEIGHT" -lt "$((WIN_HEIGHT - 1))" ] 2>/dev/null; then
    tmux resize-pane -t "$SIDEBAR" -y "$WIN_HEIGHT" 2>/dev/null
fi

exit 0
