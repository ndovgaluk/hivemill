# Markdown in VS Code

## Q: Is there an MD viewer for VS Code? What's the best one with the greatest star rating?

Yes, and you may not need an extension at all: **VS Code has a Markdown preview built in**. Open any `.md` file and press **`Ctrl+Shift+V`** for a preview tab, or **`Ctrl+K` then `V`** for a side-by-side preview that updates as you type.

**Most popular Markdown extensions** (live VS Code Marketplace data, queried 2026-11-13):

| Extension | Installs | Rating | What it adds |
|---|---|---|---|
| **Markdown All in One** (`yzhang.markdown-all-in-one`) | **14.9 M** | **4.69 ★** (172 ratings) | Editing help: shortcuts, auto table of contents, list continuation, table formatting. Works with the built-in preview |
| **Markdown Preview Enhanced** (`shd101wyy.markdown-preview-enhanced`) | 10.6 M | 4.33 ★ (145) | Its own, richer preview: diagrams, math, export to HTML/PDF, presentations |
| Markdown Preview Mermaid Support (`bierner.markdown-mermaid`) | 5.5 M | 4.61 ★ (62) | Mermaid diagrams in the built-in preview |
| Markdown Preview Github Styling (`bierner.markdown-preview-github-styles`) | 3.0 M | 4.45 ★ (40) | Makes the preview look like GitHub |

**My pick:** **Markdown All in One**. It has the most installs and the best rating among the ones with many ratings. Add **Markdown Preview Enhanced** only if you need diagrams, math or PDF export. Some small extensions show higher averages (e.g. 5.00 ★ from 8 ratings), but with so few votes those numbers don't mean much.

**Install it where your files are:** in the **WSL** VS Code window, extensions install on the Ubuntu side. From the Ubuntu terminal: `code --install-extension yzhang.markdown-all-in-one`, or use the Extensions sidebar in that window ("Install in WSL: Ubuntu").

---

## Q: What if I want the preview to be the default view for md files?

In the editor's view menu, use **Set Default for '\*.md'** → **Markdown Preview**. From then on, opening any `.md` file opens straight into the rendered preview.

**Same thing as a setting:** `Ctrl+Shift+P` → **Preferences: Open User Settings (JSON)**:
```json
"workbench.editorAssociations": {
  "*.md": "vscode.markdown.preview.editor"
}
```
Put it in your **user** settings, so it applies in the WSL window and on Windows alike.

**Editing a file again:** in the preview, click the **"Open Source"** icon at the top right, or right-click the tab → **Reopen Editor With…** → **Text Editor**.

**To undo it:** the same menu → **Set Default for '\*.md'** → **Text Editor**, or remove the setting. The "(Open to the Side)" entries only affect the current file.

---

## Q: Can I change the colour to blue instead of the dark grey background (inline code)?

Yes. VS Code's built-in preview accepts your own CSS through the `markdown.styles` setting.

- **`.local-docs/preview.css`** (git-ignored): blue text (`#79c0ff`) on a translucent blue background for inline code in dark themes, darker blue for light themes. Code blocks keep their normal look.
- **User settings** (`C:\Users\Dell\AppData\Roaming\Code\User\settings.json`):
  ```json
  "markdown.styles": [".local-docs/preview.css"]
  ```
  The path is relative to the folder open in VS Code, so it applies when `~/src/hivemill` is open; elsewhere VS Code ignores it.

To see it: reopen the preview or **Developer: Reload Window**. To change the shade, edit the two values in `preview.css`: background `rgba(56, 139, 253, 0.18)` (last number = opacity) and text `#79c0ff`.

---

## Q: Is there a way to zoom the MD file preview or make the font larger?

Yes, three ways:

1. **Preview font only (best):** user setting `markdown.preview.fontSize` (default 14). `Ctrl+,` → search "markdown preview font size", or in settings JSON:
   ```json
   "markdown.preview.fontSize": 16,
   "markdown.preview.lineHeight": 1.6
   ```
   Applies to every Markdown preview, leaves the rest of VS Code as it is.
2. **Zoom all of VS Code:** `Ctrl+=` / `Ctrl+-` (reset `Ctrl+0`), or setting `window.zoomLevel` (e.g. `1`). Makes everything bigger, menus included.
3. **Via the custom CSS** already in use (`.local-docs/preview.css`): add `body { font-size: 16px; }`. Only for this folder; option 1 is simpler.

The preview picks up setting changes right away; CSS changes after reopening the preview or Developer: Reload Window.
