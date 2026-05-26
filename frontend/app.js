// ESPStreamer Frontend Logic - VERSION 8.4 (Syntax Hardened)
let currentClientMode = 'mc_gray', isHires = false, isFLI = false, isIFLI = false, currentBgColor = 0;
let running = true, usePCBackend = true, screenshots = [];
let lastStatsTime = 0, lastFrames = 0, lastKB = 0, currentFPS = 0, currentKBs = 0;

// Kung Fu Flash WebSocket client
let kungFuWebSocket = null;
let kungFuConnected = false;
let kungFuViceMode = false; // VICE simulation mode
let frameResolve = null; // For async frame sync

// Size tracking for export limits
const MAX_PRG_SIZE = 65536; // ~64KB max for C64 PRG
const MAX_CRT_SIZE = 1048576; // 1MB max for EasyFlash CRT
const MAX_EF_FRAMES = 63; // Max images in 1MB EasyFlash CRT (10KB/image across ROML+ROMH)
let totalCaptureSize = 0;
const palettes = [[[0, 0, 0], [255, 255, 255], [104, 55, 43], [112, 164, 178], [111, 61, 134], [88, 141, 67], [53, 40, 121], [184, 199, 111], [111, 79, 37], [67, 57, 0], [154, 103, 89], [68, 68, 68], [108, 108, 108], [154, 210, 132], [108, 94, 181], [149, 149, 149]], [[0, 0, 0], [255, 255, 255], [129, 51, 56], [117, 205, 200], [142, 60, 151], [86, 172, 93], [45, 48, 173], [237, 240, 175], [142, 80, 41], [85, 56, 0], [196, 108, 113], [74, 74, 74], [123, 123, 123], [169, 255, 159], [112, 117, 213], [170, 170, 170]]];
let currentPaletteIdx = 0, c64Pal = palettes[0];
let espBaseUrl = 'http://192.168.50.145'; // Updated from input field
async function apiFetch(path) {
  if (usePCBackend) { return await window.C64Engine.apiCall(path); }
  const ipEl = document.getElementById('esp-ip');
  if (ipEl) espBaseUrl = 'http://' + ipEl.value.replace(/^https?:\/\//, '');
  return fetch(espBaseUrl + path);
}
function setBackendMode(m) { usePCBackend = (m === 'pc'); document.getElementById('btn-backend-pc').style.borderColor = usePCBackend ? '#40ff40' : '#6c8cff'; if (usePCBackend) window.C64Engine.start(); else window.C64Engine.stop(); syncAll(); }
function syncAll() { sendContrast(); sendBrightness(); sendSaturation(); sendBg(); sendPalette(); sendDither(); sendDitherType(); sendScaling(); }
function resetKungFuStreamBuffers(mode) {
  if (kungFuWebSocket && kungFuWebSocket.readyState === WebSocket.OPEN) {
    kungFuWebSocket.send(JSON.stringify({ command: 'reset_buffers', mode }));
  }
}
function sendSettingWithC64Reset(path, reason) { resetKungFuStreamBuffers(reason); return apiFetch(path); }
function toggleMode() { const m = document.getElementById('mode-sel').value; currentClientMode = m; updateModeUI(); resetKungFuStreamBuffers(m); apiFetch('/setmode?m=' + m); syncAll(); }
function updateModeUI() { isHires = currentClientMode.includes('hr'); isFLI = currentClientMode.includes('fli'); isIFLI = currentClientMode.includes('ifli'); const cv = document.getElementById('c'); cv.width = isHires ? 320 : 160; cv.height = 200; let bge = document.getElementById('badge'); if (bge) { bge.style.display = 'inline-block'; bge.innerText = currentClientMode.toUpperCase().replace(/_/g, ' '); } }
function updateContrastText() { document.getElementById('cval').innerText = parseFloat(document.getElementById('contrast').value).toFixed(1); }
function sendContrast() { sendSettingWithC64Reset('/setcontrast?c=' + document.getElementById('contrast').value, 'contrast'); }
function updateBrightnessText() { document.getElementById('bval').innerText = document.getElementById('brightness').value; }
function sendBrightness() { sendSettingWithC64Reset('/setbrightness?b=' + document.getElementById('brightness').value, 'brightness'); }
function updateSaturationText() { document.getElementById('sval').innerText = parseFloat(document.getElementById('saturation').value).toFixed(1); }
function sendSaturation() { sendSettingWithC64Reset('/setsaturation?s=' + document.getElementById('saturation').value, 'saturation'); }
function updateDitherText() { document.getElementById('dval').innerText = document.getElementById('dither').value; }
function sendDither(resetBuffers = true) { const path = '/setdither?d=' + document.getElementById('dither').value; return resetBuffers ? sendSettingWithC64Reset(path, 'dither') : apiFetch(path); }
function sendDitherType() { sendSettingWithC64Reset('/setdithertype?t=' + document.getElementById('ditherType').value, 'dither type'); sendDither(false); }
function sendBg() { const e = document.getElementById('bgcolor'); if (e) sendSettingWithC64Reset('/setbg?c=' + e.value, 'background color'); }
function sendScaling() { const e = document.getElementById('scaling'); if (e) { sendSettingWithC64Reset('/setscaling?s=' + e.value, 'scaling'); document.getElementById('c').setAttribute('data-scale', e.value); } }
function sendPalette() { sendSettingWithC64Reset('/setpalette?p=' + document.getElementById('pal-sel').value, 'palette'); }
function download(d, n) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([d])); a.download = n; a.click(); }

// Kung Fu Flash WebSocket functions
async function connectKungFuFlash() {
  try {
    // Choose server based on mode
    const port = kungFuViceMode ? 8766 : 8765;
    const serverName = kungFuViceMode ? 'VICE Simulation' : 'Kung Fu Flash';
    
    kungFuWebSocket = new WebSocket(`ws://localhost:${port}`);
    
    kungFuWebSocket.onopen = function() {
      void 0;
      kungFuConnected = true;
      updateKungFuStatus('Connecting to USB...', true);
      
      // Request connection to COM port
      kungFuWebSocket.send(JSON.stringify({command: 'connect'}));
    };
    
    kungFuWebSocket.onmessage = function(event) {
      const response = JSON.parse(event.data);
      handleKungFuResponse(response);
    };
    
    kungFuWebSocket.onclose = function() {
      void 0;
      kungFuConnected = false;
      updateKungFuStatus('Disconnected', false);
    };
    
    kungFuWebSocket.onerror = function(error) {
      void 0;
      updateKungFuStatus('Error', false);
    };
    
  } catch (error) {
    void 0;
    updateKungFuStatus('Connection Failed', false);
  }
}

async function downloadKFFViewer() {
  if (!kungFuWebSocket || kungFuWebSocket.readyState !== WebSocket.OPEN) {
    alert('Not connected to Kung Fu Flash server. Please click Connect first.');
    return;
  }
  
  updateKungFuStatus('Requesting Viewer PRG...', true);
  kungFuWebSocket.send(JSON.stringify({command: 'get_viewer'}));
}

async function sendKFFViewer() {
  if (!kungFuWebSocket || kungFuWebSocket.readyState !== WebSocket.OPEN) {
    alert('Not connected to Kung Fu Flash server. Please click Connect first.');
    return;
  }
  
  updateKungFuStatus('Sending Viewer PRG to C64...', true);
  kungFuWebSocket.send(JSON.stringify({command: 'send_viewer'}));
}

function toggleViceMode() {
  kungFuViceMode = !kungFuViceMode;
  const modeText = kungFuViceMode ? 'VICE Mode' : 'Hardware Mode';
  const modeColor = kungFuViceMode ? '#ff8040' : '#40ff40';
  
  const modeElement = document.getElementById('vice-mode');
  if (modeElement) {
    modeElement.textContent = modeText;
    modeElement.style.color = modeColor;
  }
  
  // Disconnect if connected
  if (kungFuWebSocket) {
    disconnectKungFuFlash();
  }
  
  updateKungFuStatus(`Ready for ${modeText}`, false);
}

function handleKungFuResponse(response) {
  if (response.type === 'response') {
    switch (response.command) {
      case 'connect':
        updateKungFuStatus(response.success ? 'USB Connected' : 'USB Failed', response.success);
        break;
      case 'send_viewer':
        updateKungFuStatus(response.success ? 'Viewer Running!' : (response.message || 'Viewer Failed'), response.success);
        break;
      case 'stream_frame':
        updateKungFuStatus(response.success ? (response.message || 'Frame Sent') : 'Send Failed', response.success);
        if (frameResolve) {
          frameResolve(response.success);
          frameResolve = null;
        }
        break;
      case 'status':
        updateKungFuStatus(response.connected ? 'USB Connected' : 'USB Disconnected', response.connected);
        break;
      case 'reset':
        updateKungFuStatus('Reset sent', response.success);
        break;
      case 'get_viewer':
        if (response.success && response.prg_data) {
          // Decode base64 and download
          const binaryString = window.atob(response.prg_data);
          const bytes = new Uint8Array(binaryString.length);
          for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
          }
          download(bytes, response.filename || 'kungfu_viewer.prg');
          updateKungFuStatus('Viewer Downloaded', true);
        } else {
          updateKungFuStatus('Download Failed', false);
        }
        break;
    }
  } else if (response.type === 'error') {
    updateKungFuStatus('Error: ' + response.message, false);
  }
}


