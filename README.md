# Flow Map Painter [Blender] — Blender 5.0 Fork

This is a fork of [ClemensBeute/flow_map_painter](https://github.com/ClemensBeute/flow_map_painter), updated to be compatible with **Blender 5.0**.

This Blender add-on provides a brush tool for flow map painting. The brush color updates dynamically based on the painting direction, making it easy to author flow maps directly inside Blender.

It supports:
- **2D Image Editor** — Paint Mode
- **3D Viewport** — Texture Paint Mode
- **3D Viewport** — Vertex Paint Mode

![image](https://github.com/ClemensBeute/flow_map_painter/assets/3758308/704e9279-ea38-40d4-9fdf-1cfbd3ddfd1a)

---

## Changes from the original (Blender 5.0 compatibility)

### `blender_manifest.toml` (new file)
- Added the extension manifest required by Blender 5.0's new extension system, replacing the legacy `bl_info` registration format.
- Sets `blender_version_min = "5.0.0"`.

### `funcs.py`
- **`draw_circle_2d_compat()`** — Replaced the removed `gpu_extras.presets.draw_circle_2d` with a custom implementation using `gpu.shader` and `batch_for_shader`.
- **`_get_paint_settings()`** — New helper to retrieve `unified_paint_settings` from the correct location. In Blender 5.0, this was moved from `bpy.context.tool_settings.unified_paint_settings` to per-mode settings (e.g., `tool_settings.image_paint.unified_paint_settings`).
- **`get_paint_color()` / `set_paint_color()` / `get_paint_size()`** — Updated to read and write through `unified_paint_settings` via the new helper, ensuring the paint system in Blender 5.0 picks up the direction-based color correctly.

### `__init__.py`
- Wrapped class registration in `try/except` blocks to surface errors clearly instead of silently failing.
- Cleaned up the `unregister()` function to check for the `flowmap_painter_props` attribute before deleting it.

### `ops.py`
- Removed leftover debug print statements from the operator `invoke` methods.
- Restored the `RUNNING_MODAL` + `paint_a_dot` approach (Blender 5.0's built-in paint tool snapshots the brush color at stroke start, so mid-stroke color changes would not take effect without this approach).

### `props.py`
- Minor cleanup of property definitions.

---

## Known limitation

When painting in **3D Texture Paint** or **Vertex Paint** mode using perspective projection, painting may stop if the viewport camera is dollied very close to (or past) the mesh surface. This is a Blender limitation: the internal paint projection fails when the near clip plane obscures the geometry. **Switching to Orthographic view** (`Numpad 5`) resolves this.

---

## Usage

1. Enter one of the supported modes (Texture Paint, Vertex Paint, or Image Editor in Paint mode).
2. Open the **N-panel** (press `N`) and go to the **Flowmap** tab.
3. Click **Flowmap Paint Mode** to activate the brush. The brush color will automatically update to reflect the direction of your stroke.
4. Press **ESC** to exit the mode.

Settings available in the panel:
- **Brush Spacing** — Minimum mouse travel (in pixels) before a new paint dot is placed.
- **Trace Distance** — Raycast depth used for 3D projection (3D and Vertex modes only).
- **Space Type** — Direction space: UV Space, Object Space, or World Space (3D and Vertex modes only).

Most brush settings (falloff, strength, pen pressure, etc.) are inherited from the standard Blender brush settings.

Make sure the image you want to paint on is selected in your material, and that its Color Space is set to **Linear** (EXR format is recommended for maximum quality).

If you are using multiple UV layers, highlight the one you want to use before painting in 3D.

> **Vertex Paint note:** The color is stored in sRGB. To use it correctly in a shader, convert it to linear by running it through a Gamma node set to `0.454` (or `1/2.2`).

---

## Original project

- Author: Clemens Beute — feedback.clemensbeute@gmail.com
- Original repository: https://github.com/ClemensBeute/flow_map_painter
- Support the original author on Gumroad: https://clemensbeute.gumroad.com/l/heZDT

---

## License

GNU General Public License v3.0 or later — see `COPYING.txt`.
