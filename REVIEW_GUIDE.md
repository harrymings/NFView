# NFView — reviewing photos

Open `LaunchNFView.cmd` or `dist\NFView.exe`.

- Left-button drag down/up: zoom in/out. Release keeps the zoom. Double-click jumps to 50% of the embedded preview pixels.
- Middle-button drag: pan. Right-click or `0`: fit the photo.
- Wheel or `+` / `-`: zoom. Arrow keys: previous/next photo.
- `P`: toggle favourite. `L`: lock/unlock review choices. `C`: start/end comparison.
- `F`: recommended-only filter. `S`: rescan. `Ctrl+O`: open folder. `Esc`: deselect. `?`: help.

The Photo browser toolbar offers **Sort by** (score, filename, capture date/time, file modification date), **Ascending / Descending**, and **Show** (all photos, favourites, locked photos, custom lists). Capture date uses EXIF camera time and falls back to file modification time. Sorting changes the browser order, not scores or recommendations.

Use **Lists → Create list** to name a list. Select a photo, then use **Lists → Add current photo to**. Choose a list in **Show** to browse its members. The menu can remove the current photo, rename a list, or delete a list. Originals are untouched. A new empty list keeps the current preview available so it can be added.

**Lock** protects favourite status and list memberships. Unlock before changing either. Locking does not alter the original file or change copy recommendations. A list containing locked photos cannot be deleted until those photos are unlocked.

**Compare** pins the current photo as A and opens another as B. Use arrows or thumbnails to choose B. Drag the central vertical divider/handle left or right to swipe between A and B. Drag up/down elsewhere to zoom; middle-drag pans. **End compare** returns to one photo.

Favourites, locks, and lists are saved in `.image-screener-review.json` in the photo folder. Preferences are saved in `.image-screener-settings.json`. Capture date metadata is cached in `.image-screener-dates.json`. Sorting reorders existing thumbnail cards without reloading them. Scores remain in the existing version-3 `.image-screener-cache.json`; thumbnails use `.image-screener-previews`. Keep the review JSON when moving a folder to retain review choices.

**Copy photos** still copies the recommended originals, using the recommendation percentage and existing scoring method. It does not copy only the displayed list. Optional CSV/HTML reports remain available under File or Tools.

Nikon focus overlays show recorded autofocus metadata when supported; grid positions can be approximate. RAW previews retain the camera's embedded resolution. A black embedded preview cannot reveal detail merely by zooming.

The right-hand details panel includes an **RGB histogram** of the displayed preview. The left side represents dark pixels and the right side bright pixels; red, green and blue curves show each colour channel. This display does not change scores. Folder opening and scan actions are in the File menu (Ctrl+O and S), without duplicate toolbar buttons.

Drag the divider at the left edge of the details panel to adjust its width. The chosen width is remembered across launches and when hiding or showing details.
Use the Zoom and Pan buttons beside the zoom controls to choose the left-drag tool. Zoom adjusts magnification vertically; Pan moves the enlarged image. Middle-drag always pans, right-click fits, and double-click zooms to 50%.
Mouse controls can be customised under Edit → Settings. By default, right-drag pans and a right-click without dragging fits the photo. Choose Pan only to disable right-click reset, or Fit only for the old behaviour. You can also change the left-drag tool, double-click action and wheel zoom. Settings are saved.
Swipe compare (C) pins the first photo and opens a second. Drag the centre divider to compare them. Use Edit → Delete selected photo… or Delete to move the selected original to the Recycle Bin after confirmation. Locked photos must be unlocked first. Restore deleted originals through Windows Recycle Bin; review-list memberships removed during deletion must be re-added manually.
The Grid toggle adds rule-of-thirds guides to the main photo. During swipe comparison, reference A appears in a small bottom-right preview. Double-click it to centre the divider on the photo. Its × button hides it; View → Reference preview shows it again. Locked thumbnails show a small padlock in the top-right corner.

In Edit → Settings, choose an application under **Open photos with**. The default is Photoshop with automatic detection and association fallback. The toolbar button opens the selected original with your chosen app. Use **Default: Photoshop** to restore the default.
Help → User guide opens a resizable, tabbed guide with larger text. Help → About NFView includes the project author GitHub link: https://github.com/harrymings. View groups filters, zoom, guides and panels into submenus.