function updateKungFuStatus(status, connected) {
  const statusElement = document.getElementById('kungfu-status');
  if (statusElement) {
    statusElement.textContent = status;
    statusElement.style.color = connected ? '#40ff40' : '#ff4040';
  }
}

async function sendImageToC64() {
  if (!kungFuWebSocket || kungFuWebSocket.readyState !== WebSocket.OPEN) {
    alert('Not connected to Kung Fu Flash server');
    return;
  }
  
  if (screenshots.length === 0) {
    alert('No screenshots to stream');
    return;
  }
  
  try {
    // Get the latest screenshot
    const latestScreenshot = screenshots[screenshots.length - 1];
    if (!latestScreenshot.bmpData) {
      alert('Legacy screenshot without binary data cannot be streamed');
      return;
    }
    
    // Build binary payload
    const payload = new Uint8Array(2 + latestScreenshot.bmpData.length);
    payload[0] = latestScreenshot.isHires ? 1 : 0;
    payload[1] = currentBgColor || 0;
    payload.set(latestScreenshot.bmpData, 2);
    
    kungFuWebSocket.send(payload);
    updateKungFuStatus('Image Sent', true);
    
  } catch (error) {
    void 0;
    updateKungFuStatus('Stream Failed', false);
  }
}

let c64StreamInterval = null;
let kffFpsFrames = 0;
let kffFpsLastTime = 0;

async function toggleStream() {
  if (!kungFuWebSocket || kungFuWebSocket.readyState !== WebSocket.OPEN) {
    alert('Not connected to Kung Fu Flash server');
    return;
  }

  const toggleBtn = document.getElementById('stream-toggle-btn');
  const fpsEl = document.getElementById('kungfu-fps');

  if (c64StreamInterval) {
    // We reuse this variable name for the "running" state
    c64StreamInterval = false; 
    if (toggleBtn) toggleBtn.textContent = 'Start Stream';
    updateKungFuStatus('Stream Stopped', true);
    if (fpsEl) fpsEl.style.display = 'none';
  } else {
    c64StreamInterval = true;
    if (toggleBtn) toggleBtn.textContent = 'Stop Stream';
    updateKungFuStatus('Streaming...', true);
    
    kffFpsFrames = 0;
    kffFpsLastTime = Date.now();
    if (fpsEl) {
      fpsEl.style.display = 'inline-block';
      fpsEl.textContent = 'FPS: 0.0';
    }
    
    // Start the async loop
    const streamLoop = async () => {
      if (!c64StreamInterval || !kungFuWebSocket || kungFuWebSocket.readyState !== WebSocket.OPEN) {
        c64StreamInterval = false;
        if (fpsEl) fpsEl.style.display = 'none';
        return;
      }
      
      try {
        const r = await apiFetch('/data?t=' + Date.now());
        if (!r.ok) {
          setTimeout(streamLoop, 100);
          return;
        }
        const rawBmp = new Uint8Array(await r.arrayBuffer());
        
        const payload = new Uint8Array(2 + rawBmp.length);
        payload[0] = isHires ? 1 : 0;
        payload[1] = currentBgColor || 0;
        payload.set(rawBmp, 2);
        
        // Wait for response from server before next frame
        const frameDone = new Promise(resolve => { frameResolve = resolve; });
        kungFuWebSocket.send(payload);
        
        // Wait for the ACK from the server (which waited for ACK from C64)
        await Promise.race([
            frameDone,
            new Promise((_, reject) => setTimeout(() => reject('timeout'), 5000))
        ]);
        
        // FPS Tracking
        kffFpsFrames++;
        const now = Date.now();
        if (now - kffFpsLastTime >= 1000) {
          const fps = (kffFpsFrames * 1000 / (now - kffFpsLastTime)).toFixed(1);
          if (fpsEl) {
            fpsEl.textContent = `FPS: ${fps}`;
          }
          kffFpsFrames = 0;
          kffFpsLastTime = now;
        }
        
        // Next frame immediately (or with small delay to prevent browser locking)
        if (c64StreamInterval) setTimeout(streamLoop, 10); 
      } catch (error) {
        void 0;
        if (c64StreamInterval) setTimeout(streamLoop, 1000);
      }
    };
    
    streamLoop();
  }
}

function testInjection() {
  if (!kungFuWebSocket || kungFuWebSocket.readyState !== WebSocket.OPEN) {
    alert('Not connected to Kung Fu Flash server');
    return;
  }
  
  try {
    // Send test injection command
    const message = {
      command: 'test_injection'
    };
    
    kungFuWebSocket.send(JSON.stringify(message));
    updateKungFuStatus('Testing injection...', true);
    
  } catch (error) {
    void 0;
    updateKungFuStatus('Test Failed', false);
  }
}

function disconnectKungFuFlash() {
  if (kungFuWebSocket) {
    kungFuWebSocket.close();
    kungFuWebSocket = null;
  }
  kungFuConnected = false;
  updateKungFuStatus('Disconnected', false);
}

// Per-frame size: 10000 bytes for MC, 17000 for FLI, 34000 for IFLI
function frameSizeForMode(mode) {
  if (!mode) mode = currentClientMode;
  return mode.includes('ifli') ? 34000 : (mode.includes('fli') ? 17000 : 10000);
}
// PRG slideshow: frames at $4000, $6710, $8E20 (max 3 frames)
// Bitmap copy writes to $2000-$3F3F — any frame below $4000 gets overwritten!
// With $0001=$36 (BASIC ROM off), $A000-$BFFF is accessible RAM.
// Frame 2 ($8E20-$B52F) crosses into that area safely.
// Frame 3 would start at $B530 and end at $DC3F, crossing I/O at $D000 — not safe.
const MAX_PRG_FRAMES = 3;
function prgSlideshowSize(nFrames) {
  nFrames = Math.min(nFrames, MAX_PRG_FRAMES);
  const frameBase = [0x4000, 0x6710, 0x8E20];
  return 2 + (frameBase[nFrames - 1] + 10000 - 0x0801);
}

function calculateCaptureSize() {
  const n = screenshots.length;
  if (n === 0) return 0;
  const fsize = frameSizeForMode(screenshots[0] ? screenshots[0].mode : null);
  if (n === 1) return 14145; // single PRG min size
  return prgSlideshowSize(n); // multi-frame PRG size estimate
}

function updateButtonStates() {
  const n = screenshots.length;
  totalCaptureSize = calculateCaptureSize();
  const fsize = frameSizeForMode(screenshots[0] ? screenshots[0].mode : null);
  const perFrame = (fsize / 1024).toFixed(1);
  const totalKB = (totalCaptureSize / 1024).toFixed(1);
  const multiPRGSize = n > 1 ? prgSlideshowSize(Math.min(n, MAX_PRG_FRAMES)) : 14145;
  const prgOK = multiPRGSize <= MAX_PRG_SIZE;
  const crtOK = n <= MAX_EF_FRAMES;

  // Update size display
  let sizeEl = document.getElementById('size-info');
  if (sizeEl) {
    if (n === 0) sizeEl.innerHTML = '';
    else sizeEl.innerHTML = `<span style="color:#a0b4ff">${perFrame} KB/frame &nbsp;|&nbsp; <span style="color:${prgOK?'#a0ff90':'#ff6060'}">${(multiPRGSize/1024).toFixed(1)} KB PRG</span> &nbsp;|&nbsp; <span style="color:${crtOK?'#a0ff90':'#ff6060'}">${n}/${MAX_EF_FRAMES} CRT</span> &nbsp;|&nbsp; ${n} frame${n>1?'s':''}</span>`;
  }

  document.querySelectorAll('button[onclick*="save(\'PRG\'"]').forEach(btn => {
    btn.disabled = !prgOK;
    btn.style.opacity = prgOK ? '1' : '0.5';
    btn.style.cursor = prgOK ? 'pointer' : 'not-allowed';
    btn.title = prgOK ? `PRG slideshow (${(multiPRGSize/1024).toFixed(1)} KB)` : `Too large: ${(multiPRGSize/1024).toFixed(0)} KB > 64 KB. Max ${MAX_PRG_FRAMES} frames.`;
  });
  document.querySelectorAll('button[onclick*="save(\'CRT\'"]').forEach(btn => {
    btn.disabled = !crtOK;
    btn.style.opacity = crtOK ? '1' : '0.5';
    btn.title = crtOK ? `EasyFlash CRT slideshow (${n}/${MAX_EF_FRAMES} frames)` : `Too many frames for 1MB EasyFlash CRT (max ${MAX_EF_FRAMES})`;
  });
  document.querySelectorAll('button[onclick*="save(\'KOA\'"]').forEach(btn => {
    btn.title = 'KOA: single frame export';
  });
}
async function captureImage() {
  const canvas = document.getElementById('c');
  if (!canvas) { alert('Canvas not found!'); return; }
  try {
    // Fetch raw C64 binary data alongside the visual thumbnail
    const r = await apiFetch('/data?t=' + Date.now());
    const bmpData = new Uint8Array(await r.arrayBuffer());
    const thumb = canvas.toDataURL('image/png');
    const timestamp = new Date().toLocaleTimeString();
    screenshots.push({ thumb, bmpData, timestamp, mode: currentClientMode, isHires, isFLI, isIFLI });
    document.getElementById('screenshot-count').textContent = screenshots.length;
    updateButtonStates();
    void 0;
  } catch(e) {
    void 0;
    alert('Capture failed: ' + e.message);
  }
}

