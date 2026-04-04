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
enum StreamMode { M_MC_GRAY, M_HR_GRAY, M_MC_COLOR, M_HR_COLOR };
StreamMode currentMode = M_MC_COLOR;
#define IS_HIRES (currentMode == M_HR_GRAY || currentMode == M_HR_COLOR)
#define IS_COLOR (currentMode == M_MC_COLOR || currentMode == M_HR_COLOR)

// --- Buffers ---
uint8_t c64_buffer[20000];          // Two 10000 byte buffers (double buffering)
volatile uint8_t active_buffer = 0; // The buffer currently being read by the web server (0 or 1)
uint8_t* render_buffer = c64_buffer + 10000; // Pointer to the inactive buffer for writing
uint8_t temp_jpg_buffer[32000];     // Buffer for one JPEG frame (increased from 25K)
uint8_t color_buffer[64000];        // Intermediate mapped colors

// --- Coordinate Mapping Tables ---
int16_t mapX_start[1280];
int16_t mapX_end[1280];
int16_t mapY_start[1024];
int16_t mapY_end[1024];

// --- MJPEG stream state ---
WiFiClient mjpgClient;
bool       streamConnected = false;
String     boundary = "";

// --- Stats for debug ---
volatile uint32_t frameCount = 0;
volatile uint32_t lastFrameSize = 0;
volatile uint32_t lastDecodeResult = 0;
volatile uint32_t nonZeroPixels = 0;
volatile uint64_t totalBytes = 0;

// --- Image Adjustments ---
float imgContrast = 1.0f;
int16_t contrast_fp = 256;
uint8_t jpgScale = 1;
uint8_t ditherStrength = 4;  // Bayer dither intensity: 0=off, 1-8
uint16_t currentJpgWidth = 320;
uint16_t currentJpgHeight = 200;

// C64 Pepto Palette (RGB888)
const uint8_t c64_pal_r[16] = {0,255,136,170,204,0,  0,  238,221,102,255,51,119,170,0,  187};
const uint8_t c64_pal_g[16] = {0,255,0,  255,68, 204,0,  238,136,68, 119,51,119,255,136,187};
const uint8_t c64_pal_b[16] = {0,255,0,  238,204,85, 170,119,85, 0,  119,51,119,102,255,187};

// Bayer 8x8 ordered dither matrix (centered, range -32..+31)
const int8_t bayer8x8[8][8] = {
    {-32,  0, -24,  8, -30,  2, -22, 10},
    { 16,-16,  24, -8,  18,-14,  26, -6},
    {-20, 12, -28,  4, -18, 14, -26,  6},
    { 28, -4,  20,-12,  30, -2,  22,-10},
    {-29,  3, -21, 11, -31,  1, -23,  9},
    { 19,-13,  27, -5,  17,-15,  25, -7},
    {-17, 15, -25,  7, -19, 13, -27,  5},
    { 31, -1,  23, -9,  29, -3,  21,-11}
};

inline uint32_t manhattanDist(uint8_t c1, uint8_t c2) {
  return abs(c64_pal_r[c1] - c64_pal_r[c2]) + abs(c64_pal_g[c1] - c64_pal_g[c2]) + abs(c64_pal_b[c1] - c64_pal_b[c2]);
}

inline uint8_t rgb565_to_c64(uint16_t p) {
  int r = (p >> 8) & 0xF8;
  int g = (p >> 3) & 0xFC;
  int b = (p << 3) & 0xF8;
  
  if (contrast_fp != 256) {
    r = (int)((((r - 128) * contrast_fp) >> 8) + 128);
    g = (int)((((g - 128) * contrast_fp) >> 8) + 128);
    b = (int)((((b - 128) * contrast_fp) >> 8) + 128);
    if(r<0) r=0; if(r>255) r=255;
    if(g<0) g=0; if(g>255) g=255;
    if(b<0) b=0; if(b>255) b=255;
  }
  
  uint32_t best_dist = 0xFFFFFFFF;
  uint8_t best_col = 0;
  for (int i=0; i<16; i++) {
    uint32_t dist = abs(r - c64_pal_r[i]) + abs(g - c64_pal_g[i]) + abs(b - c64_pal_b[i]);
    if (dist < best_dist) {
      best_dist = dist;
      best_col = i;
    }
  }
  return best_col;
}

