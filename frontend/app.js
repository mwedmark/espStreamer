// ESPStreamer Frontend Logic - VERSION 8.4 (Syntax Hardened)
let currentClientMode = 'mc_gray', isHires = false, isFLI = false, isIFLI = false, currentBgColor = 0;
let running = true, usePCBackend = true, screenshots = [];
let lastStatsTime = 0, lastFrames = 0, lastKB = 0, currentFPS = 0, currentKBs = 0;

// Size tracking for export limits
const MAX_PRG_SIZE = 65536; // ~64KB max for C64 PRG
const MAX_CRT_SIZE = 1048576; // 1MB max for EasyFlash CRT
let totalCaptureSize = 0;
const palettes = [[[0, 0, 0], [255, 255, 255], [104, 55, 43], [112, 164, 178], [111, 61, 134], [88, 141, 67], [53, 40, 121], [184, 199, 111], [111, 79, 37], [67, 57, 0], [154, 103, 89], [68, 68, 68], [108, 108, 108], [154, 210, 132], [108, 94, 181], [149, 149, 149]], [[0, 0, 0], [255, 255, 255], [129, 51, 56], [117, 205, 200], [142, 60, 151], [86, 172, 93], [45, 48, 173], [237, 240, 175], [142, 80, 41], [85, 56, 0], [196, 108, 113], [74, 74, 74], [123, 123, 123], [169, 255, 159], [112, 117, 213], [170, 170, 170]]];
let currentPaletteIdx = 0, c64Pal = palettes[0];
async function apiFetch(path) { if (usePCBackend) { return await window.C64Engine.apiCall(path); } return fetch(path); }
function setBackendMode(m) { usePCBackend = (m === 'pc'); document.getElementById('btn-backend-pc').style.borderColor = usePCBackend ? '#40ff40' : '#6c8cff'; if (usePCBackend) window.C64Engine.start(); else window.C64Engine.stop(); syncAll(); }
function syncAll() { sendContrast(); sendBrightness(); sendBg(); sendPalette(); sendDither(); sendDitherType(); }
function toggleMode() { const m = document.getElementById('mode-sel').value; currentClientMode = m; updateModeUI(); apiFetch('/setmode?m=' + m); syncAll(); }
function updateModeUI() { isHires = currentClientMode.includes('hr'); isFLI = currentClientMode.includes('fli'); isIFLI = currentClientMode.includes('ifli'); const cv = document.getElementById('c'); cv.width = isHires ? 320 : 160; cv.height = 200; let bge = document.getElementById('badge'); if (bge) { bge.style.display = 'inline-block'; bge.innerText = currentClientMode.toUpperCase().replace(/_/g, ' '); } }
function updateContrastText() { document.getElementById('cval').innerText = parseFloat(document.getElementById('contrast').value).toFixed(1); }
function sendContrast() { apiFetch('/setcontrast?c=' + document.getElementById('contrast').value); }
function updateBrightnessText() { document.getElementById('bval').innerText = document.getElementById('brightness').value; }
function sendBrightness() { apiFetch('/setbrightness?b=' + document.getElementById('brightness').value); }
function updateDitherText() { document.getElementById('dval').innerText = document.getElementById('dither').value; }
function sendDither() { apiFetch('/setdither?d=' + document.getElementById('dither').value); }
function sendDitherType() { apiFetch('/setdithertype?t=' + document.getElementById('ditherType').value); sendDither(); }
function sendBg() { const e = document.getElementById('bgcolor'); if (e) apiFetch('/setbg?c=' + e.value); }
function sendScaling() { const e = document.getElementById('scaling'); if (e) apiFetch('/setscaling?s=' + e.value); }
function sendPalette() { apiFetch('/setpalette?p=' + document.getElementById('pal-sel').value); }
function download(d, n) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([d])); a.download = n; a.click(); }

function calculateCaptureSize() {
  // Estimate size based on mode and number of captures
  const baseSize = isIFLI ? 49155 : (isFLI ? 32768 : 14145);
  const slideshowOverhead = screenshots.length * 100; // Rough estimate for slideshow code
  return baseSize * screenshots.length + slideshowOverhead;
}