function viewScreenshots() {
  void 0;
  
  const existingModal = document.getElementById('screenshots-modal');
  if (existingModal) existingModal.remove();

  if (screenshots.length === 0) {
    alert('No screenshots captured yet. Click the CAPTURE button to save frames.');
    return;
  }
  
  // Create modal or simple display
  let html = `<div style="background: rgba(20,20,50,0.95); padding: 20px; border-radius: 16px; max-width: 800px; max-height: 600px; overflow-y: auto;">
    <h3 style="color: #e0e0ff; margin-bottom: 15px;">Captured Screenshots (${screenshots.length})</h3>`;
  
  screenshots.forEach((shot, index) => {
    // Handle both simplified and full capture data
    const mode = shot.mode || currentClientMode || 'unknown';
    const isHires = shot.isHires || currentClientMode.includes('hr') || false;
    const isFLI = shot.isFLI || currentClientMode.includes('fli') || false;
    const isIFLI = shot.isIFLI || currentClientMode.includes('ifli') || false;
    const timestamp = shot.timestamp || 'Unknown time';
    
    void 0;
    
    html += `
      <div style="margin-bottom: 15px; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 8px;">
        <div style="display: flex; gap: 15px; align-items: center;">
          <img src="${shot.thumb}" style="width: 240px; aspect-ratio: 8 / 5; height: auto; image-rendering: pixelated; object-fit: fill; border: 2px solid #6c8cff; border-radius: 4px;">
          <div style="color: #a0b4ff; font-family: 'Share Tech Mono', monospace;">
            <div><strong>Frame ${index + 1}</strong></div>
            <div>Mode: ${mode.toUpperCase()}</div>
            <div>Time: ${timestamp}</div>
            <div>Colors: ${isHires ? 'Hires' : (isFLI ? 'FLI' : (isIFLI ? 'IFLI' : 'Multicolor'))}</div>
            <div>Type: ${shot.test ? 'Direct Capture' : 'API Capture'}</div>
            <div style="margin-top: 10px;">
              <button onclick="downloadScreenshot(${index})" style="padding: 5px 10px; background: #6c8cff; border: none; border-radius: 4px; color: white; cursor: pointer;">Download</button>
              <button onclick="deleteScreenshot(${index})" style="padding: 5px 10px; background: #ff6b6b; border: none; border-radius: 4px; color: white; cursor: pointer; margin-left: 5px;">Delete</button>
            </div>
          </div>
        </div>
      </div>`;
  });
  
  html += `<div style="text-align: center; margin-top: 20px;">
    <button onclick="document.getElementById('screenshots-modal')?.remove()" style="padding: 10px 20px; background: #404080; border: none; border-radius: 8px; color: white; cursor: pointer;">Close</button>
  </div></div>`;
  
  void 0;
  const modal = document.createElement('div');
  modal.id = 'screenshots-modal';
  modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center; z-index: 1000;';
  modal.innerHTML = html;
  document.body.appendChild(modal);
  void 0;
}

function downloadScreenshot(index) {
  void 0;
  const shot = screenshots[index];
  
  // Handle both simplified and full capture data
  const isHires = shot.isHires || currentClientMode.includes('hr') || false;
  const mode = shot.mode || currentClientMode || 'capture';
  const timestamp = shot.timestamp || new Date().toLocaleTimeString();
  
  // Create download link directly from dataURL
  const a = document.createElement('a');
  a.href = shot.thumb;
  a.download = `c64_capture_${index + 1}_${mode}_${timestamp.replace(/:/g, '-')}.png`;
  a.click();
  
  void 0;
}

function deleteScreenshot(index) {
  screenshots.splice(index, 1);
  
  // Update button states based on new total size
  updateButtonStates();
  
  // Update screenshot count display
  const countElement = document.getElementById('screenshot-count');
  if (countElement) {
    countElement.textContent = screenshots.length;
  }
  
  viewScreenshots(); // Refresh the view
}

