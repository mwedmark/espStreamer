Location: Chunk transfer loops and WebSocket I/O handling

Current State:
- Python `while offset < len(payload)` loop runs synchronously in async handler  
- Multiple `self.ser.read()`/`self.ser.write()` calls per frame (high syscall overhead)
- No buffer pooling for serial I/O operations
- Thread locking on every frame adds contention in multi-client scenarios

Suggested Improvements:
1. Use bytearray views or memoryview for zero-copy operations
2. Batch serial I/O calls using larger buffer transfers when possible  
3. Implement connection pool pattern for serial ports
4. Move heavy delta computation to worker thread or use multiprocessing
5. Consider asyncio.to_thread() for blocking serial operations instead of RunInExecutor