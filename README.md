# VJ-Link

A high-performance NDI Receiver for Blender on Linux.

Built for professional VJ setups (like Resolume, Synesthesia, OBS), VJ-Link bypasses standard Python wrappers by using a custom, rock-solid `ctypes` engine that talks directly to the official `libndi.so` (NDI 6 SDK).

## Features
- **Triple-Buffered Protection:** Prevents screen tearing and flickering by isolating network writes from Blender's read operations.
- **Zero UI Lag:** Asynchronous discovery and dedicated background threads mean Blender never freezes while looking for streams.
- **Ultra-Fast Injection:** Uses `foreach_set` and numpy normalization with a persistent, pre-allocated memory buffer to push video directly into Blender images with minimal CPU overhead.
- **Auto-Image Creation:** Automatically creates correctly sized image textures based on the incoming NDI resolution.
- **Smart Unique Frame Tracking:** Tracks NDI timestamps to ensure only new frames are processed, keeping CPU usage low while maintaining smooth output.
- **Robust Recovery:** Automatically reconnects if the network stream is dropped.
- **Linux Compatibility:** Lets you specify the exact location of your `libndi.so` file to avoid any system conflict or missing library errors.

## Installation
1. Download the repository as a ZIP file.
2. In Blender, go to `Edit > Preferences > Add-ons` and click `Install`.
3. Select the downloaded ZIP file.
4. Enable **VJ-Link**.
5. (Optional) In the add-on preferences, you can verify the **NDI Library Path**. VJ-Link will auto-discover standard Linux installations (`/usr/lib/`), but you can explicitly point it to a custom location if needed.

## Usage
1. Open the **Sidebar** in the 3D Viewport (`N` key).
2. Go to the **VJ-Link** tab.
3. Click the **Scan Network** (refresh) icon if your source isn't listed.
4. Select your **NDI Source**.
5. Click **START LINK**. 
6. VJ-Link will automatically create an image texture named `NDI_[YourSourceName]`. You can apply this image to any shader or object in Blender.

## Requirements
- Blender 4.0 or higher.
- Official NDI SDK for Linux installed on your system.

## Version
Current Version: 1.6.3 Stable