async function save(t) {
  // Multi-frame: route to slideshow generators
  if (screenshots.length > 1 && t === 'PRG') { await createSlideshow('PRG'); return; }
  if (screenshots.length > 1 && t === 'CRT') { await createSlideshow('CRT'); return; }
  
  // Single image or CRT export - use original logic
  const r = await apiFetch('/data?t=' + Date.now());
  const rawBmp = new Uint8Array(await r.arrayBuffer());

  let sZ = isIFLI ? 49155 : (isFLI ? 32768 : 14145);
  let f = new Uint8Array(sZ);
  f[0] = 0x01;
  f[1] = 0x08;
  f.set([0x0B, 0x08, 0x0A, 0x00, 0x9E, 0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00], 2);

  let o = (addr) => addr - 0x0801 + 2;
  const hVal = isHires ? 0xC8 : 0xD8;

  if (isIFLI) {
    const asm = [
      0x78, 0xD8, 0xA9, 0x34, 0x85, 0x01, 0xA9, 0x03, 0x8D, 0x02, 0xDD, 0xA9, 0x00, 0x85, 0xFC, 0x85,
      0xFE, 0xA9, 0x80, 0x85, 0xFD, 0xA9, 0xC0, 0x85, 0xFF, 0xA2, 0x40, 0xA0, 0x00, 0xB1, 0xFC, 0x91,
      0xFE, 0xC8, 0xD0, 0xF9, 0xE6, 0xFD, 0xE6, 0xFF, 0xCA, 0xD0, 0xF2, 0xA9, 0x35, 0x85, 0x01, 0xA2,
      0x00, 0x8A, 0x29, 0x07, 0x09, 0x38, 0x9D, 0x00, 0x09, 0x8A, 0x29, 0x07, 0x0A, 0x0A, 0x0A, 0x0A,
      0x09, 0x08, 0x9D, 0x00, 0x0A, 0xE8, 0xE0, 0xC8, 0xD0, 0xE7, 0xA2, 0x00, 0xBD, 0x00, 0x10, 0x9D,
      0x00, 0xD8, 0xBD, 0xFA, 0x10, 0x9D, 0xFA, 0xD8, 0xBD, 0xF4, 0x11, 0x9D, 0xF4, 0xD9, 0xBD, 0xEE,
      0x12, 0x9D, 0xEE, 0xDA, 0xE8, 0xE0, 0xFA, 0xD0, 0xE3, 0xA9, 0x3B, 0x8D, 0x11, 0xD0, 0xA9,
      0xD8, 0x8D, 0x16, 0xD0, 0xA9, currentBgColor, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0, 0xA9, 0x08, 0x8D,
      0x18, 0xD0, 0xA9, 0x02, 0x85, 0x02, 0xAD, 0x12, 0xD0, 0xC9, 0xF8, 0xD0, 0xF9, 0xA5, 0x02, 0x49,
      0x02, 0x85, 0x02, 0x8D, 0x00, 0xDD, 0xAD, 0x11, 0xD0, 0x30, 0xFB, 0xAD, 0x12, 0xD0, 0xC9, 0x2F,
      0xD0, 0xF9, 0xA2, 0x07, 0xCA, 0xD0, 0xFD, 0xEA, 0xA0, 0x00, 0xB9, 0x00, 0x0A, 0x8D, 0x11, 0xD0,
      0xB9, 0x00, 0x09, 0x8D, 0x18, 0xD0, 0xC8, 0xC0, 0xC8, 0xD0, 0xEF, 0x4C, 0x8E, 0x08
    ];
    f.set(asm, 14);
    for (let i = 0; i < 1000; i++) f[o(0x1000) + i] = rawBmp[16000 + i];
    for (let i = 0; i < 8192; i++) {
      f[o(0x4000) + i] = rawBmp[8000 + i];
      f[o(0x6000) + i] = rawBmp[i];
      f[o(0x8000) + i] = rawBmp[25000 + i];
      f[o(0xA000) + i] = rawBmp[17000 + i];
    }
  } else if (isFLI) {
    const asm = [
      0x78, 0xD8, 0xA9, 0x37, 0x85, 0x01, 0xA9, 0x03, 0x8D, 0x02, 0xDD, 0xA2, 0x00, 0x8A, 0x29, 0x07,
      0x09, 0x38, 0x9D, 0x00, 0x09, 0x8A, 0x29, 0x07, 0x0A, 0x0A, 0x0A, 0x0A, 0x09, 0x08, 0x9D, 0x00,
      0x0A, 0xE8, 0xE0, 0xC8, 0xD0, 0xE7, 0xA2, 0x00, 0xBD, 0x00, 0x10, 0x9D, 0x00, 0xD8, 0xBD, 0xFA,
      0x10, 0x9D, 0xFA, 0xD8, 0xBD, 0xF4, 0x11, 0x9D, 0xF4, 0xD9, 0xBD, 0xEE, 0x12, 0x9D, 0xEE, 0xDA,
      0xE8, 0xE0, 0xFA, 0xD0, 0xE3, 0xA9, 0x3B, 0x8D, 0x11, 0xD0, 0xA9, 0xD8, 0x8D, 0x16, 0xD0, 0xA9,
      currentBgColor, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0, 0xA9, 0x08, 0x8D, 0x18, 0xD0, 0xA9, 0x02, 0x8D,
      0x00, 0xDD, 0xAD, 0x12, 0xD0, 0xC9, 0xF8, 0xD0, 0xF9, 0xAD, 0x11, 0xD0, 0x30, 0xFB, 0xAD, 0x12,
      0xD0, 0xC9, 0x2F, 0xD0, 0xF9, 0xA2, 0x07, 0xCA, 0xD0, 0xFD, 0xEA, 0xA0, 0x00, 0xB9, 0x00, 0x0A,
      0x8D, 0x18, 0xD0, 0xB9, 0x00, 0x09, 0x8D, 0x11, 0xD0, 0xC8, 0xC0, 0xC8, 0xD0, 0xEF, 0x4C, 0x6E, 0x08
    ];
    f.set(asm, 14);
    for (let i = 0; i < 1000; i++) f[o(0x1000) + i] = rawBmp[16000 + i];
    for (let i = 0; i < 8192; i++) f[o(0x4000) + i] = rawBmp[8000 + i];
    for (let i = 0; i < 8000; i++) f[o(0x6000) + i] = rawBmp[i];
  } else {
    const asm = [
      0x78, 0xD8, 0xA9, 0x37, 0x85, 0x01, 0xA9, 0x03, 0x8D, 0x02, 0xDD, 0xA9, 0x03, 0x8D, 0x00, 0xDD,
      0xA9, 0x3B, 0x8D, 0x11, 0xD0, 0xA9, hVal, 0x8D, 0x16, 0xD0, 0xA9, 0x18, 0x8D, 0x18, 0xD0, 0xA9,
      currentBgColor, 0x8D, 0x20, 0xD0, 0x8D, 0x21, 0xD0, 0xA2, 0x00, 0xBD, 0x75, 0x08, 0x9D, 0x00, 0x04,
      0xBD, 0x6F, 0x09, 0x9D, 0xFA, 0x04, 0xBD, 0x69, 0x0A, 0x9D, 0xF4, 0x05, 0xBD, 0x63, 0x0B, 0x9D,
      0xEE, 0x06, 0xE8, 0xE0, 0xFA, 0xD0, 0xE3, 0xA2, 0x00, 0xBD, 0x5D, 0x0C, 0x9D, 0x00, 0xD8, 0xBD,
      0x57, 0x0D, 0x9D, 0xFA, 0xD8, 0xBD, 0x51, 0x0E, 0x9D, 0xF4, 0xD9, 0xBD, 0x4B, 0x0F, 0x9D, 0xEE,
      0xDA, 0xE8, 0xE0, 0xFA, 0xD0, 0xE3, 0x4C, 0x6E, 0x08
    ];
    f.set(asm, 14);
    for (let i = 0; i < 1000; i++) f[118 + i] = rawBmp[8000 + i];
    for (let i = 0; i < 1000; i++) f[1118 + i] = rawBmp[9000 + i];
    f.set(rawBmp.subarray(0, 8000), 6145);
  }

  if (t === 'PRG') return download(f, isIFLI ? 'ifli.prg' : (isFLI ? 'fli.prg' : (isHires ? 'hires.prg' : 'v.prg')));

  const pbL = f.subarray(2);
  const nB = Math.ceil(pbL.length / 8192);
  const h = new Uint8Array(64);
  h.set([0x43, 0x36, 0x34, 0x20, 0x43, 0x41, 0x52, 0x54, 0x52, 0x49, 0x44, 0x47, 0x45, 0x20, 0x20, 0x20], 0);
  h[0x13] = 0x40; h[0x14] = 0x01; h[0x15] = 0x00; h[0x17] = 0x20; h[0x18] = 0x01; h[0x19] = 0x00;
  h.set(new TextEncoder().encode("ESPSTREAMER").subarray(0, 32), 0x20);

  const crt = [h];
  const mk = (b, a, t, d) => {
    const p = new Uint8Array(16 + 8192).fill(0);
    p.set([0x43, 0x48, 0x49, 0x50, 0, 0, 0x20, 0x10, 0, t, (b >> 8), (b & 0xFF), (a >> 8), (a & 0xFF), 0x20, 0], 0);
    p.set(d.subarray(0, 8192), 16);
    return p;
  };
  const nB1 = nB + 1;

  const boot = new Uint8Array(8192).fill(0xFF);
  boot.set([
    0x78, 0xD8, 0xA2, 0xFF, 0x9A, 0xA9, 0x35, 0x85, 0x01, 0xA2, 0x47, 0xBD, 0x17, 0xE0, 0x9D, 0x00, 
    0x02, 0xCA, 0x10, 0xF7, 0x4C, 0x00, 0x02, 0xA9, 0x02, 0x8D, 0x02, 0xDE, 0xA9, 0x01, 0x85, 0xFD, 
    0xA9, 0x01, 0x85, 0xFB, 0xA9, 0x08, 0x85, 0xFC, 0xA5, 0xFD, 0x8D, 0x00, 0xDE, 0xA9, 0x00, 0x85, 
    0xFE, 0xA9, 0x80, 0x85, 0xFF, 0xA9, 0x20, 0x8D, 0x00, 0x03, 0xA0, 0x00, 0xB1, 0xFE, 0x91, 0xFB, 
    0xC8, 0xD0, 0xF9, 0xE6, 0xFC, 0xE6, 0xFF, 0xCE, 0x00, 0x03, 0xD0, 0xEE, 0xE6, 0xFD, 0xA5, 0xFD, 
    0xC9, nB1, 0xD0, 0xD4, 0xA9, 0x04, 0x8D, 0x02, 0xDE, 0x8D, 0xFF, 0xDF, 0x4C, 0x0D, 0x08
  ], 0);
  boot.set([0x00, 0xE0, 0x00, 0xE0, 0x01, 0xE0], 8186);

  crt.push(mk(0, 0xA000, 2, boot));
  for (let b = 0; b < nB; b++) {
    crt.push(mk(b + 1, 0x8000, 2, pbL.subarray(b * 8192, (b + 1) * 8192)));
  }

  const totalL = crt.reduce((acc, v) => acc + v.length, 0);
  const res = new Uint8Array(totalL);
  let txOf = 0;
  for (const c of crt) {
    res.set(c, txOf);
    txOf += c.length;
  }
  download(res, 'stream.crt');
}