void packC64Frame() {
  uint8_t* bitmap_ram = render_buffer;
  uint8_t* screen_ram = render_buffer + 8000;
  uint8_t* color_ram  = render_buffer + 9000;
  
  uint8_t bgColor = 0; // Black global background
  
  for (int cy = 0; cy < 25; cy++) {
    for (int cx = 0; cx < 40; cx++) {
      int cellIdx = cy * 40 + cx;
      
      if (IS_HIRES) {
        int counts[16] = {0};
        for (int py=0; py<8; py++) {
          for (int px=0; px<8; px++) {
            counts[color_buffer[(cy*8 + py)*320 + (cx*8 + px)]]++;
          }
        }
        
        uint8_t bg = 0, fg = 1;
        int max_bg = -1, max_fg = -1;
        for (int i=0; i<16; i++) {
          if (counts[i] > max_bg) { max_fg = max_bg; fg = bg; max_bg = counts[i]; bg = i; }
          else if (counts[i] > max_fg) { max_fg = counts[i]; fg = i; }
        }
        
        screen_ram[cellIdx] = (fg << 4) | (bg & 0x0F);
        
        for (int py=0; py<8; py++) {
          uint8_t byte = 0;
          for (int px=0; px<8; px++) {
            uint8_t c = color_buffer[(cy*8 + py)*320 + (cx*8 + px)];
            int32_t dbg = (int32_t)manhattanDist(c, bg);
            int32_t dfg = (int32_t)manhattanDist(c, fg);
            int32_t bayer = (ditherStrength > 0) ? (int32_t)bayer8x8[py & 7][px & 7] * ditherStrength : 0;
            
            if (dfg - bayer < dbg + bayer) byte |= (1 << (7 - px));
          }
          bitmap_ram[cellIdx * 8 + py] = byte;
        }
      } else {
        int counts[16] = {0};
        for (int py=0; py<8; py++) {
          for (int px=0; px<4; px++) {
            counts[color_buffer[(cy*8 + py)*160 + (cx*4 + px)]]++;
          }
        }
        
        counts[bgColor] = -1; 
        
        uint8_t c1=0, c2=0, c3=0;
        int m1=-1, m2=-1, m3=-1;
        for(int i=0;i<16;i++){
          if(counts[i]>m1){ m3=m2;c3=c2; m2=m1;c2=c1; m1=counts[i];c1=i; }
          else if(counts[i]>m2){ m3=m2;c3=c2; m2=counts[i];c2=i; }
          else if(counts[i]>m3){ m3=counts[i];c3=i; }
        }
        if(m2==-1) c2=c1;
        if(m3==-1) c3=c1;
        
        screen_ram[cellIdx] = (c1 << 4) | (c2 & 0x0F);
        color_ram[cellIdx]  = c3;
        
        for (int py=0; py<8; py++) {
          uint8_t byte = 0;
          for (int px=0; px<4; px++) {
            uint8_t c = color_buffer[(cy*8 + py)*160 + (cx*4 + px)];
            int32_t d0 = (int32_t)manhattanDist(c, bgColor);
            int32_t d1 = (int32_t)manhattanDist(c, c1);
            int32_t d2 = (int32_t)manhattanDist(c, c2);
            int32_t d3 = (int32_t)manhattanDist(c, c3);
            
            // Partial sort: bring best two candidates to front
            int32_t dists[4] = {d0, d1, d2, d3};
            uint8_t slots[4] = {0, 1, 2, 3};
            for (int a = 0; a < 2; a++) {
              for (int b = a+1; b < 4; b++) {
                if (dists[b] < dists[a]) {
                  int32_t td = dists[a]; dists[a] = dists[b]; dists[b] = td;
                  uint8_t ts = slots[a]; slots[a] = slots[b]; slots[b] = ts;
                }
              }
            }
            
            uint8_t bits;
            if (ditherStrength > 0) {
              // Bayer 8x8: dither between nearest and second-nearest palette color
              int gx = (cx * 4 + px) & 7;
              int gy = (cy * 8 + py) & 7;
              int32_t bayerVal = (int32_t)bayer8x8[gy][gx] * ditherStrength;
              bits = (dists[1] - bayerVal < dists[0] + bayerVal) ? slots[1] : slots[0];
            } else {
              bits = slots[0];
            }
            
            byte |= (bits << ((3 - px) * 2));
          }
          bitmap_ram[cellIdx * 8 + py] = byte;
        }
      }
    }
  }
}

