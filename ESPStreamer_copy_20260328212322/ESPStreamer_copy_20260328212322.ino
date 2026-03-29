#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <TJpg_Decoder.h>

// --- KONFIGURATION ---
const char* ssid = "MagnusAsus_Boa";
const char* password = "R36RulesAgain";
const char* streamUrl = "http://MagnusDesktop:90/pc.mjpg";

WebServer server(80);

// VIKTIGT: Skapa instansen här och döp den till 'decoder'
TJpg_Decoder decoder;

uint8_t temp_jpg_buffer[15000]; // Plats för en enskild JPEG-bildruta
uint8_t c64_buffer[8000]; // Storleksangivelse tillagd
Stream* _jpgStream = nullptr;

const int8_t bayer4x4[4][4] = {
    {-32,  0, -24,  8},
    { 16, -16, 24, -8},
    {-20, 12, -28,  4},
    { 28, -4,  20, -12}
};

// --- CALLBACKS ---
bool process_output(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t* bitmap) {
  for (int j = 0; j < h; j++) {
    for (int i = 0; i < w; i++) {
      int currX = x + i;
      int currY = y + j;
      if (currX >= 160 || currY >= 200) continue;

      uint16_t p = bitmap[i + j * w];
      uint8_t r = (p >> 8) & 0xF8;
      uint8_t g = (p >> 3) & 0xFC;
      uint8_t b = (p << 3) & 0xF8;
      int16_t gray = (r + g + b) / 3;

      int16_t dithered = gray + bayer4x4[currX % 4][currY % 4];
      uint8_t level = map(constrain(dithered, 0, 255), 0, 255, 0, 3);

      int pixelIdx = currY * 160 + currX;
      int byteIdx = pixelIdx / 4;
      int shift = (3 - (pixelIdx % 4)) * 2;
      
      c64_buffer[byteIdx] &= ~(0x03 << shift);
      c64_buffer[byteIdx] |= (level << shift);
    }
  }
  return true;
}

uint16_t jpg_stream_reader(uint8_t *buf, uint16_t len) {
  if (buf && _jpgStream && _jpgStream->available() > 0) {
    return _jpgStream->readBytes(buf, len);
  }
  return 0;
}

// --- WEBSERVER ---
void handleRoot() {
  String html = "<html><head><style>";
  html += "body{background:#404080;display:flex;flex-direction:column;align-items:center;color:white;font-family:monospace;margin:20px;}";
  html += "canvas{width:640px;height:400px;image-rendering:pixelated;border:15px solid #8080ff;background:black;}";
  html += ".btns{margin-top:20px;display:flex;gap:10px;}";
  html += "button{padding:10px 20px;background:#8080ff;color:white;border:2px solid white;cursor:pointer;font-family:monospace;font-weight:bold;}";
  html += "</style></head><body>";
  html += "<h2>ESP32 C64 ENCODER LIVE</h2>";
  html += "<canvas id='c' width='160' height='200'></canvas>";
  html += "<div class='btns'>";
  html += "<button onclick='saveFile(\"PRG\")'>DOWNLOAD .PRG</button>";
  html += "<button onclick='saveFile(\"KOA\")'>DOWNLOAD .KOA</button>";
  html += "</div><script>";
  html += "const palette=[0,85,170,255];";
  html += "async function saveFile(t){const r=await fetch('/data');const buf=await r.arrayBuffer();const d=new Uint8Array(buf);";
  html += "let f;if(t==='KOA'){f=new Uint8Array(10003);f[0]=0x00;f[1]=0x60;f.set(d,2);for(let i=8002;i<9002;i++)f[i]=0xBC;for(let i=9002;i<10002;i++)f[i]=0x01;download(f,'img.koa');}";
  html += "else{f=new Uint8Array(10044);f[0]=0x01;f[1]=0x08;f.set([0x0B,0x08,0x0A,0x00,0x9E,0x32,0x30,0x36,0x31,0x00,0x00,0x00],2);";
  html += "f.set([0x78,0xA9,0x3B,0x8D,0x11,0xD0,0xA9,0x18,0x8D,0x16,0xD0,0xA9,0x18,0x8D,0x18,0xD0,0xA9,0x00,0x8D,0x20,0xD0,0xA9,0x00,0x8D,0x21,0xD0,0x4C,0x1D,0x08],14);";
  html += "f.set(d,44);for(let i=8044;i<9044;i++)f[i]=0xBC;for(let i=9044;i<10044;i++)f[i]=0x01;download(f,'view.prg');}}";
  html += "function download(d,n){const b=new Blob([d],{type:'application/octet-stream'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=n;a.click();}";
  html += "async function update(){try{const r=await fetch('/data');const b=await r.arrayBuffer();const d=new Uint8Array(b);const ctx=document.getElementById('c').getContext('2d');const img=ctx.createImageData(160,200);";
  html += "for(let i=0;i<32000;i++){let v=palette[(d[Math.floor(i/4)]>>(3-i%4)*2)&0x03];img.data[i*4]=v;img.data[i*4+1]=v;img.data[i*4+2]=v;img.data[i*4+3]=255;}ctx.putImageData(img,0,0);}catch(e){}setTimeout(update,100);}update();</script></body></html>";
  server.send(200, "text/html", html);
}

void handleData() {
  // Vi använder en tom sträng i send() för att initiera, 
  // men vi låter servern veta att vi skickar rådata manuellt.
  server.setContentLength(8000); 
  server.send(200, "application/octet-stream", "");
  server.sendContent((const char*)c64_buffer, 8000);
}



// --- SETUP & LOOP ---
void setup() {
 Serial.begin(115200);
  delay(1000);
  
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi Connected!");
  Serial.print("ESP32 IP-address: ");
  Serial.println(WiFi.localIP()); // HÄR SKRIVS IP UT
  Serial.println("Open this IP in your browser for Live Preview.");

  // Använd instansen 'decoder' istället för klassnamnet
  decoder.setJpgScale(1);
  decoder.setCallback(process_output);

  server.on("/", handleRoot);
  server.on("/data", handleData);
  server.begin();
}

void loop() {
  server.handleClient();
  
  static unsigned long lastUpdate = 0;
  if (millis() - lastUpdate > 50) { // Försök var 50:e ms
    HTTPClient http;
    http.setConnectTimeout(1000);
    http.begin(streamUrl);
    int httpCode = http.GET();
    
    if (httpCode == HTTP_CODE_OK) {
      WiFiClient* stream = http.getStreamPtr();
      uint32_t timeout = millis();
      
      // Vi letar efter JPEG-start (0xFF 0xD8)
      bool foundStart = false;
      while (http.connected() && (millis() - timeout < 1000)) {
        if (stream->available() >= 2) {
          if (stream->read() == 0xFF && stream->peek() == 0xD8) {
            foundStart = true;
            break;
          }
        }
        yield();
      }

      if (foundStart) {
        // Läs in en lagom mängd data för en 160x200 bild (ofta 3-7 KB)
        size_t size = stream->readBytes(temp_jpg_buffer, sizeof(temp_jpg_buffer));
        if (size > 0) {
           // Nu avkodar vi den buffrade bilden
           decoder.drawJpg(0, 0, temp_jpg_buffer, size);
           Serial.println("Bild avkodad!"); // Debug-utskrift
        }
      }
    }
    http.end();
    lastUpdate = millis();
  }
}



