#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <TJpg_Decoder.h>

const char* ssid = "MagnusAsus_Boa";
const char* password = "R36RulesAgain";
const char* streamHost = "192.168.50.145";
const int   streamPort = 90;
const char* streamPath = "/pc.mjpg";

WebServer server(80);

// --- Mode ---
bool hiResMode = false;  // false = multicolor 160x200 2bpp, true = hires 320x200 1bpp

// --- Buffers ---
uint8_t c64_buffer[8000];           // 160x200@2bpp or 320x200@1bpp = 8000 bytes
uint8_t temp_jpg_buffer[25000];     // Buffer for one JPEG frame (increased from 15K)

// --- MJPEG stream state ---
WiFiClient mjpgClient;
bool       streamConnected = false;
String     boundary = "";

// --- Stats for debug ---
volatile uint32_t frameCount = 0;
volatile uint32_t lastFrameSize = 0;
volatile uint32_t lastDecodeResult = 0;
volatile uint32_t nonZeroPixels = 0;

// Bayer 4x4 dither matrix
const int8_t bayer4x4[4][4] = {
    {-32,  0, -24,  8},
    { 16, -16, 24, -8},
    {-20, 12, -28,  4},
    { 28, -4,  20, -12}
};

// TJpg_Decoder callback - converts decoded pixels to C64 bitmap format
bool process_output(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t* bitmap) {
  for (int j = 0; j < h; j++) {
    for (int i = 0; i < w; i++) {
      int currX = x + i;
      int currY = y + j;

      uint16_t p = bitmap[i + j * w];
      // RGB565 to greyscale
      uint8_t r = (p >> 8) & 0xF8;
      uint8_t g = (p >> 3) & 0xFC;
      uint8_t b = (p << 3) & 0xF8;
      int16_t gray = (r + g + b) / 3;

      if (hiResMode) {
        // --- Hi-Res 320x200 1bpp ---
        if (currX >= 320 || currY >= 200) continue;
        // Bayer threshold to 1 bit (use 4x4 matrix, threshold at 128)
        int16_t dithered = gray + bayer4x4[currX % 4][currY % 4];
        uint8_t bit = (constrain(dithered, 0, 255) >= 128) ? 1 : 0;
        // Pack: MSB = pixel 0
        int byteIdx = currY * 40 + (currX / 8);
        int bitPos  = 7 - (currX % 8);
        if (bit) c64_buffer[byteIdx] |=  (1 << bitPos);
        else     c64_buffer[byteIdx] &= ~(1 << bitPos);
      } else {
        // --- Multi-color 160x200 2bpp ---
        if (currX >= 160 || currY >= 200) continue;
        // Bayer dithering to 4 levels
        int16_t dithered = gray + bayer4x4[currX % 4][currY % 4];
        uint8_t level = map(constrain(dithered, 0, 255), 0, 255, 0, 3);
        // Pack into 2bpp buffer (MSB left)
        int byteIdx = currY * 40 + (currX / 4);
        int bitPos  = (3 - (currX % 4)) * 2;
        c64_buffer[byteIdx] &= ~(0x03 << bitPos);
        c64_buffer[byteIdx] |= (level << bitPos);
      }
    }
  }
  return true;
}

// --- Web Server Handlers ---

void handleData() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.setContentLength(8000);
  server.send(200, "application/octet-stream", "");
  server.sendContent((const char*)c64_buffer, 8000);
}

void handleSetMode() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("m")) {
    String m = server.arg("m");
    hiResMode = (m == "hires");
    // Clear buffer when switching modes
    memset(c64_buffer, 0, sizeof(c64_buffer));
    server.send(200, "text/plain", hiResMode ? "hires" : "multicolor");
  } else {
    server.send(400, "text/plain", "Missing ?m= param");
  }
}

void handleStats() {
  // Count non-zero bytes for debug
  uint32_t nz = 0;
  for (int i = 0; i < 8000; i++) {
    if (c64_buffer[i] != 0) nz++;
  }
  String json = "{\"frames\":" + String(frameCount) +
                ",\"lastSize\":" + String(lastFrameSize) +
                ",\"decode\":" + String(lastDecodeResult) +
                ",\"nonZero\":" + String(nz) +
                ",\"connected\":" + String(streamConnected ? 1 : 0) +
                ",\"hires\":" + String(hiResMode ? 1 : 0) + "}";
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", json);
}

