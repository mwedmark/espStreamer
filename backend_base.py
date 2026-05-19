#!/usr/bin/env python3
"""
Abstract base class for streaming backends.
All backend implementations must inherit from this and implement all methods.
"""

from abc import ABC, abstractmethod
from typing import Dict, Tuple


class StreamingBackend(ABC):
    """Abstract interface for C64 streaming backends."""

    @abstractmethod
    def connect(self, port=None) -> bool:
        """Connect to the backend (serial port, network, etc).

        Args:
            port: Optional port/address identifier

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the backend.

        Returns:
            True if disconnect successful
        """
        pass

    @abstractmethod
    def send_viewer(self, viewer_data: bytes = None) -> bool:
        """Send the viewer/streamer program to the backend.

        Args:
            viewer_data: Optional custom viewer data. If None, use default.

        Returns:
            True if viewer sent successfully
        """
        pass

    @abstractmethod
    def stream_frame(
        self, mode: int, bg_color: int, bitmap: bytes, screen: bytes, color: bytes
    ) -> bool:
        """Stream a single frame to the C64.

        Args:
            mode: Display mode (0=multicolor, 1=hires, etc)
            bg_color: Background color index (0-15)
            bitmap: 8000 bytes of bitmap data
            screen: 1000 bytes of screen RAM
            color: 1000 bytes of color RAM

        Returns:
            True if frame sent successfully
        """
        pass

    @abstractmethod
    def reset(self) -> bool:
        """Reset the backend to menu/initial state.

        Returns:
            True if reset successful
        """
        pass

    @abstractmethod
    def reset_stream_buffers(self, reason: str = "manual") -> bool:
        """Reset/invalidate internal stream buffers to force full refresh.

        Args:
            reason: Human-readable reason for reset

        Returns:
            True if reset successful
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict:
        """Get current backend status.

        Returns:
            Dictionary with keys: 'connected', 'viewer_running', 'frame_count',
            'message', and any backend-specific fields
        """
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if backend is currently connected."""
        pass

    @property
    @abstractmethod
    def is_viewer_running(self) -> bool:
        """Check if viewer/streamer is running on the target device."""
        pass