// Legacy Gray functions
inline int16_t get_gray(uint16_t p) {
  uint8_t r = (p >> 8) & 0xF8;
  uint8_t g = (p >> 3) & 0xFC;
  uint8_t b = (p << 3) & 0xF8;
  int16_t gray = ((r + g + b) * 85) >> 8;
  if (contrast_fp != 256) {
    gray = (int16_t)((((int32_t)gray - 128) * contrast_fp) >> 8) + 128;
    if (gray < 0) gray = 0;
    if (gray > 255) gray = 255;
  }
  return gray;
}

inline void drawHiResPixel(int x, int y, int16_t gray) {
  if (x >= 320 || y >= 200) return;
  int16_t dithered = (ditherStrength > 0) ? gray + bayer8x8[y & 7][x & 7] : gray;
  if (dithered >= 128) {
    int cellIdx = (y / 8) * 40 + (x / 8);
    int py = (y % 8);
    int bitPos = 7 - (x % 8);
    render_buffer[cellIdx * 8 + py] |= (1 << bitPos);
  }
}

inline void drawMultiColorPixel(int x, int y, int16_t gray) {
  if (x >= 160 || y >= 200) return;
  int16_t dithered = (ditherStrength > 0) ? gray + bayer8x8[y & 7][x & 7] : gray;
  if (dithered < 0) dithered = 0;
  if (dithered > 255) dithered = 255;
  uint8_t level = dithered >> 6;
  if (level) {
    int cellIdx = (y / 8) * 40 + (x / 4);
    int py = (y % 8);
    int bitPos = (3 - (x % 4)) * 2;
    render_buffer[cellIdx * 8 + py] |= (level << bitPos);
  }
}

// TJpg_Decoder callback
bool process_output(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t* bitmap) {
  if (currentJpgWidth == 0 || currentJpgHeight == 0) return true;

  for (int j = 0; j < h; j++) {
    int currY = y + j;
    if (currY >= currentJpgHeight || currY >= 1024) continue;
    
    int startY = mapY_start[currY];
    int endY   = mapY_end[currY];
    if (startY == endY) continue; 

    for (int i = 0; i < w; i++) {
      int currX = x + i;
      if (currX >= currentJpgWidth || currX >= 1280) continue;
      
      int startX = mapX_start[currX];
      int endX   = mapX_end[currX];
      if (startX == endX) continue; 

      if (IS_COLOR) {
        uint8_t c64col = rgb565_to_c64(bitmap[i + j * w]);
        int wTarget = IS_HIRES ? 320 : 160;
        for (int ty = startY; ty < endY; ty++) {
          for (int tx = startX; tx < endX; tx++) {
            if (ty < 200 && tx < wTarget) {
              color_buffer[ty * wTarget + tx] = c64col;
            }
          }
        }
      } else {
        int16_t gray = get_gray(bitmap[i + j * w]);
        for (int ty = startY; ty < endY; ty++) {
          for (int tx = startX; tx < endX; tx++) {
            if (IS_HIRES) drawHiResPixel(tx, ty, gray);
            else          drawMultiColorPixel(tx, ty, gray);
          }
        }
      }
    }
  }
  return true;
}

// --- Web Server Handlers ---

void handleData() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.setContentLength(10000);
  server.send(200, "application/octet-stream", "");
  server.sendContent((const char*)(c64_buffer + active_buffer * 10000), 10000);
}

