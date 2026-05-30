# ESP32 SPIFFS Migration Guide

## Overview

The ESP32 now serves the **same HTML/CSS/JS files** as the local web app from SPIFFS (SPI Flash File System) instead of having them embedded in the firmware. This means:

✅ **Single source of truth** for the UI  
✅ **Update UI without recompiling firmware** (just upload SPIFFS data)  
✅ **Same experience** on both ESP32 and local web server  
✅ **Easy maintenance** - changes made in `frontend/` automatically used everywhere

## File Structure

```
ESPStreamer/
├── ESPStreamer.ino          (Main sketch)
├── ESPStreamer_SPIFFS_template.ino  (Reference template - shows SPIFFS approach)
└── data/                    (SPIFFS filesystem - uploaded to ESP32)
    ├── index.html           (Unified web UI)
    ├── app.js               (Frontend logic)
    ├── c64Engine.js         (C64 encoder engine)
    └── c64Worker.js         (Web Worker)
```

## Migration Steps

### Step 1: Backup Current Firmware
```bash
# Keep your current ESPStreamer.ino as backup
cp ESPStreamer/ESPStreamer.ino ESPStreamer/ESPStreamer.ino.backup
```

### Step 2: Update ESPStreamer.ino

The key changes needed:

#### Add SPIFFS include at top:
```cpp
#include <SPIFFS.h>
```

#### Add MIME type helper:
```cpp
String getMimeType(String filename) {
  if (filename.endsWith(".html")) return "text/html; charset=UTF-8";
  if (filename.endsWith(".css")) return "text/css";
  if (filename.endsWith(".js")) return "application/javascript";
  if (filename.endsWith(".json")) return "application/json";
  if (filename.endsWith(".png")) return "image/png";
  if (filename.endsWith(".gif")) return "image/gif";
  if (filename.endsWith(".jpg") || filename.endsWith(".jpeg")) return "image/jpeg";
  if (filename.endsWith(".ico")) return "image/x-icon";
  return "application/octet-stream";
}
```

#### Add file serving handler:
```cpp
void handleStaticFile() {
  String path = server.uri();
  if (path == "/") path = "/index.html";

  if (SPIFFS.exists(path)) {
    File file = SPIFFS.open(path, "r");
    server.sendHeader("Cache-Control", "public, max-age=3600");
    server.send(200, getMimeType(path), file.readString());
    file.close();
  } else {
    server.send(404, "text/plain", "File not found");
  }
}
```

#### In setup(), initialize SPIFFS:
```cpp
void setup() {
  Serial.begin(115200);
  delay(1000);

  // Initialize SPIFFS
  if (!SPIFFS.begin(true)) {
    Serial.println("SPIFFS Mount Failed");
    return;
  }

  // ... rest of setup ...
}
```

#### Replace the embedded HTML handler:
**Remove:**
```cpp
void handleRoot() {
  server.send(200, "text/html", INDEX_HTML);
}
```

**Replace with:**
```cpp
void handleRoot() {
  handleStaticFile();
}
```

#### In server setup, use onNotFound for fallthrough:
```cpp
// Specific API routes (these match first)
server.on("/data", handleData);
server.on("/stats", handleStats);
server.on("/setmode", handleSetMode);
// ... etc ...

// Catch-all for static files (CSS, JS, etc.)
server.onNotFound(handleStaticFile);
```

#### Remove the large embedded INDEX_HTML string:
Delete these lines (saves ~20KB of firmware):
```cpp
static const char INDEX_HTML[] PROGMEM = R"rawhtml(
  ... all that HTML ...
)rawhtml";
```

### Step 3: Upload to ESP32

#### In Arduino IDE:

1. **Tools → Flash Size**: Select a board with SPIFFS support (e.g., ESP32 Dev Module)
2. **Tools → Partition Scheme**: Select one with SPIFFS (e.g., "Huge APP (3MB No OTA)")
3. **Upload firmware** normally: Sketch → Upload

#### Upload SPIFFS Data:

1. **Tools → ESP32 Sketch Data Upload**
   - This uploads files from `ESPStreamer/data/` to ESP32's SPIFFS
   - First time takes ~10 seconds
   - Subsequent uploads only update changed files

*Note: If you don't see "ESP32 Sketch Data Upload" option:*
- Install esp32fs plugin: https://github.com/me-no-dev/arduino-esp32fs-plugin
- Place in `~/Arduino/tools/ESP32FS/tool/esp32fs.jar`

### Step 4: Verify

- Open browser to `http://<ESP32_IP>:80`
- You should see the same UI as the local web app
- Check Serial Monitor for `SPIFFS mounted successfully`
- List of uploaded files should appear

## Updating the UI

**Before:** Had to recompile and upload firmware  
**Now:** Just update and re-upload SPIFFS:

```bash
# 1. Edit frontend/index.html, app.js, or c64Engine.js
# 2. Copy updated file to ESPStreamer/data/
cp frontend/index.html ESPStreamer/data/index.html

# 3. In Arduino IDE: Tools → ESP32 Sketch Data Upload
# Done! No firmware recompilation needed
```

Or use a build script:
```bash
#!/bin/bash
# sync_frontend.sh
cp frontend/index.html ESPStreamer/data/
cp frontend/app.js ESPStreamer/data/
cp frontend/c64Engine.js ESPStreamer/data/
cp frontend/c64Worker.js ESPStreamer/data/
echo "Frontend synced to ESP32 data folder"
```

## Troubleshooting

### "SPIFFS Mount Failed"
- Check partition scheme has SPIFFS space
- Try with `format_spiffs_filesystem=true` in the upload tool

### 404 errors for JS/CSS
- Verify files exist in `ESPStreamer/data/`
- Check file permissions (should be readable)
- Serial output should list files on startup

### Changes don't take effect
- Ensure you run **Tools → ESP32 Sketch Data Upload** (not just sketch upload)
- Power cycle the ESP32 after data upload

## API Endpoints (Unchanged)

All existing endpoints work the same:
- `/` — Serves index.html
- `/data` — Current bitmap data
- `/stats` — Statistics
- `/setmode?m=...` — Set encoding mode
- `/setcontrast?c=...` — Set contrast
- `/setbrightness?b=...` — Set brightness
- etc.

## Benefits

1. **Single source** - frontend/index.html is used everywhere
2. **Smaller firmware** - ~20KB savings (no embedded HTML)
3. **Faster development** - UI changes don't require firmware recompile
4. **Same experience** - Identical UI on local and ESP32
5. **SPIFFS updates** - Deploy UI updates independently from firmware

## Reference

- Template: See `ESPStreamer_SPIFFS_template.ino`
- Original file still there for comparison: `ESPStreamer.ino.backup`
- ESP32FS tool: https://github.com/me-no-dev/arduino-esp32fs-plugin
- SPIFFS docs: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/storage/spiffs.html
