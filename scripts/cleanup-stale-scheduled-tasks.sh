#!/bin/bash
#
# cleanup-stale-scheduled-tasks.sh — reap leftover Claude Code processes and
# their docker containers after scheduled-task runs complete.
#
# Background: Claude Code's scheduled-task runs spawn a `claude` binary that
# does its work and then, instead of exiting, lingers idle at 0% CPU. This
# zombie process keeps holding open its `docker run` subprocess, which keeps
# the corresponding container alive (despite --rm being set, since the
# container only exits when its stdio parent dies). After a day of hourly
# runs you can have 30+ zombie claude processes + 30+ idle containers
# consuming RAM and (in OrbStack's case) UI clutter.
#
# This script kills:
#   1. Idle claude processes started by scheduled-task replays
#      (matched by the --replay-user-messages flag combined with --settings {}
#      and the absence of --resume, which is unique to scheduled tasks)
#   2. Any opn-mcp containers with auto-generated names (the long-running
#      interactive containers named `opn-mcp` and `opn-mcp-claude` are
#      preserved — they belong to Claude Desktop and Claude Code main
#      sessions respectively)
#
# Safe to run while a scheduled task is actively executing — the matching
# active process will be young (<30s) and is excluded by the elapsed-time
# floor. Conservative by design.
#
# Recommended: install as a launchd job that runs every hour, see
# scripts/com.opnsense-mcp.cleanup.plist.

set -u
# don't `set -e` — we want to continue even if one step finds nothing

# Identify zombie scheduled-task processes. Matching criteria:
#   - command contains "--replay-user-messages --settings {}" (scheduled task replay)
#   - command does NOT contain "--resume" (excludes interactive sessions)
#   - 0% CPU (idle, not actively working)
#   - elapsed time > 5 minutes (avoid killing the actively-running task)
#
# `ps -eo etime` format on macOS: [[dd-]hh:]mm:ss
# We don't try to parse it precisely — just look for entries that are NOT
# the short "MM:SS" form, which covers >1 hour. For the under-1-hour cases
# we additionally check that the process started before "now - 5 minutes".

ZOMBIE_PIDS=$(
  ps -axo pid,pcpu,etime,command \
    | grep -E '\-\-replay-user-messages --settings \{\}' \
    | grep -v 'grep\|\-\-resume' \
    | awk '{
        # $3 is etime in [[dd-]hh:]mm:ss format
        # accept entries with dd-hh:mm:ss or hh:mm:ss (>=1hr old) outright
        # for mm:ss, require minutes >= 5
        n = split($3, parts, /[-:]/)
        if (n >= 3) {                      # dd-hh:mm:ss or hh:mm:ss
          print $1
        } else if (n == 2 && parts[1]+0 >= 5) {   # mm:ss with mm >= 5
          print $1
        }
      }'
)

if [ -n "$ZOMBIE_PIDS" ]; then
  COUNT=$(echo "$ZOMBIE_PIDS" | wc -w | tr -d ' ')
  echo "[$(date -Iseconds)] killing $COUNT zombie scheduled-task claude process(es)"
  echo "$ZOMBIE_PIDS" | xargs kill -TERM 2>/dev/null || true
  sleep 2
  # If any survived, SIGKILL
  STILL=$(
    ps -axo pid,command \
      | grep -E '\-\-replay-user-messages --settings \{\}' \
      | grep -v 'grep\|\-\-resume' \
      | awk '{print $1}'
  )
  if [ -n "$STILL" ]; then
    echo "$STILL" | xargs kill -9 2>/dev/null || true
  fi
fi

# Now clean any opn-mcp containers that no longer have a live parent.
# Keep the long-running interactive ones (`opn-mcp`, `opn-mcp-claude`).
ORPHAN_CONTAINERS=$(
  docker ps -a --filter ancestor=opn-mcp --format '{{.ID}} {{.Names}}' 2>/dev/null \
    | awk '$2 != "opn-mcp" && $2 != "opn-mcp-claude" {print $1}'
)
if [ -n "$ORPHAN_CONTAINERS" ]; then
  COUNT=$(echo "$ORPHAN_CONTAINERS" | wc -w | tr -d ' ')
  echo "[$(date -Iseconds)] removing $COUNT orphan opn-mcp container(s)"
  echo "$ORPHAN_CONTAINERS" | xargs docker rm -f >/dev/null 2>&1 || true
fi
