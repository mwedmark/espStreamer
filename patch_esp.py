from pathlib import Path
path = Path('ESPStreamer/ESPStreamer.ino')
text = path.read_text(encoding='utf-8')
start = text.find('static const char INDEX_HTML[] PROGMEM = R"rawhtml(')
if start == -1:
    raise SystemExit('start missing')
end = text.find(')rawhtml";', start)
if end == -1:
    raise SystemExit('end missing')
text = text[:start] + text[end + len(')rawhtml";'):]
if '#include <SPIFFS.h>' not in text:
    text = text.replace('#include <HTTPClient.h>\n', '#include <HTTPClient.h>\n#include <SPIFFS.h>\n')
helper = '''
String getContentType(const String& filename) {
  if (filename.endsWith(".html")) return "text/html";
  if (filename.endsWith(".css")) return "text/css";
  if (filename.endsWith(".js")) return "application/javascript";
  if (filename.endsWith(".json")) return "application/json";
  if (filename.endsWith(".png")) return "image/png";
  if (filename.endsWith(".gif")) return "image/gif";
  if (filename.endsWith(".jpg") or filename.endsWith(".jpeg")) return "image/jpeg";
  if (filename.endsWith(".ico")) return "image/x-icon";
  return "application/octet-stream";
}

void handleStaticFile() {
  String path = server.uri();
  if (path == "/" || path == "") path = "/index.html";
  if (path.endsWith("/")) path += "index.html";

  if (!SPIFFS.exists(path)) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(404, "text/plain", "File not found");
    return;
  }

  File file = SPIFFS.open(path, "r");
  if (!file) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(500, "text/plain", "Failed to open file");
    return;
  }

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Cache-Control", "max-age=600");
  server.streamFile(file, getContentType(path));
  file.close();
}
'''
if helper not in text:
    text = text.replace('WebServer server(80);\n', 'WebServer server(80);\n' + helper)
text = text.replace('  server.on("/", handleRoot);\n', '  server.on("/", handleStaticFile);\n')
text = text.replace('  server.on("/setpalette", handleSetPalette);\n', '  server.on("/setpalette", handleSetPalette);\n  server.onNotFound(handleStaticFile);\n')
text = text.replace('void handleRoot() {\n  server.send_P(200, "text/html", INDEX_HTML);\n}\n\n', '')
path.write_text(text, encoding='utf-8')
print('patched')
