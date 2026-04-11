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

static const char INDEX_HTML[] PROGMEM = R"rawhtml(
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
    display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 12px; font-size: 13px; color: #a0b4ff; flex-wrap: wrap;
    background: rgba(0,0,0,0.2); padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(100,140,255,0.2);
  }
  input[type=range] {
    -webkit-appearance: none; width: 80px; background: rgba(100,140,255,0.2);
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
      <option value="mc_color">MULTI-COLOR COLOR</option>
      <option value="hr_color">HI-RES COLOR</option>
      <option value="mc_fli">MULTI-COLOR FLI</option>
      <option value="mc_gray_fli">GRAYSCALE FLI</option>
      <option value="mc_gray_ifli">GRAYSCALE IFLI</option>
    </select>
    <button onclick="save('PRG')">&#x25B6; PRG</button>
    <button onclick="save('KOA')">&#x25B6; KOA</button>
    <button onclick="save('CRT')">&#x25B6; CRT</button>
  </div>
  <div class="slider-container">
    <span>CT: <span id="cval" class="val">1.0</span></span>
    <input type="range" id="contrast" min="0.5" max="3.0" step="0.1" value="1.0" oninput="updateContrastText()" onchange="sendContrast()">
    <span>BR: <span id="bval" class="val">0</span></span>
    <input type="range" id="brightness" min="-128" max="128" step="4" value="0" oninput="updateBrightnessText()" onchange="sendBrightness()">
    <span style="margin-left:4px">SCALE:</span>
    <select id="scale" onchange="sendScale()">
      <option value="1">1:1 (HQ)</option>
      <option value="2">1:2 (FAST)</option>
      <option value="4">1:4 (FASTER)</option>
      <option value="8">1:8 (FASTEST)</option>
    </select>
    <span style="margin-left:8px">RATIO:</span>
    <select id="scaling" onchange="sendScaling()">
      <option value="0">STRETCH</option>
      <option value="1">FIT</option>
      <option value="2">CROP</option>
    </select>
    <span style="margin-left:8px">BG (MC):</span>
    <select id="bgcolor" onchange="sendBg()" style="padding:4px">
      <option value="0">0:BLK</option><option value="1">1:WHT</option><option value="2">2:RED</option><option value="3:CYN">3:CYN</option>
      <option value="4">4:PUR</option><option value="5">5:GRN</option><option value="6">6:BLU</option><option value="7">7:YEL</option>
      <option value="8">8:ORG</option><option value="9">9:BRN</option><option value="10">10:LRD</option><option value="11">11:DGY</option>
      <option value="12">12:MGY</option><option value="13">13:LGN</option><option value="14">14:LBL</option><option value="15">15:LGY</option>
    </select>
    <span style="margin-left:8px">DITHER:</span>
    <select id="ditherType" onchange="sendDitherType()">
      <option value="0">NONE</option>
      <option value="1">BAYER 4x4</option>
      <option value="2" selected>BAYER 8x8</option>
      <option value="3">WHITE NOISE</option>
      <option value="4">BLUE NOISE</option>
      <option value="5">FLOYD-STEINBERG</option>
    </select>
    <span style="margin-left:4px">STR:</span>
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
let running = true, isHires = false, isFLI = false, isGrayFLI = false, isIFLI = false, currentClientMode = 'mc_color', currentBgColor = 0;
let lastStatsTime = 0, lastFrames = 0, lastKB = 0, currentFPS = 0, currentKBs = 0;

function resizeCanvas(hires) {
  const cv = document.getElementById('c');
  cv.width = hires ? 320 : 160; cv.height = 200;
  cv.style.height = '400px'; cv.style.width = '640px';
}
async function toggleMode() {
  const target = document.getElementById('mode-sel').value;
  try {
    const r = await fetch('/setmode?m=' + target + '&t=' + Date.now());
    if (r.ok) { currentClientMode = target; updateModeUI(); }
  } catch(e) { console.log('setmode error:', e); }
}
function updateModeUI() {
  document.getElementById('mode-sel').value = currentClientMode;
  isHires = currentClientMode.startsWith('hr_');
  isFLI = currentClientMode.includes('_fli');
  isGrayFLI = currentClientMode === 'mc_gray_fli';
  isIFLI = currentClientMode === 'mc_gray_ifli';
  resizeCanvas(isHires);
}
function updateContrastText() { document.getElementById('cval').innerText = parseFloat(document.getElementById('contrast').value).toFixed(1); }
function updateBrightnessText() { document.getElementById('bval').innerText = document.getElementById('brightness').value; }
async function sendContrast() { try { await fetch('/setcontrast?c=' + document.getElementById('contrast').value); } catch(e) {} }
async function sendBrightness() { try { await fetch('/setbrightness?b=' + document.getElementById('brightness').value); } catch(e) {} }
async function sendBg() { try { await fetch('/setbg?c=' + document.getElementById('bgcolor').value); } catch(e) {} }
async function sendScale() { try { await fetch('/setscale?s=' + document.getElementById('scale').value); } catch(e) {} }
async function sendScaling() { try { await fetch('/setscaling?s=' + document.getElementById('scaling').value); } catch(e) {} }
function updateDitherText() { document.getElementById('dval').innerText = document.getElementById('dither').value; }
async function sendDither() { try { await fetch('/setdither?d=' + document.getElementById('dither').value); } catch(e) {} }
async function sendDitherType() { try { await fetch('/setdithertype?t=' + document.getElementById('ditherType').value); } catch(e) {} }

async function save(t) {
  const r = await fetch('/data?t=' + Date.now()); const bmp = new Uint8Array(await r.arrayBuffer());
  let f;
  if (t === 'KOA') {
    f = new Uint8Array(10003); f[0] = 0; f[1] = 0x60; f.set(bmp.subarray(0, 8000), 2);
    for (let i = 0; i < 1000; i++) { f[8002 + i] = bmp[8000 + i]; f[9002 + i] = bmp[9000 + i]; }
    f[10002] = currentBgColor; download(f, 'img.koa'); return;
  }
  if (isIFLI) {
    f = new Uint8Array(49155); f[0] = 1; f[1] = 8; f.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
    const asm = [0x78,0xA9,0x34,0x85,0x01,0xA9,0x00,0x85,0xFC,0x85,0xFE,0xA9,0x80,0x85,0xFD,0xA9,0xC0,0x85,0xFF,0xA2,0x40,0xA0,0x00,0xB1,0xFC,0x91,0xFE,0xC8,0xD0,0xF9,0xE6,0xFD,0xE6,0xFF,0xCA,0xD0,0xF2,0xA9,0x35,0x85,0x01,0xA2,0x00,0x8A,0x29,0x07,0x09,0x38,0x9D,0x00,0x09,0x8A,0x29,0x07,0x0A,0x0A,0x0A,0x0A,0x09,0x08,0x9D,0x00,0x0A,0xE8,0xE0,0xC8,0xD0,0xE7,0xA2,0x00,0xBD,0x00,0x10,0x9D,0x00,0xD8,0xBD,0xFA,0x10,0x9D,0xFA,0xD8,0xBD,0xF4,0x11,0x9D,0xF4,0xD9,0xBD,0xEE,0x12,0x9D,0xEE,0xDA,0xE8,0xE0,0xFA,0xD0,0xE3,0xA9,0x3B,0x8D,0x11,0xD0,0xA9,0xD8,0x8D,0x16,0xD0,0xA9,currentBgColor,0x8D,0x20,0xD0,0x8D,0x21,0xD0,0xA9,0x08,0x8D,0x18,0xD0,0xA9,0x02,0x85,0x02,0xAD,0x12,0xD0,0xC9,0xF8,0xD0,0xF9,0xA5,0x02,0x49,0x02,0x85,0x02,0x8D,0x00,0xDD,0xAD,0x11,0xD0,0x30,0xFB,0xAD,0x12,0xD0,0xC9,0x2F,0xD0,0xF9,0xA2,0x08,0xCA,0xD0,0xFD,0xEA,0xA0,0x00,0xB9,0x00,0x09,0x8D,0x11,0xD0,0xB9,0x00,0x0A,0x8D,0x18,0xD0,0xC8,0xC0,0xC8,0xD0,0xEF,0x4C,0x89,0x08];
    f.set(asm, 14); const o = a => a - 2049 + 2;
    for(let i=0; i<1000; i++) f[o(0x1000)+i] = bmp[16000+i];
    for(let i=0; i<8192; i++) {
        f[o(0x4000)+i] = bmp[8000+i]; f[o(0x6000)+i] = i < 8000 ? bmp[i] : 0;
        f[o(0x8000)+i] = bmp[17000+8000+i]; f[o(0xA000)+i] = i < 8000 ? bmp[17000+i] : 0;
    }
  } else if (isFLI) {
    f = new Uint8Array(30721); f[0] = 1; f[1] = 8; f.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
    const asm = [0x78,0xA2,0x00,0x8A,0x29,0x07,0x09,0x38,0x9D,0x00,0x09,0x8A,0x29,0x07,0x0A,0x0A,0x0A,0x0A,0x09,0x08,0x9D,0x00,0x0A,0xE8,0xE0,0xC8,0xD0,0xE7,0xA2,0x00,0xBD,0x00,0x10,0x9D,0x00,0xD8,0xBD,0xFA,0x10,0x9D,0xFA,0xD8,0xBD,0xF4,0x11,0x9D,0xF4,0xD9,0xBD,0xEE,0x12,0x9D,0xEE,0xDA,0xE8,0xE0,0xFA,0xD0,0xE3,0xA9,0x3B,0x8D,0x11,0xD0,0xA9,0xD8,0x8D,0x16,0xD0,0xA9,currentBgColor,0x8D,0x20,0xD0,0x8D,0x21,0xD0,0xA9,0x08,0x8D,0x18,0xD0,0xA9,0x02,0x8D,0x00,0xDD,0xAD,0x12,0xD0,0xC9,0xF8,0xD0,0xF9,0xAD,0x11,0xD0,0x30,0xFB,0xAD,0x12,0xD0,0xC9,0x2F,0xD0,0xF9,0xA2,0x08,0xCA,0xD0,0xFD,0xEA,0xA0,0x00,0xB9,0x00,0x09,0x8D,0x11,0xD0,0xB9,0x00,0x0A,0x8D,0x18,0xD0,0xC8,0xC0,0xC8,0xD0,0xEF,0x4C,0x69,0x08];
    f.set(asm, 14); for(let i=0; i<8192; i++) f[14337+i] = bmp[8000+i];
    for(let i=0; i<8000; i++) f[22529+i] = bmp[i]; for(let i=0; i<1000; i++) f[2049+i] = bmp[16000+i];
  } else {
    f = new Uint8Array(14145); f[0] = 1; f[1] = 8; f.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
    const asm = [0x78,0xA9,0x3B,0x8D,0x11,0xD0,0xA9,(isHires?0xC8:0xD8),0x8D,0x16,0xD0,0xA9,0x18,0x8D,0x18,0xD0,0xA9,currentBgColor,0x8D,0x20,0xD0,0x8D,0x21,0xD0,0xA2,0x00,0xBD,0x70,0x08,0x9D,0x00,0x04,0xBD,0x6A,0x09,0x9D,0xFA,0x04,0xBD,0x64,0x0A,0x9D,0xF4,0x05,0xBD,0x5E,0x0B,0x9D,0xEE,0x06,0xE8,0xE0,0xFA,0xD0,0xE3,0xA2,0x00,0xBD,0x58,0x0C,0x9D,0x00,0xD8,0xBD,0x52,0x0D,0x9D,0xFA,0xD8,0xBD,0x4C,0x0E,0x9D,0xF4,0xD9,0xBD,0x46,0x0F,0x9D,0xEE,0xDA,0xE8,0xE0,0xFA,0xD0,0xE3,0x4C,0x63,0x08];
    f.set(asm, 14); for(let i=0; i<1000; i++) f[113+i]=bmp[8000+i];
    for(let i=0; i<1000; i++) f[1113+i]=bmp[9000+i]; f.set(bmp.subarray(0,8000), 6145);
  }

  if (t === 'PRG') { download(f, isIFLI ? 'ifli.prg' : (isFLI ? 'fli.prg' : (isHires ? 'hires.prg' : 'v.prg'))); }
  else {
    const payload = f.subarray(2); const nBanks = Math.ceil(payload.length / 8192);
    const crt = []; const h = new Uint8Array(64);
    h.set([0x43,0x36,0x34,0x20,0x43,0x41,0x52,0x54,0x52,0x49,0x44,0x47,0x45,0x20,0x20,0x20]);
    h[0x13] = 0x40; h[0x15] = 0x01; h[0x17] = 0x20; h[0x1A] = 0x01;    h.set(new TextEncoder().encode("ESPSTREAMER").subarray(0,32), 0x20);
    crt.push(h);
    const createChip = (bank, data) => {
      const c = new Uint8Array(16 + 8192);
      c.set([0x43,0x48,0x49,0x50, 0x00,0x00,0x20,0x10, 0x00,0x00, (bank>>8), (bank&0xFF), 0x80,0x00, 0x20,0x00], 0);
      c.set(data, 16); return c;
    };
    const boot = new Uint8Array(8192);
    const stub = [
      0xA9,0x01,0x85,0xFB,0xA9,0x08,0x85,0xFC,0xA5,0xFD,0x8D,0x00,0xDE,0xA9,0x00,0x85,0xFE,0xA9,0x80,0x85,0xFF,0xA2,0x20,0xA0,0x00,0xB1,0xFE,0x91,0xFB,0xC8,0xD0,0xF9,0xE6,0xFC,0xE6,0xFF,0xCA,0xD0,0xF0,0xE6,0xFD,0xA5,0xFD,0xC9,(nBanks+1),0xD0,0xD9,0xA9,0x06,0x8D,0x02,0xDE,0x4C,0x0D,0x08
    ];
    const bootCode = [
      0x09,0x80,0x09,0x80,0xC3,0xC2,0xCD,0x38,0x30,0x78,0xD8,0xA2,0xFF,0x9A,0xA9,0x37,0x85,0x01,
      0xA2,(stub.length-1),0xBD,36,0x80,0x9D,0x00,0x03,0xCA,0x10,0xF7,0xA9,0x01,0x85,0xFD,0x4C,0x00,0x03
    ].concat(stub);
    boot.set(bootCode, 0); crt.push(createChip(0, boot));
    for (let b=0; b < nBanks; b++) {
      const chunk = new Uint8Array(8192); chunk.set(payload.subarray(b * 8192, (b + 1) * 8192));
      crt.push(createChip(b + 1, chunk));
    }
    const finalSize = crt.reduce((a, b) => a + b.length, 0);
    const combined = new Uint8Array(finalSize);
    let offset = 0;
    for (const chunk of crt) { combined.set(chunk, offset); offset += chunk.length; }
    download(combined, 'stream.crt');
  }
}
function download(d, n) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([d]));
  a.download = n; a.click();
}
async function upd() {
  try {
    const srPromise = fetch('/stats?t=' + Date.now()); const rPromise = fetch('/data?t=' + Date.now());
    const [sr, r] = await Promise.all([srPromise, rPromise]);
    if (sr.ok) {
      const s = await sr.json(); if (s.mode && s.mode !== currentClientMode) { currentClientMode = s.mode; updateModeUI(); }
      if (s.contrast !== undefined && document.activeElement !== document.getElementById('contrast')) { document.getElementById('contrast').value = s.contrast; updateContrastText(); }
      if (s.brightness !== undefined && document.activeElement !== document.getElementById('brightness')) { document.getElementById('brightness').value = s.brightness; updateBrightnessText(); }
      if (s.scale !== undefined && document.activeElement !== document.getElementById('scale')) document.getElementById('scale').value = s.scale;
      if (s.scaling !== undefined && document.activeElement !== document.getElementById('scaling')) document.getElementById('scaling').value = s.scaling;
      if (s.bg !== undefined && document.activeElement !== document.getElementById('bgcolor')) { currentBgColor = s.bg; document.getElementById('bgcolor').value = s.bg; }
      if (s.dither !== undefined && document.activeElement !== document.getElementById('dither')) { document.getElementById('dither').value = s.dither; updateDitherText(); }
      if (s.ditherType !== undefined && document.activeElement !== document.getElementById('ditherType')) document.getElementById('ditherType').value = s.ditherType;

      const now = Date.now();
      if (lastStatsTime > 0) {
        const dt = (now - lastStatsTime) / 1000.0;
        if (dt >= 1.0) { currentFPS = ((s.frames - lastFrames) / dt).toFixed(1); currentKBs = ((s.totalKB - lastKB) / dt).toFixed(1); lastStatsTime = now; lastFrames = s.frames; lastKB = s.totalKB; }
      } else { lastStatsTime = now; lastFrames = s.frames; lastKB = s.totalKB; }
      const dot = document.getElementById('dot'); const stxt = document.getElementById('stxt');
      dot.className = s.connected ? 'dot on' : 'dot';
      stxt.innerHTML = 'Status: ' + (s.connected ? '<span class="val">LIVE</span>' : '<span class="err">DISCONNECTED</span>') + ' &nbsp;|&nbsp; FPS: <span class="val">' + Math.max(0, currentFPS) + '</span> &nbsp;|&nbsp; <span class="val">' + Math.max(0, currentKBs) + '</span> KB/s &nbsp;|&nbsp; Total: <span class="val">' + s.totalKB + '</span> KB';
    }
    if (!r.ok) return;
    const d = new Uint8Array(await r.arrayBuffer()); const cv = document.getElementById('c'); const ctx = cv.getContext('2d');
    if (isIFLI) {
      const img = ctx.createImageData(160, 200); const bgCol = c64Pal[d[34000]];
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8), py = by % 8, screenBank = py * 1024;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx, byteA = d[cellIdx * 8 + py], sByA = d[8000 + screenBank + cellIdx], cByA = d[16000 + cellIdx];
          let colsA = [ bgCol, c64Pal[sByA >> 4], c64Pal[sByA & 0x0F], c64Pal[cByA & 0x0F] ];
          let cellB = cellIdx + 17000, offB = 17000, byteB2 = d[offB + cellIdx * 8 + py], sByB = d[offB + 8000 + screenBank + cellIdx], cByB = d[offB + 16000 + cellIdx];
          let colsB = [ bgCol, c64Pal[sByB >> 4], c64Pal[sByB & 0x0F], c64Pal[cByB & 0x0F] ];
          for (let px = 0; px < 4; px++) {
            let colA = colsA[(byteA >> ((3 - px) * 2)) & 3] || [0,0,0], colB = colsB[(byteB2 >> ((3 - px) * 2)) & 3] || [0,0,0], outIdx = (by * 160 + bx * 4 + px) * 4;
            img.data[outIdx] = (colA[0] + colB[0]) >> 1; img.data[outIdx+1] = (colA[1] + colB[1]) >> 1; img.data[outIdx+2] = (colA[2] + colB[2]) >> 1; img.data[outIdx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0); ctx.fillStyle = "rgba(200, 200, 200, 0.9)"; ctx.font = "bold 8px monospace"; ctx.fillText("IFLI GRAY", 110, 10);
    } else if (isFLI) {
      const img = ctx.createImageData(160, 200); const bgCol = c64Pal[d[17000]];
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8), py = by % 8, screenBank = py * 1024;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx, byte = d[cellIdx * 8 + py], screenByte = d[8000 + screenBank + cellIdx], colorByte = d[16000 + cellIdx];
          let cols = [ bgCol, c64Pal[screenByte >> 4], c64Pal[screenByte & 0x0F], c64Pal[colorByte & 0x0F] ];
          for (let px = 0; px < 4; px++) {
            let col = cols[(byte >> ((3 - px) * 2)) & 3] || [0,0,0], outIdx = (by * 160 + bx * 4 + px) * 4;
            img.data[outIdx] = col[0]; img.data[outIdx+1] = col[1]; img.data[outIdx+2] = col[2]; img.data[outIdx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0); ctx.fillStyle = isGrayFLI ? "rgba(200, 200, 200, 0.9)" : "rgba(0, 255, 180, 0.7)"; ctx.font = "bold 8px monospace"; 
      ctx.fillText(isGrayFLI ? "GRAY FLI" : "FLI", isGrayFLI ? 120 : 145, 10);
    } else if (isHires) {
      const img = ctx.createImageData(320, 200);
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8), py = by % 8;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx; const byte = d[cellIdx * 8 + py];
          let screenByte = d[8000 + cellIdx], fgCol = c64Pal[screenByte >> 4], bgCol = c64Pal[screenByte & 0x0F];
          for (let bit = 7; bit >= 0; bit--) {
            const px = bx * 8 + (7 - bit); const isFg = (byte >> bit) & 1; const c = isFg ? fgCol : bgCol; const idx = (by * 320 + px) * 4;
            img.data[idx] = c[0]; img.data[idx+1] = c[1]; img.data[idx+2] = c[2]; img.data[idx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0);
    } else {
      const img = ctx.createImageData(160, 200); let bgCol = c64Pal[currentBgColor];
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8), py = by % 8;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx, byte = d[cellIdx * 8 + py], screenByte = d[8000 + cellIdx], colorByte = d[9000 + cellIdx];
          let cols = [ bgCol, c64Pal[screenByte >> 4], c64Pal[screenByte & 0x0F], c64Pal[colorByte & 0x0F] ];
          for (let px = 0; px < 4; px++) {
            let col = cols[(byte >> ((3 - px) * 2)) & 3], outIdx = (by * 160 + bx * 4 + px) * 4;
            img.data[outIdx] = col[0]; img.data[outIdx+1] = col[1]; img.data[outIdx+2] = col[2]; img.data[outIdx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0);
    }
  } catch(e) { console.log('Fetch error:', e); }
  if (running) setTimeout(upd, 70);
}
upd();
</script>
</body></html>
)rawhtml";

