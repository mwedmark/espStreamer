// Pure JavaScript port of ESPStreamer C++ engine - VERSION 9.0 (Sync with C++ Reference)
window.C64Engine = (function () {
    let currentMode = 'mc_gray', isRunning = false, connected = false;
    let cf = 256, bv = 0, ds = 4, da = 2, bgC = 0, sc = 0, palIdx = 0, fCount = 0, tKB = 0;
    
    // Pre-allocated arrays to match ESP32 buffer sizes and avoid GC
    const preAllocated = {
        cb: new Uint8Array(320 * 200),
        er: new Float32Array(322 * 201 * 3),
        cnts: new Int32Array(16),
        lc: new Int32Array(16),
        rgb: new Uint8Array(320 * 200 * 3)
    };
    
    // 68010 bytes for two 34005 byte buffers (IFLI support)
    let b = new Uint8Array(68010), activeB = 0;
    let offC = null, offCtx = null, imgS = null, lastWT = 0;
    
    const pals = [
        { r: [0, 255, 104, 112, 111, 88, 53, 184, 111, 67, 154, 68, 108, 154, 108, 149], g: [0, 255, 55, 164, 61, 141, 40, 199, 79, 57, 103, 68, 108, 210, 94, 149], b: [0, 255, 43, 178, 134, 67, 121, 111, 37, 0, 89, 68, 108, 132, 181, 149] },
        { r: [0, 255, 129, 117, 142, 86, 45, 237, 142, 85, 196, 74, 123, 169, 112, 170], g: [0, 255, 51, 205, 60, 172, 48, 240, 80, 56, 108, 74, 123, 255, 117, 170], b: [0, 255, 56, 200, 151, 93, 173, 175, 41, 0, 113, 74, 123, 159, 213, 170] },
        { r: [0, 255, 136, 170, 204, 0, 0, 238, 221, 102, 255, 51, 119, 170, 0, 187], g: [0, 255, 0, 255, 68, 204, 0, 238, 136, 68, 119, 51, 119, 255, 136, 187], b: [0, 255, 0, 238, 204, 85, 170, 119, 85, 0, 119, 51, 119, 102, 255, 187] },
        { r: [0, 255, 192, 0, 192, 0, 0, 255, 192, 128, 240, 64, 128, 128, 128, 192], g: [0, 255, 0, 255, 0, 192, 0, 255, 128, 64, 128, 64, 128, 255, 128, 192], b: [0, 255, 0, 255, 192, 0, 192, 0, 0, 0, 128, 64, 128, 128, 255, 192] }
    ];
    let pal = pals[0];
    const grayIdx = [0, 11, 12, 15, 1]; // Standard C64 Grays

    // Bayer matrices matching C++ exactly
    const b4 = [-8, 8, -6, 10, 0, -4, 2, -2, -5, 11, -7, 9, 3, -1, 5, -3];
    const b8 = [-32, 0, -24, 8, -30, 2, -22, 10, 16, -16, 24, -8, 18, -14, 26, -6, -20, 12, -28, 4, -18, 14, -26, 6, 28, -4, 20, -12, 30, -2, 22, -10, -29, 3, -21, 11, -31, 1, -23, 9, 19, -13, 27, -5, 17, -15, 25, -7, -17, 15, -25, 7, -19, 13, -27, 5, 31, -1, 23, -9, 29, -3, 21, -11];
    const blue = [-8, 23, -18, 12, -31, 17, -4, 28, 19, -14, 5, -25, 20, -9, 14, -22, -3, 30, -21, 9, -16, 26, -7, 11, 24, -11, 16, -28, 3, -20, 21, -13, -27, 7, -19, 22, -6, 29, -24, 0, 13, -30, 1, -15, 18, -12, 10, -17, -23, 27, -5, 25, -29, 6, -26, 15, 8, -10, 31, -2, 11, -32, 4, -8];

    function log(m) { /* console.log(m); */ }

    function dist(r, g, b, c2) { 
        return (Math.abs(r - pal.r[c2]) * 2) + 
               (Math.abs(g - pal.g[c2]) * 4) + 
               (Math.abs(b - pal.b[c2]));
    }

    function process(idat, wT, isH, isF, isI, isG) {
        const cb = preAllocated.cb; 
        const aP = isG ? grayIdx : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
        const d = idat.data;

        // Phase 1: Color Mapping & Dithering
        if (da == 5) { // Floyd-Steinberg
            const er = preAllocated.er; er.fill(0); const eS = ds / 8.0;
            for (let y = 0; y < 200; y++) {
                for (let x = 0; x < wT; x++) {
                    let i = (y * wT + x) * 4, ei = (y * 322 + x) * 3;
                    let r = (((d[i] - 128) * cf) >> 8) + 128 + bv + er[ei];
                    let g = (((d[i + 1] - 128) * cf) >> 8) + 128 + bv + er[ei + 1];
                    let bl = (((d[i + 2] - 128) * cf) >> 8) + 128 + bv + er[ei + 2];
                    r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); bl = Math.max(0, Math.min(255, bl));

                    let bc = aP[0], bd = (Math.abs(r - pal.r[bc]) * 2) + (Math.abs(g - pal.g[bc]) * 4) + Math.abs(bl - pal.b[bc]);
                    if (isI && isG) {
                        const lumas = [0, 24, 48, 77, 107, 137, 168, 211, 255], pairsH = [0, 0, 11, 11, 12, 12, 15, 15, 1], pairsL = [0, 11, 11, 12, 12, 15, 15, 1, 1];
                        let l = (r * 77 + g * 153 + bl * 26) >> 8, bDL = 1000, bI = 0;
                        for (let k = 0; k < 9; k++) { let dL = Math.abs(l - lumas[k]); if (dL < bDL) { bDL = dL; bI = k; } }
                        bc = (pairsH[bI] << 4) | (pairsL[bI] & 0x0F);
                        let aL = lumas[bI]; r = g = bl = aL;
                    } else {
                        for (let k = 1; k < aP.length; k++) {
                            const it = aP[k];
                            const dy = (Math.abs(r - pal.r[it]) * 2) + (Math.abs(g - pal.g[it]) * 4) + Math.abs(bl - pal.b[it]);
                            if (dy < bd) { bd = dy; bc = it; }
                        }
                    }
                    cb[y * wT + x] = bc;
                    let ri = (y * wT + x) * 3;
                    const rgb = preAllocated.rgb;
                    rgb[ri] = r; rgb[ri + 1] = g; rgb[ri + 2] = bl;
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
                    let i = (y * wT + x) * 4;
                    let r = (((d[i] - 128) * cf) >> 8) + 128 + bv;
                    let g = (((d[i + 1] - 128) * cf) >> 8) + 128 + bv;
                    let bl = (((d[i + 2] - 128) * cf) >> 8) + 128 + bv;
                    if (da > 0 && ds > 0) {
                        let thr = 0; 
                        if (da == 1) thr = b4[(y % 4) * 4 + (x % 4)] / 4;
                        else if (da == 2) thr = b8[(y % 8) * 8 + (x % 8)] / 4;
                        else if (da == 3) thr = (Math.random() - 0.5) * 32;
                        else if (da == 4) thr = blue[(y % 8) * 8 + (x % 8)] / 4;
                        let s = ds; r += thr * s; g += thr * s; bl += thr * s;
                    }
                    r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); bl = Math.max(0, Math.min(255, bl));
                    let bc = aP[0], bd = (Math.abs(r - pal.r[bc]) * 2) + (Math.abs(g - pal.g[bc]) * 4) + Math.abs(bl - pal.b[bc]);
                    if (isI && isG) {
                        const lumas = [0, 24, 48, 77, 107, 137, 168, 211, 255], pairsH = [0, 0, 11, 11, 12, 12, 15, 15, 1], pairsL = [0, 11, 11, 12, 12, 15, 15, 1, 1];
                        let l = (r * 77 + g * 153 + bl * 26) >> 8, bDL = 1000, bI = 0;
                        for (let k = 0; k < 9; k++) { let dL = Math.abs(l - lumas[k]); if (dL < bDL) { bDL = dL; bI = k; } }
                        bc = (pairsH[bI] << 4) | (pairsL[bI] & 0x0F);
                    } else {
                        for (let k = 1; k < aP.length; k++) {
                            const it = aP[k];
                            const dy = (Math.abs(r - pal.r[it]) * 2) + (Math.abs(g - pal.g[it]) * 4) + Math.abs(bl - pal.b[it]);
                            if (dy < bd) { bd = dy; bc = it; }
                        }
                    }
                    cb[y * wT + x] = bc;
                    let ri = (y * wT + x) * 3;
                    const rgb = preAllocated.rgb;
                    rgb[ri] = r; rgb[ri + 1] = g; rgb[ri + 2] = bl;
                }
            }
        }

        // Phase 2: Bitplane Packing (Reference Offsets: 8000, 9000, 16000, 17000)
        let mF = isI ? 2 : 1, writeB = 1 - activeB;
        for (let f = 0; f < mF; f++) {
            let base = writeB * 34005 + (f * 17000);
            const getCol = (idx) => { let c = cb[idx]; return isI ? (f == 0 ? (c >> 4) : (c & 0x0F)) : c; };

            for (let cy = 0; cy < 25; cy++) {
                for (let cx = 0; cx < 40; cx++) {
                    let cIdx = cy * 40 + cx;
                    if (isF) {
                        // FLI Logic: 8 screens starting at base + 8000, color ram at base + 16000
                        const cnts = preAllocated.cnts; cnts.fill(0);
                        for (let py = 0; py < 8; py++) for (let px = 0; px < 4; px++) cnts[getCol((cy * 8 + py) * 160 + (cx * 4 + px))]++;
                        cnts[bgC] = -1; let cC = 1, mcC = -1;
                        for (let i = 0; i < 16; i++) if (cnts[i] > mcC) { mcC = cnts[i]; cC = i; }
                        if (mcC <= 0 || isI) cC = 1;
                        b[base + 16000 + cIdx] = cC;

                        for (let py = 0; py < 8; py++) {
                            const lc = preAllocated.lc; lc.fill(0);
                            for (let px = 0; px < 4; px++) lc[getCol((cy * 8 + py) * 160 + (cx * 4 + px))]++;
                            lc[bgC] = -1; lc[cC] = -1;
                            let c1 = 0, c2 = 0, m1 = 0, m2 = 0;
                            for (let i = 0; i < 16; i++) {
                                if (lc[i] > m1) { m2 = m1; c2 = c1; m1 = lc[i]; c1 = i; }
                                else if (lc[i] > m2) { m2 = lc[i]; c2 = i; }
                            }
                            if (m1 === 0) c1 = cC; if (m2 === 0) c2 = c1;
                            b[base + 8000 + py * 1024 + cIdx] = (c1 << 4) | (c2 & 15);

                            let pb = 0;
                            for (let px = 0; px < 4; px++) {
                                let rIdx = ((cy * 8 + py) * 160 + (cx * 4 + px)) * 3;
                                let rVal = preAllocated.rgb[rIdx], gVal = preAllocated.rgb[rIdx + 1], bVal = preAllocated.rgb[rIdx + 2];
                                let d0 = dist(rVal, gVal, bVal, bgC), d1 = dist(rVal, gVal, bVal, c1), d2 = dist(rVal, gVal, bVal, c2), d3 = dist(rVal, gVal, bVal, cC);
                                let d = [d0, d1, d2, d3], s = [0, 1, 2, 3];
                                for (let a = 0; a < 2; a++) for (let k = a + 1; k < 4; k++) if (d[k] < d[a]) { [d[a], d[k]] = [d[k], d[a]]; [s[a], s[k]] = [s[k], s[a]]; }
                                let bits = s[0];
                                if (da > 0 && ds > 0) {
                                    let thr = (da == 1 ? b4[(py % 4) * 4 + (cx * 4 + px) % 4] : b8[(py % 8) * 8 + (cx * 4 + px) % 8]) * ds;
                                    if (d[1] - thr < d[0] + thr) bits = s[1];
                                }
                                pb |= (bits << ((3 - px) * 2));
                            }
                            b[base + cIdx * 8 + py] = pb;
                        }
                    } else if (isH) {
                        const cnts = preAllocated.cnts; cnts.fill(0);
                        for (let py = 0; py < 8; py++) for (let px = 0; px < 8; px++) cnts[cb[(cy * 8 + py) * 320 + (cx * 8 + px)]]++;
                        let bg = 0, fg = 1, mB = -1, mF2 = -1;
                        for (let i = 0; i < 16; i++) { if (cnts[i] > mB) { mF2 = mB; fg = bg; mB = cnts[i]; bg = i; } else if (cnts[i] > mF2) { mF2 = cnts[i]; fg = i; } }
                        b[base + 8000 + cIdx] = (fg << 4) | (bg & 15);
                        for (let py = 0; py < 8; py++) {
                            let pb = 0;
                            for (let px = 0; px < 8; px++) {
                                let rIdx = ((cy * 8 + py) * 320 + (cx * 8 + px)) * 3;
                                let rVal = preAllocated.rgb[rIdx], gVal = preAllocated.rgb[rIdx + 1], bVal = preAllocated.rgb[rIdx + 2];
                                let dB = dist(rVal, gVal, bVal, bg), dF = dist(rVal, gVal, bVal, fg);
                                let thr = (da > 0 && ds > 0) ? (da == 1 ? b4[(py % 4) * 4 + px % 4] : b8[(py % 8) * 8 + px % 8]) * ds : 0;
                                if (dF - thr < dB + thr) pb |= (1 << (7 - px));
                            }
                            b[base + cIdx * 8 + py] = pb;
                        }
                    } else {
                        // Standard Multicolor: Screen @ 8000, Color @ 9000
                        const cnts = preAllocated.cnts; cnts.fill(0);
                        for (let py = 0; py < 8; py++) for (let px = 0; px < 4; px++) cnts[cb[(cy * 8 + py) * 160 + (cx * 4 + px)]]++;
                        cnts[bgC] = -1; let c1 = 1, c2 = 1, c3 = 1, m1 = 0, m2 = 0, m3 = 0;
                        for (let i = 0; i < 16; i++) { if (cnts[i] > m1) { m3 = m2; c3 = c2; m2 = m1; c2 = c1; m1 = cnts[i]; c1 = i; } else if (cnts[i] > m2) { m3 = m2; c3 = c2; m2 = cnts[i]; c2 = i; } else if (cnts[i] > m3) { m3 = cnts[i]; c3 = i; } }
                        if (m1 === 0) c1 = 1; if (m2 === 0) c2 = c1; if (m3 === 0) c3 = c1;
                        b[base + 8000 + cIdx] = (c1 << 4) | (c2 & 15); b[base + 9000 + cIdx] = c3;
                        for (let py = 0; py < 8; py++) {
                            let pb = 0;
                            for (let px = 0; px < 4; px++) {
                                let rIdx = ((cy * 8 + py) * 160 + (cx * 4 + px)) * 3;
                                let rVal = preAllocated.rgb[rIdx], gVal = preAllocated.rgb[rIdx + 1], bVal = preAllocated.rgb[rIdx + 2];
                                let d0 = dist(rVal, gVal, bVal, bgC), d1 = dist(rVal, gVal, bVal, c1), d2 = dist(rVal, gVal, bVal, c2), d3 = dist(rVal, gVal, bVal, c3);
                                let d = [d0, d1, d2, d3], s = [0, 1, 2, 3];
                                for (let a = 0; a < 2; a++) for (let k = a + 1; k < 4; k++) if (d[k] < d[a]) { [d[a], d[k]] = [d[k], d[a]]; [s[a], s[k]] = [s[k], s[a]]; }
                                let bits = s[0];
                                if (da > 0 && ds > 0) {
                                    let thr = (da == 1 ? b4[(cy * 8 + py) % 4 * 4 + (cx * 4 + px) % 4] : b8[(cy * 8 + py) % 8 * 8 + (cx * 4 + px) % 8]) * ds;
                                    if (d[1] - thr < d[0] + thr) bits = s[1];
                                }
                                pb |= (bits << ((3 - px) * 2));
                            }
                            b[base + cIdx * 8 + py] = pb;
                        }
                    }
                }
            }
            b[base + (isI ? 34000 : (isF ? 17000 : 10000))] = bgC;
        }
        activeB = writeB;
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
                                            offCtx = offC.getContext('2d', { willReadFrequently: true }); 
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
        start: function () { if (isRunning) return; isRunning = true; if (!offC) offC = document.getElementById('offscreen-c'); if (!offCtx) offCtx = offC.getContext('2d', { willReadFrequently: true }); if (!imgS) { imgS = new Image(); document.body.appendChild(imgS); imgS.style.display = "none"; } MLoop(); },
        stop: function () { isRunning = false; connected = false; },
        apiCall: async function (p) {
            let u = new URL(p, 'http://h'); if (p.startsWith('/data')) { 
                let isI = currentMode.includes('ifli'), isF = currentMode.includes('fli');
                let s = isI ? 34001 : (isF ? 17001 : 10000), r = new ArrayBuffer(s); 
                const dataToReturn = b.subarray(activeB * 34005, activeB * 34005 + s);
                new Uint8Array(r).set(dataToReturn); 
                return { ok: true, arrayBuffer: async () => r }; 
            }
            if (p.startsWith('/stats')) return { ok: true, json: async () => ({ frames: fCount, mode: currentMode, connected: connected, contrast: cf / 256, brightness: bv, bg: bgC, dither: ds, ditherType: da, totalKB: tKB, paletteIdx: palIdx, scale: 1, scaling: sc }) };
            if (p.startsWith('/setmode')) currentMode = u.searchParams.get('m'); if (p.startsWith('/setcontrast')) cf = Math.floor(parseFloat(u.searchParams.get('c')) * 256); if (p.startsWith('/setbrightness')) bv = parseInt(u.searchParams.get('b')); if (p.startsWith('/setbg')) bgC = parseInt(u.searchParams.get('c')); if (p.startsWith('/setpalette')) { palIdx = parseInt(u.searchParams.get('p')); pal = pals[palIdx]; } if (p.startsWith('/setdither')) ds = parseInt(u.searchParams.get('d')); if (p.startsWith('/setdithertype')) da = parseInt(u.searchParams.get('t')); if (p.startsWith('/setscaling')) sc = parseInt(u.searchParams.get('s')); return { ok: true };
        }
    };
})();