// ==========================================================
// Slideshow PRG generator
// Frames at $1000, $3710, $5E20, $8530 (max 4 for PRG)
// Machine code at $080D (217 bytes), frame table at $0900
// ==========================================================
function buildSlideshowPRG(frames, bgColor) {
  const n = Math.min(frames.length, MAX_PRG_FRAMES);
  // Frame storage starts at $4000 — safely above bitmap copy dest ($2000-$3F3F)
  const frameAddrs = [0x4000, 0x6710, 0x8E20];
  const tableAddr  = 0x0900;
  const showFrameAbs = 0x0832; // $080D + 37 bytes of init code

  // Assembled 6502 machine code (222 bytes) starting at $080D:
  // - Kills EasyFlash cart (no-op for PRG, ensures ROML at $8000 is gone for CRT)
  // - Inits VIC for MC bitmap, disables BASIC ROM ($0001=$36 to access $A000 RAM)
  // - Copies each frame's bitmap->$2000, screen->$0400, color->$D800
  // - Waits ~2s via raster-$FE counting, then advances frame and loops
  const asm = [
    0x78,                               // SEI
    0xA9,0x04, 0x8D,0x02,0xDE,        // LDA #$04, STA $DE02 (kill EasyFlash — NOP if no cart)
    0xA9,0x35, 0x85,0x01,              // LDA #$35, STA $01 (BASIC+KERNAL ROM off, I/O on)
    0xA9,0x3B, 0x8D,0x11,0xD0,        // LDA #$3B, STA $D011 (bitmap on)
    0xA9,0xD8, 0x8D,0x16,0xD0,        // LDA #$D8, STA $D016 (multicolor)
    0xA9,0x18, 0x8D,0x18,0xD0,        // LDA #$18, STA $D018 (scr@$0400 bmp@$2000)
    0xA9,bgColor&0xFF, 0x8D,0x20,0xD0,0x8D,0x21,0xD0, // border+bg
    0xA9,0x00, 0x85,0xFB,              // LDA #0, STA $FB (frame_idx)
    // show_frame: (offset 37 = $0832)
    0xA5,0xFB, 0x0A, 0xAA,            // LDA $FB; ASL; TAX
    0xBD,tableAddr&0xFF,(tableAddr>>8)&0xFF, 0x85,0xFD, // LDA tbl,X → src_lo
    0xE8,
    0xBD,tableAddr&0xFF,(tableAddr>>8)&0xFF, 0x85,0xFE, // LDA tbl,X → src_hi
    // Copy bitmap: dest=$2000, 31 pages + 64 bytes
    0xA9,0x00,0x85,0x02, 0xA9,0x20,0x85,0x03, // dest=$2000
    0xA2,0x1F, 0xA0,0x00,              // LDX #31, LDY #0
    0xB1,0xFD, 0x91,0x02, 0xC8,0xD0,0xF9, // inner 256-byte loop
    0xE6,0xFE, 0xE6,0x03, 0xCA,0xD0,0xF2, // advance ptrs, outer loop
    0xA0,0x00, 0xB1,0xFD, 0x91,0x02, 0xC8,0xC0,0x40,0xD0,0xF7, // 64 remaining
    0xA5,0xFD,0x18,0x69,0x40,0x85,0xFD, 0x90,0x02,0xE6,0xFE, // advance src +64
    // Copy screen: dest=$0400, 3 pages + 232 bytes
    0xA9,0x00,0x85,0x02, 0xA9,0x04,0x85,0x03,
    0xA2,0x03, 0xA0,0x00,
    0xB1,0xFD, 0x91,0x02, 0xC8,0xD0,0xF9,
    0xE6,0xFE, 0xE6,0x03, 0xCA,0xD0,0xF2,
    0xA0,0x00, 0xB1,0xFD, 0x91,0x02, 0xC8,0xC0,0xE8,0xD0,0xF7,
    0xA5,0xFD,0x18,0x69,0xE8,0x85,0xFD, 0x90,0x02,0xE6,0xFE, // advance +232
    // Copy color: dest=$D800, 3 pages + 232 bytes
    0xA9,0x00,0x85,0x02, 0xA9,0xD8,0x85,0x03,
    0xA2,0x03, 0xA0,0x00,
    0xB1,0xFD, 0x91,0x02, 0xC8,0xD0,0xF9,
    0xE6,0xFE, 0xE6,0x03, 0xCA,0xD0,0xF2,
    0xA0,0x00, 0xB1,0xFD, 0x91,0x02, 0xC8,0xC0,0xE8,0xD0,0xF7,
    // Wait: count 100 raster-$FE crossings (~2s at 50Hz)
    0xA9,100, 0x85,0xFC,
    0xAD,0x12,0xD0, 0xC9,0xFE, 0xD0,0xF9, // wait_find_FE
    0xAD,0x12,0xD0, 0xC9,0xFE, 0xF0,0xF9, // wait_pass_FE
    0xC6,0xFC, 0xD0,0xEE,                  // DEC $FC; BNE wait_find_FE
    // Advance frame and loop
    0xE6,0xFB, 0xA5,0xFB, 0xC9,n,         // INC $FB; LDA $FB; CMP #n
    0xD0,0x04,                             // BNE → JMP show_frame
    0xA9,0x00, 0x85,0xFB,                  // reset frame_idx=0
    0x4C,showFrameAbs&0xFF,(showFrameAbs>>8)&0xFF // JMP show_frame
  ];

  // Frame address table (2 bytes lo/hi per frame)
  const table = [];
  for (let i = 0; i < n; i++) {
    table.push(frameAddrs[i] & 0xFF);
    table.push((frameAddrs[i] >> 8) & 0xFF);
  }

  // Total file size: load until end of last frame
  const fileSize = 2 + (frameAddrs[n-1] + 10000 - 0x0801);
  const prg = new Uint8Array(fileSize);
  prg[0] = 0x01; prg[1] = 0x08; // load address $0801
  // BASIC stub: 10 SYS 2061  (=$080D)
  prg.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 2);
  // Machine code at $080D
  prg.set(asm, 2 + (0x080D - 0x0801));
  // Frame table at $0900
  prg.set(table, 2 + (tableAddr - 0x0801));
  // Frame data — rearrange to match what the machine code expects:
  //   machine code reads: bitmap from [+0], screen from [+8000], color from [+9000]
  //   engine raw buffer layout: bitmap [0..7999], screen [8000..8999], color [9000..9999]
  for (let i = 0; i < n; i++) {
    const off = 2 + (frameAddrs[i] - 0x0801);
    const f = frames[i];
    const frameData = new Uint8Array(10000); // zero-initialised
    // Bitmap (8000 bytes)
    frameData.set(f.subarray(0, 8000), 0);
    // Screen RAM (1000 bytes) — engine writes at offset 8000
    if (f.length > 8000) frameData.set(f.subarray(8000, Math.min(9000, f.length)), 8000);
    // Color RAM (1000 bytes) — engine writes at offset 9000
    if (f.length > 9000) frameData.set(f.subarray(9000, Math.min(10000, f.length)), 9000);
    prg.set(frameData, off);
  }
  return prg;
}

async function createSlideshow(type) {
  const frames = screenshots.filter(s => s.bmpData).map(s => s.bmpData);
  if (frames.length === 0) {
    alert('No captured frames with binary data.\nUse the CAPTURE button to save frames first.');
    return;
  }
  const bg = currentBgColor || 0;
  try {
    if (type === 'PRG') {
      if (frames.length > MAX_PRG_FRAMES)
        alert(`PRG slideshow: using first ${MAX_PRG_FRAMES} of ${frames.length} frames (64KB limit).`);
      const prg = buildSlideshowPRG(frames, bg);
      download(prg, 'slideshow.prg');
    } else if (type === 'CRT') {
      // For CRT: build a native 1MB EasyFlash cartridge with bank-switching viewer
      // Supports up to 63 multicolor images (10KB each) across ROML+ROMH banks
      const usedFrames = frames.slice(0, MAX_EF_FRAMES);
      if (frames.length > MAX_EF_FRAMES)
        alert(`CRT slideshow: using first ${MAX_EF_FRAMES} of ${frames.length} frames.`);
      const crtData = buildEasyFlashSlideshow(usedFrames, bg);
      download(crtData, 'slideshow.crt');
    }
  } catch(e) {
    alert('Slideshow generation failed: ' + e.message);
    void 0;
  }
}

// Wraps a PRG in an EasyFlash CRT using the existing loader boot code
function wrapPRGinCRT(prg) {
  const pbL = prg.subarray(2); // strip 2-byte load address
  const nB = Math.ceil(pbL.length / 8192);
  const nB1 = nB + 1;
  const h = new Uint8Array(64);
  h.set([0x43,0x36,0x34,0x20,0x43,0x41,0x52,0x54,0x52,0x49,0x44,0x47,0x45,0x20,0x20,0x20], 0);
  h[0x13]=0x40; h[0x14]=0x01; h[0x15]=0x00; h[0x17]=0x20; h[0x18]=0x01; h[0x19]=0x00;
  h.set(new TextEncoder().encode('SLIDESHW').subarray(0,32), 0x20);
  const mk = (b,a,t,d) => {
    const p = new Uint8Array(16+8192).fill(0);
    p.set([0x43,0x48,0x49,0x50,0,0,0x20,0x10,0,t,(b>>8),(b&0xFF),(a>>8),(a&0xFF),0x20,0],0);
    p.set(d.subarray(0,8192),16); return p;
  };
  const boot = new Uint8Array(8192).fill(0xFF);
  boot.set([
    0x78,0xD8,0xA2,0xFF,0x9A,0xA9,0x35,0x85,0x01,0xA2,0x47,0xBD,0x17,0xE0,0x9D,0x00,
    0x02,0xCA,0x10,0xF7,0x4C,0x00,0x02,0xA9,0x02,0x8D,0x02,0xDE,0xA9,0x01,0x85,0xFD,
    0xA9,0x01,0x85,0xFB,0xA9,0x08,0x85,0xFC,0xA5,0xFD,0x8D,0x00,0xDE,0xA9,0x00,0x85,
    0xFE,0xA9,0x80,0x85,0xFF,0xA9,0x20,0x8D,0x00,0x03,0xA0,0x00,0xB1,0xFE,0x91,0xFB,
    0xC8,0xD0,0xF9,0xE6,0xFC,0xE6,0xFF,0xCE,0x00,0x03,0xD0,0xEE,0xE6,0xFD,0xA5,0xFD,
    0xC9,nB1,0xD0,0xD4,0xA9,0x04,0x8D,0x02,0xDE,0x8D,0xFF,0xDF,0x4C,0x0D,0x08
  ], 0);
  boot.set([0x00,0xE0,0x00,0xE0,0x01,0xE0], 8186);
  const crt = [h, mk(0,0xA000,2,boot)];
  for (let b = 0; b < nB; b++) crt.push(mk(b+1,0x8000,2,pbL.subarray(b*8192,(b+1)*8192)));
  const total = crt.reduce((a,v)=>a+v.length,0);
  const out = new Uint8Array(total); let off=0;
  for (const c of crt) { out.set(c,off); off+=c.length; }
  return out;
}

// ==========================================================
// 1MB EasyFlash CRT Slideshow (up to 63 images)
// ==========================================================
// Architecture:
//   Bank 0 ROMH ($E000 in Ultimax): Boot code copies viewer to RAM
//   Bank 0 ROML ($8000): Viewer code (BASIC stub + 6502 machine code)
//   Banks 1-N ROML+ROMH: Image data packed contiguously
//     Each image = 8000 bytes bitmap + 1000 screen + 1000 color = 10000 bytes
//     Each bank provides 16384 bytes (ROML $8000-$9FFF + ROMH $A000-$BFFF)
//   Viewer runs from RAM at $0801, bank-switches to read images at runtime
//   Uses 16K cart mode ($DE02=$87) so both ROML and ROMH are visible
// ==========================================================