void handleRoot() {
  String html = R"rawhtml(
<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>C64 LIVE ENCODER</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    min-height: 100vh;
    display: flex; flex-direction: column; align-items: center;
    color: #e0e0ff;
    font-family: 'Share Tech Mono', monospace;
    padding: 20px;
  }
  h2 {
    font-size: 28px;
    letter-spacing: 6px;
    margin: 20px 0;
    text-shadow: 0 0 20px rgba(100, 140, 255, 0.6);
    background: linear-gradient(90deg, #6c8cff, #a87fff, #6c8cff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .container {
    background: rgba(20, 20, 50, 0.7);
    border: 1px solid rgba(100, 140, 255, 0.3);
    border-radius: 16px;
    padding: 24px;
    backdrop-filter: blur(10px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05);
  }
  canvas {
    width: 640px; height: 400px;
    image-rendering: pixelated;
    border: 3px solid rgba(100, 140, 255, 0.4);
    border-radius: 8px;
    background: #000;
    box-shadow: 0 0 30px rgba(80, 120, 255, 0.15), inset 0 0 60px rgba(0,0,0,0.5);
    display: block;
  }
  .mode-badge {
    text-align: center;
    font-size: 11px;
    letter-spacing: 3px;
    margin-bottom: 8px;
    padding: 4px 12px;
    border-radius: 4px;
    display: inline-block;
    transition: all 0.3s;
  }
  .mode-badge.mc  { color: #ffd080; background: rgba(255,180,0,0.10); border: 1px solid rgba(255,180,0,0.3); }
  .mode-badge.hr  { color: #80ffcc; background: rgba(0,255,180,0.10); border: 1px solid rgba(0,255,180,0.3); }
  .badge-wrap { display:flex; justify-content:center; margin-bottom:10px; }
  .controls {
    display: flex; gap: 10px; margin-top: 16px; justify-content: center; flex-wrap: wrap;
  }
  button {
    padding: 10px 28px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 14px;
    letter-spacing: 2px;
    cursor: pointer;
    background: linear-gradient(180deg, rgba(100,140,255,0.2), rgba(60,80,180,0.3));
    color: #a0b4ff;
    border: 1px solid rgba(100,140,255,0.4);
    border-radius: 8px;
    transition: all 0.2s;
  }
  button:hover {
    background: linear-gradient(180deg, rgba(100,140,255,0.4), rgba(60,80,180,0.5));
    box-shadow: 0 0 16px rgba(100,140,255,0.3);
    color: #fff;
  }
  #btn-mode.mc {
    background: linear-gradient(180deg, rgba(255,180,0,0.15), rgba(180,100,0,0.25));
    color: #ffd080;
    border-color: rgba(255,180,0,0.4);
  }
  #btn-mode.mc:hover {
    background: linear-gradient(180deg, rgba(255,180,0,0.35), rgba(180,100,0,0.45));
    box-shadow: 0 0 16px rgba(255,160,0,0.3);
    color: #fff;
  }
  #btn-mode.hr {
    background: linear-gradient(180deg, rgba(0,255,180,0.15), rgba(0,130,100,0.25));
    color: #80ffcc;
    border-color: rgba(0,255,180,0.4);
  }
  #btn-mode.hr:hover {
    background: linear-gradient(180deg, rgba(0,255,180,0.35), rgba(0,130,100,0.45));
    box-shadow: 0 0 16px rgba(0,255,160,0.3);
    color: #fff;
  }
  #stats {
    margin-top: 16px;
    font-size: 12px;
    color: #7088cc;
    text-align: center;
    line-height: 1.8;
  }
  #stats .val { color: #a0ff90; }
  #stats .err { color: #ff6060; }
  .dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; margin-right: 6px;
    background: #444;
    transition: background 0.3s;
  }
  .dot.on { background: #40ff40; box-shadow: 0 0 8px #40ff40; }
</style>
</head><body>
<h2>&#x25C8; C64 LIVE ENCODER &#x25C8;</h2>
<div class="container">
  <div class="badge-wrap">
    <span class="mode-badge mc" id="badge">MULTI-COLOR 160x200</span>
  </div>
  <canvas id="c" width="160" height="200"></canvas>
  <div class="controls">
    <button id="btn-mode" class="mc" onclick="toggleMode()">&#x21C4; HIRES 320x200</button>
    <button onclick="save('PRG')">&#x25B6; PRG</button>
    <button onclick="save('KOA')">&#x25B6; KOA</button>
  </div>
  <div id="stats">
    <span class="dot" id="dot"></span>
    <span id="stxt">Connecting...</span>
  </div>
</div>

<script>
const palMC = [0, 85, 170, 255];  // 4-level grey for multicolor
let running = true;
let isHires = false;  // mirrors ESP32 mode

// --- Canvas resize helper ---
function resizeCanvas(hires) {
  const cv = document.getElementById('c');
  cv.width  = hires ? 320 : 160;
  cv.height = 200;
  cv.style.height = hires ? '400px' : '400px';  // always 400px display height
  cv.style.width  = '640px';
}

// --- Mode toggle ---
async function toggleMode() {
  const target = isHires ? 'multicolor' : 'hires';
  try {
    const r = await fetch('/setmode?m=' + target + '&t=' + Date.now());
    if (r.ok) {
      isHires = (target === 'hires');
      updateModeUI();
    }
  } catch(e) { console.log('setmode error:', e); }
}

function updateModeUI() {
  const btn   = document.getElementById('btn-mode');
  const badge = document.getElementById('badge');
  resizeCanvas(isHires);
  if (isHires) {
    btn.className   = 'hr';
    btn.innerHTML   = '&#x21C4; MULTI-COLOR 160x200';
    badge.className = 'mode-badge hr';
    badge.textContent = 'HI-RES 320x200';
  } else {
    btn.className   = 'mc';
    btn.innerHTML   = '&#x21C4; HIRES 320x200';
    badge.className = 'mode-badge mc';
    badge.textContent = 'MULTI-COLOR 160x200';
  }
}

// --- C64 bitmap layout conversion (same formula for both modes: 40 bytes/row) ---
function linearToC64(linear) {
  const c64 = new Uint8Array(8000);
  for (let y = 0; y < 200; y++) {
    for (let xByte = 0; xByte < 40; xByte++) {
      let linIdx = y * 40 + xByte;
      let charRow = Math.floor(y / 8);
      let c64Idx  = (charRow * 40 + xByte) * 8 + (y % 8);
      c64[c64Idx] = linear[linIdx];
    }
  }
  return c64;
}

// --- Save ---
async function save(t) {
  const r = await fetch('/data?t=' + Date.now());
  const d = new Uint8Array(await r.arrayBuffer());
  const bmp = linearToC64(d);
  let f;
  if (t === 'KOA') {
    // KOA only makes sense in multicolor
    f = new Uint8Array(10003);
    f[0] = 0; f[1] = 0x60;
    f.set(bmp, 2);
    for (let i = 8002; i < 9002; i++) f[i] = 0xBC;
    for (let i = 9002; i < 10002; i++) f[i] = 1;
    download(f, 'img.koa');
  } else {
    f = new Uint8Array(14145);
    f[0] = 1; f[1] = 8; // Load address $0801
    // BASIC Stub: 10 SYS 2061
    f.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);

    // PRG machine code
    // Hi-res uses $D016 = $C8. Multicolor uses $D016 = $D8. $D011 is always $3B (Bitmap mode on).
    const prgAsm = [
      0x78, // SEI
      0xA9, 0x3B, 0x8D, 0x11, 0xD0, // LDA #$3B, STA $D011
      0xA9, isHires ? 0xC8 : 0xD8, 0x8D, 0x16, 0xD0, // LDA #$D8/$C8, STA $D016
      0xA9, 0x18, 0x8D, 0x18, 0xD0, // LDA #$18, STA $D018 (Screen $0400, Bitmap $2000)
      0xA9, 0x00, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0, // LDA #0, STA border/bg
      0xA2, 0x00, // LDX #0
      // Memory Copy Loop: Screen RAM
      0xBD, 0x70, 0x08, 0x9D, 0x00, 0x04,
      0xBD, 0x6A, 0x09, 0x9D, 0xFA, 0x04,
      0xBD, 0x64, 0x0A, 0x9D, 0xF4, 0x05,
      0xBD, 0x5E, 0x0B, 0x9D, 0xEE, 0x06,
      0xE8, 0xE0, 0xFA, 0xD0, 0xE3,
      0xA2, 0x00, // LDX #0
      // Memory Copy Loop: Color RAM
      0xBD, 0x58, 0x0C, 0x9D, 0x00, 0xD8,
      0xBD, 0x52, 0x0D, 0x9D, 0xFA, 0xD8,
      0xBD, 0x4C, 0x0E, 0x9D, 0xF4, 0xD9,
      0xBD, 0x46, 0x0F, 0x9D, 0xEE, 0xDA,
      0xE8, 0xE0, 0xFA, 0xD0, 0xE3,
      0x4C, 0x63, 0x08 // JMP $0863 (infinite loop)
    ];
    f.set(prgAsm, 14);

    // Embed Screen RAM source data (at $0870, offset 113)
    // For HiRes, we need $10 (foreground white, background black) per cell.
    // For Multicolor, we use $BC.
    for (let i = 113; i < 1113; i++) f[i] = isHires ? 0x10 : 0xBC;
    
    // Embed Color RAM source data (at $0C58, offset 1113)
    // Always 1 (White) for both modes.
    for (let i = 1113; i < 2113; i++) f[i] = 1;

    // Bitmap data always at $2000 (offset 6145 from file start)
    f.set(bmp, 6145);
    download(f, isHires ? 'hires.prg' : 'v.prg');
  }
}

