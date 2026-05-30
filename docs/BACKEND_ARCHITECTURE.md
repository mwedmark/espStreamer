# Unified Streaming Backend Architecture

The streaming backends have been refactored into a modular plugin architecture for easier maintenance and extensibility.

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  frontend/index.html                     │
│  (HTML UI - unchanged)                   │
└────────────────┬────────────────────────┘
                 │
        ┌────────▼─────────┐
        │  ws_server.py    │
        │  (WebSocket      │
        │   Router)        │
        └────────┬─────────┘
                 │
        ┌────────▼──────────────────┐
        │   StreamingBackend        │
        │   (Abstract Interface)    │
        └────────┬──────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
┌───▼──────────────┐   ┌─────▼──────────┐
│ backend_kungfu   │   │ backend_vice   │
│ (Kung Fu Flash)  │   │ (VICE Emulator)│
└──────────────────┘   └────────────────┘
```

## Files

- **`backend_base.py`** - Abstract base class defining the StreamingBackend interface
- **`backend_kungfu.py`** - Kung Fu Flash hardware implementation
- **`backend_vice.py`** - VICE emulator implementation
- **`ws_server.py`** - Unified WebSocket server (works with any backend)
- **`server_launcher.py`** - Entry point to start any backend

## Usage

### Start Kung Fu Flash Backend (Default)
```bash
python server_launcher.py --backend kung_fu --port 8765
```

### Start VICE Emulator Backend
```bash
python server_launcher.py --backend vice --port 8766
```

### Custom Host/Port
```bash
python server_launcher.py --backend kung_fu --host 0.0.0.0 --port 9000
```

## Adding a New Backend

1. Create `backend_newname.py` that inherits from `StreamingBackend`
2. Implement all abstract methods:
   - `connect(port=None) -> bool`
   - `disconnect() -> bool`
   - `send_viewer(viewer_data=None) -> bool`
   - `stream_frame(mode, bg_color, bitmap, screen, color) -> bool`
   - `reset() -> bool`
   - `reset_stream_buffers(reason) -> bool`
   - `get_status() -> dict`
   - `is_connected` property
   - `is_viewer_running` property

3. Update `server_launcher.py` to add your backend to the choices

Example:
```python
# backend_mydevice.py
from backend_base import StreamingBackend

class MyDeviceBackend(StreamingBackend):
    def connect(self, port=None) -> bool:
        # Implementation
        pass
    
    # ... implement all abstract methods
```

4. Use it:
```bash
python server_launcher.py --backend my_device --port 8767
```

## Frontend Integration

The frontend HTML (`frontend/index.html`) automatically works with all backends through the WebSocket interface. The JavaScript code doesn't need to know which backend is running—it just sends the same commands to the appropriate port.

To switch backends in the UI:
- Connect button → opens WebSocket to the server port
- Stream mode selector → sends `setmode` command to backend
- Stream button → sends binary frame data

## Migration from Old Servers

The old `kungfu_server.py` and `kungfu_vice_server.py` can now be replaced by:
```bash
# Terminal 1 (Kung Fu Flash)
python server_launcher.py --backend kung_fu --port 8765

# Terminal 2 (VICE)
python server_launcher.py --backend vice --port 8766
```

Or run both in one terminal with backgrounding:
```bash
python server_launcher.py --backend kung_fu --port 8765 &
python server_launcher.py --backend vice --port 8766 &
```
