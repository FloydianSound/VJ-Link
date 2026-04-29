import threading
import time
import numpy as np
from pathlib import Path
import os
from .ndi_6_engine import NDI6Engine

class NDIManager:
    def __init__(self):
        self.engine = None
        self._finder_ptr = None
        self._recv_ptr = None
        
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.thread = None
        
        # No more defaults - user must select from the list
        self.source_name = "" 
        self.rig_ip = "10.0.0.20"
        
        self.fps = 0
        self._frame_count = 0
        self._last_fps_time = time.time()
        self.resolution = (0, 0)
        self.status = "Idle"
        
        self.discovered_sources = []
        self._last_discovery_time = 0
        self.lib_path = ""
        
        # Unique Frame Tracking (v1.6.2)
        self.last_timestamp = -1

    def initialize_engine(self, lib_path):
        if self.engine and self.lib_path == lib_path:
            return True
        self.lib_path = lib_path
        
        # Check standard locations
        actual_path = lib_path
        if not actual_path or not os.path.exists(actual_path):
            standard_paths = [
                "/usr/lib/libndi.so",
                "/usr/lib/libndi.so.6",
                "/usr/local/lib/libndi.so",
                "/usr/lib/x86_64-linux-gnu/libndi.so",
                "/usr/lib/x86_64-linux-gnu/libndi.so.6"
            ]
            for p in standard_paths:
                if os.path.exists(p):
                    actual_path = p
                    break
                    
        if not actual_path or not os.path.exists(actual_path):
            self.status = "Error: libndi.so not found"
            return False

        try:
            self.engine = NDI6Engine(actual_path)
            self.status = "Engine Loaded"
            return True
        except Exception as e:
            print(f"VJ-Link: Engine Init Error - {e}")
            self.status = f"Error: SDK Init Fail"
            return False

    @property
    def finder(self):
        # Meticulously using _finder_ptr to avoid previous AttributeError
        if self.engine and self._finder_ptr is None:
            self._finder_ptr = self.engine.create_finder()
        return self._finder_ptr

    def find_sources(self, force=False):
        if not self.engine: return []
        
        now = time.time()
        if force:
            if self._finder_ptr:
                self.engine.lib.NDIlib_find_destroy(self._finder_ptr)
                self._finder_ptr = None
            
        if force or (now - self._last_discovery_time > 2.0):
            ptr = self.finder
            if ptr:
                self.engine.lib.NDIlib_find_wait_for_sources(ptr, 100)
                source_dicts = self.engine.get_sources(ptr)
                self.discovered_sources = source_dicts
                self._last_discovery_time = now
                
        return [s["name"] for s in self.discovered_sources]

    def start(self, source_name):
        if not self.engine or self.running:
            return
        self.source_name = source_name if source_name != "NONE" else ""
        self.running = True
        self.status = "Connecting..."
        self.last_timestamp = -1 # Reset tracking
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.status = "Stopping..."
        if self.thread:
            self.thread.join(timeout=0.5)
        
        if self.engine and self._recv_ptr:
            self.engine.lib.NDIlib_recv_destroy(self._recv_ptr)
            self._recv_ptr = None
            
        self.latest_frame = None
        self.resolution = (0, 0)
        self.fps = 0
        self.status = "Idle"

    def _update_loop(self):
        print(f"VJ-Link: Direct Engine thread started for '{self.source_name}'")
        
        while self.running:
            source_struct = None
            target_lower = self.source_name.lower()
            
            for i in range(100):
                if not self.running: return
                self.find_sources()
                for s in self.discovered_sources:
                    if self.source_name == s["name"]: 
                        source_struct = s["raw_struct"]
                        print(f"VJ-Link: MATCH FOUND - {s['name']} ({s['address']})")
                        break
                if source_struct: break
                time.sleep(0.1)
            
            if not source_struct:
                self.status = "Error: Source Not Found"
                time.sleep(1.0)
                continue 

            # 2. CREATE RECEIVER
            try:
                self._recv_ptr = self.engine.create_receiver(source_struct)
                self.status = "Waiting for Frames..."
                print("VJ-Link: Receiver created. Awaiting first frame...")
            except Exception as e:
                self.status = "Error: Receiver Fail"
                time.sleep(1.0)
                continue

            # 3. CAPTURE LOOP (v1.6.2 High-Performance Background Thread)
            while self.running:
                try:
                    frame, res, ts = self.engine.capture_video(self._recv_ptr, timeout_ms=16)
                    
                    if frame is None and res == "ERROR":
                        self.status = "Link Lost - Reconnecting..."
                        if self._recv_ptr:
                            self.engine.lib.NDIlib_recv_destroy(self._recv_ptr)
                            self._recv_ptr = None
                        break 
                        
                    if frame is not None:
                        # Only update if this is a NEW frame from the rig
                        if ts > self.last_timestamp:
                            with self.frame_lock:
                                self.latest_frame = frame
                                self.resolution = res
                            self.status = "Streaming"
                            
                            self._frame_count += 1
                            self.last_timestamp = ts
                        
                        # Calculate FPS stats
                        now = time.time()
                        if now - self._last_fps_time >= 1.0:
                            self.fps = self._frame_count / (now - self._last_fps_time)
                            self._frame_count = 0
                            self._last_fps_time = now
                    else:
                        if self.status != "Streaming":
                            self.status = "Waiting for Data..."
                        time.sleep(0.001)
                except Exception as e:
                    print(f"VJ-Link Capture Error: {e}")
                    time.sleep(0.1)
        
        # Final cleanup on exit
        if self.engine and self._recv_ptr:
            self.engine.lib.NDIlib_recv_destroy(self._recv_ptr)
            self._recv_ptr = None
            
        print("VJ-Link: Direct Engine thread exiting.")

    def get_latest_frame(self):
        with self.frame_lock:
            return self.latest_frame, self.resolution, self.fps
