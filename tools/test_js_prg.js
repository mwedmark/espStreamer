/**
 * test_js_prg.js
 * ==============
 * Tests the JavaScript PRG generator for FLI and IFLI modes.
 * Uses the same working machine code proven in generate_fli_rainbow.py.
 *
 * The generated PRG uses the same memory layout as the Python generator:
 *   Load address: $0801
 *   $0900-$09C7 : D011 table (200 bytes) - bad-line scroll per scanline
 *   $0A00-$0AC7 : D018 table (200 bytes) - screen page pointer per scanline
 *   $1000-$13E7 : Color RAM (1000 bytes, copied to $D800 at startup)
 *   $4000-$5FFF : Screen RAM pages 0-7 (8 x 1024 bytes)
 *   $6000-$7F3F : Bitmap RAM (8000 bytes)
 *
 * Run: node tools/test_js_prg.js
 */

const fs = require('fs');

// PRG offset helper: C64 address -> byte offset in PRG file
const o = (addr) => (addr - 0x0801) + 2;

/**
 * Generate the FLI machine code for the PRG file.
 * This is the proven working routine from generate_fli_rainbow.py.
 *
 * @param {number} bgColor - Background color index (0-15)
 * @returns {Uint8Array} - PRG byte array (30529 bytes, $0801-$7F40)
 */
