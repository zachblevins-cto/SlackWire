#!/bin/bash
# SlackWire monitoring script

# Check if process is running
if ! pgrep -f "python3.*main.py" > /dev/null; then
    echo "$(date): SlackWire bot is not running!" >> monitor.log
    # Optionally restart
    # systemctl restart slackwire
fi

# Check memory usage
MEM_USAGE=$(ps aux | grep -E "python3.*main.py" | grep -v grep | awk '{print $4}')
if [ ! -z "$MEM_USAGE" ]; then
    if (( $(echo "$MEM_USAGE > 10.0" | bc -l) )); then
        echo "$(date): High memory usage: ${MEM_USAGE}%" >> monitor.log
    fi
fi

# Check cache file size
CACHE_SIZE=$(stat -f%z "feed_cache.json" 2>/dev/null || stat -c%s "feed_cache.json" 2>/dev/null)
if [ "$CACHE_SIZE" -gt 1048576 ]; then  # 1MB
    echo "$(date): Large cache file: $CACHE_SIZE bytes" >> monitor.log
fi

# Check for errors in last hour
RECENT_ERRORS=$(tail -1000 errors.log | grep -c "ERROR")
if [ "$RECENT_ERRORS" -gt 10 ]; then
    echo "$(date): High error rate: $RECENT_ERRORS errors" >> monitor.log
fi
