// Pure JavaScript port of ESPStreamer C++ engine - VERSION 8.5 (Low Latency)
window.C64Engine = (function () {
    let currentMode = 'mc_gray', isRunning = false, connected = false;
    let cf = 256, bv = 0, ds = 4, da = 2, bgC = 0, sc = 0, palIdx = 0, fCount = 0, tKB = 0;
    // Pre-allocated arrays to avoid garbage collection
    const preAllocated = {
        cb: new Uint8Array(200 * 320),
        er: new Float32Array(322 * 201 * 3),
        cnts: new Uint16Array(16),
        lc: new Uint16Array(16),
        distArray: new Uint16Array(4),
        tempArray: new Uint8Array(0)
    };
    let b = new Uint8Array(65536), activeB = 0;
    let offC = null, offCtx = null, imgS = null, lastWT = 0;
    const pals = [{ r: [0, 255, 104, 112, 111, 88, 53, 184, 111, 67, 154, 68, 108, 154, 108, 149], g: [0, 255, 55, 164, 61, 141, 40, 199, 79, 57, 103, 68, 108, 210, 94, 149], b: [0, 255, 43, 178, 134, 67, 121, 111, 37, 0, 89, 68, 108, 132, 181, 149] }, { r: [0, 255, 129, 117, 142, 86, 45, 237, 142, 85, 196, 108, 123, 169, 112, 170], g: [0, 255, 51, 205, 60, 172, 48, 240, 80, 56, 108, 74, 123, 255, 117, 170], b: [0, 255, 56, 200, 151, 93, 173, 175, 41, 0, 113, 74, 123, 159, 213, 170] }];
    let pal = pals[0]; const grayIdx = [0, 1, 11, 12, 15];
    const b4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
    const b8 = [0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4, 36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22, 3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7, 39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21];
    const blue = [21, 151, 80, 231, 41, 171, 95, 241, 23, 149, 78, 229, 39, 169, 93, 239, 107, 4, 190, 56, 121, 11, 201, 62, 111, 6, 192, 58, 119, 13, 203, 60, 245, 87, 161, 32, 253, 91, 177, 46, 243, 85, 163, 30, 255, 89, 175, 48, 69, 212, 136, 101, 75, 220, 142, 103, 71, 214, 138, 99, 73, 218, 140, 105, 17, 145, 76, 225, 35, 166, 83, 235, 19, 147, 74, 227, 37, 164, 81, 237, 115, 2, 198, 51, 127, 9, 207, 66, 113, 0, 196, 53, 125, 7, 205, 64, 249, 92, 155, 44, 251, 88, 157, 34, 247, 94, 153, 42, 253, 90, 155, 36, 61, 209, 131, 109, 63, 211, 133, 102, 59, 213, 129, 107, 65, 215, 131, 106, 22, 152, 79, 230, 42, 172, 94, 242, 24, 150, 77, 228, 40, 170, 92, 240, 108, 5, 191, 57, 122, 12, 200, 63, 110, 7, 193, 59, 118, 14, 202, 61, 244, 86, 160, 31, 254, 90, 176, 47, 242, 84, 162, 31, 254, 88, 174, 49, 70, 213, 137, 100, 74, 221, 143, 104, 72, 215, 139, 98, 74, 219, 141, 106, 18, 146, 75, 224, 36, 167, 84, 236, 20, 148, 73, 226, 38, 165, 82, 238, 116, 3, 199, 52, 126, 8, 206, 67, 114, 1, 197, 54, 124, 6, 204, 65, 248, 93, 154, 45, 250, 89, 156, 35, 246, 95, 152, 43, 252, 91, 154, 37, 62, 210, 132, 108, 64, 212, 134, 103, 60, 214, 130, 106, 66, 216, 132, 105];
    // Optimized distance calculation with pre-multiplied weights
    function dist(c1, c2) { 
        const dr = pal.r[c1] - pal.r[c2];
        const dg = pal.g[c1] - pal.g[c2];
        const db = pal.b[c1] - pal.b[c2];
        return (dr * dr * 2) + (dg * dg * 4) + (db * db);
    }
    function log(m) { /* Disabled - use console.log instead to prevent status blinking */ void 0; }
    function process(idat, wT, isH, isF, isI, isG) {
        log(`process() called: ${wT}x200, H:${isH} F:${isF} I:${isI} G:${isG}`);
        const cb = preAllocated.cb; 
        const aP = isG ? grayIdx : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
        const d = idat.data;
        if (da == 5) {
            const er = preAllocated.er; er.fill(0); const eS = ds / 8.0;
            for (let y = 0; y < 200; y++) {
                for (let x = 0; x < wT; x++) {
                    let i = (y * wT + x) * 4, ei = (y * 322 + x) * 3;
                    let r = (((d[i] - 128) * cf) >> 8) + 128 + bv + er[ei], g = (((d[i + 1] - 128) * cf) >> 8) + 128 + bv + er[ei + 1], bl = (((d[i + 2] - 128) * cf) >> 8) + 128 + bv + er[ei + 2];
                    r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); bl = Math.max(0, Math.min(255, bl));
                    // Optimized color finding with early exit
                    let bc = aP[0]; let bd = (Math.abs(r - pal.r[bc]) * 2) + (Math.abs(g - pal.g[bc]) * 4) + Math.abs(bl - pal.b[bc]);
                    for (let i = 1; i < aP.length; i++) {
                        const it = aP[i];
                        const dy = (Math.abs(r - pal.r[it]) * 2) + (Math.abs(g - pal.g[it]) * 4) + Math.abs(bl - pal.b[it]);
                        if (dy < bd) { bd = dy; bc = it; }
                    }
                    cb[y * wT + x] = bc;
                    if (eS > 0) {
                        let rE = (r - pal.r[bc]) * eS, gE = (g - pal.g[bc]) * eS, bE = (bl - pal.b[bc]) * eS;
                        const diff = (nx, ny, w) => { if (nx >= 0 && nx < wT && ny < 200) { let ni = (ny * 322 + nx) * 3; er[ni] += rE * w; er[ni + 1] += gE * w; er[ni + 2] += bE * w; } };
                        diff(x + 1, y, 7 / 16); diff(x - 1, y + 1, 3 / 16); diff(x, y + 1, 5 / 16); diff(x + 1, y + 1, 1 / 16);
                    }
                }
            }
        } else {
            for (let y = 0; y < 200; y++) {
                for (let x = 0; x < wT; x++) {
                    let i = (y * wT + x) * 4, r = (((d[i] - 128) * cf) >> 8) + 128 + bv, g = (((d[i + 1] - 128) * cf) >> 8) + 128 + bv, bl = (((d[i + 2] - 128) * cf) >> 8) + 128 + bv;
                    if (da > 0 && ds > 0) {
                        let thr = 0; if (da == 1) thr = (b4[(y % 4) * 4 + (x % 4)] / 16) - 0.5;
                        else if (da == 2) thr = (b8[(y % 8) * 8 + (x % 8)] / 64) - 0.5;
                        else if (da == 3) thr = Math.random() - 0.5;
                        else if (da == 4) thr = (blue[(y % 16) * 16 + (x % 16)] / 255) - 0.5;
                        let s = ds * 12; r += thr * s; g += thr * s; bl += thr * s;
                    }
                    r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); bl = Math.max(0, Math.min(255, bl));
                    // Optimized color finding with early exit
                    let bc = aP[0]; let bd = (Math.abs(r - pal.r[bc]) * 2) + (Math.abs(g - pal.g[bc]) * 4) + Math.abs(bl - pal.b[bc]);
                    for (let i = 1; i < aP.length; i++) {
                        const it = aP[i];
                        const dy = (Math.abs(r - pal.r[it]) * 2) + (Math.abs(g - pal.g[it]) * 4) + Math.abs(bl - pal.b[it]);
                        if (dy < bd) { bd = dy; bc = it; }
                    }
                    cb[y * wT + x] = bc;
                }
            }
        }
        let mF = isI ? 2 : 1; for (let f = 0; f < mF; f++) {
            let base = (1 - activeB) * 32768 + (f * 16384);
            for (let cy = 0; cy < 25; cy++) {
                for (let cx = 0; cx < 40; cx++) {
                    let cIdx = cy * 40 + cx; if (isF) {
                        const cnts = preAllocated.cnts; cnts.fill(0); for (let py = 0; py < 8; py++) for (let px = 0; px < 4; px++) cnts[cb[(cy * 8 + py) * 160 + (cx * 4 + px)]]++; cnts[bgC] = -1; let cC = 1, mcC = -1; for (let i = 0; i < 16; i++) if (cnts[i] > mcC) { mcC = cnts[i]; cC = i; } b[base + 15360 + cIdx] = cC;
                        for (let py = 0; py < 8; py++) { 
                            const lc = preAllocated.lc; lc.fill(0); 
                            for (let px = 0; px < 4; px++) lc[cb[(cy * 8 + py) * 160 + (cx * 4 + px)]]++; lc[bgC] = -1; lc[cC] = -1; let c1 = 0, c2 = 0, m1 = 0, m2 = 0; for (let i = 0; i < 16; i++) { if (lc[i] > m1) { m2 = m1; c2 = c1; m1 = lc[i]; c1 = i; } else if (lc[i] > m2) { m2 = lc[i]; c2 = i; } } if (m1 === 0) c1 = cC; if (m2 === 0) c2 = c1; b[base + 8192 + py * 1024 + cIdx] = (c1 << 4) | (c2 & 15); let pb = 0; for (let px = 0; px < 4; px++) { let c = cb[(cy * 8 + py) * 160 + (cx * 4 + px)], d0 = dist(c, bgC), d1 = dist(c, c1), d2 = dist(c, c2), d3 = dist(c, cC), bst = [{ d: d0, s: 0 }, { d: d1, s: 1 }, { d: d2, s: 2 }, { d: d3, s: 3 }].sort((a, bi) => a.d - bi.d); pb |= (bst[0].s << ((3 - px) * 2)); } b[base + cIdx * 8 + py] = pb; }
                    } else if (isH) { const cnts = preAllocated.cnts; cnts.fill(0); for (let py = 0; py < 8; py++) for (let px = 0; px < 8; px++) cnts[cb[(cy * 8 + py) * 320 + (cx * 8 + px)]]++; let bg = 0, fg = 1, mB = -1, mF2 = -1; for (let i = 0; i < 16; i++) { if (cnts[i] > mB) { mF2 = mB; fg = bg; mB = cnts[i]; bg = i; } else if (cnts[i] > mF2) { mF2 = cnts[i]; fg = i; } } b[base + 8192 + cIdx] = (fg << 4) | (bg & 15); for (let py = 0; py < 8; py++) { let pb = 0; for (let px = 0; px < 8; px++) { if (dist(cb[(cy * 8 + py) * 320 + (cx * 8 + px)], fg) < dist(cb[(cy * 8 + py) * 320 + (cx * 8 + px)], bg)) pb |= (1 << (7 - px)); } b[base + cIdx * 8 + py] = pb; } } else { const cnts = preAllocated.cnts; cnts.fill(0); for (let py = 0; py < 8; py++) for (let px = 0; px < 4; px++) cnts[cb[(cy * 8 + py) * 160 + (cx * 4 + px)]]++; cnts[bgC] = -1; let c1 = 1, c2 = 1, c3 = 1, m1 = 0, m2 = 0, m3 = 0; for (let i = 0; i < 16; i++) { if (cnts[i] > m1) { m3 = m2; c3 = c2; m2 = m1; c2 = c1; m1 = cnts[i]; c1 = i; } else if (cnts[i] > m2) { m3 = m2; c3 = c2; m2 = cnts[i]; c2 = i; } else if (cnts[i] > m3) { m3 = cnts[i]; c3 = i; } } b[base + 8192 + cIdx] = (c1 << 4) | (c2 & 15); b[base + 9216 + cIdx] = c3; for (let py = 0; py < 8; py++) { let pb = 0; for (let px = 0; px < 4; px++) { let c = cb[(cy * 8 + py) * 160 + (cx * 4 + px)], d0 = dist(c, bgC), d1 = dist(c, c1), d2 = dist(c, c2), d3 = dist(c, c3), bst = [{ d: d0, s: 0 }, { d: d1, s: 1 }, { d: d2, s: 2 }, { d: d3, s: 3 }].sort((ax, bx) => ax.d - bx.d); pb |= (bst[0].s << ((3 - px) * 2)); } b[base + cIdx * 8 + py] = pb; } }
                }
            }
        }
        b[(1 - activeB) * 32768 + (isI ? 32767 : 16383)] = bgC; activeB = 1 - activeB;
        log(`Frame processing completed, activeB: ${activeB}`);
    }
    async function MLoop() {
        log("MLoop (V8.5) Start...");
        while (isRunning) {
            try {
                const res = await fetch('/stream/pc.mjpg', { cache: 'no-store' }); const reader = res.body.getReader(); let buf = new Uint8Array(0);
                while (isRunning) {
                    const { done, value } = await reader.read(); if (done) break;
                    let t = new Uint8Array(buf.length + value.length); t.set(buf); t.set(value, buf.length); buf = t;
                    while (buf.length > 2) {
                        let sI = -1; for (let i = 0; i < buf.length - 1; i++) if (buf[i] === 0xFF && buf[i + 1] === 0xD8) { sI = i; break; }
                        if (sI === -1) { if (buf.length > 256 * 1024) buf = new Uint8Array(0); break; }
                        if (sI > 0) buf = buf.slice(sI);
                        let eI = -1; for (let i = 2; i < buf.length - 1; i++) if (buf[i] === 0xFF && buf[i + 1] === 0xD9) { eI = i + 2; break; }
                        if (eI === -1) break;
                        const fD = buf.subarray(0, eI); buf = buf.slice(eI);
                        const url = URL.createObjectURL(new Blob([fD], { type: 'image/jpeg' }));
                        if (imgS) {
                            imgS.src = url; await new Promise(r => {
                                imgS.onload = () => {
                                    connected = true; URL.revokeObjectURL(url);
                                    if (offCtx) {
                                        let wT = currentMode.includes('hr') ? 320 : 160; 
                                        if (wT !== lastWT) { 
                                            offC.width = wT; 
                                            lastWT = wT; 
                                            offCtx = offC.getContext('2d'); 
                                            log(`Canvas resized to ${wT}x200`);
                                        }
                                        // Clear background with current background color
                                        offCtx.fillStyle = `rgb(${pal.r[bgC]},${pal.g[bgC]},${pal.b[bgC]})`;
                                        offCtx.fillRect(0, 0, wT, 200);

                                        // Calculate scaling coordinates
                                        let sx = 0, sy = 0, sw = imgS.width, sh = imgS.height;
                                        let dx = 0, dy = 0, dw = wT, dh = 200;

                                        const pixelAspect = currentMode.includes('hr') ? 1 : 2;
                                        const targetAspect = 1.6; // Visual target aspect (320:200)
                                        const imgAspect = imgS.width / imgS.height;
                                        
                                        // Target aspect ratio for the buffer pixels (0.8 for MC, 1.6 for HR)
                                        const targetPixelAspect = targetAspect / pixelAspect;

                                        if (sc === 1) { // FIT
                                            if (imgAspect > targetAspect) {
                                                // Image is wider: pillarbox (fit width)
                                                dw = wT;
                                                dh = (wT * pixelAspect) / imgAspect;
                                                dy = (200 - dh) / 2;
                                            } else {
                                                // Image is taller: letterbox (fit height)
                                                dh = 200;
                                                dw = (200 * imgAspect) / pixelAspect;
                                                dx = (wT - dw) / 2;
                                            }
                                        } else if (sc === 2) { // CROP
                                            if (imgAspect > targetPixelAspect) {
                                                // Image is wider than the target buffer ratio: crop sides
                                                sw = imgS.height * targetPixelAspect;
                                                sx = (imgS.width - sw) / 2;
                                            } else {
                                                // Image is taller than the target buffer ratio: crop top/bottom
                                                sh = imgS.width / targetPixelAspect;
                                                sy = (imgS.height - sh) / 2;
                                            }
                                        }




                                        offCtx.drawImage(imgS, sx, sy, sw, sh, dx, dy, dw, dh);
                                        const imageData = offCtx.getImageData(0, 0, wT, 200);
                                        fCount++;
                                        log(`Frame ${fCount}: Processing ${wT}x200, mode: ${currentMode}`);
                                        process(imageData, wT, currentMode.includes('hr'), currentMode.includes('fli'), currentMode.includes('ifli'), currentMode.includes('gray'));
                                    } r();
                                };
                                imgS.onerror = () => { URL.revokeObjectURL(url); r(); };
                                setTimeout(() => r(), 2000);
                            });
                        }
                        tKB += Math.floor(fD.length / 1024);
                    }
                }
            } catch (e) { log("Error: " + e.message); connected = false; if (isRunning) await new Promise(r => setTimeout(r, 1000)); }
        }
    }
    return {
        start: function () { if (isRunning) return; isRunning = true; if (!offC) offC = document.getElementById('offscreen-c'); if (!offCtx) offCtx = offC.getContext('2d'); if (!imgS) { imgS = new Image(); document.body.appendChild(imgS); imgS.style.display = "none"; } MLoop(); },
        stop: function () { isRunning = false; connected = false; },
        apiCall: async function (p) {
            let u = new URL(p, 'http://h'); if (p.startsWith('/data')) { 
                let isI = currentMode.includes('ifli'), s = isI ? 32768 : 16384, r = new ArrayBuffer(s + 1); 
                const dataToReturn = b.subarray(activeB * 32768, activeB * 32768 + s + 1);
                new Uint8Array(r).set(dataToReturn); 
                return { ok: true, arrayBuffer: async () => r }; 
            }
            if (p.startsWith('/stats')) return { ok: true, json: async () => ({ frames: fCount, mode: currentMode, connected: connected, contrast: cf / 256, brightness: bv, bg: bgC, dither: ds, ditherType: da, totalKB: tKB, paletteIdx: palIdx, scale: 1, scaling: sc }) };
            if (p.startsWith('/setmode')) currentMode = u.searchParams.get('m'); if (p.startsWith('/setcontrast')) cf = Math.floor(parseFloat(u.searchParams.get('c')) * 256); if (p.startsWith('/setbrightness')) bv = parseInt(u.searchParams.get('b')); if (p.startsWith('/setbg')) bgC = parseInt(u.searchParams.get('c')); if (p.startsWith('/setpalette')) { palIdx = parseInt(u.searchParams.get('p')); pal = pals[palIdx]; } if (p.startsWith('/setdither')) ds = parseInt(u.searchParams.get('d')); if (p.startsWith('/setdithertype')) da = parseInt(u.searchParams.get('t')); if (p.startsWith('/setscaling')) sc = parseInt(u.searchParams.get('s')); return { ok: true };
        }
    };
})();