function buildFliMachineCode(bgColor) {
  // PRG spans $0801 to $7F40 = 30529 bytes
  const PRG_SIZE = (0x7F40 - 0x0801) + 2;
  const prg = new Uint8Array(PRG_SIZE);

  // Load address $0801
  prg[0] = 0x01;
  prg[1] = 0x08;

  // BASIC stub: 10 SYS 2061 ($080D)
  prg.set([0x0B, 0x08, 0x0A, 0x00, 0x9E, 0x32, 0x30, 0x36, 0x31, 0x00, 0x00, 0x00], 2);

  // ----------------------------------------------------------------
  // D011 TABLE at $0900 (200 bytes)
  // Bad-line condition: (raster & 7) == ($D011 & 7)
  // For screen line Y: raster = $33 + Y
  // D011 = $38 | (raster & 7)  (BMM=1, DEN=1, RSEL=1, yscroll=raster&7)
  // ----------------------------------------------------------------
  for (let y = 0; y < 200; y++) {
    const raster = 0x33 + y;
    prg[o(0x0900) + y] = 0x38 | (raster & 0x07);
  }

  // ----------------------------------------------------------------
  // D018 TABLE at $0A00 (200 bytes)
  // Cycles through 8 screen RAM pages at $4000,$4400,...,$5C00
  // Bitmap at $6000 in bank -> low nibble = $08
  // D018 = (page << 4) | $08
  // ----------------------------------------------------------------
  for (let y = 0; y < 200; y++) {
    const page = y % 8;
    prg[o(0x0A00) + y] = (page << 4) | 0x08;
  }

  // ----------------------------------------------------------------
  // MACHINE CODE at $080D (emit helper tracks PC)
  // ----------------------------------------------------------------
  let pc = 0x080D;

  function emit(...bytes) {
    const startPc = pc;
    for (const b of bytes) {
      prg[o(pc)] = b & 0xFF;
      pc++;
    }
    return startPc;
  }

  // SEI, CLD
  emit(0x78);            // SEI
  emit(0xD8);            // CLD

  // Set VIC Bank 1 ($4000-$7FFF): $DD00 bits[1:0] = %10
  emit(0xAD, 0x00, 0xDD); // LDA $DD00
  emit(0x29, 0xFC);        // AND #$FC
  emit(0x09, 0x02);        // ORA #$02
  emit(0x8D, 0x00, 0xDD); // STA $DD00
  emit(0xAD, 0x02, 0xDD); // LDA $DD02
  emit(0x09, 0x03);        // ORA #$03
  emit(0x8D, 0x02, 0xDD); // STA $DD02

  // VIC modes: multicolor bitmap
  emit(0xA9, 0x3B);        // LDA #$3B (BMM=1, DEN=1, RSEL=1, yscroll=3)
  emit(0x8D, 0x11, 0xD0); // STA $D011
  emit(0xA9, 0x18);        // LDA #$18 (MCM=1, CSEL=1)
  emit(0x8D, 0x16, 0xD0); // STA $D016
  emit(0xA9, 0x08);        // LDA #$08 (screen page 0 @ $4000, bitmap @ $6000)
  emit(0x8D, 0x18, 0xD0); // STA $D018

  // Border + background color
  emit(0xA9, bgColor);     // LDA #bgColor
  emit(0x8D, 0x20, 0xD0); // STA $D020
  emit(0x8D, 0x21, 0xD0); // STA $D021

  // Copy Color RAM: $1000 -> $D800 (1000 bytes in 4 x 250-byte chunks)
  emit(0xA2, 0x00);        // LDX #$00
  const copyLoop = pc;
  emit(0xBD, 0x00, 0x10); // LDA $1000,X
  emit(0x9D, 0x00, 0xD8); // STA $D800,X
  emit(0xBD, 0xFA, 0x10); // LDA $10FA,X
  emit(0x9D, 0xFA, 0xD8); // STA $D8FA,X
  emit(0xBD, 0xF4, 0x11); // LDA $11F4,X
  emit(0x9D, 0xF4, 0xD9); // STA $D9F4,X
  emit(0xBD, 0xEE, 0x12); // LDA $12EE,X
  emit(0x9D, 0xEE, 0xDA); // STA $DAEE,X
  emit(0xE8);              // INX
  emit(0xE0, 0xFA);        // CPX #$FA (250)
  emit(0xD0, (copyLoop - (pc + 2)) & 0xFF); // BNE copyLoop

  // Disable CIA interrupts
  emit(0xA9, 0x7F);        // LDA #$7F
  emit(0x8D, 0x0D, 0xDC); // STA $DC0D
  emit(0x8D, 0x0D, 0xDD); // STA $DD0D
  emit(0xAD, 0x0D, 0xDC); // LDA $DC0D (clear pending)
  emit(0xAD, 0x0D, 0xDD); // LDA $DD0D

  // Acknowledge any pending VIC interrupt
  emit(0xA9, 0xFF);        // LDA #$FF
  emit(0x8D, 0x19, 0xD0); // STA $D019

  // Set raster IRQ to line $30 (just before visible area at $33)
  emit(0xA9, 0x30);        // LDA #$30
  emit(0x8D, 0x12, 0xD0); // STA $D012
  emit(0xAD, 0x11, 0xD0); // LDA $D011
  emit(0x29, 0x7F);        // AND #$7F (clear raster bit 8)
  emit(0x8D, 0x11, 0xD0); // STA $D011

  // Enable VIC raster interrupt
  emit(0xA9, 0x01);        // LDA #$01
  emit(0x8D, 0x1A, 0xD0); // STA $D01A

  // Set IRQ vector to IRQ1 (mainLoopAddr + 14 bytes ahead)
  const mainLoopAddr = pc;
  const irq1Addr = mainLoopAddr + 14; // 10 (vector set) + 1 (CLI) + 3 (JMP)

  emit(0xA9, irq1Addr & 0xFF);         // LDA #lo(IRQ1)
  emit(0x8D, 0x14, 0x03);              // STA $0314
  emit(0xA9, (irq1Addr >> 8) & 0xFF);  // LDA #hi(IRQ1)
  emit(0x8D, 0x15, 0x03);              // STA $0315

  emit(0x58);              // CLI

  // main_loop: spin forever, IRQ does all work
  const realMain = pc;
  emit(0x4C, realMain & 0xFF, (realMain >> 8) & 0xFF); // JMP main_loop

  if (pc !== irq1Addr) throw new Error(`IRQ1 addr mismatch: expected $${irq1Addr.toString(16)}, got $${pc.toString(16)}`);

  // ----------------------------------------------------------------
  // IRQ1: double-IRQ first stage - just re-arms IRQ2 on next line
  // ----------------------------------------------------------------
  const irq1Start = pc;

  emit(0xA9, 0xFF);        // LDA #$FF
  emit(0x8D, 0x19, 0xD0); // STA $D019 (ack VIC IRQ)
  emit(0xA9, 0x31);        // LDA #$31  (next raster line)
  emit(0x8D, 0x12, 0xD0); // STA $D012

  // IRQ2 is exactly 23 bytes after IRQ1 start
  const irq2Addr = irq1Start + 23;

  emit(0xA9, irq2Addr & 0xFF);         // LDA #lo(IRQ2)
  emit(0x8D, 0x14, 0x03);              // STA $0314
  emit(0xA9, (irq2Addr >> 8) & 0xFF);  // LDA #hi(IRQ2)
  emit(0x8D, 0x15, 0x03);              // STA $0315
  emit(0x4C, 0x81, 0xEA);              // JMP $EA81 (KERNAL IRQ exit)

  if (pc !== irq2Addr) throw new Error(`IRQ2 addr mismatch: expected $${irq2Addr.toString(16)}, got $${pc.toString(16)}`);

  // ----------------------------------------------------------------
  // IRQ2: stable second stage - spin-wait for raster $33, then FLI
  // ----------------------------------------------------------------
  emit(0xA9, 0xFF);        // LDA #$FF
  emit(0x8D, 0x19, 0xD0); // STA $D019 (ack VIC IRQ)

  // Double spin: wait for $32, then $33
  const wait32 = pc;
  emit(0xAD, 0x12, 0xD0); // LDA $D012
  emit(0xC9, 0x32);        // CMP #$32
  emit(0xD0, (wait32 - (pc + 2)) & 0xFF); // BNE wait32

  const wait33 = pc;
  emit(0xAD, 0x12, 0xD0); // LDA $D012
  emit(0xC9, 0x33);        // CMP #$33
  emit(0xD0, (wait33 - (pc + 2)) & 0xFF); // BNE wait33

  emit(0xEA);              // NOP (2 cycles) to shift write past cycle 14
  emit(0xA0, 0x01);        // LDY #$01 (Start at line 1)

  // ----------------------------------------------------------------
  // FLI LOOP: exactly 23 cycles per iteration
  //   LDA $0900,Y  [4] load D011 value
  //   STA $D011    [4] write VIC scroll/bad-line trigger
  //   LDA $0A00,Y  [4] load D018 value
  //   STA $D018    [4] write VIC screen page pointer
  //   INY          [2]
  //   CPY #$C8     [2]
  //   BNE fliLoop  [3]
  //   Total = 23 cycles ✓ (fits the 24-cycle window after VIC DMA)
  // ----------------------------------------------------------------
  const fliLoop = pc;
  emit(0xB9, 0x00, 0x09); // LDA $0900,Y  [4]
  emit(0x8D, 0x11, 0xD0); // STA $D011    [4]
  emit(0xB9, 0x00, 0x0A); // LDA $0A00,Y  [4]
  emit(0x8D, 0x18, 0xD0); // STA $D018    [4]
  emit(0xC8);              // INY          [2]
  emit(0xC0, 0xC8);        // CPY #$C8     [2]
  emit(0xD0, (fliLoop - (pc + 2)) & 0xFF); // BNE fliLoop [3]

  // After 200 lines: restore state and re-arm IRQ1 for next frame
  emit(0xA9, 0x3B);        // LDA #$3B
  emit(0x8D, 0x11, 0xD0); // STA $D011
  emit(0xA9, 0x08);        // LDA #$08
  emit(0x8D, 0x18, 0xD0); // STA $D018
  emit(0xA9, 0x30);        // LDA #$30
  emit(0x8D, 0x12, 0xD0); // STA $D012
  emit(0xA9, irq1Addr & 0xFF);         // LDA #lo(IRQ1)
  emit(0x8D, 0x14, 0x03);              // STA $0314
  emit(0xA9, (irq1Addr >> 8) & 0xFF);  // LDA #hi(IRQ1)
  emit(0x8D, 0x15, 0x03);              // STA $0315
  emit(0x4C, 0x81, 0xEA);              // JMP $EA81

  console.log(`  Code: $080D-$${(pc-1).toString(16).toUpperCase()}`);
  console.log(`  IRQ1: $${irq1Addr.toString(16).toUpperCase()}`);
  console.log(`  IRQ2: $${irq2Addr.toString(16).toUpperCase()}`);
  console.log(`  FLI loop: $${fliLoop.toString(16).toUpperCase()}`);

  return prg;
}