function download(d, n) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([d]));
  a.download = n;
  a.click();
}

async function upd() {
  try {
    // Fetch stats first to get mode
    const sr = await fetch('/stats?t=' + Date.now());
    if (sr.ok) {
      const s = await sr.json();
      const serverHires = !!s.hires;
      if (serverHires !== isHires) {
        isHires = serverHires;
        updateModeUI();
      }
      const dot  = document.getElementById('dot');
      const stxt = document.getElementById('stxt');
      dot.className = s.connected ? 'dot on' : 'dot';
      stxt.innerHTML =
        'Stream: ' + (s.connected ? '<span class="val">LIVE</span>' : '<span class="err">DISCONNECTED</span>') +
        ' &nbsp;|&nbsp; Frames: <span class="val">' + s.frames + '</span>' +
        ' &nbsp;|&nbsp; Last: <span class="val">' + s.lastSize + ' B</span>' +
        ' &nbsp;|&nbsp; Buffer: <span class="val">' + s.nonZero + '/8000</span>';
    }

    const r = await fetch('/data?t=' + Date.now());
    if (!r.ok) return;
    const d = new Uint8Array(await r.arrayBuffer());
    const cv  = document.getElementById('c');
    const ctx = cv.getContext('2d');

    if (isHires) {
      // 320x200 1-bit: 1 byte = 8 pixels
      const img = ctx.createImageData(320, 200);
      for (let by = 0; by < 200; by++) {
        for (let bx = 0; bx < 40; bx++) {
          const byte = d[by * 40 + bx];
          for (let bit = 7; bit >= 0; bit--) {
            const px = bx * 8 + (7 - bit);
            const v  = (byte >> bit) & 1 ? 255 : 0;
            const idx = (by * 320 + px) * 4;
            img.data[idx]   = v;
            img.data[idx+1] = v;
            img.data[idx+2] = v;
            img.data[idx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0);
    } else {
      // 160x200 2-bit
      const img = ctx.createImageData(160, 200);
      for (let i = 0; i < 32000; i++) {
        let bIdx = Math.floor(i / 4);
        let bit  = (3 - (i % 4)) * 2;
        let v    = palMC[(d[bIdx] >> bit) & 3];
        img.data[i * 4]     = v;
        img.data[i * 4 + 1] = v;
        img.data[i * 4 + 2] = v;
        img.data[i * 4 + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
    }
  } catch(e) {
    console.log('Fetch error:', e);
  }
  if (running) setTimeout(upd, 150);
}
upd();
</script>
</body></html>
)rawhtml";
  server.send(200, "text/html", html);
}

// --- MJPEG Stream Functions ---

// Read a line from the stream (up to \n), with timeout
String readStreamLine(WiFiClient& client, unsigned long timeoutMs = 3000) {
  String line = "";
  unsigned long start = millis();
  while (millis() - start < timeoutMs) {
    if (client.available()) {
      char c = client.read();
      if (c == '\n') return line;
      if (c != '\r') line += c;
    } else {
      delay(1);
    }
  }
  return line;
}

// Connect to the MJPEG stream and extract boundary string
bool connectToStream() {
  Serial.println("[MJPG] Connecting to stream...");
  
  if (!mjpgClient.connect(streamHost, streamPort)) {
    Serial.println("[MJPG] Connection failed!");
    return false;
  }

  // Send HTTP GET request
  mjpgClient.print("GET ");
  mjpgClient.print(streamPath);
  mjpgClient.println(" HTTP/1.1");
  mjpgClient.print("Host: ");
  mjpgClient.println(streamHost);
  mjpgClient.println("Connection: keep-alive");
  mjpgClient.println();

  // Read HTTP response headers
  unsigned long start = millis();
  while (millis() - start < 5000) {
    if (mjpgClient.available()) break;
    delay(10);
  }

  if (!mjpgClient.available()) {
    Serial.println("[MJPG] No response from server");
    mjpgClient.stop();
    return false;
  }

  // Parse response headers to find boundary
  boundary = "";
  while (mjpgClient.connected() && mjpgClient.available()) {
    String line = readStreamLine(mjpgClient);
    Serial.println("[HDR] " + line);
    
    if (line.length() == 0) break; // Empty line = end of headers

    // Look for boundary in Content-Type header
    if (line.startsWith("Content-Type:") || line.startsWith("content-type:")) {
      int bIdx = line.indexOf("boundary=");
      if (bIdx >= 0) {
        boundary = line.substring(bIdx + 9);
        boundary.trim();
        // Remove quotes if present
        if (boundary.startsWith("\"")) boundary = boundary.substring(1);
        if (boundary.endsWith("\""))   boundary = boundary.substring(0, boundary.length() - 1);
      }
    }
  }

  if (boundary.length() == 0) {
    Serial.println("[MJPG] WARNING: No boundary found in headers, using default");
    boundary = "frame";  // Common default for VLC
  }

  Serial.println("[MJPG] Connected! Boundary: '" + boundary + "'");
  return true;
}

// Read one JPEG frame from the MJPEG stream
// Strategy: directly scan for JPEG SOI (0xFF 0xD8) and EOI (0xFF 0xD9) markers
// This is more robust than boundary parsing since it works regardless of
// the multipart framing format used by the server.
size_t readOneFrame() {
  if (!mjpgClient.connected()) return 0;

  // 1. Scan byte-by-byte for JPEG SOI marker (0xFF 0xD8)
  bool foundSOI = false;
  unsigned long soiStart = millis();
  uint8_t prev = 0;
  int skipped = 0;

  while (millis() - soiStart < 5000) {
    if (!mjpgClient.connected()) return 0;
    if (!mjpgClient.available()) { delay(1); continue; }
    
    uint8_t b = mjpgClient.read();
    
    // Debug: print first 40 bytes we see (to understand stream format)
    if (skipped < 40 && frameCount == 0) {
      Serial.printf("%02X ", b);
      if (skipped == 39) Serial.println(" ...");
    }
    
    if (prev == 0xFF && b == 0xD8) {
      // Found JPEG Start Of Image
      temp_jpg_buffer[0] = 0xFF;
      temp_jpg_buffer[1] = 0xD8;
      foundSOI = true;
      break;
    }
    prev = b;
    skipped++;
  }

  if (!foundSOI) {
    Serial.printf("[MJPG] SOI not found after %d bytes / %lu ms\n", skipped, millis() - soiStart);
    return 0;
  }

  if (frameCount == 0) {
    Serial.printf("[MJPG] Found SOI after skipping %d bytes\n", skipped);
  }

  // 2. Read JPEG data until EOI marker (0xFF 0xD9)
  size_t bytesRead = 2;  // We already have FF D8
  prev = 0xD8;
  unsigned long eoiStart = millis();
  
  while (bytesRead < sizeof(temp_jpg_buffer) - 1 && millis() - eoiStart < 5000) {
    if (!mjpgClient.connected()) {
      Serial.println("[MJPG] Disconnected while reading frame");
      return 0;
    }
    if (!mjpgClient.available()) { delay(1); continue; }
    
    // Read in chunks for speed when data is available
    if (prev != 0xFF) {
      // Fast path: read a chunk
      size_t avail = mjpgClient.available();
      size_t toRead = min(avail, sizeof(temp_jpg_buffer) - bytesRead);
      if (toRead > 0) {
        size_t got = mjpgClient.read(temp_jpg_buffer + bytesRead, toRead);
        // Scan the chunk for EOI marker
        for (size_t i = 0; i < got; i++) {
          if (i == 0 && prev == 0xFF && temp_jpg_buffer[bytesRead] == 0xD9) {
            // EOI found at chunk boundary
            bytesRead += 1;
            return bytesRead;
          }
          if (i > 0 && temp_jpg_buffer[bytesRead + i - 1] == 0xFF && 
              temp_jpg_buffer[bytesRead + i] == 0xD9) {
            // EOI found within chunk
            bytesRead += i + 1;
            return bytesRead;
          }
        }
        prev = temp_jpg_buffer[bytesRead + got - 1];
        bytesRead += got;
      }
    } else {
      // Previous byte was 0xFF, read one byte to check for 0xD9
      uint8_t b = mjpgClient.read();
      temp_jpg_buffer[bytesRead++] = b;
      if (b == 0xD9) {
        return bytesRead;  // Found EOI!
      }
      prev = b;
    }
  }

  Serial.printf("[MJPG] EOI not found, got %d bytes\n", bytesRead);
  // Return what we have anyway - the decoder might still handle it
  return bytesRead;
}

// --- Arduino Setup & Loop ---

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== C64 LIVE ENCODER ===");

  // Clear buffer
  memset(c64_buffer, 0, sizeof(c64_buffer));

  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nIP: " + WiFi.localIP().toString());

  // Setup JPEG decoder
  TJpgDec.setJpgScale(1);
  TJpgDec.setCallback(process_output);

  // Setup web server
  server.on("/", handleRoot);
  server.on("/data", handleData);
  server.on("/stats", handleStats);
  server.on("/setmode", handleSetMode);
  server.begin();
  Serial.println("Web server started");
}

void loop() {
  server.handleClient();

  // Connect to stream if not connected
  if (!streamConnected) {
    if (connectToStream()) {
      streamConnected = true;
    } else {
      delay(2000);  // Wait before retry
      return;
    }
  }

  // Check if still connected
  if (!mjpgClient.connected()) {
    Serial.println("[MJPG] Stream disconnected, reconnecting...");
    mjpgClient.stop();
    streamConnected = false;
    return;
  }

  // Try to read a frame if data is available
  if (mjpgClient.available()) {
    size_t frameSize = readOneFrame();

    if (frameSize > 0) {
      lastFrameSize = frameSize;

      // Debug: print first 8 bytes of JPEG
      Serial.printf("[MJPG] Frame %d: %d bytes, header: ", frameCount + 1, frameSize);
      for (int i = 0; i < min((size_t)8, frameSize); i++) {
        Serial.printf("%02X ", temp_jpg_buffer[i]);
      }
      Serial.println();

      // Verify it looks like a JPEG (starts with FF D8)
      if (frameSize > 2 && temp_jpg_buffer[0] == 0xFF && temp_jpg_buffer[1] == 0xD8) {
        // Decode the JPEG into c64_buffer via the callback
        uint16_t w = 0, h = 0;
        TJpgDec.getJpgSize(&w, &h, temp_jpg_buffer, frameSize);
        Serial.printf("[MJPG] JPEG dimensions: %dx%d\n", w, h);

        JRESULT res = TJpgDec.drawJpg(0, 0, temp_jpg_buffer, frameSize);
        lastDecodeResult = (uint32_t)res;

        if (res == JDR_OK) {
          frameCount++;
          // Count non-zero bytes for debug
          uint32_t nz = 0;
          for (int i = 0; i < 8000; i++) {
            if (c64_buffer[i] != 0) nz++;
          }
          nonZeroPixels = nz;
          Serial.printf("[MJPG] Decode OK! Non-zero bytes: %d/8000\n", nz);
        } else {
          Serial.printf("[MJPG] Decode FAILED: error %d\n", res);
        }
      } else {
        Serial.println("[MJPG] Invalid JPEG - bad header!");
      }
    }
  }
}
