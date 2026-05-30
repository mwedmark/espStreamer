Location: page_records() and delta_payload construction in stream_frame()

Current State:
- 256-byte chunk granularity forces minimum 256-byte delta payloads even for single-pixel changes  
- No threshold optimization (sending full frame when <10% changed would be slower)
- Delta records stored but not compared against previous frame deltas  
- Missing run-length encoding within same-color regions

Suggested Improvements:
1. Add configurable chunk granularity (e.g., 64-byte default instead of 256)
2. Implement delta threshold heuristic (<5% change → full refresh, >90% → delta)  
3. Compare against historical deltas to avoid redundant full transmissions
4. Consider adaptive payload sizing based on screen motion patterns