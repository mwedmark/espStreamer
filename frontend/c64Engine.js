// Pure JavaScript port of ESPStreamer C++ engine - VERSION 8.5 (Low Latency)
window.C64Engine = (function () {
    let currentMode = 'mc_gray', isRunning = false, connected = false;
    let cf = 256, bv = 0, ds = 4, da = 2, bgC = 0, sc = 0, palIdx = 0, fCount = 0, tKB = 0;
    let b = new Uint8Array(65536), activeB = 0;
    let offC = null, offCtx = null, imgS = null, lastWT = 0;
    const pals = [{ r: [0, 255, 104, 112, 111, 88, 53, 184, 111, 67, 154, 68, 108, 154, 108, 149], g: [0, 255, 55, 164, 61, 141, 40, 199, 79, 57, 103, 68, 108, 210, 94, 149], b: [0, 255, 43, 178, 134, 67, 121, 111, 37, 0, 89, 68, 108, 132, 181, 149] }, { r: [0, 255, 129, 117, 142, 86, 45, 237, 142, 85, 196, 108, 123, 169, 112, 170], g: [0, 255, 51, 205, 60, 172, 48, 240, 80, 56, 108, 74, 123, 255, 117, 170], b: [0, 255, 56, 200, 151, 93, 173, 175, 41, 0, 113, 74, 123, 159, 213, 170] }];
    let pal = pals[0]; const grayIdx = [0, 1, 11, 12, 15];
    function dist(c1, c2) { return (Math.abs(pal.r[c1] - pal.r[c2]) * 2) + (Math.abs(pal.g[c1] - pal.g[c2]) * 4) + Math.abs(pal.b[c1] - pal.b[c2]); }
    function log(m) { const s = document.getElementById('stxt'); if (s) s.innerText = m; }
    function process(idat, wT, isH, isF, isI, isG) {
        const d = idat.data; let cb = new Uint8Array(200 * 320); let aP = isG ? grayIdx : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
        for (let y = 0; y < 200; y++) { for (let x = 0; x < wT; x++) { let i = (y * wT + x) * 4, r = (((d[i] - 128) * cf) >> 8) + 128 + bv, g = (((d[i + 1] - 128) * cf) >> 8) + 128 + bv, bl = (((d[i + 2] - 128) * cf) >> 8) + 128 + bv; r = Math.max(0, Math.min(255, r)); g = Math.max(0, Math.min(255, g)); bl = Math.max(0, Math.min(255, bl)); let bd = 0xFFFFFF, bc = 0; for (let it of aP) { let dy = (Math.abs(r - pal.r[it]) * 2) + (Math.abs(g - pal.g[it]) * 4) + Math.abs(bl - pal.b[it]); if (dy < bd) { bd = dy; bc = it; } } cb[y * wT + x] = bc; } }
        let mF = isI ? 2 : 1; for (let f = 0; f < mF; f++) {
            let base = (1 - activeB) * 32768 + (f * 16384);
            for (let cy = 0; cy < 25; cy++) {
                for (let cx = 0; cx < 40; cx++) {
                    let cIdx = cy * 40 + cx; if (isF) {
                        let cnts = new Array(16).fill(0); for (let py = 0; py < 8; py++) for (let px = 0; px < 4; px++) cnts[cb[(cy * 8 + py) * 160 + (cx * 4 + px)]]++; cnts[bgC] = -1; let cC = 1, mcC = -1; for (let i = 0; i < 16; i++) if (cnts[i] > mcC) { mcC = cnts[i]; cC = i; } b[base + 15360 + cIdx] = cC;
                        for (let py = 0; py < 8; py++) { let lc = new Array(16).fill(0); for (let px = 0; px < 4; px++) lc[cb[(cy * 8 + py) * 160 + (cx * 4 + px)]]++; lc[bgC] = -1; lc[cC] = -1; let c1 = 0, c2 = 0, m1 = 0, m2 = 0; for (let i = 0; i < 16; i++) { if (lc[i] > m1) { m2 = m1; c2 = c1; m1 = lc[i]; c1 = i; } else if (lc[i] > m2) { m2 = lc[i]; c2 = i; } } if (m1 === 0) c1 = cC; if (m2 === 0) c2 = c1; b[base + 8192 + py * 1024 + cIdx] = (c1 << 4) | (c2 & 15); let pb = 0; for (let px = 0; px < 4; px++) { let c = cb[(cy * 8 + py) * 160 + (cx * 4 + px)], d0 = dist(c, bgC), d1 = dist(c, c1), d2 = dist(c, c2), d3 = dist(c, cC), bst = [{ d: d0, s: 0 }, { d: d1, s: 1 }, { d: d2, s: 2 }, { d: d3, s: 3 }].sort((a, bi) => a.d - bi.d); pb |= (bst[0].s << ((3 - px) * 2)); } b[base + cIdx * 8 + py] = pb; }
                    } else if (isH) { let cnts = new Array(16).fill(0); for (let py = 0; py < 8; py++) for (let px = 0; px < 8; px++) cnts[cb[(cy * 8 + py) * 320 + (cx * 8 + px)]]++; let bg = 0, fg = 1, mB = -1, mF2 = -1; for (let i = 0; i < 16; i++) { if (cnts[i] > mB) { mF2 = mB; fg = bg; mB = cnts[i]; bg = i; } else if (cnts[i] > mF2) { mF2 = cnts[i]; fg = i; } } b[base + 8192 + cIdx] = (fg << 4) | (bg & 15); for (let py = 0; py < 8; py++) { let pb = 0; for (let px = 0; px < 8; px++) { if (dist(cb[(cy * 8 + py) * 320 + (cx * 8 + px)], fg) < dist(cb[(cy * 8 + py) * 320 + (cx * 8 + px)], bg)) pb |= (1 << (7 - px)); } b[base + cIdx * 8 + py] = pb; } } else { let cnts = new Array(16).fill(0); for (let py = 0; py < 8; py++) for (let px = 0; px < 4; px++) cnts[cb[(cy * 8 + py) * 160 + (cx * 4 + px)]]++; cnts[bgC] = -1; let c1 = 1, c2 = 1, c3 = 1, m1 = 0, m2 = 0, m3 = 0; for (let i = 0; i < 16; i++) { if (cnts[i] > m1) { m3 = m2; c3 = c2; m2 = m1; c2 = c1; m1 = cnts[i]; c1 = i; } else if (cnts[i] > m2) { m3 = m2; c3 = c2; m2 = cnts[i]; c2 = i; } else if (cnts[i] > m3) { m3 = cnts[i]; c3 = i; } } b[base + 8192 + cIdx] = (c1 << 4) | (c2 & 15); b[base + 9216 + cIdx] = c3; for (let py = 0; py < 8; py++) { let pb = 0; for (let px = 0; px < 4; px++) { let c = cb[(cy * 8 + py) * 160 + (cx * 4 + px)], d0 = dist(c, bgC), d1 = dist(c, c1), d2 = dist(c, c2), d3 = dist(c, c3), bst = [{ d: d0, s: 0 }, { d: d1, s: 1 }, { d: d2, s: 2 }, { d: d3, s: 3 }].sort((ax, bx) => ax.d - bx.d); pb |= (bst[0].s << ((3 - px) * 2)); } b[base + cIdx * 8 + py] = pb; } }
                }
            }
        }
        b[(1 - activeB) * 32768 + (isI ? 32767 : 16383)] = bgC; activeB = 1 - activeB; fCount++;
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
                                        let wT = currentMode.includes('hr') ? 320 : 160; if (wT !== lastWT) { offC.width = wT; lastWT = wT; offCtx = offC.getContext('2d'); }
                                        offCtx.drawImage(imgS, 0, 0, wT, 200); process(offCtx.getImageData(0, 0, wT, 200), wT, currentMode.includes('hr'), currentMode.includes('fli'), currentMode.includes('ifli'), currentMode.includes('gray'));
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
            let u = new URL(p, 'http://h'); if (p.startsWith('/data')) { let isI = currentMode.includes('ifli'), s = isI ? 32768 : 16384, r = new ArrayBuffer(s + 1); new Uint8Array(r).set(b.subarray(activeB * 32768, activeB * 32768 + s + 1)); return { ok: true, arrayBuffer: async () => r }; }
            if (p.startsWith('/stats')) return { ok: true, json: async () => ({ frames: fCount, mode: currentMode, connected: connected, contrast: cf / 256, brightness: bv, bg: bgC, dither: ds, ditherType: da, totalKB: tKB, paletteIdx: palIdx, scale: 1, scaling: sc }) };
            if (p.startsWith('/setmode')) currentMode = u.searchParams.get('m'); if (p.startsWith('/setcontrast')) cf = Math.floor(parseFloat(u.searchParams.get('c')) * 256); if (p.startsWith('/setbrightness')) bv = parseInt(u.searchParams.get('b')); if (p.startsWith('/setbg')) bgC = parseInt(u.searchParams.get('c')); if (p.startsWith('/setpalette')) { palIdx = parseInt(u.searchParams.get('p')); pal = pals[palIdx]; } if (p.startsWith('/setdither')) ds = parseInt(u.searchParams.get('d')); if (p.startsWith('/setdithertype')) da = parseInt(u.searchParams.get('t')); if (p.startsWith('/setscaling')) sc = parseInt(u.searchParams.get('s')); return { ok: true };
        }
    };
})();