void handleSetMode() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("m")) {
    String m = server.arg("m");
    if (m == "mc_gray") currentMode = M_MC_GRAY;
    else if (m == "hr_gray") currentMode = M_HR_GRAY;
    else if (m == "mc_color") currentMode = M_MC_COLOR;
    else if (m == "hr_color") currentMode = M_HR_COLOR;
    memset(c64_buffer, 0, sizeof(c64_buffer));
    server.send(200, "text/plain", m);
  } else {
    server.send(400, "text/plain", "Missing ?m= param");
  }
}

void handleSetContrast() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("c")) {
    imgContrast = server.arg("c").toFloat();
    contrast_fp = (int16_t)(imgContrast * 256.0f);
    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Missing ?c= param");
  }
}

void handleSetDither() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("d")) {
    int d = server.arg("d").toInt();
    if (d >= 0 && d <= 8) {
      ditherStrength = (uint8_t)d;
      server.send(200, "text/plain", "OK");
    } else {
      server.send(400, "text/plain", "Invalid value (0-8)");
    }
  } else {
    server.send(400, "text/plain", "Missing ?d= param");
  }
}

void handleSetScale() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("s")) {
    int s = server.arg("s").toInt();
    if (s == 1 || s == 2 || s == 4 || s == 8) {
      jpgScale = s;
      TJpgDec.setJpgScale(jpgScale);
      memset(c64_buffer, 0, sizeof(c64_buffer)); // clear buffer on scale change
      server.send(200, "text/plain", "OK");
    } else {
      server.send(400, "text/plain", "Invalid scale");
    }
  } else {
    server.send(400, "text/plain", "Missing ?s= param");
  }
}

