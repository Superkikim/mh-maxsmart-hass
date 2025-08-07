#!/usr/bin/env python3
"""
Test script for maxsmart 2.0.5 to understand callback behavior
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test device IP (replace with your device IP)
TEST_IP = "172.30.47.77"

class CallbackTester:
    """Test callback behavior of maxsmart 2.0.5"""
    
    def __init__(self):
        self.callback_count = 0
        self.callback_data = []
        
    async def test_callback(self, data: Dict[str, Any]) -> None:
        """Callback function to test what maxsmart sends"""
        self.callback_count += 1
        timestamp = time.time()
        
        logger.info(f"🔔 CALLBACK #{self.callback_count} - Timestamp: {timestamp}")
        logger.info(f"🔔 CALLBACK DATA: {data}")
        logger.info(f"🔔 CALLBACK TYPE: {type(data)}")
        
        if data:
            logger.info(f"🔔 CALLBACK KEYS: {list(data.keys())}")
            for key, value in data.items():
                logger.info(f"🔔   {key}: {value} (type: {type(value)})")
        else:
            logger.warning(f"🔔 CALLBACK EMPTY OR NONE!")
            
        # Store for analysis
        self.callback_data.append({
            'timestamp': timestamp,
            'data': data,
            'count': self.callback_count
        })

async def test_maxsmart_discovery():
    """Test maxsmart discovery"""
    logger.info("=== TESTING MAXSMART 2.0.5 DISCOVERY ===")
    
    try:
        from maxsmart import MaxSmartDiscovery
        
        logger.info("🔍 Starting discovery...")
        devices = await MaxSmartDiscovery.discover_maxsmart()
        
        logger.info(f"🔍 Found {len(devices)} devices")
        
        if devices:
            device = devices[0]
            logger.info(f"🔍 First device: {device}")
            logger.info(f"🔍 Device keys: {list(device.keys())}")
            return device
        else:
            logger.error("❌ No devices found!")
            return None
            
    except Exception as e:
        logger.error(f"❌ Discovery failed: {e}")
        return None

async def test_maxsmart_device_direct():
    """Test direct device connection"""
    logger.info("=== TESTING MAXSMART 2.0.5 DEVICE DIRECT ===")
    
    try:
        from maxsmart import MaxSmartDevice
        
        logger.info(f"🔌 Connecting to device at {TEST_IP}")
        device = MaxSmartDevice(TEST_IP)
        
        logger.info("🔌 Initializing device...")
        await device.initialize_device()
        
        logger.info("🔌 Device initialized successfully")
        logger.info(f"🔌 Device name: {getattr(device, 'name', 'Unknown')}")
        logger.info(f"🔌 Device version: {getattr(device, 'version', 'Unknown')}")
        
        return device
        
    except Exception as e:
        logger.error(f"❌ Device connection failed: {e}")
        return None

async def test_device_get_data(device):
    """Test device.get_data() method"""
    logger.info("=== TESTING DEVICE.GET_DATA() ===")
    
    try:
        logger.info("📊 Calling device.get_data()...")
        data = await device.get_data()
        
        logger.info(f"📊 get_data() returned: {data}")
        logger.info(f"📊 Data type: {type(data)}")
        
        if data:
            logger.info(f"📊 Data keys: {list(data.keys())}")
            for key, value in data.items():
                logger.info(f"📊   {key}: {value} (type: {type(value)})")
        else:
            logger.warning("📊 get_data() returned empty or None!")
            
        return data
        
    except Exception as e:
        logger.error(f"❌ get_data() failed: {e}")
        return None

async def test_adaptive_polling(device):
    """Test adaptive polling with callback"""
    logger.info("=== TESTING ADAPTIVE POLLING WITH CALLBACK ===")
    
    callback_tester = CallbackTester()
    
    try:
        logger.info("🔄 Starting adaptive polling...")
        await device.start_adaptive_polling(enable_burst=True)
        
        logger.info("🔄 Registering callback...")
        device.register_poll_callback("test_callback", callback_tester.test_callback)
        
        logger.info("🔄 Waiting 30 seconds for callbacks...")
        await asyncio.sleep(30)
        
        logger.info(f"🔄 Received {callback_tester.callback_count} callbacks")
        
        # Analyze callback data
        if callback_tester.callback_data:
            logger.info("📈 CALLBACK ANALYSIS:")
            for i, cb_data in enumerate(callback_tester.callback_data):
                logger.info(f"📈   Callback {i+1}: {cb_data['data']}")
        else:
            logger.warning("📈 No callback data received!")
            
        return callback_tester.callback_data
        
    except Exception as e:
        logger.error(f"❌ Adaptive polling test failed: {e}")
        return []

async def main():
    """Main test function"""
    logger.info("🚀 Starting maxsmart 2.0.5 comprehensive test")
    
    # Test 1: Discovery
    discovered_device = await test_maxsmart_discovery()
    
    # Test 2: Direct device connection
    device = await test_maxsmart_device_direct()
    
    if not device:
        logger.error("❌ Cannot continue without device connection")
        return
    
    # Test 3: get_data() method
    data = await test_device_get_data(device)
    
    # Test 4: Adaptive polling with callback
    callback_data = await test_adaptive_polling(device)
    
    # Final analysis
    logger.info("=== FINAL ANALYSIS ===")
    logger.info(f"✅ Discovery worked: {discovered_device is not None}")
    logger.info(f"✅ Device connection worked: {device is not None}")
    logger.info(f"✅ get_data() worked: {data is not None}")
    logger.info(f"✅ Callbacks received: {len(callback_data)}")
    
    if callback_data:
        logger.info("📊 CALLBACK SUMMARY:")
        for i, cb in enumerate(callback_data):
            logger.info(f"📊   #{i+1}: {cb['data']}")
    
    # Cleanup
    try:
        await device.close()
        logger.info("🧹 Device closed successfully")
    except:
        pass

if __name__ == "__main__":
    asyncio.run(main())