/**
 * Generate a complete FLI PRG from raw frame data.
 *
 * @param {Uint8Array} rawData - 17001 bytes: [0..7999]=bitmap, [8000..15999]=8 screen pages (8x1000),
 *                               [16000..16999]=color RAM, [17000]=bgColor
 * @returns {Uint8Array} PRG file bytes
 */
function generateFliPRG(rawData) {
  const bgColor = rawData[17000] & 0x0F;
  console.log(`\nGenerating FLI PRG (bgColor=${bgColor})...`);

  const prg = buildFliMachineCode(bgColor);

  // Color RAM at $1000 (1000 bytes) -> source: rawData[16000..16999]
  for (let i = 0; i < 1000; i++) {
    prg[o(0x1000) + i] = rawData[16000 + i];
  }

  // Screen RAM pages 0-7 at $4000-$5FFF (8 pages x 1024 bytes, padded from 1000)
  // Source: rawData[8000..15999] = 8 x 1000 bytes packed
  for (let py = 0; py < 8; py++) {
    for (let cIdx = 0; cIdx < 1000; cIdx++) {
      prg[o(0x4000) + py * 1024 + cIdx] = rawData[8000 + py * 1000 + cIdx];
    }
  }

  // Bitmap at $6000 (8000 bytes) -> source: rawData[0..7999]
  for (let i = 0; i < 8000; i++) {
    prg[o(0x6000) + i] = rawData[i];
  }

  return prg;
}

