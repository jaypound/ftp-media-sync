# Content Rotation Quick Reference

## Essential Files

### Configuration
- `backend/config.json` - Stores rotation_order configuration
- `backend/config_manager.py` - Loads and saves configuration

### Backend Logic
- `backend/scheduler_postgres.py` - Main rotation implementation
  - `_get_next_duration_category()` - Returns next category
  - `_advance_rotation()` - Moves to next category
  - `_load_config_if_needed()` - Loads rotation order

- `backend/app.py` - API endpoints
  - `/api/config` - Save configuration endpoint
  - `/api/fill-template-gaps` - Uses rotation for gap filling

### Frontend
- `frontend/script.js`
  - `saveRotationConfig()` - Saves rotation order (line ~4002)
  - `updateRotationOrder()` - Updates UI (line ~3795)
  - `scheduleConfig.ROTATION_ORDER` - Stores current order

## Quick Fixes

### Rotation Order Not Saving
```python
# In config_manager.py, ensure _merge_config includes:
else:
    # Add new keys that don't exist in defaults
    default[key] = value
```

### Force Config Reload
```python
# Add to any schedule creation function
scheduler._config_loaded = False
scheduler._load_config_if_needed()
```

### Debug Rotation
```python
# Add to scheduler_postgres.py
logger.info(f"Scheduling config loaded: {scheduling_config}")
logger.info(f"Using rotation order: {self.duration_rotation}")
```

## Testing Commands

### Check Current Configuration
```bash
cat backend/config.json | jq '.scheduling.rotation_order'
```

### Test Config Loading
```python
from config_manager import ConfigManager
cm = ConfigManager()
print(cm.get_scheduling_settings())
```

### Verify Scheduler Rotation
```python
from scheduler_postgres import scheduler_postgres
scheduler_postgres._config_loaded = False
scheduler_postgres._load_config_if_needed()
print(scheduler_postgres.duration_rotation)
```

## Common Issues

1. **Mismatched Defaults**
   - Frontend: `['id', 'spots', 'short_form', 'long_form']`
   - Backend: `['id', 'short_form', 'long_form', 'spots']`

2. **Config Not Loading**
   - Check if "scheduling" section exists in config.json
   - Verify ConfigManager includes scheduling in defaults

3. **Rotation Not Advancing**
   - Ensure `_advance_rotation()` is called AFTER content is scheduled
   - Don't advance in `_get_next_duration_category()`

## Log Messages to Watch

✅ **Good**:
```
Loaded rotation order from config: ['id', 'spots', 'short_form', 'long_form']
Using rotation order: ['id', 'spots', 'short_form', 'long_form']
```

❌ **Bad**:
```
No rotation_order in config, using default: ['id', 'short_form', 'long_form', 'spots']
```