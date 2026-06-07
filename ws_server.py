#!/usr/bin/env python3
"""
Unified WebSocket Server
Handles WebSocket connections and routes to any backend implementation.
"""

import asyncio
import websockets
import json
import base64
import time
import collections
import http
from typing import Optional
from backend_base import StreamingBackend


class FPSTracker:
    def __init__(self, window_size=100):
        self.timestamps = collections.deque(maxlen=window_size)
        
    def tick(self):
        self.timestamps.append(time.perf_counter())
        
    @property
    def fps(self):
        if len(self.timestamps) < 2:
            return 0.0
        duration = self.timestamps[-1] - self.timestamps[0]
        if duration == 0:
            return 0.0
        return (len(self.timestamps) - 1) / duration


class UnifiedWebSocketServer:
    """Generic WebSocket server that works with any StreamingBackend."""

    def __init__(self, backend: StreamingBackend, name: str = "Streaming Backend"):
        self.backend = backend
        self.name = name
        self.clients = set()
        self.start_time = time.time()
        self.fps_tracker = FPSTracker()
        self.error_count = 0

    async def handle_client(self, websocket):
        """Handle a new client connection."""
        self.clients.add(websocket)
        print(f"Client connected: {websocket.remote_address}")

        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            print(f"Client disconnected: {websocket.remote_address}")
        finally:
            self.clients.remove(websocket)

    async def handle_message(self, websocket, message):
        """Route incoming messages to backend."""
        try:
            if isinstance(message, bytes):
                # Binary frame payload
                await self._handle_binary_frame(websocket, message)
                return

            # JSON command
            data = json.loads(message)
            command = data.get("command")

            if command == "connect":
                port = data.get("port", None)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None, self.backend.connect, port
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "connect",
                            "success": success,
                            "message": f"Connected to {self.name}"
                            if success
                            else f"Failed to connect to {self.name}",
                        }
                    )
                )

            elif command == "disconnect":
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.backend.disconnect)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "disconnect",
                            "success": success,
                            "message": "Disconnected",
                        }
                    )
                )

            elif command == "get_viewer":
                loop = asyncio.get_event_loop()

                def get_viewer_data():
                    try:
                        from streamer_machinecode import STREAMER_PRG
                        return base64.b64encode(STREAMER_PRG).decode('utf-8')
                    except ImportError:
                        return None

                encoded_prg = await loop.run_in_executor(None, get_viewer_data)
                if encoded_prg:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "response",
                                "command": "get_viewer",
                                "success": True,
                                "prg_data": encoded_prg,
                                "filename": "kungfu_viewer.prg",
                            }
                        )
                    )
                else:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "response",
                                "command": "get_viewer",
                                "success": False,
                                "message": "Viewer not available for this backend",
                            }
                        )
                    )

            elif command == "send_viewer":
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.backend.send_viewer)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "send_viewer",
                            "success": success,
                            "message": "Viewer sent successfully!"
                            if success
                            else "Failed to send viewer",
                        }
                    )
                )

            elif command == "status":
                status = self.backend.get_status()
                await websocket.send(
                    json.dumps(
                        {"type": "response", "command": "status", **status}
                    )
                )

            elif command == "reset":
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.backend.reset)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "reset",
                            "success": success,
                            "message": "Reset signal sent" if success else "Reset failed",
                        }
                    )
                )

            elif command == "reset_buffers":
                mode = data.get("mode", "unknown")
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None, self.backend.reset_stream_buffers, f"mode change to {mode}"
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "reset_buffers",
                            "success": success,
                            "message": "Stream buffers will be fully refreshed",
                        }
                    )
                )

            elif command == "stream_frame":
                await websocket.send(
                    json.dumps(
                        {
                            "type": "response",
                            "command": "stream_frame",
                            "success": False,
                            "message": "Please use binary streaming for frames",
                        }
                    )
                )

            else:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"Unknown command: {command}",
                        }
                    )
                )

        except Exception as e:
            print(f"Message handling failed: {e}")
            import traceback
            traceback.print_exc()
            await websocket.send(
                json.dumps({"type": "error", "message": str(e)})
            )

    async def _handle_binary_frame(self, websocket, message: bytes):
        """Handle binary frame streaming."""
        if len(message) < 10002:
            print(f"Binary payload too small: {len(message)}")
            return

        mode = message[0]
        bg_color = message[1]
        bitmap = message[2:8002]
        screen = message[8002:9002]
        color = message[9002:10002]

        if self.backend.is_viewer_running:
            self.fps_tracker.tick()
            try:
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None,
                    self.backend.stream_frame,
                    mode,
                    bg_color,
                    bitmap,
                    screen,
                    color,
                )
                if not success:
                    self.error_count += 1
            except Exception as e:
                self.error_count += 1
                raise e

            status = self.backend.get_status()
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "command": "stream_frame",
                        "success": success,
                        "frame_count": status.get("frame_count", 0),
                        "message": "Frame sent" if success else "Frame failed",
                    }
                )
            )
        else:
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "command": "stream_frame",
                        "success": False,
                        "message": "Viewer not running. Send viewer first.",
                    }
                )
            )

    def get_unified_status(self):
        backend_status = self.backend.get_status()
        uptime = time.time() - self.start_time
        viewer_running = backend_status.get("viewer_running", False) or backend_status.get("is_viewer_running", False)
        return {
            "server_name": self.name,
            "connected": backend_status.get("connected", False),
            "viewer_running": viewer_running,
            "fps": round(self.fps_tracker.fps, 2),
            "total_frames_sent": backend_status.get("frame_count", 0),
            "error_count": self.error_count,
            "uptime_seconds": round(uptime, 2),
            "backend_details": backend_status,
        }

    def get_prometheus_metrics(self):
        backend_status = self.backend.get_status()
        uptime = time.time() - self.start_time
        fps = self.fps_tracker.fps
        viewer_running = backend_status.get("viewer_running", False) or backend_status.get("is_viewer_running", False)
        
        lines = [
            "# HELP espstreamer_connected Connection status (1=connected, 0=disconnected)",
            "# TYPE espstreamer_connected gauge",
            f"espstreamer_connected {1 if backend_status.get('connected', False) else 0}",
            
            "# HELP espstreamer_viewer_running Viewer running status (1=running, 0=stopped)",
            "# TYPE espstreamer_viewer_running gauge",
            f"espstreamer_viewer_running {1 if viewer_running else 0}",
            
            "# HELP espstreamer_fps Current frames per second",
            "# TYPE espstreamer_fps gauge",
            f"espstreamer_fps {fps:.2f}",
            
            "# HELP espstreamer_frames_total Total frames sent",
            "# TYPE espstreamer_frames_total counter",
            f"espstreamer_frames_total {backend_status.get('frame_count', 0)}",
            
            "# HELP espstreamer_errors_total Total error count",
            "# TYPE espstreamer_errors_total counter",
            f"espstreamer_errors_total {self.error_count}",
            
            "# HELP espstreamer_uptime_seconds Server uptime in seconds",
            "# TYPE espstreamer_uptime_seconds counter",
            f"espstreamer_uptime_seconds {uptime:.2f}",
        ]
        
        bytes_sent = backend_status.get("bytes_sent", 0)
        lines.extend([
            "# HELP espstreamer_bytes_sent_total Total bytes sent to hardware",
            "# TYPE espstreamer_bytes_sent_total counter",
            f"espstreamer_bytes_sent_total {bytes_sent}",
        ])
            
        ratio_count = backend_status.get("ratio_count", 0)
        total_ratio = backend_status.get("total_ratio_sum", 0.0)
        if ratio_count > 0:
            avg_ratio = total_ratio / ratio_count
            lines.extend([
                "# HELP espstreamer_avg_compression_ratio Average delta compression ratio",
                "# TYPE espstreamer_avg_compression_ratio gauge",
                f"espstreamer_avg_compression_ratio {avg_ratio:.4f}",
            ])
            
        return "\n".join(lines) + "\n"

    def get_dashboard_html(self):
        return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ESPStreamer Performance Monitor</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #0b0d19;
      --card-bg: rgba(18, 22, 41, 0.7);
      --border: rgba(100, 140, 255, 0.15);
      --primary: #4f46e5;
      --primary-glow: rgba(79, 70, 229, 0.4);
      --success: #10b981;
      --success-glow: rgba(16, 185, 129, 0.4);
      --warning: #f59e0b;
      --error: #ef4444;
      --error-glow: rgba(239, 68, 68, 0.4);
      --text: #e2e8f0;
      --text-muted: #64748b;
    }
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      background: radial-gradient(circle at top, #14172e 0%, var(--bg) 100%);
      color: var(--text);
      font-family: 'Inter', sans-serif;
      min-height: 100vh;
      padding: 40px 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    header {
      width: 100%;
      max-width: 900px;
      margin-bottom: 30px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
    }
    h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(90deg, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .status-badge {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 600;
      background: rgba(0, 0, 0, 0.3);
      padding: 6px 14px;
      border-radius: 20px;
      border: 1px solid var(--border);
    }
    .indicator {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--text-muted);
      box-shadow: 0 0 8px var(--text-muted);
    }
    .indicator.active {
      background: var(--success);
      box-shadow: 0 0 12px var(--success-glow);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
      100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
    .grid {
      width: 100%;
      max-width: 900px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px;
      margin-bottom: 30px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      transition: all 0.3s ease;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      height: 160px;
    }
    .card:hover {
      border-color: rgba(100, 140, 255, 0.3);
      transform: translateY(-4px);
    }
    .card-title {
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: var(--text-muted);
    }
    .card-value {
      font-family: 'Outfit', sans-serif;
      font-size: 36px;
      font-weight: 800;
      margin-top: 10px;
      letter-spacing: -0.5px;
    }
    .card-value.fps {
      color: #6366f1;
      text-shadow: 0 0 20px rgba(99, 102, 241, 0.3);
    }
    .card-value.success {
      color: var(--success);
    }
    .card-value.error {
      color: var(--error);
    }
    .card-footer {
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 10px;
    }
    .progress-container {
      width: 100%;
      height: 6px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 3px;
      overflow: hidden;
      margin-top: 6px;
    }
    .progress-bar {
      height: 100%;
      width: 100%;
      background: linear-gradient(90deg, #7f00ff, #e100ff);
      border-radius: 3px;
      transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .chart-container {
      width: 100%;
      max-width: 900px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      margin-bottom: 30px;
      display: flex;
      flex-direction: column;
      gap: 15px;
    }
    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .chart-title {
      font-family: 'Outfit', sans-serif;
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
    }
    .details-panel {
      width: 100%;
      max-width: 900px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      backdrop-filter: blur(12px);
    }
    .details-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 15px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 10px;
    }
    .row {
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      font-size: 14px;
    }
    .row:not(:last-child) {
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .row-label {
      color: var(--text-muted);
    }
    .row-value {
      font-weight: 600;
    }
  </style>
</head>
<body>
  <header>
    <h1>ESPStreamer Performance</h1>
    <div class="status-badge">
      <div id="status-ind" class="indicator"></div>
      <span id="status-txt">Offline</span>
    </div>
  </header>
  
  <div class="grid">
    <div class="card">
      <div class="card-title">Framerate</div>
      <div class="card-value fps" id="val-fps">0.0 <span style="font-size: 16px; font-weight: 400; color: var(--text-muted);">FPS</span></div>
      <div class="card-footer" id="foot-fps">Stream inactive</div>
    </div>
    
    <div class="card">
      <div class="card-title">Bandwidth</div>
      <div class="card-value" id="val-bytes">0.00 <span style="font-size: 16px; font-weight: 400; color: var(--text-muted);">MB</span></div>
      <div class="card-footer" id="foot-bytes">Total bytes written</div>
    </div>
    
    <div class="card">
      <div class="card-title">Compression</div>
      <div class="card-value" id="val-ratio">100%</div>
      <div class="progress-container">
        <div id="compressionBar" class="progress-bar"></div>
      </div>
      <div class="card-footer" id="foot-ratio">Average size ratio</div>
    </div>
    
    <div class="card">
      <div class="card-title">System Health</div>
      <div class="card-value success" id="val-health">OK</div>
      <div class="card-footer" id="foot-errors">0 errors encountered</div>
    </div>
  </div>

  <div class="chart-container">
    <div class="chart-header">
      <div class="chart-title">Real-Time Performance</div>
    </div>
    <div style="position: relative; height: 260px; width: 100%;">
      <canvas id="performanceChart"></canvas>
    </div>
  </div>
  
  <div class="details-panel">
    <div class="details-title">System Status</div>
    <div class="row">
      <div class="row-label">Server Name</div>
      <div class="row-value" id="det-name">-</div>
    </div>
    <div class="row">
      <div class="row-label">Backend Engine</div>
      <div class="row-value" id="det-backend">-</div>
    </div>
    <div class="row">
      <div class="row-label">Port / Connection Target</div>
      <div class="row-value" id="det-target">-</div>
    </div>
    <div class="row">
      <div class="row-label">Uptime</div>
      <div class="row-value" id="det-uptime">-</div>
    </div>
    <div class="row">
      <div class="row-label">Total Frames Processed</div>
      <div class="row-value" id="det-frames">0</div>
    </div>
  </div>

  <script>
    // Setup Chart
    let chart = null;
    let chartData = null;
    if (typeof Chart !== 'undefined') {
      const ctx = document.getElementById('performanceChart').getContext('2d');
      const maxDataPoints = 30;
      
      chartData = {
        labels: Array(maxDataPoints).fill(''),
        datasets: [
          {
            label: 'FPS (Frames/sec)',
            data: Array(maxDataPoints).fill(0),
            borderColor: '#6366f1',
            backgroundColor: 'rgba(99, 102, 241, 0.05)',
            borderWidth: 3,
            pointRadius: 0,
            tension: 0.4,
            fill: true,
            yAxisID: 'y'
          },
          {
            label: 'Throughput (KB/s)',
            data: Array(maxDataPoints).fill(0),
            borderColor: '#a855f7',
            backgroundColor: 'rgba(168, 85, 247, 0.05)',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.4,
            fill: true,
            yAxisID: 'y1'
          }
        ]
      };

      const config = {
        type: 'line',
        data: chartData,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              labels: {
                color: '#94a3b8',
                font: { family: 'Inter', size: 12 }
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { display: false }
            },
            y: {
              type: 'linear',
              display: true,
              position: 'left',
              min: 0,
              max: 60,
              grid: { color: 'rgba(255, 255, 255, 0.05)' },
              ticks: { color: '#94a3b8', font: { family: 'Inter' } }
            },
            y1: {
              type: 'linear',
              display: true,
              position: 'right',
              min: 0,
              grid: { drawOnChartArea: false },
              ticks: { color: '#94a3b8', font: { family: 'Inter' } }
            }
          }
        }
      };

      chart = new Chart(ctx, config);
    } else {
      // Hide chart container if Chart.js is not loaded
      const chartContainer = document.querySelector('.chart-container');
      if (chartContainer) {
        chartContainer.style.display = 'none';
      }
    }

    function formatBytes(bytes) {
      if (bytes === 0) return '0.00 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    function formatUptime(seconds) {
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = Math.floor(seconds % 60);
      return [
        h.toString().padStart(2, '0'),
        m.toString().padStart(2, '0'),
        s.toString().padStart(2, '0')
      ].join(':');
    }

    let lastBytesSent = 0;
    let lastTime = Date.now();
    
    async function updateMetrics() {
      try {
        const res = await fetch(window.location.origin + '/status');
        if (!res.ok) throw new Error('Status fetch failed');
        const data = await res.json();
        
        // Status indicator
        const ind = document.getElementById('status-ind');
        const txt = document.getElementById('status-txt');
        if (data.connected) {
          ind.className = 'indicator active';
          txt.textContent = data.viewer_running ? 'Streaming' : 'Connected';
        } else {
          ind.className = 'indicator';
          txt.textContent = 'Disconnected';
        }
        
        // Cards
        document.getElementById('val-fps').innerHTML = data.fps.toFixed(1) + ' <span style="font-size: 16px; font-weight: 400; color: var(--text-muted);">FPS</span>';
        document.getElementById('foot-fps').textContent = data.viewer_running ? 'Active stream session' : 'Session idle';
        
        const bytes = data.backend_details.bytes_sent || 0;
        document.getElementById('val-bytes').innerHTML = formatBytes(bytes);
        
        // Calculate Throughput
        const now = Date.now();
        const dt = (now - lastTime) / 1000;
        let speedKBps = 0;
        if (dt > 0 && lastBytesSent > 0 && bytes >= lastBytesSent) {
          speedKBps = ((bytes - lastBytesSent) / 1024) / dt;
        }
        lastBytesSent = bytes;
        lastTime = now;
        document.getElementById('foot-bytes').textContent = `${speedKBps.toFixed(1)} KB/s throughput`;
        
        // Compression
        const ratioCount = data.backend_details.ratio_count || 0;
        const totalRatio = data.backend_details.total_ratio_sum || 0;
        let ratioPercent = 100;
        if (ratioCount > 0) {
          ratioPercent = (totalRatio / ratioCount) * 100;
          document.getElementById('val-ratio').textContent = ratioPercent.toFixed(1) + '%';
          document.getElementById('foot-ratio').textContent = `Deltas compressed to ${ratioPercent.toFixed(1)}%`;
        } else {
          document.getElementById('val-ratio').textContent = '100%';
          document.getElementById('foot-ratio').textContent = 'Full frames only';
        }

        const ratioBar = document.getElementById('compressionBar');
        if (ratioBar) {
          ratioBar.style.width = `${ratioPercent}%`;
          if (ratioPercent < 40) {
            ratioBar.style.background = 'linear-gradient(90deg, #10b981, #38ef7d)';
          } else if (ratioPercent < 80) {
            ratioBar.style.background = 'linear-gradient(90deg, #6366f1, #a855f7)';
          } else {
            ratioBar.style.background = 'linear-gradient(90deg, #f59e0b, #ef4444)';
          }
        }
        
        // Health
        const errors = data.error_count || 0;
        const health = document.getElementById('val-health');
        if (errors === 0) {
          health.textContent = 'OK';
          health.className = 'card-value success';
        } else {
          health.textContent = 'WARN';
          health.className = 'card-value error';
        }
        document.getElementById('foot-errors').textContent = `${errors} error${errors !== 1 ? 's' : ''} encountered`;
        
        // Details
        document.getElementById('det-name').textContent = data.server_name;
        document.getElementById('det-backend').textContent = data.backend_details.backend_name || 'Generic';
        document.getElementById('det-target').textContent = data.backend_details.port || 'localhost';
        document.getElementById('det-uptime').textContent = formatUptime(data.uptime_seconds);
        document.getElementById('det-frames').textContent = data.total_frames_sent;

        // Chart Update
        if (chart && typeof Chart !== 'undefined' && chartData) {
          chartData.datasets[0].data.shift();
          chartData.datasets[0].data.push(data.fps);
          chartData.datasets[1].data.shift();
          chartData.datasets[1].data.push(speedKBps);
          
          // Adjust Throughput max dynamically
          let maxThroughput = Math.max(...chartData.datasets[1].data, 10);
          chart.options.scales.y1.max = Math.ceil(maxThroughput * 1.2);
          
          chart.update('none');
        }
        
      } catch (err) {
        console.error(err);
        document.getElementById('status-ind').className = 'indicator';
        document.getElementById('status-txt').textContent = 'Error';
      }
    }
    
    updateMetrics();
    setInterval(updateMetrics, 1000);
  </script>
</body>
</html>
"""

    async def process_request(self, *args):
        """Intercept HTTP requests to serve status or metrics."""
        is_new_signature = False
        connection = None
        request = None
        path_str = None

        try:
            if len(args) >= 2:
                if isinstance(args[0], str):
                    # Old signature: (path, request_headers)
                    path_str = args[0]
                    is_new_signature = False
                else:
                    # New signature: (connection, request)
                    connection = args[0]
                    request = args[1]
                    path_str = request.path
                    is_new_signature = True
            elif len(args) == 1:
                arg = args[0]
                if isinstance(arg, str):
                    path_str = arg
                elif hasattr(arg, "path") and isinstance(arg.path, str):
                    path_str = arg.path
                    request = arg
        except Exception as e:
            print(f"Error parsing process_request arguments: {e}")
            import traceback
            traceback.print_exc()
            return None

        if path_str is None:
            return None

        path_only = path_str.split('?')[0]
        if path_only not in ("/status", "/metrics", "/dashboard"):
            return None

        try:
            if path_only == "/status":
                status = self.get_unified_status()
                response_body_str = json.dumps(status, indent=2)
                content_type = "application/json"
            elif path_only == "/metrics":
                response_body_str = self.get_prometheus_metrics()
                content_type = "text/plain; version=0.0.4; charset=utf-8"
            elif path_only == "/dashboard":
                response_body_str = self.get_dashboard_html()
                content_type = "text/html; charset=utf-8"

            if is_new_signature and connection is not None:
                # websockets >= 14 expects a Response object returned by connection.respond()
                response = connection.respond(200, response_body_str)
                # Safely delete default headers to avoid duplicates
                if "Content-Type" in response.headers:
                    del response.headers["Content-Type"]
                if "Content-Length" in response.headers:
                    del response.headers["Content-Length"]
                if "Access-Control-Allow-Origin" in response.headers:
                    del response.headers["Access-Control-Allow-Origin"]
                response.headers["Content-Type"] = content_type
                response.headers["Content-Length"] = str(len(response.body))
                response.headers["Access-Control-Allow-Origin"] = "*"
                return response
            else:
                # Older websockets expects a 3-tuple: (status, headers, body_bytes)
                response_body_bytes = response_body_str.encode('utf-8')
                response_headers = [
                    ("Content-Type", content_type),
                    ("Content-Length", str(len(response_body_bytes))),
                    ("Access-Control-Allow-Origin", "*"),
                ]
                return 200, response_headers, response_body_bytes

        except Exception as e:
            print(f"Error handling HTTP request for {path_only}: {e}")
            import traceback
            traceback.print_exc()

            # Internal server error fallback
            err_msg = f"Internal Server Error: {e}\n"
            if is_new_signature and connection is not None:
                response = connection.respond(500, err_msg)
                if "Content-Type" in response.headers:
                    del response.headers["Content-Type"]
                response.headers["Content-Type"] = "text/plain; charset=utf-8"
                return response
            else:
                err_bytes = err_msg.encode('utf-8')
                return 500, [("Content-Type", "text/plain; charset=utf-8")], err_bytes
            
        return None


async def start_server(
    backend: StreamingBackend,
    backend_name: str,
    host: str = "localhost",
    port: int = 8765,
):
    """Start the unified WebSocket server."""
    server = UnifiedWebSocketServer(backend, backend_name)

    print("=" * 60)
    print(f"Unified WebSocket Server - {backend_name}")
    print("=" * 60)
    print(f"WebSocket server on ws://{host}:{port}")
    print()

    async with websockets.serve(server.handle_client, host, port, process_request=server.process_request):
        print("Server running. Press Ctrl+C to stop.")
        await asyncio.Future()


def run_server(
    backend: StreamingBackend,
    backend_name: str = "Backend",
    host: str = "localhost",
    port: int = 8765,
):
    """Convenience function to run server."""
    try:
        asyncio.run(start_server(backend, backend_name, host, port))
    except KeyboardInterrupt:
        print("\nServer stopped.")
