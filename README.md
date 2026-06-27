# dol2iso (GUI / standalone .exe)

A GUI `.exe` that builds a **bootable GameCube `.iso` from a `.dol`** — the same
technique as `cubiboot.iso`, but for any `.dol`.

**100% self-contained:** the `.exe` needs no Docker, WSL, genisoimage, or installed
Python. Everything (the Python runtime, image conversion, `gbi.hdr`, and the default
banner) is embedded in the executable itself. The ISO is assembled in **pure Python** —
nothing external.

## Usage

Run `dist\dol2iso.exe` (double-click). In the window:

1. **DOL file** — pick the `.dol`.
2. **Banner (optional)** — any image (PNG/JPG/BMP/… any size). If left empty, the
   **tool's default banner** is used. The image is resized to 96×32 and converted to
   RGB5A3 automatically (check *Stretch* to fill without keeping aspect ratio).
3. **Save .iso to** — output file.
4. **Title / Subtitle** — BIOS intro text (optional; title defaults to the `.dol`
   name; leave a field empty to keep it blank).
5. **Generate .iso**.

### Command-line mode (bonus)

The same `.exe` also accepts arguments:

```
dol2iso.exe input.dol output.iso [banner.png] [--title "T"] [--subtitle "S"] [--stretch]
```

## How it works (boot)

The `.iso` is a GameCube disc whose apploader (embedded in `gbi.hdr`, from
`makeo/cubeboot-tools`) reads and executes the `.dol` at boot. On the console the
apploader only reads:

- **sector 0** → `gbi.hdr` (disc header + apploader + FST)
- **sector 17** → El-Torito Boot Record → boot catalog pointer
- **boot catalog** → `load_rba` (where the `.dol` is) and `sector_count`
- **`.dol`** at `load_rba × 2048` → executes

So the ISO9660 filesystem itself doesn't affect booting; even so, the disc is a valid
ISO9660 (`BOOT.DOL` + `BOOT.CAT`) that mounts and inspects normally.

> Verified: the output was checked with `isoinfo` and the Boot Record (sector 17) is
> byte-identical to `genisoimage`'s; a simulation of the apploader's steps confirms it
> reaches the `.dol`. Real boot on hardware/Dolphin depends on the `.dol` having a
> valid layout (that's the `.dol`'s responsibility, not the packaging's).

## Rebuilding the .exe

Requires Python + `pip install pyinstaller pillow`. Then:

```powershell
.\build.ps1
```

Produces `dist\dol2iso.exe`.

## Files

- `dol2iso_gui.py` — GUI (entry point) + CLI mode
- `dol2iso_core.py` — RGB5A3 branding + ISO9660/El-Torito writer (pure Python)
- `assets/gbi.hdr` — boot header/apploader (32 KB)
- `assets/default_banner.png` — default banner
- `assets/dolphin.ico` — app icon
- `make_default_banner.py` — regenerates the default banner
- `build.ps1` — builds the `.exe`
- `dist/dol2iso.exe` — the standalone executable