function buildEasyFlashSlideshow(frames, bgColor) {
  const n = Math.min(frames.length, MAX_EF_FRAMES);
  if (n === 0) throw new Error('No frames to build slideshow');

  // --- 1. Build viewer machine code ---
  const viewerCode = _buildSlideViewer(n, bgColor & 0xFF);

  // --- 2. Build ROML bank 0: BASIC stub + viewer ---
  const roml0 = new Uint8Array(8192).fill(0xFF);
  // BASIC stub at offset 0 → loads at $0801: "10 SYS 2061"
  roml0.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00], 0);
  // Viewer machine code at offset 12 → runs at $080D
  roml0.set(viewerCode, 12);

  // --- 3. Build ROMH bank 0: boot code ---
  const viewerTotalBytes = 12 + viewerCode.length;
  const viewerPages = Math.ceil(viewerTotalBytes / 256);
  const romh0 = _buildSlideBootCode(viewerPages);

  // --- 4. Pack image data across ROML+ROMH of banks 1..N ---
  const streamSize = n * 10000;
  const imageStream = new Uint8Array(streamSize);
  for (let i = 0; i < n; i++) {
    const f = frames[i];
    const base = i * 10000;
    // Bitmap 8000 bytes
    imageStream.set(f.subarray(0, Math.min(8000, f.length)), base);
    // Screen RAM 1000 bytes (at offset 8000 in engine buffer)
    if (f.length > 8000)
      imageStream.set(f.subarray(8000, Math.min(9000, f.length)), base + 8000);
    // Color RAM 1000 bytes (at offset 9000 in engine buffer)
    if (f.length > 9000)
      imageStream.set(f.subarray(9000, Math.min(10000, f.length)), base + 9000);
  }

  const dataBanks = Math.ceil(streamSize / 16384);

  // --- 5. Assemble CRT file ---
  // Helper: make 8KB CHIP packet
  const mkChip = (bank, addr, data) => {
    const p = new Uint8Array(16 + 8192).fill(0);
    p.set([0x43,0x48,0x49,0x50, 0,0,0x20,0x10, 0,0x02,
           (bank>>8)&0xFF, bank&0xFF, (addr>>8)&0xFF, addr&0xFF, 0x20,0x00], 0);
    p.set(data.subarray(0, 8192), 16);
    return p;
  };

  // CRT header
  const hdr = new Uint8Array(64);
  hdr.set([0x43,0x36,0x34,0x20,0x43,0x41,0x52,0x54,0x52,0x49,0x44,0x47,0x45,0x20,0x20,0x20], 0);
  hdr[0x13] = 0x40;                    // header length = 64
  hdr[0x14] = 0x01; hdr[0x15] = 0x00;  // version 1.0
  hdr[0x17] = 0x20;                    // hardware type 32 = EasyFlash
  hdr[0x18] = 0x01; hdr[0x19] = 0x00;  // EXROM=1, GAME=0 → Ultimax boot
  hdr.set(new TextEncoder().encode('EF SLIDESHOW').subarray(0, 32), 0x20);

  const chips = [];
  // Bank 0: boot (ROMH) + viewer (ROML)
  chips.push(mkChip(0, 0x8000, roml0));
  chips.push(mkChip(0, 0xA000, romh0));

  // Data banks 1..N: ROML + ROMH per bank
  for (let b = 0; b < dataBanks; b++) {
    const bankStreamOff = b * 16384;
    // ROML portion (first 8192 bytes of this bank's data)
    const rl = new Uint8Array(8192).fill(0xFF);
    const rlLen = Math.min(8192, streamSize - bankStreamOff);
    if (rlLen > 0) rl.set(imageStream.subarray(bankStreamOff, bankStreamOff + rlLen));
    chips.push(mkChip(b + 1, 0x8000, rl));

    // ROMH portion (next 8192 bytes)
    const rh = new Uint8Array(8192).fill(0xFF);
    const rhOff = bankStreamOff + 8192;
    const rhLen = Math.min(8192, streamSize - rhOff);
    if (rhLen > 0) rh.set(imageStream.subarray(rhOff, rhOff + rhLen));
    chips.push(mkChip(b + 1, 0xA000, rh));
  }

  // Concatenate
  const totalSize = 64 + chips.reduce((a, c) => a + c.length, 0);
  const crt = new Uint8Array(totalSize);
  crt.set(hdr, 0);
  let off = 64;
  for (const c of chips) { crt.set(c, off); off += c.length; }

  console.log(`EasyFlash CRT: ${n} frames, ${dataBanks} data banks, ${totalSize} bytes`);
  return crt;
}

// Build the 6502 viewer code for the EasyFlash slideshow (runs at $080D from RAM)
function _buildSlideViewer(numFrames, bgColor) {
  const c = [];    // code bytes
  const B = 0x080D; // base address

  // Helpers
  const here = () => c.length;
  const abs  = () => B + c.length;
  const rel  = (brOff, tgtOff) => {
    const d = tgtOff - (brOff + 2);
    if (d < -128 || d > 127) throw new Error('Branch out of range: ' + d);
    return d & 0xFF;
  };

  // ===== INIT =====
  c.push(0x78);                                     // SEI
  c.push(0xD8);                                     // CLD
  c.push(0xA9, 0x35, 0x85, 0x01);                   // LDA #$35, STA $01

  // Disable CIA interrupts (prevent NMI)
  c.push(0xA9, 0x7F, 0x8D, 0x0D, 0xDC);             // LDA #$7F, STA $DC0D
  c.push(0x8D, 0x0D, 0xDD);                          // STA $DD0D
  c.push(0xAD, 0x0D, 0xDC);                          // LDA $DC0D (ack)
  c.push(0xAD, 0x0D, 0xDD);                          // LDA $DD0D (ack)

  // VIC-II multicolor bitmap mode
  c.push(0xA9, 0x3B, 0x8D, 0x11, 0xD0);             // LDA #$3B, STA $D011
  c.push(0xA9, 0xD8, 0x8D, 0x16, 0xD0);             // LDA #$D8, STA $D016
  c.push(0xA9, 0x18, 0x8D, 0x18, 0xD0);             // LDA #$18, STA $D018
  c.push(0xA9, bgColor, 0x8D, 0x20, 0xD0);           // border color
  c.push(0xA9, bgColor, 0x8D, 0x21, 0xD0);           // background color

  // VIC bank 0 ($0000-$3FFF)
  c.push(0xAD, 0x02, 0xDD, 0x09, 0x03, 0x8D, 0x02, 0xDD); // LDA $DD02, ORA #3, STA $DD02
  c.push(0xAD, 0x00, 0xDD, 0x09, 0x03, 0x8D, 0x00, 0xDD); // LDA $DD00, ORA #3, STA $DD00

  // Enable 16K cartridge mode (ROML $8000 + ROMH $A000)
  c.push(0xA9, 0x87, 0x8D, 0x02, 0xDE);             // LDA #$87, STA $DE02

  // Init source pointer: bank 1, address $8000
  c.push(0xA9, 0x01, 0x85, 0x02);                   // bank = 1 → ZP $02
  c.push(0xA9, 0x00, 0x85, 0xFE);                   // src lo → ZP $FE
  c.push(0xA9, 0x80, 0x85, 0xFF);                   // src hi → ZP $FF
  c.push(0xA9, 0x00, 0x85, 0xFB);                   // frame_idx → ZP $FB

  // ===== SHOW_FRAME =====
  const sf = here(); const sfA = abs();
  c.push(0xA5, 0x02, 0x8D, 0x00, 0xDE);             // LDA bank, STA $DE00

  // Copy bitmap: 8000 ($1F40) bytes → $2000
  c.push(0xA9,0x00,0x85,0xFC, 0xA9,0x20,0x85,0xFD); // dest = $2000
  c.push(0xA9,0x40,0x85,0x06, 0xA9,0x1F,0x85,0x07); // count = $1F40
  const j1 = here(); c.push(0x20, 0x00, 0x00);      // JSR copy_banked

  // Copy screen: 1000 ($03E8) bytes → $0400
  c.push(0xA9,0x00,0x85,0xFC, 0xA9,0x04,0x85,0xFD);
  c.push(0xA9,0xE8,0x85,0x06, 0xA9,0x03,0x85,0x07);
  const j2 = here(); c.push(0x20, 0x00, 0x00);

  // Copy color: 1000 bytes → $D800
  c.push(0xA9,0x00,0x85,0xFC, 0xA9,0xD8,0x85,0xFD);
  c.push(0xA9,0xE8,0x85,0x06, 0xA9,0x03,0x85,0x07);
  const j3 = here(); c.push(0x20, 0x00, 0x00);

  // ===== WAIT ~3 seconds (150 raster-$FE passes ≈ 3s at 50Hz) =====
  c.push(0xA9, 150, 0x85, 0xFC);                    // LDA #150, STA $FC
  const wf = here();
  c.push(0xAD, 0x12, 0xD0, 0xC9, 0xFE);             // LDA $D012, CMP #$FE
  const bWf = here(); c.push(0xD0, 0x00);            // BNE wait_find
  const wp = here();
  c.push(0xAD, 0x12, 0xD0, 0xC9, 0xFE);             // LDA $D012, CMP #$FE
  const bWp = here(); c.push(0xF0, 0x00);            // BEQ wait_pass
  c.push(0xC6, 0xFC);                               // DEC counter
  const bWf2 = here(); c.push(0xD0, 0x00);           // BNE wait_find
  c[bWf + 1] = rel(bWf, wf);  c[bWp + 1] = rel(bWp, wp);  c[bWf2 + 1] = rel(bWf2, wf);

  // ===== ADVANCE FRAME =====
  c.push(0xE6, 0xFB, 0xA5, 0xFB);                   // INC $FB, LDA $FB
  c.push(0xC9, numFrames & 0xFF);                    // CMP #numFrames
  const bRst = here(); c.push(0xF0, 0x00);           // BEQ reset
  c.push(0x4C, sfA & 0xFF, (sfA >> 8) & 0xFF);      // JMP show_frame

  // Reset to first frame
  const rstOff = here();
  c[bRst + 1] = rel(bRst, rstOff);
  c.push(0xA9,0x00,0x85,0xFB);                       // frame_idx = 0
  c.push(0xA9,0x01,0x85,0x02);                       // bank = 1
  c.push(0xA9,0x00,0x85,0xFE);                       // src lo = 0
  c.push(0xA9,0x80,0x85,0xFF);                       // src hi = $80
  c.push(0x4C, sfA & 0xFF, (sfA >> 8) & 0xFF);      // JMP show_frame

  // ===== COPY_BANKED SUBROUTINE =====
  // Copies $06:$07 bytes from banked ROM (bank=$02, addr=$FE/$FF) to $FC/$FD
  // Handles bank boundaries at $C000 (ROML $8000 + ROMH $A000 = 16KB per bank)
  // After return, $02/$FE/$FF point to next byte (ready for next copy)
  const cbOff = here(); const cbA = abs();
  c[j1+1]=cbA&0xFF; c[j1+2]=(cbA>>8)&0xFF;
  c[j2+1]=cbA&0xFF; c[j2+2]=(cbA>>8)&0xFF;
  c[j3+1]=cbA&0xFF; c[j3+2]=(cbA>>8)&0xFF;

  c.push(0xA0, 0x00);                               // LDY #0
  const bChk = here(); c.push(0xF0, 0x00);           // BEQ check (always taken)

  // loop:
  const lp = here();
  c.push(0xB1, 0xFE);                               // LDA ($FE),Y
  c.push(0x91, 0xFC);                               // STA ($FC),Y
  // Advance source
  c.push(0xE6, 0xFE);                               // INC $FE
  const bNs = here(); c.push(0xD0, 0x00);            // BNE no_src_carry
  c.push(0xE6, 0xFF);                               // INC $FF
  c.push(0xA5, 0xFF);                               // LDA $FF
  c.push(0xC9, 0xC0);                               // CMP #$C0
  const bNb = here(); c.push(0xD0, 0x00);            // BNE no_bank_cross
  // Bank boundary: reset to $8000, next bank
  c.push(0xA9, 0x80, 0x85, 0xFF);                   // LDA #$80, STA $FF
  c.push(0xE6, 0x02);                               // INC bank
  c.push(0xA5, 0x02, 0x8D, 0x00, 0xDE);             // LDA bank, STA $DE00
  // no_src_carry / no_bank_cross target:
  const nsOff = here();
  c[bNs + 1] = rel(bNs, nsOff);  c[bNb + 1] = rel(bNb, nsOff);
  // Advance destination
  c.push(0xE6, 0xFC);                               // INC $FC
  const bNd = here(); c.push(0xD0, 0x00);            // BNE no_dst_carry
  c.push(0xE6, 0xFD);                               // INC $FD
  const ndOff = here(); c[bNd + 1] = rel(bNd, ndOff);
  // Decrement 16-bit count
  c.push(0xA5, 0x06);                               // LDA $06
  const bNbr = here(); c.push(0xD0, 0x00);           // BNE no_borrow
  c.push(0xC6, 0x07);                               // DEC $07
  const nbrOff = here(); c[bNbr + 1] = rel(bNbr, nbrOff);
  c.push(0xC6, 0x06);                               // DEC $06
  // check:
  const chkOff = here(); c[bChk + 1] = rel(bChk, chkOff);
  c.push(0xA5, 0x06, 0x05, 0x07);                   // LDA $06, ORA $07
  const bLp = here(); c.push(0xD0, 0x00);            // BNE loop
  c.push(0x60);                                     // RTS
  c[bLp + 1] = rel(bLp, lp);

  console.log(`Viewer code: ${c.length} bytes ($080D-$${(B + c.length - 1).toString(16).toUpperCase()})`);
  return new Uint8Array(c);
}