//WebServer server(80);

// --- Mode ---
enum StreamMode { M_MC_GRAY, M_HR_GRAY, M_MC_COLOR, M_HR_COLOR, M_MC_FLI, M_MC_GRAY_FLI, M_MC_GRAY_IFLI };
StreamMode currentMode = M_MC_COLOR;
#define FLI_FRAME_SIZE 17001
#define IFLI_FRAME_SIZE 34001
#define IS_HIRES (currentMode == M_HR_GRAY || currentMode == M_HR_COLOR)
#define IS_COLOR (currentMode == M_MC_COLOR || currentMode == M_HR_COLOR || currentMode == M_MC_FLI || currentMode == M_MC_GRAY_FLI || currentMode == M_MC_GRAY_IFLI)
#define IS_FLI   (currentMode == M_MC_FLI || currentMode == M_MC_GRAY_FLI || currentMode == M_MC_GRAY_IFLI)
#define IS_IFLI  (currentMode == M_MC_GRAY_IFLI)
#define IS_GRAY_MODE (currentMode == M_MC_GRAY || currentMode == M_HR_GRAY || currentMode == M_MC_GRAY_FLI || currentMode == M_MC_GRAY_IFLI)

// --- Buffers ---
uint8_t c64_buffer[68010];          // Two 34005 byte buffers (covers IFLI's 34K)
volatile uint8_t active_buffer = 0; // The buffer currently being read by the web server (0 or 1)
uint8_t* render_buffer = c64_buffer + 34005; // Pointer to the inactive buffer for writing
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
float imgBrightness = 0.0f;
int16_t brightness_val = 0;
uint8_t jpgScale = 1;
uint8_t scalingMode = 0;   // 0=Stretch, 1=Fit (letterbox), 2=Crop (zoom)
uint8_t ditherStrength = 4;  // Dither intensity: 0=off, 1-8
uint8_t ditherAlgo = 2;      // 0=None, 1=Bayer4x4, 2=Bayer8x8, 3=WhiteNoise, 4=BlueNoise, 5=FloydSteinberg
uint8_t globalBgColor = 0;   // User-selected background color
uint16_t currentJpgWidth = 320;
uint16_t currentJpgHeight = 200;

