const fs = require('fs');
const cp = require('child_process');

// Get the original HEAD contents directly via node child_process
const orig = cp.execSync('git --no-pager show HEAD:frontend/app.js', {encoding: 'utf8'});
let curr = fs.readFileSync('frontend/app.js', 'utf8');

const targetIndex = orig.indexOf('function generateCRTSingle(');
if (targetIndex !== -1) {
    curr += '\n' + orig.slice(targetIndex);
    console.log('Restored tail.');
} else {
    console.log('Target function not found in original!');
}

// Remove console.logs in the restored part
curr = curr.replace(/console\.log\([^)]*\);?/g, '');
curr = curr.replace(/console\.error\([^)]*\);?/g, '');

// Fix the double if(r && r.ok) in upd()
const startIndex = curr.indexOf('    if (r && r.ok) {');
const catchIndex = curr.indexOf('  } catch (e) { }', startIndex);

if (startIndex !== -1 && catchIndex !== -1) {
    const newBlock = `    if (r && r.ok) {
      const d = new Uint8Array(await r.arrayBuffer()); 
      const cv = document.getElementById('c'), ctx = cv.getContext('2d');
      if (isIFLI) { const img = ctx.createImageData(160, 200), bg = c64Pal[d[32767]] || [0, 0, 0]; for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8, sB = py * 1024; for (let x = 0; x < 40; x++) { let cI = cR * 40 + x, bA = d[cI * 8 + py], sA = d[8192 + sB + cI], cA = d[15360 + cI], clA = [bg, c64Pal[sA >> 4], c64Pal[sA & 15], c64Pal[cA & 15]], bB = d[16384 + cI * 8 + py], sB2 = d[16384 + 8192 + sB + cI], cB = d[16384 + 15360 + cI], clB = [bg, c64Pal[sB2 >> 4], c64Pal[sB2 & 15], c64Pal[cB & 15]]; for (let px = 0; px < 4; px++) { let coA = clA[(bA >> ((3 - px) * 2)) & 3], coB = clB[(bB >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = (coA[0] + coB[0]) >> 1; img.data[o + 1] = (coA[1] + coB[1]) >> 1; img.data[o + 2] = (coA[2] + coB[2]) >> 1; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else if (isFLI) { const img = ctx.createImageData(160, 200), bg = c64Pal[d[16383]] || [0, 0, 0]; for (let y = 0; y < 200; y++) { let row = Math.floor(y / 8), py = y % 8, sB = py * 1024; for (let x = 0; x < 40; x++) { let cI = row * 40 + x, byte = d[cI * 8 + py], sBy = d[8192 + sB + cI], cBy = d[15360 + cI], cols = [bg, c64Pal[sBy >> 4], c64Pal[sBy & 15], c64Pal[cBy & 15]]; for (let px = 0; px < 4; px++) { let col = cols[(byte >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else if (isHires) { const img = ctx.createImageData(320, 200); for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8; for (let x = 0; x < 40; x++) { let cI = cR * 40 + x, byte = d[cI * 8 + py], sBy = d[8192 + cI], fg = c64Pal[sBy >> 4], bg = c64Pal[sBy & 15]; for (let bit = 7; bit >= 0; bit--) { let px = x * 8 + (7 - bit), isF = (byte >> bit) & 1, c = isF ? fg : bg, o = (y * 320 + px) * 4; img.data[o] = c[0]; img.data[o + 1] = c[1]; img.data[o + 2] = c[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
      else { const img = ctx.createImageData(160, 200), bg = c64Pal[currentBgColor]; for (let y = 0; y < 200; y++) { let cR = Math.floor(y / 8), py = y % 8; for (let x = 0; x < 40; x++) { let cellIdx = cR * 40 + x, byte = d[cellIdx * 8 + py], sBy = d[8192 + cellIdx], cBy = d[9216 + cellIdx], cols = [bg, c64Pal[sBy >> 4], c64Pal[sBy & 15], c64Pal[cBy & 15]]; for (let px = 0; px < 4; px++) { let col = cols[(byte >> ((3 - px) * 2)) & 3], o = (y * 160 + x * 4 + px) * 4; img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2]; img.data[o + 3] = 255; } } } ctx.putImageData(img, 0, 0); }
    }`;

    curr = curr.slice(0, startIndex) + newBlock + curr.slice(catchIndex);
    console.log('Fixed stream parsing logic.');
}

// Ensure the data-scale is populated cleanly
curr = curr.replace(/document\.getElementById\('c'\)\.setAttribute\('data-scale',\s*s\.scaling\);/g, '');
let statsTarget = `if (document.getElementById('scaling') && document.activeElement !== document.getElementById('scaling')) { document.getElementById('scaling').value = s.scaling;`;
if (curr.includes(statsTarget)) {
    curr = curr.replace(statsTarget, `if (document.getElementById('scaling') && document.activeElement !== document.getElementById('scaling')) { document.getElementById('scaling').value = s.scaling; document.getElementById('c').setAttribute('data-scale', s.scaling);`);
}

fs.writeFileSync('frontend/app.js', curr);
console.log('All recovery completed.');