// Build boot code for ROMH bank 0 (runs at $E000 in Ultimax mode)
function _buildSlideBootCode(viewerPages) {
  const romh = new Uint8Array(8192).fill(0xFF);

  // Phase 2: copies viewer from ROML bank 0 to $0801, enables 16K mode, jumps to viewer
  const p2 = [
    0xA9, 0x00, 0x8D, 0x00, 0xDE,           // LDA #0, STA $DE00 (select bank 0)
    0xA9, 0x00, 0x85, 0xFE,                  // src lo = $00
    0xA9, 0x80, 0x85, 0xFF,                  // src hi = $80 → ROML $8000
    0xA9, 0x01, 0x85, 0xFB,                  // dst lo = $01
    0xA9, 0x08, 0x85, 0xFC,                  // dst hi = $08 → RAM $0801
    0xA9, viewerPages & 0xFF,                // LDA #viewerPages
    0x8D, 0x00, 0x03,                        // STA $0300 (page counter)
    // page_loop:
    0xA0, 0x00,                              // LDY #0
    0xB1, 0xFE,                              // LDA ($FE),Y
    0x91, 0xFB,                              // STA ($FB),Y
    0xC8,                                    // INY
    0xD0, 0xF9,                              // BNE byte_loop (-7 → LDA ($FE),Y)
    0xE6, 0xFF,                              // INC src hi
    0xE6, 0xFC,                              // INC dst hi
    0xCE, 0x00, 0x03,                        // DEC $0300
    0xD0, 0xEE,                              // BNE page_loop (-18 → LDY #0)
    // Enable 16K cart mode and jump to viewer
    0xA9, 0x87,                              // LDA #$87 (16K mode + LED)
    0x8D, 0x02, 0xDE,                        // STA $DE02
    0x8D, 0xFF, 0xDF,                        // STA $DFFF (real hardware)
    0x4C, 0x0D, 0x08                         // JMP $080D
  ];

  // Phase 1: copies Phase 2 to $0200, jumps there
  const p2len = p2.length;
  const p1 = [
    0x78,                                    // SEI
    0xD8,                                    // CLD
    0xA2, 0xFF, 0x9A,                        // LDX #$FF, TXS
    0xA9, 0x37, 0x85, 0x01,                  // LDA #$37, STA $01
    0xA2, (p2len - 1) & 0xFF,                // LDX #(p2len-1)
    // copy_loop:
    0xBD, 0x17, 0xE0,                        // LDA $E017,X (Phase 2 at ROMH offset $17)
    0x9D, 0x00, 0x02,                        // STA $0200,X
    0xCA,                                    // DEX
    0x10, 0xF7,                              // BPL copy_loop
    0x4C, 0x00, 0x02                         // JMP $0200
  ];

  if (p1.length !== 23) throw new Error('Phase 1 size mismatch: ' + p1.length);

  romh.set(p1, 0);           // Phase 1 at offset 0 ($E000)
  romh.set(p2, 23);          // Phase 2 at offset 23 ($E017)

  // Ultimax reset vectors (read from ROMH at $FFFA-$FFFF)
  romh[0x1FFA] = 0x00; romh[0x1FFB] = 0xE0; // NMI  → $E000
  romh[0x1FFC] = 0x00; romh[0x1FFD] = 0xE0; // RESET→ $E000
  romh[0x1FFE] = 0x01; romh[0x1FFF] = 0xE0; // IRQ  → $E001

  return romh;
}

async function convertScreenshotToC64Bitmap(screenshot, frameIndex) {
  // Convert screenshot to C64 multicolor bitmap format
  const frameData = new Uint8Array(8192 + 1024 + 1024); // bitmap + screen + color
  let offset = 0;
  
  try {
    // Create canvas from screenshot
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    await new Promise((resolve) => {
      img.onload = resolve;
      img.src = screenshot.thumb;
    });
    
    canvas.width = 160;
    canvas.height = 200;
    ctx.drawImage(img, 0, 0, 160, 200);
    
    // Get pixel data and convert to C64 colors
    const imageData = ctx.getImageData(0, 0, 160, 200);
    const pixels = imageData.data;
    
    // Generate bitmap data
    for (let y = 0; y < 25; y++) {
      for (let x = 0; x < 40; x++) {
        // Screen RAM entry
        frameData[8192 + y * 40 + x] = 0;
        
        // Color RAM entry (alternating colors for visibility)
        frameData[9216 + y * 40 + x] = (frameIndex * 2 + x) % 16;
        
        // Bitmap data (8 bytes per character)
        for (let py = 0; py < 8; py++) {
          let byte = 0;
          for (let px = 0; px < 4; px++) {
            const pixelX = x * 4 + px;
            const pixelY = y * 8 + py;
            const pixelIndex = (pixelY * 160 + pixelX) * 4;
            const r = pixels[pixelIndex], g = pixels[pixelIndex + 1], b = pixels[pixelIndex + 2];
            
            // Simple color mapping based on brightness
            let color = 0;
            const brightness = (r + g + b) / 3;
            if (brightness > 200) color = 1; // White
            else if (brightness > 150) color = 6; // Blue
            else if (brightness > 100) color = 8; // Orange
            else if (brightness > 50) color = 12; // Medium gray
            else color = 0; // Black
            
            byte |= (color & 3) << ((3 - px) * 2);
          }
          frameData[x * 8 + py + y * 320] = byte;
        }
      }
    }
    
  } catch (error) {
    void 0;
    // Create simple test pattern as fallback
    for (let i = 0; i < 8192; i++) {
      frameData[i] = (frameIndex + 1) % 16 * 17;
    }
    for (let i = 8192; i < 10240; i++) {
      frameData[i] = frameIndex % 16;
    }
    for (let i = 10240; i < 11264; i++) {
      frameData[i] = (frameIndex * 3) % 16;
    }
  }
  
  return frameData;
}

