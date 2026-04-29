bl_info = {
    "name": "VJ-Link",
    "author": "FloydianSound & Gemini",
    "version": (1, 6, 3),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > VJ-Link",
    "description": "Hyper-optimized NDI Receiver for Linux (Stable Build)",
    "category": "System",
}

import bpy
import sys
import subprocess
from pathlib import Path

# Path setup
ADDON_ROOT = Path(__file__).parent.absolute()
LIBS_PATH = ADDON_ROOT / "libs"

def ensure_libs_in_path():
    libs_str = str(LIBS_PATH)
    if libs_str not in sys.path:
        sys.path.insert(0, libs_str)

from .core.ndi_manager import NDIManager
_ndi_manager = NDIManager()

# -------------------------------------------------------------------------
# Preferences
# -------------------------------------------------------------------------

class VJLINK_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    ndi_lib_path: bpy.props.StringProperty(
        name="NDI Library Path",
        subtype='FILE_PATH',
        default="",
        description="Path to libndi.so (e.g., /usr/lib/libndi.so.6)"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "ndi_lib_path")

# -------------------------------------------------------------------------
# Properties
# -------------------------------------------------------------------------

def get_source_items(self, context):
    ensure_engine_init()
    sources = _ndi_manager.find_sources()
    items = [("NONE", "[NONE]", "No source selected")]
    for n in sources:
        if n != "NONE":
            items.append((n, n, n))
    return items

class VJLINK_ReceiverSettings(bpy.types.PropertyGroup):
    source_name: bpy.props.EnumProperty(
        name="Source",
        description="Select an NDI source from the network",
        items=get_source_items
    )
    
    target_image: bpy.props.PointerProperty(
        name="Target Image",
        type=bpy.types.Image
    )
    
    is_running: bpy.props.BoolProperty(
        name="Enable Link",
        default=False,
        update=lambda self, context: toggle_link(self, context)
    )

# -------------------------------------------------------------------------
# Operators
# -------------------------------------------------------------------------

class VJLINK_OT_InstallDeps(bpy.types.Operator):
    bl_idname = "vjlink.install_deps"
    bl_label = "Install NDI Dependencies"
    def execute(self, context):
        LIBS_PATH.mkdir(exist_ok=True)
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--target", str(LIBS_PATH), "cyndilib", "numpy"]
        try:
            subprocess.check_call(cmd)
            self.report({'INFO'}, "Installed. Restart Blender.")
        except Exception as e:
            self.report({'ERROR'}, str(e))
        return {'FINISHED'}

class VJLINK_OT_RefreshSources(bpy.types.Operator):
    bl_idname = "vjlink.refresh_sources"
    bl_label = "Scan Network"
    def execute(self, context):
        ensure_engine_init()
        _ndi_manager.find_sources(force=True)
        return {'FINISHED'}

# -------------------------------------------------------------------------
# Logic
# -------------------------------------------------------------------------

def ensure_engine_init():
    addon_prefs = bpy.context.preferences.addons.get(__package__)
    if not addon_prefs or not addon_prefs.preferences:
        lib_path = ""
    else:
        lib_path = addon_prefs.preferences.ndi_lib_path
        
    if not _ndi_manager.engine:
        _ndi_manager.initialize_engine(lib_path)

def vlink_timer():
    if not _ndi_manager.running:
        return None
        
    frame_data, res, fps = _ndi_manager.get_latest_frame()
    
    # If no data yet, wait (handshake period)
    if frame_data is None or res[0] <= 0:
        return 0.01

    for scene in bpy.data.scenes:
        if not hasattr(scene, "vj_link"): continue
        settings = scene.vj_link
        if not settings.is_running: continue

        img = settings.target_image
        if not img: continue

        # --- SMART RESIZE (Pixel Perfect v1.6.2+) ---
        try:
            # We check resolution every frame to support mid-stream resolution changes
            if img.size[0] != res[0] or img.size[1] != res[1]:
                img.scale(res[0], res[1])
                print(f"VJ-Link: Image scaled to match NDI stream: {res[0]}x{res[1]}")
            
            # Critical: foreach_set expects exact size
            expected_size = img.size[0] * img.size[1] * 4
            if frame_data.size == expected_size:
                img.pixels.foreach_set(frame_data)
                img.update_tag()
            else:
                # If size mismatch, we don't crash, we just scale for the next frame
                pass
        except Exception as e:
            print(f"VJ-Link Sync Error: {e}")

    return 0.01

def toggle_link(self, context):
    ensure_engine_init()
    if self.is_running:
        if self.source_name != "NONE":
            # --- INSTANT IMAGE CREATION ---
            if not self.target_image:
                img_name = f"NDI_{self.source_name}"
                img_name = img_name.replace(" ", "_").replace("(", "").replace(")", "")
                img = bpy.data.images.get(img_name)
                if not img:
                    img = bpy.data.images.new(img_name, width=1920, height=1080, alpha=True)
                self.target_image = img
                print(f"VJ-Link: Instant image creation: {img_name}")

            # Start NDI background thread
            _ndi_manager.start(self.source_name)
            
            # Safe timer registration
            bpy.app.timers.register(vlink_timer)
        else:
            self.is_running = False
    else:
        _ndi_manager.stop()
        try:
            bpy.app.timers.unregister(vlink_timer)
        except ValueError:
            pass

# -------------------------------------------------------------------------
# UI
# -------------------------------------------------------------------------

class VJLINK_PT_MainPanel(bpy.types.Panel):
    bl_label = "VJ-Link v1.6.3"
    bl_idname = "VJLINK_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'VJ-Link'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.vj_link

        try:
            import cyndilib
            deps_ok = True
        except ImportError:
            deps_ok = False

        if not deps_ok:
            layout.operator("vjlink.install_deps", icon='IMPORT')
            return

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(settings, "source_name")
        row.operator("vjlink.refresh_sources", text="", icon='FILE_REFRESH')
        
        col.prop(settings, "target_image")
        
        layout.prop(settings, "is_running", text="STOP" if settings.is_running else "START LINK", toggle=True)
        
        if settings.is_running or _ndi_manager.status != "Idle":
            box = layout.box()
            box.label(text=f"Status: {_ndi_manager.status}")
            if _ndi_manager.resolution[0] > 0:
                box.label(text=f"Res: {_ndi_manager.resolution[0]}x{_ndi_manager.resolution[1]}")
                box.label(text=f"Link FPS: {_ndi_manager.fps:.1f}")

# -------------------------------------------------------------------------
# Registration
# -------------------------------------------------------------------------

classes = (VJLINK_Preferences, VJLINK_ReceiverSettings, VJLINK_OT_InstallDeps, VJLINK_OT_RefreshSources, VJLINK_PT_MainPanel)

def register():
    ensure_libs_in_path()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.vj_link = bpy.props.PointerProperty(type=VJLINK_ReceiverSettings)

def unregister():
    _ndi_manager.stop()
    try: bpy.app.timers.unregister(vlink_timer)
    except ValueError: pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.vj_link

if __name__ == "__main__":
    register()