function updateButtonStates() {
  totalCaptureSize = calculateCaptureSize();
  
  // Update PRG button state
  const prgButtons = document.querySelectorAll('button[onclick*="save(\'PRG\'"]');
  prgButtons.forEach(btn => {
    if (totalCaptureSize > MAX_PRG_SIZE) {
      btn.disabled = true;
      btn.style.opacity = '0.5';
      btn.style.cursor = 'not-allowed';
      btn.title = `Too large for PRG (${(totalCaptureSize/1024).toFixed(1)}KB > ${(MAX_PRG_SIZE/1024).toFixed(1)}KB)`;
    } else {
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.style.cursor = 'pointer';
      btn.title = `Export as PRG (${(totalCaptureSize/1024).toFixed(1)}KB)`;
    }
  });
  
  // Update CRT button state
  const crtButtons = document.querySelectorAll('button[onclick*="save(\'CRT\'"]');
  crtButtons.forEach(btn => {
    if (totalCaptureSize > MAX_CRT_SIZE) {
      btn.disabled = true;
      btn.style.opacity = '0.5';
      btn.style.cursor = 'not-allowed';
      btn.title = `Too large for CRT (${(totalCaptureSize/1024).toFixed(1)}KB > ${(MAX_CRT_SIZE/1024).toFixed(1)}KB)`;
    } else {
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.style.cursor = 'pointer';
      btn.title = `Export as CRT (${(totalCaptureSize/1024).toFixed(1)}KB)`;
    }
  });
  
  // Update KOA button (same as PRG)
  const koaButtons = document.querySelectorAll('button[onclick*="save(\'KOA\'"]');
  koaButtons.forEach(btn => {
    if (totalCaptureSize > MAX_PRG_SIZE) {
      btn.disabled = true;
      btn.style.opacity = '0.5';
      btn.style.cursor = 'not-allowed';
      btn.title = `Too large for KOA (${(totalCaptureSize/1024).toFixed(1)}KB > ${(MAX_PRG_SIZE/1024).toFixed(1)}KB)`;
    } else {
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.style.cursor = 'pointer';
      btn.title = `Export as KOA (${(totalCaptureSize/1024).toFixed(1)}KB)`;
    }
  });
  
  console.log(`Updated button states - Total size: ${(totalCaptureSize/1024).toFixed(1)}KB`);
}
function captureImage() {
  console.log('CAPTURE BUTTON CLICKED!');
  
  try {
    // Test 1: Check if canvas exists
    const canvas = document.getElementById('c');
    if (!canvas) {
      console.error('Canvas not found!');
      alert('Canvas not found!');
      return;
    }
    console.log('Canvas found:', canvas.width, 'x', canvas.height);
    
    // Test 2: Try basic canvas capture
    const dataURL = canvas.toDataURL('image/png');
    console.log('Canvas dataURL length:', dataURL.length);
    
    // Test 3: Create simple capture
    const timestamp = new Date().toLocaleTimeString();
    const capture = {
      thumb: dataURL,
      timestamp: timestamp,
      test: true
    };
    
    screenshots.push(capture);
    console.log('Screenshot added, total:', screenshots.length);
    
    // Update button states based on new total size
    updateButtonStates();
    
    // Test 4: Update UI
    const countElement = document.getElementById('screenshot-count');
    if (countElement) {
      countElement.textContent = screenshots.length;
      console.log('Updated count display');
    } else {
      console.error('Count element not found!');
    }
    
    // Test 5: Show feedback in console only
    console.log(`Captured frame ${screenshots.length}`);
    
    alert(`Capture successful! Frame ${screenshots.length} saved.`);
    
  } catch (error) {
    console.error('Capture error:', error);
    alert('Capture failed: ' + error.message);
  }
}

function viewScreenshots() {
  console.log('VIEW button clicked, screenshots:', screenshots.length);
  
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
    
    console.log(`Screenshot ${index}:`, shot);
    
    html += `
      <div style="margin-bottom: 15px; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 8px;">
        <div style="display: flex; gap: 15px; align-items: center;">
          <img src="${shot.thumb}" style="width: 160px; height: 200px; image-rendering: pixelated; border: 2px solid #6c8cff; border-radius: 4px;">
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
    <button onclick="this.parentElement.parentElement.parentElement.remove()" style="padding: 10px 20px; background: #404080; border: none; border-radius: 8px; color: white; cursor: pointer;">Close</button>
  </div></div>`;
  
  console.log('Creating modal with HTML...');
  const modal = document.createElement('div');
  modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center; z-index: 1000;';
  modal.innerHTML = html;
  document.body.appendChild(modal);
  console.log('Modal added to page');
}

