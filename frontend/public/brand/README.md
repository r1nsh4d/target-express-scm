# Brand assets

Drop the client's files in this folder using **exactly these filenames**. The
app picks them up automatically — no code change, no rebuild step beyond the
normal one. Until a file exists, the app falls back to the built-in placeholder
mark, so nothing breaks if you only supply some of them.

## The logo

| Filename | Used where | Notes |
|---|---|---|
| `logo.svg` | Everywhere in **dark mode** (the default) | Must be a **light-coloured** logo — white or near-white — or it will disappear against the dark UI |
| `logo-dark.svg` | Everywhere in **light mode** | The normal dark/black version of the logo |
| `mark.svg` | The **collapsed** left rail only | The symbol on its own, **no words**, on a square canvas. Light-coloured, like `logo.svg` |

If you only have one version, supply `logo.svg`. Light mode will reuse it.

`mark.svg` is optional. The collapsed rail is 64 px wide, so the full wordmark
cannot be read there; without a `mark.svg` the collapsed rail shows the square
`TE` placeholder instead of a squashed logo.

**Format:** SVG, transparent background, artwork trimmed to its own edges (no
built-in padding — the layout adds its own spacing).

If SVG is genuinely unavailable, PNG works: 24-bit with alpha transparency, at
least **512 px** on the long edge, named `logo.png` / `logo-dark.png`. Ask for
the SVG though — the Target Express mark is simple line art and will look
noticeably crisper.

## The favicon and app icons

| Filename | Size | Purpose |
|---|---|---|
| `favicon.svg` | any | Browser tab, modern browsers. Preferred |
| `favicon.ico` | 32×32 | Older browsers and Windows taskbar pins |
| `apple-touch-icon.png` | 180×180 | iPhone and iPad home screen |
| `icon-192.png` | 192×192 | Android home screen |
| `icon-512.png` | 512×512 | Android splash screen |

**Format:** PNG for the raster sizes, 24-bit with alpha. Square canvas. Keep the
mark inside roughly the middle 80% — Android and iOS crop the edges.

The home-screen icons matter more than usual here: drivers will add the portal
to their phone's home screen, and that icon is what they tap every morning.

## Generating the set

From one square SVG, https://realfavicongenerator.net produces every size above.
Or with ImageMagick:

```bash
magick logo-square.svg -resize 180x180 apple-touch-icon.png
magick logo-square.svg -resize 192x192 icon-192.png
magick logo-square.svg -resize 512x512 icon-512.png
magick logo-square.svg -resize 32x32   favicon.ico
```

Note the favicon wants a **square** mark (the "TE" symbol alone), not the full
horizontal lockup with the wordmark — a wide logo shrunk to 32 px is unreadable.

## Colour

The brand is black and white, so the interface accent is monochrome: near-white
on the dark theme, near-black on the light one. Emphasis comes from contrast and
weight rather than hue.

Status colour is the one deliberate exception, reserved for state — delivered,
short, failed, and the severity of an odometer gap. Those are information, not
decoration; a thirty-row table cannot be scanned without them. They never carry
meaning alone: a status renders a small coloured dot beside a label in normal
ink, so the words carry the meaning and the dot only speeds up the scan.

If the client later adds a brand colour, it is four values in `src/index.css`
(`--accent`, `--accent-hover`, `--accent-dim`, `--accent-fg`) — a two-minute
change. Leave the status palette alone when doing it.
