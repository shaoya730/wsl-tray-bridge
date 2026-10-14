# Application icon

A cyan-to-blue arch connects two piers: Linux and Windows, joined by a light bridge deck. The midnight tile keeps the mark readable on light and dark taskbars.

- `icon.svg`: editable vector master, with a transparent outer margin.
- `icon.png`: 512px image for documentation and previews.
- `icon.ico`: 32-bit alpha frames at 16, 20, 24, 32, 40, 48, 64, 96, 128 and 256px.

The build embeds the ICO both as the Windows executable icon and as a managed resource for the bridge's own notification icon. The installer sets the shortcut icon to the executable. Bridged applications retain their own icons.

The exports are committed; building the application requires no graphics tools. To regenerate after editing the SVG, install Node.js and the optional `sharp` package in the repository, then run:

```sh
npm install --no-save --package-lock=false sharp
node scripts/render_icons.cjs
```