// C64 Pepto Palette (RGB888)
const uint8_t c64_pal_r[16] = {0,255,136,170,204,0,  0,  238,221,102,255,51,119,170,0,  187};
const uint8_t c64_pal_g[16] = {0,255,0,  255,68, 204,0,  238,136,68, 119,51,119,255,136,187};
const uint8_t c64_pal_b[16] = {0,255,0,  238,204,85, 170,119,85, 0,  119,51,119,102,255,187};

// Bayer 4x4 ordered dither matrix (centered, range -8..+7)
const int8_t bayer4x4[4][4] = {
    { -8,  8, -6, 10},
    {  0, -4,  2, -2},
    { -5, 11, -7,  9},
    {  3, -1,  5, -3}
};

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

// Blue Noise 8x8 matrix (precomputed, centered, range -32..+31)
const int8_t blueNoise8x8[8][8] = {
    { -8, 23,-18, 12,-31, 17, -4, 28},
    { 19,-14,  5,-25, 20, -9, 14,-22},
    { -3, 30,-21,  9,-16, 26, -7, 11},
    { 24,-11, 16,-28,  3,-20, 21,-13},
    {-27,  7,-19, 22, -6, 29,-24,  0},
    { 13,-30,  1,-15, 18,-12, 10,-17},
    {-23, 27, -5, 25,-29,  6,-26, 15},
    {  8,-10, 31, -2, 11,-32,  4,-8}
};

// Simple LFSR state for white-noise dithering
static uint32_t lfsrState = 0xDEADBEEF;
inline int8_t nextWhiteNoise() {
  lfsrState ^= lfsrState << 13;
  lfsrState ^= lfsrState >> 17;
  lfsrState ^= lfsrState << 5;
  // Map to -32..+31
  return (int8_t)((lfsrState & 0x3F) - 32);
}

// Unified dither offset helper: returns the raw matrix/noise value (-32..+31 range)
// Caller multiplies by ditherStrength and divides as needed.
inline int8_t getDitherOffset(int tx, int ty) {
  switch (ditherAlgo) {
    case 1: return bayer4x4[ty & 3][tx & 3];
    case 2: return bayer8x8[ty & 7][tx & 7];
    case 3: return nextWhiteNoise();
    case 4: return blueNoise8x8[ty & 7][tx & 7];
    default: return 0;
  }
}

inline uint32_t manhattanDist(uint8_t c1, uint8_t c2) {
  return (abs(c64_pal_r[c1] - c64_pal_r[c2]) * 2) + 
         (abs(c64_pal_g[c1] - c64_pal_g[c2]) * 4) + 
         (abs(c64_pal_b[c1] - c64_pal_b[c2]));
}

// Error buffers for Floyd-Steinberg (3 channels, 320 pixels wide + padding)
int16_t fs_err_buf[3][322];

inline uint8_t find_best_c64_match_rgb(int r, int g, int b, int& outR, int& outG, int& outB) {
  uint32_t best_dist = 0xFFFFFFFF;
  uint8_t best_col = 0;
  for (int i=0; i<16; i++) {
    uint32_t dist = (abs(r - c64_pal_r[i]) * 2) + 
                    (abs(g - c64_pal_g[i]) * 4) + 
                    (abs(b - c64_pal_b[i]));
    if (dist < best_dist) {
      best_dist = dist;
      best_col = (uint8_t)i;
    }
  }
  outR = c64_pal_r[best_col];
  outG = c64_pal_g[best_col];
  outB = c64_pal_b[best_col];
  return best_col;
}

// Fixed grayscale palette indices: 0(Blk), 11(D.Gry), 12(M.Gry), 15(L.Gry), 1(Wht)
const uint8_t c64_greys[5] = {0, 11, 12, 15, 1};

inline uint8_t find_best_gray_c64(int luma, int& outLuma) {
  int best_dist = 1000;
  uint8_t best_col = 0;
  for (int i=0; i<5; i++) {
    int g = (c64_pal_r[c64_greys[i]] * 77 + c64_pal_g[c64_greys[i]] * 153 + c64_pal_b[c64_greys[i]] * 26) >> 8;
    int dist = abs(luma - g);
    if (dist < best_dist) {
      best_dist = dist;
      best_col = c64_greys[i];
      outLuma = g;
    }
  }
  return best_col;
}

