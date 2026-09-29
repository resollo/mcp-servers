# Photo clean-up for a Resollo listing

Target: each photo shows the whole item, evenly lit, on a clean background, centred on a square canvas, **1000×1000 px**, web-optimised (JPEG or WebP).

Tools: the free local MCP servers from https://github.com/resollo/mcp-servers:

- `bgremoval`: AI background removal (rembg, runs offline after the first model download)
- `gimp`: raster editing on a running GIMP 3 (needs the MCP Bridge plug-in started: *Filters → Development → MCP Bridge → Start Bridge Server*)
- `inkscape`: SVG compositing plus export through the Inkscape CLI

Work on copies. Never overwrite the user's original photos.

## Pipeline

1. **Colour and light**: open the photo in GIMP (`gimp_open_image`), run `gimp_white_balance`, export to PNG (`gimp_export_image`). Indoor phone photos are usually too dark or too yellow; this fixes most of it.

2. **Background removal**: run `bgremoval_remove_background` on the corrected PNG, writing a new `.png` file with transparency.
   The output has the **same pixel size as the input**. The background turns transparent, but the canvas is not cropped to the item.

3. **Tight crop to the item**: crop to the item's own bounding box, measured on the **alpha channel**.
   - Don't use the bounding box of every non-transparent pixel. Segmentation leaves faint alpha noise near the edges and small false-positive islands, and both inflate the box.
   - Robust approach: take the connected component of opaque pixels that contains a point known to be on the item (contiguous select on alpha, not on colour; colour-based selection breaks on shading and highlights).
   - Crop with `gimp_crop_image`.
   - **Verify the crop** before continuing: the share of non-transparent pixels should match what you measured, the corners should be transparent and the centre opaque. A crop can return the right canvas size with the wrong content.

4. **Centre on a square**: composite the cropped item onto a square canvas with an even ~10% margin on every side. Use a plain white or very light background, unless the user wants the transparent cut-out or a specific colour. Inkscape works well for this: place the PNG as an `<image>` in a square SVG and export with `inkscape_export`.

5. **Final size**: resize to 1000×1000 (`gimp_resize_image`) and export as JPEG or WebP (`gimp_export_image`).

6. **Look at the result** before uploading: the whole item visible, not cut off, centred, not tiny in the frame, colours natural.

## Housekeeping

- Close images you opened in GIMP when done (`gimp_delete_image`). Many open images in one session have caused mix-ups between image ids.
- Keep intermediate files in a scratch folder, not next to the user's originals.
- If a tool reports success but the output looks wrong, re-open the file and check it. Don't rely on the tool's summary alone.
