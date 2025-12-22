#!/bin/bash
# Monitor holiday greeting logs during schedule creation

echo "=== Holiday Greeting Debug Monitor ==="
echo "Monitoring for holiday filter activity..."
echo ""

# Monitor multiple log files
tail -f logs/backend_restart_*.log logs/fill_gaps_json_debug_*.log 2>/dev/null | grep -E --line-buffered "Holiday filter check:|Holiday greeting filter applied|_ensure_holiday_integration|holiday_integration|scheduler.holiday_integration"