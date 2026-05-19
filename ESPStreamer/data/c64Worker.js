// Web Worker for C64 image processing - VERSION 1.0
self.onmessage = function(e) {
    const { imageData, width, height, config } = e.data;
    
    // Process image data in worker thread
    const result = processImageData(imageData, width, height, config);
    
    self.postMessage({ result });
};

function processImageData(imageData, width, height, config) {
    const { cf, bv, ds, da, bgC, pal, isG } = config;
    const d = imageData.data;
    const cb = new Uint8Array(height * width);
    const aP = isG ? [0, 1, 11, 12, 15] : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
    
    // Optimized color distance calculation
    function dist(c1, c2) { 
        const dr = pal.r[c1] - pal.r[c2];
        const dg = pal.g[c1] - pal.g[c2];
        const db = pal.b[c1] - pal.b[c2];
        return (dr * dr * 2) + (dg * dg * 4) + (db * db);
    }
    
    // Dither patterns
    const b4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
    const b8 = [0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4, 36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22, 3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7, 39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21];
    const blue = [21, 151, 80, 231, 41, 171, 95, 241, 23, 149, 78, 229, 39, 169, 93, 239, 107, 4, 190, 56, 121, 11, 201, 62, 111, 6, 192, 58, 119, 13, 203, 60, 245, 87, 161, 32, 253, 91, 177, 46, 243, 85, 163, 30, 255, 89, 175, 48, 69, 212, 136, 101, 75, 220, 142, 103, 71, 214, 138, 99, 73, 218, 140, 105, 17, 145, 76, 225, 35, 166, 83, 235, 19, 147, 74, 227, 37, 164, 81, 237, 115, 2, 198, 51, 127, 9, 207, 66, 113, 0, 196, 53, 125, 7, 205, 64, 249, 92, 155, 44, 251, 88, 157, 34, 247, 94, 153, 42, 253, 90, 155, 36, 61, 209, 131, 109, 63, 211, 133, 102, 59, 213, 129, 107, 65, 215, 131, 106, 22, 152, 79, 230, 42, 172, 94, 242, 24, 150, 77, 228, 40, 170, 92, 240, 108, 5, 191, 57, 122, 12, 200, 63, 110, 7, 193, 59, 118, 14, 202, 61, 244, 86, 160, 31, 254, 90, 176, 47, 242, 84, 162, 31, 254, 88, 174, 49, 70, 213, 137, 100, 74, 221, 143, 104, 72, 215, 139, 98, 74, 219, 141, 106, 18, 146, 75, 224, 36, 167, 84, 236, 20, 148, 73, 226, 38, 165, 82, 238, 116, 3, 199, 52, 126, 8, 206, 67, 114, 1, 197, 54, 124, 6, 204, 65, 248, 93, 154, 45, 250, 89, 156, 35, 246, 95, 152, 43, 252, 91, 154, 37, 62, 210, 132, 108, 64, 212, 134, 103, 60, 214, 130, 106, 66, 216, 132, 105];
    
    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            let i = (y * width + x) * 4;
            let r = (((d[i] - 128) * cf) >> 8) + 128 + bv;
            let g = (((d[i + 1] - 128) * cf) >> 8) + 128 + bv;
            let bl = (((d[i + 2] - 128) * cf) >> 8) + 128 + bv;
            
            if (da > 0 && ds > 0) {
                let thr = 0;
                if (da == 1) thr = (b4[(y % 4) * 4 + (x % 4)] / 16) - 0.5;
                else if (da == 2) thr = (b8[(y % 8) * 8 + (x % 8)] / 64) - 0.5;
                else if (da == 3) thr = Math.random() - 0.5;
                else if (da == 4) thr = (blue[(y % 16) * 16 + (x % 16)] / 255) - 0.5;
                let s = ds * 12;
                r += thr * s;
                g += thr * s;
                bl += thr * s;
            }
            
            r = Math.max(0, Math.min(255, r));
            g = Math.max(0, Math.min(255, g));
            bl = Math.max(0, Math.min(255, bl));
            
            // Optimized color finding
            let bc = aP[0];
            let bd = (Math.abs(r - pal.r[bc]) * 2) + (Math.abs(g - pal.g[bc]) * 4) + Math.abs(bl - pal.b[bc]);
            for (let i = 1; i < aP.length; i++) {
                const it = aP[i];
                const dy = (Math.abs(r - pal.r[it]) * 2) + (Math.abs(g - pal.g[it]) * 4) + Math.abs(bl - pal.b[it]);
                if (dy < bd) {
                    bd = dy;
                    bc = it;
                }
            }
            
            cb[y * width + x] = bc;
        }
    }
    
    return cb;
}