/**
 * Generate a test FLI PRG with a rainbow pattern (one color per scanline).
 * This is the simplest possible test - if it works you see thin colored stripes.
 */
function generateRainbowTestPRG() {
  console.log('Generating rainbow test PRG...');
  const rawData = new Uint8Array(17001);

  // Bitmap: all $55 = %01010101 -> bits=01 -> uses Screen RAM HIGH nibble
  rawData.fill(0x55, 0, 8000);

  // Screen RAM pages: page N handles lines where (line % 8) == N
  // Color for line Y = Y % 16, stored in high nibble of screen byte
  for (let page = 0; page < 8; page++) {
    for (let row = 0; row < 25; row++) {
      const lineY = row * 8 + page;
      const color = lineY % 16;
      const byte = (color << 4) | ((color + 8) % 16);
      for (let col = 0; col < 40; col++) {
        rawData[8000 + page * 1000 + row * 40 + col] = byte;
      }
    }
  }

  // Color RAM: all zero (not used since bitmap=$55 -> bits=01)
  rawData.fill(0, 16000, 17000);
  rawData[17000] = 0; // bg color = black

  return generateFliPRG(rawData);
}

// ----------------------------------------------------------------
// RUN TESTS
// ----------------------------------------------------------------

// Test 1: Rainbow test (same as working fli_rainbow_test.prg)
console.log('=== Test 1: Rainbow PRG ===');
const rainbowPRG = generateRainbowTestPRG();
fs.writeFileSync('tools/test_fli_js_rainbow.prg', rainbowPRG);
console.log(`Saved: tools/test_fli_js_rainbow.prg (${rainbowPRG.length} bytes)`);

// Test 2: Simulate a frame from the web app (patterned data for validation)
console.log('\n=== Test 2: Simulated frame PRG ===');
const simData = new Uint8Array(17001);
// Fill bitmap with known pattern
for (let i = 0; i < 8000; i++) simData[i] = i & 0xFF;
// Fill screen pages with alternating colors
for (let i = 8000; i < 16000; i++) simData[i] = ((i - 8000) >> 3) & 0xFF;
// Fill color RAM
for (let i = 16000; i < 17000; i++) simData[i] = (i - 16000) % 16;
simData[17000] = 0; // bg = black

const simPRG = generateFliPRG(simData);
fs.writeFileSync('tools/test_fli_generated.prg', simPRG);
console.log(`Saved: tools/test_fli_generated.prg (${simPRG.length} bytes)`);

// Verify: compare rainbow PRG machine code with known-good Python output
console.log('\n=== Verification: Comparing JS vs Python rainbow PRG ===');
const pythonPath = 'tools/fli_rainbow_test.prg';
if (fs.existsSync(pythonPath)) {
  const pyPRG = new Uint8Array(fs.readFileSync(pythonPath));
  const jsPRG = rainbowPRG;
  const minLen = Math.min(pyPRG.length, jsPRG.length);
  let diffs = 0;
  const diffAddrs = [];
  for (let i = 0; i < minLen; i++) {
    if (pyPRG[i] !== jsPRG[i]) {
      diffs++;
      const c64addr = 0x0801 + (i - 2);
      if (diffAddrs.length < 20) diffAddrs.push(`$${c64addr.toString(16).toUpperCase()}:py=${pyPRG[i].toString(16).padStart(2,'0')} js=${jsPRG[i].toString(16).padStart(2,'0')}`);
    }
  }
  if (diffs === 0) {
    console.log('✅ PERFECT MATCH - JS output is byte-identical to Python output!');
  } else {
    console.log(`⚠️  ${diffs} byte differences found (first ${Math.min(diffs,20)}):`)
    diffAddrs.forEach(d => console.log(`   ${d}`));
  }
} else {
  console.log(`⚠️  Python reference file not found at ${pythonPath}, skipping comparison`);
}

console.log('\nDone. Test in VICE:');
console.log('  "D:\\share\\Emulators\\GTK3VICE-3.9-win64\\bin\\x64sc.exe" -autostart tools\\test_fli_js_rainbow.prg');
