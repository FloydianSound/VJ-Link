import ctypes
import numpy as np
import os

# --- NDI SDK CONSTANTS ---
NDILIB_FRAME_TYPE_NONE = 0
NDILIB_FRAME_TYPE_VIDEO = 1
NDILIB_FRAME_TYPE_AUDIO = 2
NDILIB_FRAME_TYPE_METADATA = 3
NDILIB_FRAME_TYPE_ERROR = 4
NDILIB_FRAME_TYPE_STATUS_CHANGE = 100
NDILIB_FRAME_TYPE_SOURCE_CHANGE = 101

NDILIB_FOURCC_VIDEO_TYPE_UYVY = 1498831189
NDILIB_FOURCC_VIDEO_TYPE_BGRA = 1095910722
NDILIB_FOURCC_VIDEO_TYPE_BGRX = 1481787202
NDILIB_FOURCC_VIDEO_TYPE_RGBA = 1095911250
NDILIB_FOURCC_VIDEO_TYPE_RGBX = 1481787714

NDILIB_RECV_BANDWIDTH_LOWEST = 0
NDILIB_RECV_BANDWIDTH_HIGHEST = 100

NDILIB_RECV_COLOR_FORMAT_BGRX_BGRA = 0
NDILIB_RECV_COLOR_FORMAT_UYVY_BGRA = 1
NDILIB_RECV_COLOR_FORMAT_RGBX_RGBA = 2
NDILIB_RECV_COLOR_FORMAT_UYVY_RGBA = 3
NDILIB_RECV_COLOR_FORMAT_FASTEST = 100
NDILIB_RECV_COLOR_FORMAT_BEST = 101

# --- NDI SDK STRUCTS ---

class NDIlib_source_t(ctypes.Structure):
    _fields_ = [
        ("p_ndi_name", ctypes.c_char_p),
        ("p_url_address", ctypes.c_char_p)
    ]

class NDIlib_find_create_t(ctypes.Structure):
    _fields_ = [
        ("show_local_sources", ctypes.c_bool),
        ("p_groups", ctypes.c_char_p),
        ("p_extra_ips", ctypes.c_char_p)
    ]

class NDIlib_video_frame_v2_t(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_int),
        ("yres", ctypes.c_int),
        ("FourCC", ctypes.c_int),
        ("frame_rate_N", ctypes.c_int),
        ("frame_rate_D", ctypes.c_int),
        ("picture_aspect_ratio", ctypes.c_float),
        ("frame_format_type", ctypes.c_int),
        ("timecode", ctypes.c_int64),
        ("p_data", ctypes.POINTER(ctypes.c_ubyte)),
        ("line_stride_in_bytes", ctypes.c_int),
        ("p_metadata", ctypes.c_char_p),
        ("timestamp", ctypes.c_int64)
    ]

class NDIlib_recv_create_v3_t(ctypes.Structure):
    _fields_ = [
        ("source_to_connect_to", NDIlib_source_t),
        ("color_format", ctypes.c_int),
        ("bandwidth", ctypes.c_int),
        ("allow_video_fields", ctypes.c_bool),
        ("p_ndi_recv_name", ctypes.c_char_p)
    ]

# --- THE ENGINE ---