inline uint8_t rgb565_to_c64(uint16_t p) {
  int r = (p >> 8) & 0xF8;
  int g = (p >> 3) & 0xFC;
  int b = (p << 3) & 0xF8;
  
  if (contrast_fp != 256 || brightness_val != 0) {
    r = (int)((((r - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    g = (int)((((g - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    b = (int)((((b - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    if(r<0) r=0; if(r>255) r=255;
    if(g<0) g=0; if(g>255) g=255;
    if(b<0) b=0; if(b>255) b=255;
  }
  
  uint32_t best_dist = 0xFFFFFFFF;
  uint8_t best_col = 0;
  for (int i=0; i<16; i++) {
    uint32_t dist = (abs(r - c64_pal_r[i]) * 2) + 
                    (abs(g - c64_pal_g[i]) * 4) + 
                    (abs(b - c64_pal_b[i]));
    if (dist < best_dist) {
      best_dist = dist;
      best_col = i;
    }
  }
  return best_col;
}

// Map RGB to 5 C64 Greys with Bayer Dither
inline uint8_t rgb565_to_dithered_gray(uint16_t p, int tx, int ty) {
  int r = (p >> 8) & 0xF8;
  int g = (p >> 3) & 0xFC;
  int b = (p << 3) & 0xF8;
  if (contrast_fp != 256 || brightness_val != 0) {
    r = (int)((((r - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    g = (int)((((g - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    b = (int)((((b - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    if(r<0) r=0; if(r>255) r=255;
    if(g<0) g=0; if(g>255) g=255;
    if(b<0) b=0; if(b>255) b=255;
  }
  
  int16_t luma = (r * 77 + g * 153 + b * 26) >> 8;
  if (ditherStrength > 0 && ditherAlgo > 0) {
    luma += (getDitherOffset(tx, ty) * ditherStrength) / 4;
    if (luma < 0) luma = 0;
    if (luma > 255) luma = 255;
  }
  
  // 5 levels: Black(0), D.Grey(11), M.Grey(12), L.Grey(15), White(1)
  if (luma < 32) return 0;
  if (luma < 96) return 11;
  if (luma < 160) return 12;
  if (luma < 224) return 15;
  return 1;
}

// Map RGB to 9 interlaced C64 Greys (Frame A in high nibble, Frame B in low nibble)
inline uint8_t rgb565_to_ifli_gray(uint16_t p, int tx, int ty) {
  int r = (p >> 8) & 0xF8;
  int g = (p >> 3) & 0xFC;
  int b = (p << 3) & 0xF8;
  if (contrast_fp != 256 || brightness_val != 0) {
    r = (int)((((r - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    g = (int)((((g - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    b = (int)((((b - 128) * contrast_fp) >> 8) + 128 + brightness_val);
    if(r<0) r=0; if(r>255) r=255;
    if(g<0) g=0; if(g>255) g=255;
    if(b<0) b=0; if(b>255) b=255;
  }
  
  int16_t luma = (r * 77 + g * 153 + b * 26) >> 8;
  if (ditherStrength > 0 && ditherAlgo > 0) {
    luma += (getDitherOffset(tx, ty) * ditherStrength) / 4;
    if (luma < 0) luma = 0;
    if (luma > 255) luma = 255;
  }
  
  bool odd = ((tx & 1) ^ (ty & 1));
  uint8_t c1, c2;
  
  if (luma < 16)       { c1 = 0; c2 = 0; }
  else if (luma < 48)  { c1 = 0; c2 = 11; }
  else if (luma < 80)  { c1 = 11; c2 = 11; }
  else if (luma < 112) { c1 = 11; c2 = 12; }
  else if (luma < 144) { c1 = 12; c2 = 12; }
  else if (luma < 176) { c1 = 12; c2 = 15; }
  else if (luma < 208) { c1 = 15; c2 = 15; }
  else if (luma < 240) { c1 = 15; c2 = 1; }
  else                 { c1 = 1; c2 = 1; }
  
  if (odd) { uint8_t tmp = c1; c1 = c2; c2 = tmp; }
  return (c1 << 4) | (c2 & 0x0F);
}

void packC64Frame() {
  uint8_t bgColor = globalBgColor; // User-selected global background
  
  int max_frames = IS_IFLI ? 2 : 1;
  for (int frame = 0; frame < max_frames; frame++) {
    uint8_t* base_ptr   = render_buffer + (frame * 17000);
    uint8_t* bitmap_ram = base_ptr;
    uint8_t* screen_ram = base_ptr + 8000;
    uint8_t* color_ram  = base_ptr + 9000;
    
    auto get_col = [&](int idx) -> uint8_t {
      uint8_t c_raw = color_buffer[idx];
      return IS_IFLI ? (frame == 0 ? (c_raw >> 4) : (c_raw & 0x0F)) : c_raw;
    };
    
    for (int cy = 0; cy < 25; cy++) {
      for (int cx = 0; cx < 40; cx++) {
        int cellIdx = cy * 40 + cx;
        
        if (IS_FLI) {
          uint8_t* screens = base_ptr + 8000; 
          uint8_t* fli_color_ram = base_ptr + 16000;
          
          int counts[16] = {0};
          for (int py=0; py<8; py++) {
            for (int px=0; px<4; px++) {
              counts[get_col((cy*8 + py)*160 + (cx*4 + px))]++;
            }
          }
          counts[bgColor] = -1;
          uint8_t cellCol = 0; int mCell = -1;
          for(int i=0; i<16; i++) { if(counts[i] > mCell) { mCell = counts[i]; cellCol = i; } }
          if (mCell <= 0 || IS_IFLI) cellCol = 1; 
          fli_color_ram[cellIdx] = cellCol;
  
          for (int py = 0; py < 8; py++) {
            int lCounts[16] = {0};
            for (int px=0; px<4; px++) {
              lCounts[get_col((cy*8 + py)*160 + (cx*4 + px))]++;
            }
            lCounts[bgColor] = -1;
            lCounts[cellCol] = -1;
            uint8_t c1=0, c2=0; int m1=0, m2=0;
            for(int i=0; i<16; i++){
              if(lCounts[i]>m1){ m2=m1;c2=c1; m1=lCounts[i];c1=i; }
              else if(lCounts[i]>m2){ m2=lCounts[i];c2=i; }
            }
            if(m1==0) c1 = cellCol;
            if(m2==0) c2 = c1;
            screens[py*1024 + cellIdx] = (c1 << 4) | (c2 & 0x0F);
            
            uint8_t byte = 0;
            for (int px=0; px<4; px++) {
              uint8_t c = get_col((cy*8 + py)*160 + (cx*4 + px));
              uint32_t d0 = (int32_t)manhattanDist(c, bgColor);
              uint32_t d1 = (int32_t)manhattanDist(c, c1);
              uint32_t d2 = (int32_t)manhattanDist(c, c2);
              uint32_t d3 = (int32_t)manhattanDist(c, cellCol);
              
              uint32_t dists[4] = {d0, d1, d2, d3};
              uint8_t slots[4] = {0, 1, 2, 3};
              for (int a = 0; a < 2; a++) {
                for (int b = a+1; b < 4; b++) {
                  if (dists[b] < dists[a]) {
                    uint32_t td = dists[a]; dists[a] = dists[b]; dists[b] = td;
                    uint8_t ts = slots[a]; slots[a] = slots[b]; slots[b] = ts;
                  }
                }
              }
              uint8_t bits = slots[0];
              if (ditherStrength > 0 && ditherAlgo > 0) {
                int32_t bayer = (int32_t)getDitherOffset(cx*4 + px, py) * ditherStrength;
                if ((int32_t)dists[1] - bayer < (int32_t)dists[0] + bayer) bits = slots[1];
              }
              byte |= (bits << ((3 - px) * 2));
            }
            bitmap_ram[cellIdx * 8 + py] = byte;
          }
      } else if (IS_HIRES) {
        int counts[16] = {0};
        for (int py=0; py<8; py++) {
          for (int px=0; px<8; px++) {
            counts[get_col((cy*8 + py)*320 + (cx*8 + px))]++;
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
            uint8_t c = get_col((cy*8 + py)*320 + (cx*8 + px));
            int32_t dbg = (int32_t)manhattanDist(c, bg);
            int32_t dfg = (int32_t)manhattanDist(c, fg);
            int32_t bayer = (ditherStrength > 0 && ditherAlgo > 0) ? (int32_t)getDitherOffset(px, py) * ditherStrength : 0;
            
            if (dfg - bayer < dbg + bayer) byte |= (1 << (7 - px));
          }
          bitmap_ram[cellIdx * 8 + py] = byte;
        }
      } else {
        int counts[16] = {0};
        for (int py=0; py<8; py++) {
          for (int px=0; px<4; px++) {
            counts[get_col((cy*8 + py)*160 + (cx*4 + px))]++;
          }
        }
        
        counts[bgColor] = -1; 
        
        uint8_t c1=0, c2=0, c3=0;
        int m1=0, m2=0, m3=0;
        for(int i=0;i<16;i++){
          if(counts[i]>m1){ m3=m2;c3=c2; m2=m1;c2=c1; m1=counts[i];c1=i; }
          else if(counts[i]>m2){ m3=m2;c3=c2; m2=counts[i];c2=i; }
          else if(counts[i]>m3){ m3=counts[i];c3=i; }
        }
        if(m1==0) c1=1; // Fallback if perfectly solid bgColor
        if(m2==0) c2=c1;
        if(m3==0) c3=c1;
        
        screen_ram[cellIdx] = (c1 << 4) | (c2 & 0x0F);
        color_ram[cellIdx]  = c3;
        
        for (int py=0; py<8; py++) {
          uint8_t byte = 0;
          for (int px=0; px<4; px++) {
            uint8_t c = get_col((cy*8 + py)*160 + (cx*4 + px));
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
            if (ditherStrength > 0 && ditherAlgo > 0) {
              // Ordered dither: compare nearest and second-nearest palette color
              int32_t ditherVal = (int32_t)getDitherOffset(cx*4 + px, cy*8 + py) * ditherStrength;
              bits = (dists[1] - ditherVal < dists[0] + ditherVal) ? slots[1] : slots[0];
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

  if (IS_IFLI) {
    render_buffer[34000] = globalBgColor;
  } else if (IS_FLI) {
    render_buffer[17000] = globalBgColor;
  }
}

// Legacy Gray functions
inline int16_t get_gray(uint16_t p) {
  uint8_t r = (p >> 8) & 0xF8;
  uint8_t g = (p >> 3) & 0xFC;
  uint8_t b = (p << 3) & 0xF8;
  int16_t gray = (r * 77 + g * 150 + b * 29) >> 8;
  if (contrast_fp != 256 || brightness_val != 0) {
    gray = (int16_t)((((int32_t)gray - 128) * contrast_fp) >> 8) + 128 + brightness_val;
    if (gray < 0) gray = 0;
    if (gray > 255) gray = 255;
  }
  return gray;
}

inline void drawHiResPixel(int x, int y, int16_t gray) {
  if (x >= 320 || y >= 200) return;
  int16_t dithered = (ditherStrength > 0 && ditherAlgo > 0) ? gray + getDitherOffset(x, y) : gray;
  if (dithered >= 128) {
    int cellIdx = (y / 8) * 40 + (x / 8);
    int py = (y % 8);
    int bitPos = 7 - (x % 8);
    render_buffer[cellIdx * 8 + py] |= (1 << bitPos);
  }
}

inline void drawMultiColorPixel(int x, int y, int16_t gray) {
  if (x >= 160 || y >= 200) return;
  int16_t dithered = (ditherStrength > 0 && ditherAlgo > 0) ? gray + getDitherOffset(x, y) : gray;
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

// --- Processing variables for Floyd-Steinberg vertical state ---
static int16_t fs_h_err[3]; // Horizontal error within currently processed scanline segment

// TJpg_Decoder callback
bool process_output(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t* bitmap) {
  if (currentJpgWidth == 0 || currentJpgHeight == 0) return true;

  for (int j = 0; j < h; j++) {
    int currY = y + j;
    if (currY >= currentJpgHeight || currY >= 1024) continue;
    
    int startY = mapY_start[currY];
    int endY   = mapY_end[currY];
    if (startY == endY) continue; 

    // Reset horizontal error at the start of each MCU row (x=0) or segment start
    fs_h_err[0] = fs_h_err[1] = fs_h_err[2] = 0;

    for (int i = 0; i < w; i++) {
      int currX = x + i;
      if (currX >= currentJpgWidth || currX >= 1280) continue;
      
      int startX = mapX_start[currX];
      int endX   = mapX_end[currX];
      if (startX == endX) continue; 

      uint16_t pix = bitmap[i + j * w];
      int sr = (pix >> 8) & 0xF8;
      int sg = (pix >> 3) & 0xFC;
      int sb = (pix << 3) & 0xF8;
      
      if (contrast_fp != 256 || brightness_val != 0) {
        sr = (int)((((sr - 128) * contrast_fp) >> 8) + 128 + brightness_val);
        sg = (int)((((sg - 128) * contrast_fp) >> 8) + 128 + brightness_val);
        sb = (int)((((sb - 128) * contrast_fp) >> 8) + 128 + brightness_val);
        if(sr<0) sr=0; if(sr>255) sr=255;
        if(sg<0) sg=0; if(sg>255) sg=255;
        if(sb<0) sb=0; if(sb>255) sb=255;
      }
      
      // If we are in a grayscale mode, force source to monochromatic to avoid color error bleed
      if (IS_GRAY_MODE) {
        sr = sg = sb = (sr * 77 + sg * 153 + sb * 26) >> 8;
      }

      if (IS_COLOR) {
        int wTarget = IS_HIRES ? 320 : 160;
        
        for (int ty = startY; ty < endY; ty++) {
          for (int tx = startX; tx < endX; tx++) {
            if (ty < 200 && tx < wTarget) {
              uint8_t final_col = 0;

              if (ditherAlgo == 5) { // Floyd-Steinberg
                // Target with accumulated error
                int tr = sr + fs_h_err[0] + fs_err_buf[0][tx + 1];
                int tg = sg + fs_h_err[1] + fs_err_buf[1][tx + 1];
                int tb = sb + fs_h_err[2] + fs_err_buf[2][tx + 1];
                
                int ar, ag, ab;
                if (currentMode == M_MC_GRAY_IFLI) {
                  // IFLI Gray has 9 levels (interlaced)
                  const int ifli_lumas[9] = {0, 24, 48, 77, 107, 137, 168, 211, 255};
                  const uint8_t ifli_pair_h[9] = {0,  0, 11, 11, 12, 12, 15, 15, 1};
                  const uint8_t ifli_pair_l[9] = {0, 11, 11, 12, 12, 15, 15,  1, 1};
                  
                  int best_d = 1000; int best_idx = 0;
                  for(int k=0; k<9; k++) {
                    int d = abs(tr - ifli_lumas[k]);
                    if(d < best_d) { best_d = d; best_idx = k; }
                  }
                  final_col = (ifli_pair_h[best_idx] << 4) | (ifli_pair_l[best_idx] & 0x0F);
                  ar = ag = ab = ifli_lumas[best_idx];
                } else if (currentMode == M_MC_GRAY_FLI) {
                  final_col = find_best_gray_c64(tr, ar);
                  ag = ab = ar;
                } else {
                  final_col = find_best_c64_match_rgb(tr, tg, tb, ar, ag, ab);
                }
                
                // Calculate and distribute error
                int er = (tr - ar) * ditherStrength / 8;
                int eg = (tg - ag) * ditherStrength / 8;
                int eb = (tb - ab) * ditherStrength / 8;
                
                // Floyd-Steinberg Kernel:
                // [ *   7 ] / 16
                // [ 3 5 1 ] / 16
                fs_h_err[0] = (er * 7) >> 4;
                fs_h_err[1] = (eg * 7) >> 4;
                fs_h_err[2] = (eb * 7) >> 4;
                
                fs_err_buf[0][tx]   += (er * 3) >> 4;
                fs_err_buf[1][tx]   += (eg * 3) >> 4;
                fs_err_buf[2][tx]   += (eb * 3) >> 4;
                
                fs_err_buf[0][tx+1] = (er * 5) >> 4; // We reset tx+1 since it was used
                fs_err_buf[1][tx+1] = (eg * 5) >> 4;
                fs_err_buf[2][tx+1] = (eb * 5) >> 4;
                
                fs_err_buf[0][tx+2] += er >> 4;
                fs_err_buf[1][tx+2] += eg >> 4;
                fs_err_buf[2][tx+2] += eb >> 4;
                
                color_buffer[ty * wTarget + tx] = final_col;
              } else {
                if (currentMode == M_MC_GRAY_FLI) {
                  color_buffer[ty * wTarget + tx] = rgb565_to_dithered_gray(pix, tx, ty);
                } else if (currentMode == M_MC_GRAY_IFLI) {
                  color_buffer[ty * wTarget + tx] = rgb565_to_ifli_gray(pix, tx, ty);
                } else {
                  color_buffer[ty * wTarget + tx] = rgb565_to_c64(pix);
                }
              }
            }
          }
        }
      } else {
        int16_t grayVal = (sr * 77 + sg * 153 + sb * 26) >> 8;
        
        for (int ty = startY; ty < endY; ty++) {
          for (int tx = startX; tx < endX; tx++) {
            if (ty < 200 && (IS_HIRES ? tx < 320 : tx < 160)) {
              if (ditherAlgo == 5) {
                // Grayscale FS
                int target = grayVal + fs_h_err[0] + fs_err_buf[0][tx + 1];
                if (target < 0) target = 0; if (target > 255) target = 255;
                
                uint8_t quantized;
                int actual;
                
                if (IS_HIRES) {
                  // Hi-Res Grayscale: simple black/white (0/128 threshold)
                  quantized = (target >= 128) ? 1 : 0; // index for draw logic (not palette index)
                  actual = quantized ? 255 : 0;
                  
                  int cellIdx = (ty / 8) * 40 + (tx / 8);
                  int bitPos = 7 - (tx % 8);
                  if (quantized) render_buffer[cellIdx * 8 + (ty % 8)] |= (1 << bitPos);
                } else {
                  // Multi-Color Grayscale: 4 levels (0, 85, 170, 255) mapped to 0..3
                  int level = target >> 6; // 0, 1, 2, 3
                  if (level > 3) level = 3;
                  actual = level * 85;
                  
                  int cellIdx = (ty / 8) * 40 + (tx / 4);
                  int bitPos = (3 - (tx % 4)) * 2;
                  if (level) render_buffer[cellIdx * 8 + (ty % 8)] |= (level << bitPos);
                }
                
                int err = (target - actual) * ditherStrength / 8;
                fs_h_err[0] = (err * 7) >> 4;
                fs_err_buf[0][tx]   += (err * 3) >> 4;
                fs_err_buf[0][tx+1] = (err * 5) >> 4;
                fs_err_buf[0][tx+2] += err >> 4;
              } else {
                // Legacy Bayer/Noise
                if (IS_HIRES) drawHiResPixel(tx, ty, grayVal);
                else          drawMultiColorPixel(tx, ty, grayVal);
              }
            }
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
  size_t len = (IS_IFLI) ? IFLI_FRAME_SIZE : (IS_FLI ? FLI_FRAME_SIZE : 10000);
  server.setContentLength(len);
  server.send(200, "application/octet-stream", "");
  server.sendContent((const char*)(c64_buffer + active_buffer * 34005), len);
}

void handleSetMode() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("m")) {
    String m = server.arg("m");
    if (m == "mc_gray") currentMode = M_MC_GRAY;
    else if (m == "hr_gray") currentMode = M_HR_GRAY;
    else if (m == "mc_color") currentMode = M_MC_COLOR;
    else if (m == "hr_color") currentMode = M_HR_COLOR;
    else if (m == "mc_fli")   currentMode = M_MC_FLI;
    else if (m == "mc_gray_fli") currentMode = M_MC_GRAY_FLI;
    else if (m == "mc_gray_ifli") currentMode = M_MC_GRAY_IFLI;
    memset(c64_buffer, 0, sizeof(c64_buffer));
    server.send(200, "text/plain", m);
  } else {
    server.send(400, "text/plain", "Missing ?m= param");
  }
}

void handleSetBrightness() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("b")) {
    imgBrightness = server.arg("b").toFloat();
    brightness_val = (int16_t)imgBrightness;
    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Missing ?b= param");
  }
}

void handleSetBg() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("c")) {
    int bg = server.arg("c").toInt();
    if (bg >= 0 && bg <= 15) {
      globalBgColor = (uint8_t)bg;
      server.send(200, "text/plain", "OK");
    } else {
      server.send(400, "text/plain", "Invalid color value");
    }
  } else {
    server.send(400, "text/plain", "Missing ?c= param");
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

void handleSetDitherType() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("t")) {
    int t = server.arg("t").toInt();
    if (t >= 0 && t <= 5) {
      ditherAlgo = (uint8_t)t;
      server.send(200, "text/plain", "OK");
    } else {
      server.send(400, "text/plain", "Invalid value (0-5)");
    }
  } else {
    server.send(400, "text/plain", "Missing ?t= param");
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

void handleSetScaling() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  if (server.hasArg("s")) {
    int s = server.arg("s").toInt();
    if (s >= 0 && s <= 2) {
      scalingMode = (uint8_t)s;
      server.send(200, "text/plain", "OK");
    } else {
      server.send(400, "text/plain", "Invalid value (0-2)");
    }
  } else {
    server.send(400, "text/plain", "Missing ?s= param");
  }
}

void handleStats() {
  // Count non-zero bytes for debug
  uint32_t nz = 0;
  uint32_t checkSize = IS_IFLI ? 34000 : (IS_FLI ? 17000 : 10000);
  uint8_t* current_buf = c64_buffer + active_buffer * 34005;
  for (int i = 0; i < checkSize; i++) {
    if (current_buf[i] != 0) nz++;
  }
  nonZeroPixels = nz;
  String mStr = "mc_color";
  if (currentMode == M_MC_GRAY) mStr = "mc_gray";
  else if (currentMode == M_HR_GRAY) mStr = "hr_gray";
  else if (currentMode == M_HR_COLOR) mStr = "hr_color";
  else if (currentMode == M_MC_FLI)   mStr = "mc_fli";
  else if (currentMode == M_MC_GRAY_FLI) mStr = "mc_gray_fli";
  else if (currentMode == M_MC_GRAY_IFLI) mStr = "mc_gray_ifli";
  
  String json = "{\"frames\":" + String(frameCount) +
                ",\"mode\":\"" + mStr + "\"" +
                ",\"lastSize\":" + String(lastFrameSize) +
                ",\"decode\":" + String(lastDecodeResult) +
                ",\"nonZero\":" + String(nz) +
                ",\"connected\":" + String(streamConnected ? 1 : 0) +
                ",\"contrast\":" + String(imgContrast, 2) +
                ",\"brightness\":" + String(imgBrightness, 1) +
                ",\"scale\":" + String(jpgScale) +
                ",\"dither\":"      + String(ditherStrength) +
                ",\"ditherType\":" + String(ditherAlgo) +
                ",\"bg\":"          + String(globalBgColor) +
                ",\"scaling\":"     + String(scalingMode) +
                ",\"totalKB\":"     + String((uint32_t)(totalBytes / 1024)) + "}";
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", json);
}

void handleRoot() {
  server.send_P(200, "text/html", INDEX_HTML);
}

/*
void old_handleRoot_to_delete() {
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
    display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 12px; font-size: 13px; color: #a0b4ff; flex-wrap: wrap;
    background: rgba(0,0,0,0.2); padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(100,140,255,0.2);
  }
  input[type=range] {
    -webkit-appearance: none; width: 80px; background: rgba(100,140,255,0.2);
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
      <option value="mc_color">MULTI-COLOR COLOR</option>
      <option value="hr_color">HI-RES COLOR</option>
      <option value="mc_fli">MULTI-COLOR FLI</option>
      <option value="mc_gray_fli">GRAYSCALE FLI</option>
      <option value="mc_gray_ifli">GRAYSCALE IFLI</option>
    </select>
    <button onclick="save('PRG')">&#x25B6; PRG</button>
    <button onclick="save('KOA')">&#x25B6; KOA</button>
    <button onclick="save('CRT')">&#x25B6; CRT</button>
  </div>
  <div class="slider-container">
    <span>CT: <span id="cval" class="val">1.0</span></span>
    <input type="range" id="contrast" min="0.5" max="3.0" step="0.1" value="1.0" oninput="updateContrastText()" onchange="sendContrast()">
    <span>BR: <span id="bval" class="val">0</span></span>
    <input type="range" id="brightness" min="-128" max="128" step="4" value="0" oninput="updateBrightnessText()" onchange="sendBrightness()">
    <span style="margin-left:4px">SCALE:</span>
    <select id="scale" onchange="sendScale()">
      <option value="1">1:1 (HQ)</option>
      <option value="2">1:2 (FAST)</option>
      <option value="4">1:4 (FASTER)</option>
      <option value="8">1:8 (FASTEST)</option>
    </select>
    <span style="margin-left:8px">RATIO:</span>
    <select id="scaling" onchange="sendScaling()">
      <option value="0">STRETCH</option>
      <option value="1">FIT</option>
      <option value="2">CROP</option>
    </select>
    <span style="margin-left:8px">BG (MC):</span>
    <select id="bgcolor" onchange="sendBg()" style="padding:4px">
      <option value="0">0:BLK</option><option value="1">1:WHT</option><option value="2">2:RED</option><option value="3">3:CYN</option>
      <option value="4">4:PUR</option><option value="5">5:GRN</option><option value="6">6:BLU</option><option value="7">7:YEL</option>
      <option value="8">8:ORG</option><option value="9">9:BRN</option><option value="10">10:LRD</option><option value="11">11:DGY</option>
      <option value="12">12:MGY</option><option value="13">13:LGN</option><option value="14">14:LBL</option><option value="15">15:LGY</option>
    </select>
    <span style="margin-left:8px">DITHER:</span>
    <select id="ditherType" onchange="sendDitherType()">
      <option value="0">NONE</option>
      <option value="1">BAYER 4x4</option>
      <option value="2" selected>BAYER 8x8</option>
      <option value="3">WHITE NOISE</option>
      <option value="4">BLUE NOISE</option>
      <option value="5">FLOYD-STEINBERG</option>
    </select>
    <span style="margin-left:4px">STR:</span>
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
let isHires = false;  
let isFLI = false;
let isGrayFLI = false;
let isIFLI = false;
let currentClientMode = 'mc_color';
let currentBgColor = 0;

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
  isFLI = currentClientMode.includes('_fli');
  isGrayFLI = currentClientMode === 'mc_gray_fli';
  isIFLI = currentClientMode === 'mc_gray_ifli';
  resizeCanvas(isHires);
}

// --- Adjustments ---
function updateContrastText() {
  document.getElementById('cval').innerText = parseFloat(document.getElementById('contrast').value).toFixed(1);
}
function updateBrightnessText() {
  document.getElementById('bval').innerText = document.getElementById('brightness').value;
}
async function sendContrast() {
  const c = document.getElementById('contrast').value;
  try { await fetch('/setcontrast?c=' + c); } catch(e) {}
}
async function sendBrightness() {
  const b = document.getElementById('brightness').value;
  try { await fetch('/setbrightness?b=' + b); } catch(e) {}
}
async function sendBg() {
  const c = document.getElementById('bgcolor').value;
  try { await fetch('/setbg?c=' + c); } catch(e) {}
}
async function sendScale() {
  const s = document.getElementById('scale').value;
  try { await fetch('/setscale?s=' + s); } catch(e) {}
}
async function sendScaling() {
  const s = document.getElementById('scaling').value;
  try { await fetch('/setscaling?s=' + s); } catch(e) {}
}
function updateDitherText() {
  document.getElementById('dval').innerText = document.getElementById('dither').value;
}
async function sendDither() {
  const d = document.getElementById('dither').value;
  try { await fetch('/setdither?d=' + d); } catch(e) {}
}
async function sendDitherType() {
  const t = document.getElementById('ditherType').value;
  try { await fetch('/setdithertype?t=' + t); } catch(e) {}
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
    f[10002] = currentBgColor; // BG Color
    download(f, 'img.koa');
  } else if (t === 'PRG' && isIFLI) {
    f = new Uint8Array(49155); // fits up to $BFFF + 2
    f[0] = 1; f[1] = 8; // $0801
    f.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
    const ifliAsm = [
      0x78, // SEI
      // Disable I/O to copy memory under $D000-$DFFF
      0xA9, 0x34, 0x85, 0x01,
      // Move 16KB from $8000 to $C000 for Frame B
      0xA9, 0x00, 0x85, 0xFC, 0x85, 0xFE, // Src/Dest LSB = 00
      0xA9, 0x80, 0x85, 0xFD,             // Src MSB = 80
      0xA9, 0xC0, 0x85, 0xFF,             // Dest MSB = C0
      0xA2, 0x40, 0xA0, 0x00,             // 64 pages ($4000 bytes)
      0xB1, 0xFC, 0x91, 0xFE, 0xC8, 0xD0, 0xF9,
      0xE6, 0xFD, 0xE6, 0xFF, 0xCA, 0xD0, 0xF2,
      // Restore I/O
      0xA9, 0x35, 0x85, 0x01,
      // Pre-calculate tables at $0900 (D011) and $0A00 (D018)
      0xA2, 0x00, 
      0x8A, 0x29, 0x07, 0x09, 0x38, 0x9D, 0x00, 0x09, 
      0x8A, 0x29, 0x07, 0x0A, 0x0A, 0x0A, 0x0A, 0x09, 0x08, 0x9D, 0x00, 0x0A, 
      0xE8, 0xE0, 0xC8, 0xD0, 0xE7,
      // Color RAM Init from $1000 to $D800
      0xA2, 0x00,
      0xBD, 0x00, 0x10, 0x9D, 0x00, 0xD8,
      0xBD, 0xFA, 0x10, 0x9D, 0xFA, 0xD8,
      0xBD, 0xF4, 0x11, 0x9D, 0xF4, 0xD9,
      0xBD, 0xEE, 0x12, 0x9D, 0xEE, 0xDA,
      0xE8, 0xE0, 0xFA, 0xD0, 0xE3,
      // Setup Initial Video Registers
      0xA9, 0x3B, 0x8D, 0x11, 0xD0,
      0xA9, 0xD8, 0x8D, 0x16, 0xD0,
      0xA9, currentBgColor, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0,
      0xA9, 0x08, 0x8D, 0x18, 0xD0, // Fix top-left block bug
      // Init Bank State in $02 (Use 02 for Bank 1)
      0xA9, 0x02, 0x85, 0x02,
      // l_waitF8: Wait for raster $F8
      0xAD, 0x12, 0xD0, 0xC9, 0xF8, 0xD0, 0xF9,
      // Toggle bank state and update DD00 (Toggle between Bank 1 and Bank 3: 02 XOR 02 = 00!)
      0xA5, 0x02, 0x49, 0x02, 0x85, 0x02, 0x8D, 0x00, 0xDD,
      // l_waitMSB0: Wait until MSB of raster is 0
      0xAD, 0x11, 0xD0, 0x30, 0xFB,
      // l_wait2F: Wait for raster $2F
      0xAD, 0x12, 0xD0, 0xC9, 0x2F, 0xD0, 0xF9,
      // Delay exactly ~45 cycles into line $2F to align properly before cycle 14 of line $30
      // LDX #$08
      0xA2, 0x08,
      // l_delay: DEX
      0xCA,
      // BNE l_delay
      0xD0, 0xFD,
      // NOP
      0xEA,
      // LDY #$00
      0xA0, 0x00,
      // l_fli: 23 Cycle loop (23 CPU + 40 DMA = 63 cycles exactly)
      0xB9, 0x00, 0x09, 0x8D, 0x11, 0xD0,
      0xB9, 0x00, 0x0A, 0x8D, 0x18, 0xD0,
      0xC8, 0xC0, 0xC8, 0xD0, 0xEF,
      // Back to l_waitF8 ($0889 due to copy routine and added D018 init)
      0x4C, 0x89, 0x08
    ];
    f.set(ifliAsm, 14);
    const offset = addr => addr - 0x0801 + 2;
    for(let i=0; i<1000; i++) f[offset(0x1000)+i] = bmp[16000+i];
    for(let i=0; i<8192; i++) {
        f[offset(0x4000)+i] = bmp[8000+i]; 
        f[offset(0x6000)+i] = i < 8000 ? bmp[i] : 0;      
        f[offset(0x8000)+i] = bmp[17000+8000+i]; 
        f[offset(0xA000)+i] = i < 8000 ? bmp[17000+i] : 0;      
    }
    download(f, 'ifli.prg');
  } else if (t === 'PRG' && isFLI) {
    f = new Uint8Array(30721); // $0801 to $7FFF
    f[0] = 1; f[1] = 8; // $0801
    f.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
    // FLI Player ASM (Table driven exactly 23 cycles + 40 DMA = 63 cycles)
    const fliAsm = [
      0x78, // SEI
      // Pre-calculate tables at $0900 (D011) and $0A00 (D018)
      0xA2, 0x00, 
      0x8A, 0x29, 0x07, 0x09, 0x38, 0x9D, 0x00, 0x09, 
      0x8A, 0x29, 0x07, 0x0A, 0x0A, 0x0A, 0x0A, 0x09, 0x08, 0x9D, 0x00, 0x0A, 
      0xE8, 0xE0, 0xC8, 0xD0, 0xE7,
      // Color RAM Init
      0xA2, 0x00,
      0xBD, 0x00, 0x10, 0x9D, 0x00, 0xD8,
      0xBD, 0xFA, 0x10, 0x9D, 0xFA, 0xD8,
      0xBD, 0xF4, 0x11, 0x9D, 0xF4, 0xD9,
      0xBD, 0xEE, 0x12, 0x9D, 0xEE, 0xDA,
      0xE8, 0xE0, 0xFA, 0xD0, 0xE3,
      // Setup Initial Video Registers
      0xA9, 0x3B, 0x8D, 0x11, 0xD0,
      0xA9, 0xD8, 0x8D, 0x16, 0xD0,
      0xA9, currentBgColor, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0,
      0xA9, 0x08, 0x8D, 0x18, 0xD0, // Fix top-left block bug
      0xA9, 0x02, 0x8D, 0x00, 0xDD,
      // l_wait: Wait for raster $F8
      0xAD, 0x12, 0xD0, 0xC9, 0xF8, 0xD0, 0xF9,
      // l_waitMSB0: Wait until MSB of raster is 0
      0xAD, 0x11, 0xD0, 0x30, 0xFB,
      // l_wait2F: Wait for raster $2F
      0xAD, 0x12, 0xD0, 0xC9, 0x2F, 0xD0, 0xF9,
      // Delay exactly ~45 cycles into line $2F to align properly before cycle 14 of line $30
      0xA2, 0x08, 0xCA, 0xD0, 0xFD, 0xEA, 0xA0, 0x00,
      // l_fli: 23 Cycle loop (23 CPU + 40 DMA = 63 cycles exactly)
      0xB9, 0x00, 0x09, 0x8D, 0x11, 0xD0,
      0xB9, 0x00, 0x0A, 0x8D, 0x18, 0xD0,
      0xC8, 0xC0, 0xC8, 0xD0, 0xEF,
      // Back to wait ($0869)
      0x4C, 0x69, 0x08
    ];
    f.set(fliAsm, 14);
    // Screens @ $4000: Offset (0x4000 - 0x0801) + 2 = 14337
    for(let i=0; i<8192; i++) f[14337+i] = bmp[8000+i];
    // Bitmap @ $6000: Offset (0x6000 - 0x0801) + 2 = 22529
    for(let i=0; i<8000; i++) f[22529+i] = bmp[i];
    // Color RAM temp storage @ $1000: Offset (0x1000 - 0x0801) + 2 = 2049
    for(let i=0; i<1000; i++) f[2049+i] = bmp[16000+i];
    download(f, 'fli.prg');
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
      0xA9, currentBgColor, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0, // LDA #bg, STA border/bg
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
  } else if (t === 'CRT') {
    // 1. Build PRG Payload first (stripped of metadata)
    let prg;
    if (isIFLI) {
      prg = new Uint8Array(49155);
      prg[0] = 1; prg[1] = 8;
      prg.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
      const ifliAsm = [
        0x78,0xA9,0x34,0x85,0x01,0xA9,0x00,0x85,0xFC,0x85,0xFE,0xA9,0x80,0x85,0xFD,0xA9,0xC0,0x85,0xFF,
        0xA2,0x40,0xA0,0x00,0xB1,0xFC,0x91,0xFE,0xC8,0xD0,0xF9,0xE6,0xFD,0xE6,0xFF,0xCA,0xD0,0xF2,
        0xA9,0x35,0x85,0x01,0xA2,0x00,0x8A,0x29,0x07,0x09,0x38,0x9D,0x00,0x09,0x8A,0x29,0x07,0x0A,0x0A,
        0x0A,0x0A,0x09,0x08,0x9D,0x00,0x0A,0xE8,0xE0,0xC8,0xD0,0xE7,0xA2,0x00,0xBD,0x00,0x10,0x9D,0x00,
        0xD8,0xBD,0xFA,0x10,0x9D,0xFA,0xD8,0xBD,0xF4,0x11,0x9D,0xF4,0xD9,0xBD,0xEE,0x12,0x9D,0xEE,0xDA,
        0xE8,0xE0,0xFA,0xD0,0xE3,0xA9,0x3B,0x8D,0x11,0xD0,0xA9,0xD8,0x8D,0x16,0xD0,0xA9,currentBgColor,
        0x8D,0x20,0xD0,0x8D,0x21,0xD0,0xA9,0x08,0x8D,0x18,0xD0,0xA9,0x02,0x85,0x02,0xAD,0x12,0xD0,0xC9,
        0xF8,0xD0,0xF9,0xA5,0x02,0x49,0x02,0x85,0x02,0x8D,0x00,0xDD,0xAD,0x11,0xD0,0x30,0xFB,0xAD,0x12,
        0xD0,0xC9,0x2F,0xD0,0xF9,0xA2,0x08,0xCA,0xD0,0xFD,0xEA,0xA0,0x00,0xB9,0x00,0x09,0x8D,0x11,0xD0,
        0xB9,0x00,0x0A,0x8D,0x18,0xD0,0xC8,0xC0,0xC8,0xD0,0xEF,0x4C,0x89,0x08
      ];
      prg.set(ifliAsm, 14);
      const off = a => a - 0x0801 + 2;
      for(let i=0; i<1000; i++) prg[off(0x1000)+i] = bmp[16000+i];
      for(let i=0; i<8192; i++) {
        prg[off(0x4000)+i] = bmp[8000+i]; prg[off(0x6000)+i] = i < 8000 ? bmp[i] : 0;
        prg[off(0x8000)+i] = bmp[17000+8000+i]; prg[off(0xA000)+i] = i < 8000 ? bmp[17000+i] : 0;
      }
    } else if (isFLI) {
      prg = new Uint8Array(30721);
      prg[0] = 1; prg[1] = 8;
      prg.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
      const fliAsm = [
        0x78,0xA2,0x00,0x8A,0x29,0x07,0x09,0x38,0x9D,0x00,0x09,0x8A,0x29,0x07,0x0A,0x0A,0x0A,0x0A,0x09,
        0x08,0x9D,0x00,0x0A,0xE8,0xE0,0xC8,0xD0,0xE7,0xA2,0x00,0xBD,0x00,0x10,0x9D,0x00,0xD8,0xBD,0xFA,
        0x10,0x9D,0xFA,0xD8,0xBD,0xF4,0x11,0x9D,0xF4,0xD9,0xBD,0xEE,0x12,0x9D,0xEE,0xDA,0xE8,0xE0,0xFA,
        0xD0,0xE3,0xA9,0x3B,0x8D,0x11,0xD0,0xA9,0xD8,0x8D,0x16,0xD0,0xA9,currentBgColor,0x8D,0x20,0xD0,
        0x8D,0x21,0xD0,0xA9,0x08,0x8D,0x18,0xD0,0xA9,0x02,0x8D,0x00,0xDD,0xAD,0x12,0xD0,0xC9,0xF8,0xD0,
        0xF9,0xAD,0x11,0xD0,0x30,0xFB,0xAD,0x12,0xD0,0xC9,0x2F,0xD0,0xF9,0xA2,0x08,0xCA,0xD0,0xFD,0xEA,
        0xA0,0x00,0xB9,0x00,0x09,0x8D,0x11,0xD0,0xB9,0x00,0x0A,0x8D,0x18,0xD0,0xC8,0xC0,0xC8,0xD0,0xEF,
        0x4C,0x69,0x08
      ];
      prg.set(fliAsm, 14);
      for(let i=0; i<8192; i++) prg[14337+i] = bmp[8000+i];
      for(let i=0; i<8000; i++) prg[22529+i] = bmp[i];
      for(let i=0; i<1000; i++) prg[2049+i] = bmp[16000+i];
    } else {
      prg = new Uint8Array(14145);
      prg[0] = 1; prg[1] = 8;
      prg.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
      const prgAsm = [
        0x78,0xA9,0x3B,0x8D,0x11,0xD0,0xA9,(isHires?0xC8:0xD8),0x8D,0x16,0xD0,0xA9,0x18,0x8D,0x18,0xD0,
        0xA9,currentBgColor,0x8D,0x20,0xD0,0x8D,0x21,0xD0,0xA2,0x00,0xBD,0x70,0x08,0x9D,0x00,0x04,0xBD,
        0x6A,0x09,0x9D,0xFA,0x04,0xBD,0x64,0x0A,0x9D,0xF4,0x05,0xBD,0x5E,0x0B,0x9D,0xEE,0x06,0xE8,0xE0,
        0xFA,0xD0,0xE3,0xA2,0x00,0xBD,0x58,0x0C,0x9D,0x00,0xD8,0xBD,0x52,0x0D,0x9D,0xFA,0xD8,0xBD,0x4C,
        0x0E,0x9D,0xF4,0xD9,0xBD,0x46,0x0F,0x9D,0xEE,0xDA,0xE8,0xE0,0xFA,0xD0,0xE3,0x4C,0x63,0x08
      ];
      prg.set(prgAsm, 14);
      for(let i=0;i<1000;i++) prg[113+i]=bmp[8000+i];
      for(let i=0;i<1000;i++) prg[1113+i]=bmp[9000+i];
      prg.set(bmp.subarray(0,8000), 6145);
    }

    // 2. Wrap into EasyFlash CRT
    const payload = prg.subarray(2); // Strip $01, $08 header
    const nBanks = Math.ceil(payload.length / 8192);
    const crt = [];
    
    // Main Header (64 bytes)
    const h = new Uint8Array(64);
    h.set([0x43,0x36,0x34,0x20,0x43,0x41,0x52,0x54,0x52,0x49,0x44,0x47,0x45,0x20,0x20,0x20]); // Signature
    h[0x13] = 0x40; // Length
    h[0x15] = 0x01; // Version
    h[0x17] = 0x20; // Type: 32 (EasyFlash)
    h.set(new TextEncoder().encode("ESPSTREAMER").subarray(0,32), 0x20);
    crt.push(h);

    const createChip = (bank, data) => {
      const c = new Uint8Array(16 + 8192);
      c.set([0x43,0x48,0x49,0x50, 0x00,0x00,0x20,0x10, 0x00,0x00, (bank>>8), (bank&0xFF), 0x80,0x00, 0x20,0x00], 0);
      c.set(data, 16); return c;
    };

    // Bank 0: Bootstrap
    const boot = new Uint8Array(8192);
    const bootCode = [
      0x09,0x80,0x09,0x80,0xC3,0xC2,0xCD,0x38,0x30, // Header
      0x78,0xD8,0xA2,0xFF,0x9A,0xA9,0x37,0x85,0x01, // Init
      0xA9,0x01,0x85,0xFB,0xA9,0x08,0x85,0xFC,       // Dest=$0801
      0xA9,0x01,0x85,0xFD,                         // Bank=1
      0xA5,0xFD,0x8D,0x00,0xDE,                    // [DE00] Switch
      0xA2,0x20,0xA0,0x00,                         // 32 pages
      0xB9,0x00,0x80,0x91,0xFB,0xC8,0xD0,0xF9,       // Copy loop
      0xE6,0xFC,0xCA,0xD0,0xF2,                   // Next page
      0xE6,0xFD,0xA5,0xFD,0xC9, (nBanks+1),        // Next bank, CMP limit
      0xD0,0xE4,0xA9,0x04,0x8D,0x02,0xDE,          // Disable Cart
      0x4C,0x0D,0x08                               // JMP $080D
    ];
    boot.set(bootCode, 0);
    crt.push(createChip(0, boot));

    // Banks 1..N: Payload
    for (let b=0; b < nBanks; b++) {
      const chunk = new Uint8Array(8192);
      chunk.set(payload.subarray(b * 8192, (b + 1) * 8192));
      crt.push(createChip(b + 1, chunk));
    }

    const finalSize = crt.reduce((a, b) => a + b.length, 0);
    const combined = new Uint8Array(finalSize);
    let offset = 0;
    for (const chunk of crt) {
      combined.set(chunk, offset);
      offset += chunk.length;
    }
    download(combined, 'stream.crt');
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
      if (s.brightness !== undefined && document.activeElement !== document.getElementById('brightness')) {
        document.getElementById('brightness').value = s.brightness;
        updateBrightnessText();
      }
      if (s.scale !== undefined && document.activeElement !== document.getElementById('scale')) {
        document.getElementById('scale').value = s.scale;
      }
      if (s.scaling !== undefined && document.activeElement !== document.getElementById('scaling')) {
        document.getElementById('scaling').value = s.scaling;
      }
      if (s.bg !== undefined && document.activeElement !== document.getElementById('bgcolor')) {
        currentBgColor = s.bg;
        document.getElementById('bgcolor').value = s.bg;
      }
      if (s.dither !== undefined && document.activeElement !== document.getElementById('dither')) {
        document.getElementById('dither').value = s.dither;
        updateDitherText();
      }
      if (s.ditherType !== undefined && document.activeElement !== document.getElementById('ditherType')) {
        document.getElementById('ditherType').value = s.ditherType;
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

    if (isIFLI) {
      const img = ctx.createImageData(160, 200);
      const bgCol = c64Pal[d[34000]]; // Global Bg
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8);
        let py = by % 8;
        let screenBank = py * 1024;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx;
          // Frame A
          let byteA = d[cellIdx * 8 + py];
          let sByA = d[8000 + screenBank + cellIdx];
          let cByA = d[16000 + cellIdx];
          let colsA = [ bgCol, c64Pal[sByA >> 4], c64Pal[sByA & 0x0F], c64Pal[cByA & 0x0F] ];
          
          // Frame B (offset +17000)
          let cellB = cellIdx + 17000;
          let offB = 17000;
          let byteB2 = d[offB + cellIdx * 8 + py];
          let sByB = d[offB + 8000 + screenBank + cellIdx];
          let cByB = d[offB + 16000 + cellIdx];
          let colsB = [ bgCol, c64Pal[sByB >> 4], c64Pal[sByB & 0x0F], c64Pal[cByB & 0x0F] ];
          
          for (let px = 0; px < 4; px++) {
            let colA = colsA[(byteA >> ((3 - px) * 2)) & 3] || [0,0,0];
            let colB = colsB[(byteB2 >> ((3 - px) * 2)) & 3] || [0,0,0];
            let outIdx = (by * 160 + bx * 4 + px) * 4;
            img.data[outIdx]   = (colA[0] + colB[0]) >> 1;
            img.data[outIdx+1] = (colA[1] + colB[1]) >> 1;
            img.data[outIdx+2] = (colA[2] + colB[2]) >> 1;
            img.data[outIdx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0);
      ctx.fillStyle = "rgba(200, 200, 200, 0.9)";
      ctx.font = "bold 8px monospace";
      ctx.fillText("IFLI GRAY", 110, 10);
    } else if (isFLI) {
      const img = ctx.createImageData(160, 200);
      const bgCol = c64Pal[d[17000]]; // Global Bg
      for (let by = 0; by < 200; by++) {
        let charRow = Math.floor(by / 8);
        let py = by % 8;
        let screenBank = py * 1024;
        for (let bx = 0; bx < 40; bx++) {
          let cellIdx = charRow * 40 + bx;
          let byte = d[cellIdx * 8 + py];
          let screenByte = d[8000 + screenBank + cellIdx];
          let colorByte  = d[16000 + cellIdx];
          let cols = [ bgCol, c64Pal[screenByte >> 4], c64Pal[screenByte & 0x0F], c64Pal[colorByte & 0x0F] ];
          
          for (let px = 0; px < 4; px++) {
            let col = cols[(byte >> ((3 - px) * 2)) & 3] || [0,0,0];
            let outIdx = (by * 160 + bx * 4 + px) * 4;
            img.data[outIdx]   = col[0];
            img.data[outIdx+1] = col[1];
            img.data[outIdx+2] = col[2];
            img.data[outIdx+3] = 255;
          }
        }
      }
      ctx.putImageData(img, 0, 0);
      ctx.fillStyle = isGrayFLI ? "rgba(200, 200, 200, 0.9)" : "rgba(0, 255, 180, 0.7)";
      ctx.font = "bold 8px monospace";
      ctx.fillText(isGrayFLI ? "GRAY FLI" : "FLI", isGrayFLI ? 120 : 145, 10);
    } else if (isHires) {
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
      let bgCol = c64Pal[currentBgColor]; // Global User BG
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
*/

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
  server.on("/setbg", handleSetBg);
  server.on("/setbrightness", handleSetBrightness);
  server.on("/setcontrast", handleSetContrast);
  server.on("/setdither", handleSetDither);
  server.on("/setdithertype", handleSetDitherType);
  server.on("/setscale", handleSetScale);
  server.on("/setscaling", handleSetScaling);
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

        // Precalculate mapping tables (aspect-ratio-aware)
        int targetW = IS_HIRES ? 320 : 160;
        int targetH = 200;
        int pixelAspect = IS_HIRES ? 1 : 2; // MC logical pixels are 2x wide visually

        int scaledLogicalW = targetW, scaledLogicalH = targetH;
        int offsetX = 0, offsetY = 0;
        int srcCropX = 0, srcCropY = 0;
        int srcCropW = currentJpgWidth, srcCropH = currentJpgHeight;

        if (scalingMode == 1) {
          // FIT: letterbox/pillarbox, whole image visible with black borders
          float srcAspect = (float)currentJpgWidth / currentJpgHeight;
          float dstAspect = (float)(targetW * pixelAspect) / targetH;
          if (srcAspect > dstAspect) {
            scaledLogicalW = targetW;
            float scale = (float)(targetW * pixelAspect) / currentJpgWidth;
            scaledLogicalH = (int)(currentJpgHeight * scale);
            offsetY = (targetH - scaledLogicalH) / 2;
          } else {
            scaledLogicalH = targetH;
            float scale = (float)targetH / currentJpgHeight;
            scaledLogicalW = (int)((float)currentJpgWidth * scale / pixelAspect);
            offsetX = (targetW - scaledLogicalW) / 2;
          }
        } else if (scalingMode == 2) {
          // CROP: center-crop source to fill screen at correct aspect
          float srcAspect = (float)currentJpgWidth / currentJpgHeight;
          float dstAspect = (float)(targetW * pixelAspect) / targetH;
          if (srcAspect > dstAspect) {
            // Source wider: crop left/right
            srcCropW = (int)((float)currentJpgHeight * (targetW * pixelAspect) / targetH);
            srcCropX = (currentJpgWidth - srcCropW) / 2;
          } else {
            // Source taller: crop top/bottom
            srcCropH = (int)((float)currentJpgWidth * targetH / (targetW * pixelAspect));
            srcCropY = (currentJpgHeight - srcCropH) / 2;
          }
        }
        // scalingMode == 0 (STRETCH): defaults fill the entire target

        for (int i = 0; i < currentJpgWidth && i < 1280; i++) {
          if (scalingMode == 2) {
            if (i < srcCropX || i >= srcCropX + srcCropW) { mapX_start[i] = mapX_end[i] = 0; }
            else { int ci = i - srcCropX; mapX_start[i] = (ci * scaledLogicalW) / srcCropW; mapX_end[i] = ((ci+1) * scaledLogicalW) / srcCropW; }
          } else {
            mapX_start[i] = offsetX + (i * scaledLogicalW) / currentJpgWidth;
            mapX_end[i]   = offsetX + ((i + 1) * scaledLogicalW) / currentJpgWidth;
          }
        }
        for (int i = 0; i < currentJpgHeight && i < 1024; i++) {
          if (scalingMode == 2) {
            if (i < srcCropY || i >= srcCropY + srcCropH) { mapY_start[i] = mapY_end[i] = 0; }
            else { int ci = i - srcCropY; mapY_start[i] = (ci * scaledLogicalH) / srcCropH; mapY_end[i] = ((ci+1) * scaledLogicalH) / srcCropH; }
          } else {
            mapY_start[i] = offsetY + (i * scaledLogicalH) / currentJpgHeight;
            mapY_end[i]   = offsetY + ((i + 1) * scaledLogicalH) / currentJpgHeight;
          }
        }

        // Setup render buffer and clear it BEFORE decoding starts (so bitwise OR works)
        render_buffer = c64_buffer + (1 - active_buffer) * 34005;
        memset(render_buffer, 0, 34005);
        if (scalingMode > 0) memset(color_buffer, 0, sizeof(color_buffer)); // clear black-bar areas for FIT/CROP
        
        // Reset Floyd-Steinberg error buffers for the new frame
        if (ditherAlgo == 5) memset(fs_err_buf, 0, sizeof(fs_err_buf));

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
          uint32_t checkSize = IS_IFLI ? 34000 : (IS_FLI ? 17000 : 10000);
          for (int i = 0; i < checkSize; i++) {
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