async function convertScreenshotToC64(screenshot, frameIndex) {
  // Convert captured screenshot to proper C64 bitmap format
  const frameSize = isIFLI ? 49155 : (isFLI ? 32768 : 14145);
  const frameData = new Uint8Array(frameSize);
  
  try {
    // Create canvas from screenshot thumbnail
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    await new Promise((resolve) => {
      img.onload = resolve;
      img.src = screenshot.thumb;
    });
    
    canvas.width = isHires ? 320 : 160;
    canvas.height = 200;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    
    // Get pixel data
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const pixels = imageData.data;
    
    // Convert to C64 format using the same logic as the engine
    const cb = new Uint8Array(320 * 200);
    for (let y = 0; y < 200; y++) {
      for (let x = 0; x < (isHires ? 320 : 160); x++) {
        const i = (y * (isHires ? 320 : 160) + x) * 4;
        const r = pixels[i], g = pixels[i + 1], b = pixels[i + 2];
        let best = 0, bestDist = 999999;
        for (let c = 0; c < 16; c++) {
          const pal = c64Pal[c];
          const dist = ((r - pal[0]) * (r - pal[0]) * 2) + ((g - pal[1]) * (g - pal[1]) * 4) + ((b - pal[2]) * (b - pal[2]));
          if (dist < bestDist) { bestDist = dist; best = c; }
        }
        cb[y * (isHires ? 320 : 160) + x] = best;
      }
    }
    
    // Generate C64 bitmap data (simplified version)
    let offset = 0;
    const bgC = 0; // Black background
    
    if (isHires) {
      // Hires mode: 8KB bitmap + 1KB color RAM
      for (let cy = 0; cy < 25; cy++) {
        for (let cx = 0; cx < 40; cx++) {
          // Color RAM
          frameData[8192 + cy * 40 + cx] = 6; // Blue
          
          // Bitmap data
          for (let py = 0; py < 8; py++) {
            let byte = 0;
            for (let px = 0; px < 8; px++) {
              if (cb[(cy * 8 + py) * 320 + (cx * 8 + px)] !== bgC) {
                byte |= (1 << (7 - px));
              }
            }
            frameData[cx * 8 + py] = byte;
          }
        }
      }
    } else {
      // Multicolor mode
      for (let cy = 0; cy < 25; cy++) {
        for (let cx = 0; cx < 40; cx++) {
          // Screen RAM
          frameData[8192 + cy * 40 + cx] = 0;
          // Color RAM  
          frameData[9216 + cy * 40 + cx] = 6;
          
          // Bitmap data
          for (let py = 0; py < 8; py++) {
            let byte = 0;
            for (let px = 0; px < 4; px++) {
              const color = cb[(cy * 8 + py) * 160 + (cx * 4 + px)];
              byte |= (color & 3) << ((3 - px) * 2);
            }
            frameData[cx * 8 + py] = byte;
          }
        }
      }
    }
    
    // Add background color at end
    frameData[frameSize - 1] = bgC;
    
  } catch (error) {
    void 0;
    // Fallback: create a simple test pattern
    for (let i = 0; i < frameSize; i++) {
      frameData[i] = (frameIndex + 1) % 16;
    }
  }
  
  return frameData;
}

async function upd() {
  try {
    const srP = apiFetch('/stats?t=' + Date.now()), rP = apiFetch('/data?t=' + Date.now()); const [sr, r] = await Promise.all([srP, rP]);
    if (sr && sr.ok) {
      const s = await sr.json(); if (s.mode && s.mode !== currentClientMode) { currentClientMode = s.mode; updateModeUI(); }
      const now = Date.now(); if (lastStatsTime > 0) { const dt = (now - lastStatsTime) / 1000; if (dt >= 1) { currentFPS = ((s.frames - lastFrames) / dt).toFixed(1); currentKBs = ((s.totalKB - lastKB) / dt).toFixed(1); lastStatsTime = now; lastFrames = s.frames; lastKB = s.totalKB; } } else { lastStatsTime = now; lastFrames = s.frames; lastKB = s.totalKB; }
      currentBgColor = s.bg; let dotE = document.getElementById('dot'); if (dotE) dotE.className = s.connected ? 'dot on' : 'dot';
      let stText = 'Status: ' + (s.connected ? 'LIVE' : 'DISCONNECTED') + ' | FPS: ' + Math.max(0, currentFPS) + ' | ' + Math.max(0, currentKBs) + ' KB/s';
      let stE = document.getElementById('stxt'); if (stE) stE.innerHTML = stText;
      if (document.getElementById('contrast') && document.activeElement !== document.getElementById('contrast')) { document.getElementById('contrast').value = s.contrast; updateContrastText(); }
      if (document.getElementById('brightness') && document.activeElement !== document.getElementById('brightness')) { document.getElementById('brightness').value = s.brightness; updateBrightnessText(); }
      if (s.saturation !== undefined && document.getElementById('saturation') && document.activeElement !== document.getElementById('saturation')) { document.getElementById('saturation').value = s.saturation; updateSaturationText(); }
      if (document.getElementById('dither') && document.activeElement !== document.getElementById('dither')) { document.getElementById('dither').value = s.dither; updateDitherText(); }
      if (document.getElementById('ditherType') && document.activeElement !== document.getElementById('ditherType')) { document.getElementById('ditherType').value = s.ditherType; }
      if (document.getElementById('scaling') && document.activeElement !== document.getElementById('scaling')) { document.getElementById('scaling').value = s.scaling; document.getElementById('c').setAttribute('data-scale', s.scaling); }
      if (document.getElementById('bgcolor') && document.activeElement !== document.getElementById('bgcolor')) { document.getElementById('bgcolor').value = s.bg; }
    }
    if (r && r.ok) {
      const d = new Uint8Array(await r.arrayBuffer()); 
      const cv = document.getElementById('c'), ctx = cv.getContext('2d');
      if (isIFLI) { const img = ctx.createImageData(160, 200), bg = c64Pal[d[34000]] || [0, 0, 0]; for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8, sB = py * 1024; for (let x = 0; x < 40; x++) { let cI = cR * 40 + x, bA = d[cI * 8 + py], sA = d[8000 + sB + cI], cA = d[16000 + cI], clA = [bg, c64Pal[sA >> 4], c64Pal[sA & 15], c64Pal[cA & 15]], bB = d[17000 + cI * 8 + py], sB2 = d[25000 + sB + cI], cB = d[33000 + cI], clB = [bg, c64Pal[sB2 >> 4], c64Pal[sB2 & 15], c64Pal[cB & 15]]; for (let px = 0; px < 4; px++) { let coA = clA[(bA >> ((3 - px) * 2)) & 3], coB = clB[(bB >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = (coA[0] + coB[0]) >> 1; img.data[o + 1] = (coA[1] + coB[1]) >> 1; img.data[o + 2] = (coA[2] + coB[2]) >> 1; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else if (isFLI) { const img = ctx.createImageData(160, 200), bg = c64Pal[d[17000]] || [0, 0, 0]; for (let y = 0; y < 200; y++) { let row = Math.floor(y / 8), py = y % 8, sB = py * 1024; for (let x = 0; x < 40; x++) { let cI = row * 40 + x, byte = d[cI * 8 + py], sBy = d[8000 + sB + cI], cBy = d[16000 + cI], cols = [bg, c64Pal[sBy >> 4], c64Pal[sBy & 15], c64Pal[cBy & 15]]; for (let px = 0; px < 4; px++) { let col = cols[(byte >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else if (isHires) { const img = ctx.createImageData(320, 200); for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8; for (let x = 0; x < 40; x++) { let cI = cR * 40 + x, byte = d[cI * 8 + py], sBy = d[8000 + cI], fg = c64Pal[sBy >> 4], bg = c64Pal[sBy & 15]; for (let bit = 7; bit >= 0; bit--) { let px = x * 8 + (7 - bit), isF = (byte >> bit) & 1, c = isF ? fg : bg, o = (y * 320 + px) * 4; img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else { const img = ctx.createImageData(160, 200), bg = c64Pal[currentBgColor]; for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8; for (let x = 0; x < 40; x++) { let cellIdx = cR * 40 + x, byte = d[cellIdx * 8 + py], sBy = d[8000 + cellIdx], cBy = d[9000 + cellIdx], cols = [bg, c64Pal[sBy >> 4], c64Pal[sBy & 15], c64Pal[cBy & 15]]; for (let px = 0; px < 4; px++) { let col = cols[(byte >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
    }  } catch (e) { }
  if (running) setTimeout(upd, 70);
}
// Wire up backend buttons (safe if elements not present)
document.getElementById('btn-backend-esp')?.addEventListener('click', () => setBackendMode('esp'));
document.getElementById('btn-backend-pc')?.addEventListener('click', () => setBackendMode('pc'));

setBackendMode('pc'); updateModeUI(); updateButtonStates(); upd();

// Add fullscreen double-click handler for canvas wrapper
document.getElementById('c-wrap').addEventListener('dblclick', function() {
  if (!document.fullscreenElement && !document.webkitFullscreenElement) {
    if (this.requestFullscreen) {
      this.requestFullscreen().catch(e => void 0);
    } else if (this.webkitRequestFullscreen) {
      this.webkitRequestFullscreen();
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen();
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    }
  }
});