class NDI6Engine:
    def __init__(self, lib_path):
        self.lib = ctypes.CDLL(lib_path)
        self._setup_functions()
        self._buffers = None
        self._current_buffer_idx = 0
        self._buffer_res = (0, 0)
        if not self.lib.NDIlib_initialize():
            raise RuntimeError("Failed to initialize NDI SDK")
        print(f"NDI 6 Engine: Initialized with {lib_path}")

    def _setup_functions(self):
        # Initialize / Destroy
        self.lib.NDIlib_initialize.restype = ctypes.c_bool
        self.lib.NDIlib_destroy.restype = None
        
        # Find
        self.lib.NDIlib_find_create_v2.argtypes = [ctypes.POINTER(NDIlib_find_create_t)]
        self.lib.NDIlib_find_create_v2.restype = ctypes.c_void_p
        
        self.lib.NDIlib_find_destroy.argtypes = [ctypes.c_void_p]
        
        self.lib.NDIlib_find_get_current_sources.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        self.lib.NDIlib_find_get_current_sources.restype = ctypes.POINTER(NDIlib_source_t)
        
        self.lib.NDIlib_find_wait_for_sources.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.lib.NDIlib_find_wait_for_sources.restype = ctypes.c_bool
        
        # Recv
        self.lib.NDIlib_recv_create_v3.argtypes = [ctypes.POINTER(NDIlib_recv_create_v3_t)]
        self.lib.NDIlib_recv_create_v3.restype = ctypes.c_void_p
        
        self.lib.NDIlib_recv_destroy.argtypes = [ctypes.c_void_p]
        
        self.lib.NDIlib_recv_capture_v3.argtypes = [ctypes.c_void_p, ctypes.POINTER(NDIlib_video_frame_v2_t), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        self.lib.NDIlib_recv_capture_v3.restype = ctypes.c_int
        
        self.lib.NDIlib_recv_free_video_v2.argtypes = [ctypes.c_void_p, ctypes.POINTER(NDIlib_video_frame_v2_t)]

    def create_finder(self, extra_ips=None):
        settings = NDIlib_find_create_t(True, None, extra_ips.encode() if extra_ips else None)
        return self.lib.NDIlib_find_create_v2(ctypes.byref(settings))

    def get_sources(self, finder_ptr):
        n_sources = ctypes.c_uint32(0)
        p_sources = self.lib.NDIlib_find_get_current_sources(finder_ptr, ctypes.byref(n_sources))
        
        sources = []
        for i in range(n_sources.value):
            s = p_sources[i]
            sources.append({
                "name": s.p_ndi_name.decode('utf-8'),
                "address": s.p_url_address.decode('utf-8') if s.p_url_address else "",
                "raw_struct": s
            })
        return sources

    def create_receiver(self, source_struct=None):
        # Default source struct is an empty one (discovery will handle it if connected later)
        if source_struct is None:
            source_struct = NDIlib_source_t(None, None)
            
        settings = NDIlib_recv_create_v3_t(
            source_struct,
            NDILIB_RECV_COLOR_FORMAT_RGBX_RGBA,
            NDILIB_RECV_BANDWIDTH_HIGHEST,
            False, # allow_video_fields = False (Polite mode: forces progressive)
            "VJ-Link Receiver".encode()
        )
        return self.lib.NDIlib_recv_create_v3(ctypes.byref(settings))

    def capture_video(self, recv_ptr, timeout_ms=0):
        v_frame = NDIlib_video_frame_v2_t()
        frame_type = self.lib.NDIlib_recv_capture_v3(recv_ptr, ctypes.byref(v_frame), None, None, timeout_ms)
        
        if frame_type == NDILIB_FRAME_TYPE_VIDEO:
            res = (v_frame.xres, v_frame.yres)
            ts = v_frame.timestamp
            
            # --- TRIPLE BUFFERING (Restored for Flickering fix) ---
            if self._buffers is None or self._buffer_res != res:
                self._buffers = [
                    np.empty((v_frame.yres, v_frame.xres, 4), dtype=np.float32),
                    np.empty((v_frame.yres, v_frame.xres, 4), dtype=np.float32),
                    np.empty((v_frame.yres, v_frame.xres, 4), dtype=np.float32)
                ]
                self._current_buffer_idx = 0
                self._buffer_res = res
                print(f"VJ-Link: Allocated TRIPLE-BUFFERED storage {res}")

            # Advance buffer index
            self._current_buffer_idx = (self._current_buffer_idx + 1) % 3
            target_buffer = self._buffers[self._current_buffer_idx]

            # --- HYPER OPTIMIZATION ---
            data_size = v_frame.yres * v_frame.line_stride_in_bytes
            buffer_ptr = (ctypes.c_ubyte * data_size).from_address(ctypes.addressof(v_frame.p_data.contents))
            arr_uint8 = np.frombuffer(buffer_ptr, dtype=np.uint8).reshape(v_frame.yres, v_frame.xres, 4)
            
            # np.copyto casts uint8 -> float32 and flips vertically in one pass
            np.copyto(target_buffer, arr_uint8[::-1])
            target_buffer *= (1.0 / 255.0)
            
            # Free NDI SDK memory block
            self.lib.NDIlib_recv_free_video_v2(recv_ptr, ctypes.byref(v_frame))
            
            # Return a flattened view of the stable buffer
            return target_buffer.ravel(), res, ts
            
        elif frame_type == NDILIB_FRAME_TYPE_ERROR:
            return None, "ERROR", 0
            
        return None, None, 0

    def destroy(self):
        self.lib.NDIlib_destroy()
