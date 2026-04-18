import http.server
import socketserver
import urllib.request
import os

# ESPStreamer PC Proxy - VERSION 5.0 (Instant Relay)
PORT = 8080
VLC_URL = "http://127.0.0.1:90/pc.mjpg"

class UnifiedServer(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        root = os.path.join(os.getcwd(), 'frontend')
        path = super().translate_path(path)
        rel = os.path.relpath(path, os.getcwd())
        return os.path.join(root, rel)

    def do_GET(self):
        if self.path.startswith('/stream/'):
            print(f"[*] Relaying Raw Stream -> {VLC_URL}")
            try:
                # Absolute transparent relay.
                req = urllib.request.Request(VLC_URL, headers={'User-Agent': 'Mozilla/5.0'})
                # We use a longer timeout for the initial connection to VLC (handling slow startup).
                with urllib.request.urlopen(req, timeout=10) as res:
                    self.send_response(200)
                    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=7b3cc56e5f51bb80bab3a30367a2d2dd')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    while True:
                        chunk = res.read(4096) # Use smaller chunks for lower latency
                        if not chunk: break
                        self.wfile.write(chunk)
                        self.wfile.flush() # CRITICAL: Push data immediately to browser
            except Exception as e:
                if "10053" not in str(e):
                    print(f"[!] Stream Error: {e}")
            return
        return super().do_GET()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == '__main__':
    print(f"\n--- ESPStreamer PC Server v5.0 (Instant Relay) ---")
    print(f"Serving at http://localhost:{PORT}")
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    server = ThreadedHTTPServer(('', PORT), UnifiedServer)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down server...")
        server.shutdown()
