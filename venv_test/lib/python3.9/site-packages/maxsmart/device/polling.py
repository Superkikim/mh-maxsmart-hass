# maxsmart/device/polling.py

import asyncio
import time
import logging
from typing import Optional, Callable, Dict, Any
from enum import Enum

class PollingMode(Enum):
    """Polling mode states."""
    NORMAL = "normal"          # 5s intervals
    BURST = "burst"            # 2s intervals after commands
    STOPPED = "stopped"        # No polling


class AdaptivePollingMixin:
    """
    Mixin class providing adaptive polling functionality that mimics MaxSmart app behavior.
    
    Polling Strategy (based on Wireshark analysis):
    - Normal mode: cmd=511 every 5 seconds
    - After commands: cmd=511 every 2 seconds for 3-4 cycles  
    - Then return to normal 5s polling
    """
    
    # Polling configuration based on app analysis
    NORMAL_INTERVAL = 5.0      # seconds - normal polling
    BURST_INTERVAL = 2.0       # seconds - after commands
    BURST_CYCLES = 4           # number of burst cycles
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Polling state
        self._polling_task: Optional[asyncio.Task] = None
        self._polling_mode = PollingMode.STOPPED
        self._burst_cycles_remaining = 0
        self._last_poll_time = 0
        self._poll_callbacks: Dict[str, Callable] = {}
        self._polling_enabled = False
        
        # Statistics
        self._poll_count = 0
        self._last_poll_data = None
        
    async def start_adaptive_polling(self, enable_burst=True):
        """
        Start adaptive polling with MaxSmart app behavior.
        
        Args:
            enable_burst (bool): Enable burst mode after commands
        """
        if self._polling_task and not self._polling_task.done():
            logging.debug(f"Polling already running for device {self.ip}")
            return
            
        self._polling_enabled = True
        self._polling_mode = PollingMode.NORMAL
        self._burst_cycles_remaining = 0
        
        # Start the polling loop
        self._polling_task = asyncio.create_task(self._polling_loop(enable_burst))
        logging.debug(f"Started adaptive polling for device {self.ip}")
        
    async def stop_adaptive_polling(self):
        """Stop adaptive polling gracefully."""
        self._polling_enabled = False
        self._polling_mode = PollingMode.STOPPED
        
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
            
        logging.info(f"Stopped adaptive polling for device {self.ip}")
        
    def trigger_burst_mode(self):
        """
        Trigger burst polling mode after a command execution.
        This mimics the MaxSmart app behavior after on/off commands.
        """
        if self._polling_enabled and self._polling_mode == PollingMode.NORMAL:
            self._polling_mode = PollingMode.BURST
            self._burst_cycles_remaining = self.BURST_CYCLES
            logging.debug(f"Triggered burst mode for device {self.ip} ({self.BURST_CYCLES} cycles)")
            
    def register_poll_callback(self, name: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Register a callback to be called when poll data is received.
        
        Args:
            name (str): Unique name for the callback
            callback (Callable): Function to call with poll data
        """
        self._poll_callbacks[name] = callback
        logging.debug(f"Registered poll callback '{name}' for device {self.ip}")
        
    def unregister_poll_callback(self, name: str):
        """Remove a poll callback."""
        if name in self._poll_callbacks:
            del self._poll_callbacks[name]
            logging.debug(f"Unregistered poll callback '{name}' for device {self.ip}")
            
    async def _polling_loop(self, enable_burst: bool):
        """
        Main polling loop implementing adaptive behavior.
        
        Args:
            enable_burst (bool): Whether to use burst mode
        """
        try:
            while self._polling_enabled:
                start_time = time.time()
                
                try:
                    # Get device data (cmd=511 equivalent)
                    poll_data = await self._execute_poll()
                    
                    # Update statistics
                    self._poll_count += 1
                    self._last_poll_time = start_time
                    self._last_poll_data = poll_data
                    
                    # Notify callbacks
                    await self._notify_callbacks(poll_data)
                    
                    # Log polling activity
                    mode_info = f"{self._polling_mode.value}"
                    if self._polling_mode == PollingMode.BURST:
                        mode_info += f" ({self._burst_cycles_remaining} cycles left)"
                        
                    logging.debug(f"Poll #{self._poll_count} for {self.ip} - Mode: {mode_info}")
                    
                except Exception as e:
                    logging.warning(f"Polling error for device {self.ip}: {e}")
                    # Continue polling even if one poll fails
                    
                # Determine next interval based on mode
                if enable_burst and self._polling_mode == PollingMode.BURST:
                    interval = self.BURST_INTERVAL
                    self._burst_cycles_remaining -= 1
                    
                    # Switch back to normal mode after burst cycles
                    if self._burst_cycles_remaining <= 0:
                        self._polling_mode = PollingMode.NORMAL
                        logging.debug(f"Burst mode finished for device {self.ip}, returning to normal")
                else:
                    interval = self.NORMAL_INTERVAL
                    
                # Calculate actual sleep time accounting for poll execution time
                execution_time = time.time() - start_time
                sleep_time = max(0, interval - execution_time)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
        except asyncio.CancelledError:
            logging.debug(f"Polling loop cancelled for device {self.ip}")
            raise
        except Exception as e:
            logging.error(f"Polling loop error for device {self.ip}: {e}")
            raise
            
    async def _execute_poll(self) -> Dict[str, Any]:
        """
        Execute a single poll operation (equivalent to cmd=511).
        
        Returns:
            Dict containing device data with timestamp
        """
        try:
            # Get device data (switch states, wattage, etc.)
            device_data = await self.get_data()
            
            # Add metadata
            poll_result = {
                "timestamp": time.time(),
                "poll_count": self._poll_count,
                "mode": self._polling_mode.value,
                "device_data": device_data
            }
            
            return poll_result
            
        except Exception as e:
            # Re-raise with context
            raise Exception(f"Poll execution failed: {e}")
            
    async def _notify_callbacks(self, poll_data: Dict[str, Any]):
        """Notify all registered callbacks with poll data."""
        if not self._poll_callbacks:
            return
            
        # Call callbacks sequentially for safety
        for name, callback in self._poll_callbacks.items():
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(poll_data)
                else:
                    # Run sync callback directly (they should be fast)
                    callback(poll_data)
            except Exception as e:
                logging.warning(f"Error in callback '{name}': {e}")
                continue
                
    # Enhanced command methods that trigger burst mode
    async def turn_on(self, port):
        """Turn on a port and trigger burst polling."""
        result = await super().turn_on(port)
        self.trigger_burst_mode()
        return result
        
    async def turn_off(self, port):
        """Turn off a port and trigger burst polling.""" 
        result = await super().turn_off(port)
        self.trigger_burst_mode()
        return result
        
    async def change_port_name(self, port, new_name):
        """Change port name and trigger burst polling."""
        result = await super().change_port_name(port, new_name)
        self.trigger_burst_mode()
        return result
        
    # Polling status and statistics
    @property
    def is_polling(self) -> bool:
        """Check if polling is currently active."""
        return (self._polling_task is not None and 
                not self._polling_task.done() and 
                self._polling_enabled)
                
    @property
    def polling_stats(self) -> Dict[str, Any]:
        """Get polling statistics."""
        return {
            "enabled": self._polling_enabled,
            "mode": self._polling_mode.value,
            "poll_count": self._poll_count,
            "last_poll_time": self._last_poll_time,
            "burst_cycles_remaining": self._burst_cycles_remaining,
            "callback_count": len(self._poll_callbacks),
            "normal_interval": self.NORMAL_INTERVAL,
            "burst_interval": self.BURST_INTERVAL
        }
        
    async def get_latest_poll_data(self) -> Optional[Dict[str, Any]]:
        """Get the most recent poll data."""
        return self._last_poll_data
        
    async def force_poll(self) -> Dict[str, Any]:
        """Force an immediate poll outside of the normal cycle."""
        logging.debug(f"Force poll requested for device {self.ip}")
        return await self._execute_poll()
        
    # Cleanup
    async def close(self):
        """Enhanced close method that stops polling."""
        await self.stop_adaptive_polling()
        if hasattr(super(), 'close'):
            await super().close()