void handleStats() {
  // Count non-zero bytes for debug
  uint32_t nz = 0;
  uint8_t* current_buf = c64_buffer + active_buffer * 10000;
  for (int i = 0; i < 10000; i++) {
    if (current_buf[i] != 0) nz++;
  }
  nonZeroPixels = nz;
  String mStr = "mc_color";
  if (currentMode == M_MC_GRAY) mStr = "mc_gray";
  else if (currentMode == M_HR_GRAY) mStr = "hr_gray";
  else if (currentMode == M_HR_COLOR) mStr = "hr_color";
  
  String json = "{\"frames\":" + String(frameCount) +
                ",\"mode\":\"" + mStr + "\"" +
                ",\"lastSize\":" + String(lastFrameSize) +
                ",\"decode\":" + String(lastDecodeResult) +
                ",\"nonZero\":" + String(nz) +
                ",\"connected\":" + String(streamConnected ? 1 : 0) +
                ",\"contrast\":" + String(imgContrast, 2) +
                ",\"scale\":" + String(jpgScale) +
                ",\"dither\":" + String(ditherStrength) +
                ",\"totalKB\":" + String((uint32_t)(totalBytes / 1024)) + "}";
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
  .slider-container {
    display: flex; align-items: center; justify-content: center; gap: 15px; margin-top: 12px; font-size: 13px; color: #a0b4ff;
    background: rgba(0,0,0,0.2); padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(100,140,255,0.2);
  }
  input[type=range] {
    -webkit-appearance: none; width: 140px; background: rgba(100,140,255,0.2);
    height: 6px; border-radius: 3px; outline: none;
  }
  input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none;
    width: 16px; height: 16px; border-radius: 50%;
    background: #6c8cff; cursor: pointer; box-shadow: 0 0 10px rgba(100,140,255,0.5);
  }
  select {
    appearance: none; -webkit-appearance: none;
    background: rgba(100,140,255,0.2);
    color: #a0ff90; padding: 4px 12px;
    border: 1px solid rgba(100,140,255,0.4); border-radius: 4px;
    font-family: inherit; font-size: 13px; font-weight: bold;
    cursor: pointer; outline: none;
  }
  select option { background: #16213e; color: #a0b4ff; }
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
    <span class="mode-badge mc" id="badge" style="display:none;"></span>
  </div>
  <canvas id="c" width="160" height="200"></canvas>
  <div class="controls">
    <select id="mode-sel" onchange="toggleMode()" style="padding:10px; font-size:14px; font-family:'Share Tech Mono'; background:#333; color:#fff; border:1px solid #666; cursor:pointer;">
      <option value="mc_gray">MULTI-COLOR GRAYSCALE</option>
      <option value="hr_gray">HI-RES GRAYSCALE</option>
      <option value="mc_color" selected>MULTI-COLOR COLOR</option>
      <option value="hr_color">HI-RES COLOR</option>
    </select>
    <button onclick="save('PRG')">&#x25B6; PRG</button>
    <button onclick="save('KOA')">&#x25B6; KOA</button>
  </div>
  <div class="slider-container">
    <span>CONTRAST: <span id="cval" class="val">1.0</span></span>
    <input type="range" id="contrast" min="0.5" max="3.0" step="0.1" value="1.0" style="width:100px" oninput="updateContrastText()" onchange="sendContrast()">
    <span style="margin-left:8px">SCALE:</span>
    <select id="scale" onchange="sendScale()">
      <option value="1">1:1 (HQ)</option>
      <option value="2">1:2 (FAST)</option>
      <option value="4">1:4 (FASTER)</option>
      <option value="8">1:8 (FASTEST)</option>
    </select>
    <span style="margin-left:8px">DITHER:</span>
    <input type="range" id="dither" min="0" max="8" step="1" value="4" style="width:80px" oninput="updateDitherText()" onchange="sendDither()">
    <span id="dval" class="val">4</span>
  </div>
  <div id="stats">
    <span class="dot" id="dot"></span>
    <span id="stxt">Connecting...</span>
  </div>
</div>

<script>
const c64Pal = [
  [0,0,0], [255,255,255], [136,0,0], [170,255,238],
  [204,68,204], [0,204,85], [0,0,170], [238,238,119],
  [221,136,85], [102,68,0], [255,119,119], [51,51,51],
  [119,119,119], [170,255,102], [0,136,255], [187,187,187]
];
let running = true;
let isHires = false;  // dynamic tracking based on mode prefix
let currentClientMode = 'mc_color';

let lastStatsTime = 0;
let lastFrames = 0;
let lastKB = 0;
let currentFPS = 0;
let currentKBs = 0;

// --- Canvas resize helper ---
function resizeCanvas(hires) {
  const cv = document.getElementById('c');
  cv.width  = hires ? 320 : 160;
  cv.height = 200;
  cv.style.height = '400px'; 
  cv.style.width  = '640px';
}

// --- Mode toggle ---
async function toggleMode() {
  const target = document.getElementById('mode-sel').value;
  try {
    const r = await fetch('/setmode?m=' + target + '&t=' + Date.now());
    if (r.ok) {
      currentClientMode = target;
      updateModeUI();
    }
  } catch(e) { console.log('setmode error:', e); }
}

function updateModeUI() {
  document.getElementById('mode-sel').value = currentClientMode;
  isHires = currentClientMode.startsWith('hr_');
  resizeCanvas(isHires);
}

// --- Adjustments ---
function updateContrastText() {
  document.getElementById('cval').innerText = parseFloat(document.getElementById('contrast').value).toFixed(1);
}
async function sendContrast() {
  const c = document.getElementById('contrast').value;
  try { await fetch('/setcontrast?c=' + c); } catch(e) {}
}
async function sendScale() {
  const s = document.getElementById('scale').value;
  try { await fetch('/setscale?s=' + s); } catch(e) {}
}
function updateDitherText() {
  document.getElementById('dval').innerText = document.getElementById('dither').value;
}
async function sendDither() {
  const d = document.getElementById('dither').value;
  try { await fetch('/setdither?d=' + d); } catch(e) {}
}

// --- Save ---
async function save(t) {
  const r = await fetch('/data?t=' + Date.now());
  const bmp = new Uint8Array(await r.arrayBuffer());
  let f;
  if (t === 'KOA') {
    f = new Uint8Array(10003);
    f[0] = 0; f[1] = 0x60;
    f.set(bmp.subarray(0, 8000), 2);
    for (let i = 0; i < 1000; i++) {
      f[8002 + i] = bmp[8000 + i];
      f[9002 + i] = bmp[9000 + i];
    }
    f[10002] = 0; // BG Color (Black)
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
    for (let i = 0; i < 1000; i++) f[113 + i] = bmp[8000 + i];
    
    // Embed Color RAM source data (at $0C58, offset 1113)
    for (let i = 0; i < 1000; i++) f[1113 + i] = bmp[9000 + i];

    // Bitmap data always at $2000 (offset 6145 from file start)
    f.set(bmp.subarray(0, 8000), 6145);
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
    // Fetch stats and data in parallel
    const srPromise = fetch('/stats?t=' + Date.now());
    const rPromise = fetch('/data?t=' + Date.now());
    
    const [sr, r] = await Promise.all([srPromise, rPromise]);

    if (sr.ok) {
      const s = await sr.json();
      if (s.mode && s.mode !== currentClientMode) {
        currentClientMode = s.mode;
        updateModeUI();
      }
      if (s.contrast !== undefined && document.activeElement !== document.getElementById('contrast')) {
        document.getElementById('contrast').value = s.contrast;
        updateContrastText();
      }
      if (s.scale !== undefined && document.activeElement !== document.getElementById('scale')) {
        document.getElementById('scale').value = s.scale;
      }
      if (s.dither !== undefined && document.activeElement !== document.getElementById('dither')) {
        document.getElementById('dither').value = s.dither;
        updateDitherText();
      }

      const now = Date.now();
      if (lastStatsTime > 0) {
        const dt = (now - lastStatsTime) / 1000.0;
        if (dt >= 1.0) { // Update rates ~every 1 sec
          currentFPS = ((s.frames - lastFrames) / dt).toFixed(1);
          currentKBs = ((s.totalKB - lastKB) / dt).toFixed(1);
          lastStatsTime = now;
          lastFrames = s.frames;
          lastKB = s.totalKB;
        }
      } else {
        lastStatsTime = now;
        lastFrames = s.frames;
        lastKB = s.totalKB;
      }

      const dot  = document.getElementById('dot');
      const stxt = document.getElementById('stxt');
      dot.className = s.connected ? 'dot on' : 'dot';
      stxt.innerHTML =
        'Status: ' + (s.connected ? '<span class="val">LIVE</span>' : '<span class="err">DISCONNECTED</span>') +
        ' &nbsp;|&nbsp; FPS: <span class="val">' + Math.max(0, currentFPS) + '</span>' +
        ' &nbsp;|&nbsp; <span class="val">' + Math.max(0, currentKBs) + '</span> KB/s' +
        ' &nbsp;|&nbsp; Total: <span class="val">' + s.totalKB + '</span> KB';
    }

    if (!r.ok) return;
    const d = new Uint8Array(await r.arrayBuffer());
    const cv  = document.getElementById('c');
    const ctx = cv.getContext('2d');

    if (isHires) {
      const img = ctx.createImageData(320, 200);
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8);
        let py = by % 8;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx;
          const byte = d[cellIdx * 8 + py];
          let screenByte = d[8000 + cellIdx];
          let fgCol = c64Pal[screenByte >> 4];
          let bgCol = c64Pal[screenByte & 0x0F];
          
          for (let bit = 7; bit >= 0; bit--) {
            const px = bx * 8 + (7 - bit);
            const isFg = (byte >> bit) & 1;
            const c = isFg ? fgCol : bgCol;
            const idx = (by * 320 + px) * 4;
            img.data[idx]   = c[0];
            img.data[idx+1] = c[1];
            img.data[idx+2] = c[2];
            img.data[idx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0);
    } else {
      const img = ctx.createImageData(160, 200);
      let bgCol = c64Pal[0]; // Global Black
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8);
        let py = by % 8;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx;
          let byte = d[cellIdx * 8 + py];
          let screenByte = d[8000 + cellIdx];
          let colorByte  = d[9000 + cellIdx];
          let cols = [ bgCol, c64Pal[screenByte >> 4], c64Pal[screenByte & 0x0F], c64Pal[colorByte & 0x0F] ];
          
          for (let px = 0; px < 4; px++) {
            let col = cols[(byte >> ((3 - px) * 2)) & 3];
            let outIdx = (by * 160 + bx * 4 + px) * 4;
            img.data[outIdx]   = col[0];
            img.data[outIdx+1] = col[1];
            img.data[outIdx+2] = col[2];
            img.data[outIdx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0);
    }
  } catch(e) {
    console.log('Fetch error:', e);
  }
  if (running) setTimeout(upd, 70);
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
    //Serial.println("[HDR] " + line);
    
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
    //if (skipped < 40 && frameCount == 0) {
    //  Serial.printf("%02X ", b);
    //  if (skipped == 39) Serial.println(" ...");
    //}
    
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
  server.on("/setcontrast", handleSetContrast);
  server.on("/setdither", handleSetDither);
  server.on("/setscale", handleSetScale);
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
      totalBytes += frameSize;

      // Debug: print first 8 bytes of JPEG
      //Serial.printf("[MJPG] Frame %d: %d bytes, header: ", frameCount + 1, frameSize);
      //for (int i = 0; i < min((size_t)8, frameSize); i++) {
      //  Serial.printf("%02X ", temp_jpg_buffer[i]);
      //}
      //Serial.println();

      // Verify it looks like a JPEG (starts with FF D8)
      if (frameSize > 2 && temp_jpg_buffer[0] == 0xFF && temp_jpg_buffer[1] == 0xD8) {
        // Decode the JPEG into c64_buffer via the callback
        uint16_t w = 0, h = 0;
        TJpgDec.getJpgSize(&w, &h, temp_jpg_buffer, frameSize);
        currentJpgWidth = w / jpgScale;
        currentJpgHeight = h / jpgScale;
        //Serial.printf("[MJPG] JPEG dimensions: %dx%d (scaled: %dx%d)\n", w, h, currentJpgWidth, currentJpgHeight);

        // Precalculate mapping tables
        int targetW = IS_HIRES ? 320 : 160;
        int targetH = 200;
        for (int i = 0; i < currentJpgWidth && i < 1280; i++) {
          mapX_start[i] = (i * targetW) / currentJpgWidth;
          mapX_end[i]   = ((i + 1) * targetW) / currentJpgWidth;
        }
        for (int i = 0; i < currentJpgHeight && i < 1024; i++) {
          mapY_start[i] = (i * targetH) / currentJpgHeight;
          mapY_end[i]   = ((i + 1) * targetH) / currentJpgHeight;
        }

        // Setup render buffer and clear it BEFORE decoding starts (so bitwise OR works)
        render_buffer = c64_buffer + (1 - active_buffer) * 10000;
        memset(render_buffer, 0, 10000);

        JRESULT res = TJpgDec.drawJpg(0, 0, temp_jpg_buffer, frameSize);
        lastDecodeResult = (uint32_t)res;

        if (res == JDR_OK) {
          if (IS_COLOR) {
            packC64Frame();
          } else {
            uint8_t* screen_ram = render_buffer + 8000;
            uint8_t* color_ram  = render_buffer + 9000;
            uint8_t staticScreen = IS_HIRES ? 0x10 : 0xBC; // 1:White fg, 0:Black bg (HR) OR B:DarkGrey, C:MedGrey (MC)
            memset(screen_ram, staticScreen, 1000);
            memset(color_ram, 1, 1000); // 1:White
          }
          frameCount++;
          
          uint32_t nz = 0;
          for (int i = 0; i < 10000; i++) {
            if (render_buffer[i] != 0) nz++;
          }
          nonZeroPixels = nz;
          
          // Flip the buffer so the web server serves the new frame!
          active_buffer = 1 - active_buffer;
        } else {
          Serial.printf("[MJPG] Decode FAILED: error %d\n", res);
        }
      } else {
        Serial.println("[MJPG] Invalid JPEG - bad header!");
      }
    }
  }
}
