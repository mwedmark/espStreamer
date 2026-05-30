Location: Inline code and docstrings throughout

Current State:
- Machine code sections have detailed but scattered inline comments
- No high-level README explaining chunked protocol specifics  
- Complex pointer arithmetic in `_build_streamer_code()` lacks overview diagrams
- VICE backend has minimal usage documentation (just basic method stubs)

Suggested Improvements:
1. Add protocol specification section to main README
2. Create architecture decision records (ADRs) for key design choices  
3. Implement Sphinx docstrings with type hints and parameter descriptions
4. Generate sequence diagrams showing data flow between backends/web client