function downloadScreenshot(index) {
  console.log(`Downloading screenshot ${index}`);
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
  
  console.log(`Downloaded: ${a.download}`);
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
  // If we have multiple screenshots, create slideshow
  if (screenshots.length > 1 && (t === 'PRG' || t === 'KOA')) {
    console.log(`Creating slideshow with ${screenshots.length} images for ${t}`);
    await createSlideshow(t);
    return;
  }
  
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
    for (let i = 0; i < 1000; i++) f[o(0x1000) + i] = rawBmp[15360 + i];
    for (let i = 0; i < 8192; i++) {
      f[o(0x4000) + i] = rawBmp[8192 + i];
      f[o(0x6000) + i] = rawBmp[i];
      f[o(0x8000) + i] = rawBmp[16384 + 8192 + i];
      f[o(0xA000) + i] = rawBmp[16384 + i];
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
    for (let i = 0; i < 1000; i++) f[o(0x1000) + i] = rawBmp[15360 + i];
    for (let i = 0; i < 8192; i++) f[o(0x4000) + i] = rawBmp[8192 + i];
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
    for (let i = 0; i < 1000; i++) f[118 + i] = rawBmp[8192 + i];
    for (let i = 0; i < 1000; i++) f[1118 + i] = rawBmp[9216 + i];
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
    const p = new Uint8Array(16 + 8192).fill(0xFF);
    p.set([0x43, 0x48, 0x49, 0x50, 0, 0, 0x20, 0x10, 0, t, (b >> 8), (b & 0xFF), (a >> 8), (a & 0xFF), 0x20, 0], 0);
    p.set(d.subarray(0, 8192), 16);
    return p;
  };
  const nB1 = nB + 1;

  const boot = new Uint8Array(8192).fill(0xFF);
  boot.set([
    0x78, 0xD8, 0xA2, 0xFF, 0x9A, 0xA9, 0x37, 0x85, 0x01, 0xA2, 0x47, 0xBD, 0x17, 0xE0, 0x9D, 0x00, 
    0x02, 0xCA, 0x10, 0xF7, 0x4C, 0x00, 0x02, 0xA9, 0x06, 0x8D, 0x02, 0xDE, 0xA9, 0x01, 0x85, 0xFD, 
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

async function createSlideshow(type) {
  try {
    const shotCount = screenshots ? screenshots.length : 0;
    
    if (shotCount === 0) {
      alert('No screenshots to create slideshow from');
      return;
    }
    
    // Create minimal bitmap test - just one frame
    const f = new Uint8Array(10000); // Plenty of space
    let offset = 0;
    
    // PRG header
    f[0] = 0x01; f[1] = 0x08;
    f.set([0x0B, 0x08, 0x0A, 0x00, 0x9E, 0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00], 2);
    offset = 14;
    
    // Minimal bitmap test assembly
    const bitmapASM = [
      // Set multicolor bitmap mode
      0x78, 0xA9, 0x1B, 0x8D, 0x16, 0xD0, // VIC control: multicolor bitmap
      0xA9, 0x08, 0x8D, 0x18, 0xD0, // Screen at $0400, bitmap at $2000
      0xA9, 0x00, 0x8D, 0x20, 0xD0, 0xA9, 0x00, 0x8D, 0x21, 0xD0, // Border/bg colors
      0xA9, 0x0B, 0x8D, 0x22, 0xD0, // Background color
      
      // Fill bitmap with test pattern
      0xA9, 0x00, 0x85, 0xFD, 0xA9, 0x20, 0x85, 0xFC, // Dest pointer = $2000
      0xA2, 0x00, // LDX #$00
      0xA9, 0xFF, // LDA #$FF (white pattern)
      0x99, 0x00, 0x04, // STA $0400,X (screen RAM)
      0x99, 0x00, 0x06, // STA $0600,X (color RAM)
      0xE8, // INX
      0xE0, 0x00, // CPX #$00
      0xD0, 0xF8, // BNE loop
      
      // Fill bitmap area
      0xA2, 0x00, // LDX #$00
      0xA9, 0xAA, // LDA #$AA (checkerboard pattern)
      0x99, 0x00, 0x20, // STA $2000,X (bitmap)
      0xE8, // INX
      0xE0, 0x00, // CPX #$00
      0xD0, 0xF8, // BNE loop
      
      0x4C, 0x00, 0xA7 // Infinite loop
    ];
    
    f.set(bitmapASM, offset);
    offset += bitmapASM.length;
    
    const finalData = f.subarray(0, offset);
    const filename = `bitmap_test_${type.toLowerCase()}.prg`;
    
    download(finalData, filename);
    
  } catch (error) {
    alert('Failed to create slideshow: ' + error.message);
  }
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
    console.error('Error converting screenshot:', error);
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
    console.error('Error converting screenshot:', error);
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
      if (document.getElementById('dither') && document.activeElement !== document.getElementById('dither')) { document.getElementById('dither').value = s.dither; updateDitherText(); }
      if (document.getElementById('ditherType') && document.activeElement !== document.getElementById('ditherType')) { document.getElementById('ditherType').value = s.ditherType; }
    }
    if (r && r.ok) {
      const d = new Uint8Array(await r.arrayBuffer()); 
      console.log(`Received data buffer: ${d.length} bytes, first 10:`, d.slice(0, 10));
      const cv = document.getElementById('c'), ctx = cv.getContext('2d');
      if (isIFLI) { const img = ctx.createImageData(160, 200), bg = c64Pal[d[32767]] || [0, 0, 0]; for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8, sB = py * 1024; for (let x = 0; x < 40; x++) { let cI = cR * 40 + x, bA = d[cI * 8 + py], sA = d[8192 + sB + cI], cA = d[15360 + cI], clA = [bg, c64Pal[sA >> 4], c64Pal[sA & 15], c64Pal[cA & 15]], bB = d[16384 + cI * 8 + py], sB2 = d[16384 + 8192 + sB + cI], cB = d[16384 + 15360 + cI], clB = [bg, c64Pal[sB2 >> 4], c64Pal[sB2 & 15], c64Pal[cB & 15]]; for (let px = 0; px < 4; px++) { let coA = clA[(bA >> ((3 - px) * 2)) & 3], coB = clB[(bB >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = (coA[0] + coB[0]) >> 1; img.data[o + 1] = (coA[1] + coB[1]) >> 1; img.data[o + 2] = (coA[2] + coB[2]) >> 1; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else if (isFLI) { const img = ctx.createImageData(160, 200), bg = c64Pal[d[16383]] || [0, 0, 0]; for (let y = 0; y < 200; y++) { let row = Math.floor(y / 8), py = y % 8, sB = py * 1024; for (let x = 0; x < 40; x++) { let cI = row * 40 + x, byte = d[cI * 8 + py], sBy = d[8192 + sB + cI], cBy = d[15360 + cI], cols = [bg, c64Pal[sBy >> 4], c64Pal[sBy & 15], c64Pal[cBy & 15]]; for (let px = 0; px < 4; px++) { let col = cols[(byte >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else if (isHires) { const img = ctx.createImageData(320, 200); for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8; for (let x = 0; x < 40; x++) { let cI = cR * 40 + x, byte = d[cI * 8 + py], sBy = d[8192 + cI], fg = c64Pal[sBy >> 4], bg = c64Pal[sBy & 15]; for (let bit = 7; bit >= 0; bit--) { let px = x * 8 + (7 - bit), isF = (byte >> bit) & 1, c = isF ? fg : bg, o = (y * 320 + px) * 4; img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else { const img = ctx.createImageData(160, 200), bg = c64Pal[currentBgColor]; for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8; for (let x = 0; x < 40; x++) { let cellIdx = cR * 40 + x, byte = d[cellIdx * 8 + py], sBy = d[8192 + cellIdx], cBy = d[9216 + cellIdx], cols = [bg, c64Pal[sBy >> 4], c64Pal[sBy & 15], c64Pal[cBy & 15]]; for (let px = 0; px < 4; px++) { let col = cols[(byte >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
    }
  } catch (e) { }
  if (running) setTimeout(upd, 70);
}
setBackendMode('pc'); updateModeUI(); updateButtonStates(); upd();
