#!/bin/zsh
# One-shot wrapper: backfill Jun 15-21 2026 YouTube videos after the midnight-PT
# quota reset, then self-remove the launchd job so it only ever runs once.
set -u
DIR="/Users/mark/hyrox-weekly"
LABEL="com.hyroxweekly.backfill-jun15"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$DIR/logs/catchup/backfill-jun15-scheduled.log"

cd "$DIR" || exit 1
echo "===== BACKFILL START $(date) =====" >> "$LOG"
./venv/bin/python backfill_youtube_week.py --week 2026-06-15 >> "$LOG" 2>&1
rc=$?
echo "===== BACKFILL DONE rc=$rc $(date) =====" >> "$LOG"

# Self-remove so this never fires a second time.
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null
rm -f "$PLIST"
echo "===== launchd job ${LABEL} removed (one-shot complete) =====" >> "$LOG"
exit $rc
