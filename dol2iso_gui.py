#!/usr/bin/env python3
"""
dol2iso_gui.py — standalone GUI that builds a bootable GameCube .iso from a .dol.
Pure Python (no Docker/genisoimage); packageable into a single .exe.

Fields: .dol file, banner (optional -> uses the tool's default banner), output path,
optional title/subtitle, and the "Generate .iso" button.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import dol2iso_core as core


def resource(name):
    """Resolve a bundled asset (works both as a .py and as a PyInstaller bundle)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


GBI_HDR = resource("gbi.hdr")
DEFAULT_BANNER = resource("default_banner.png")
APP_ICON = resource("dolphin.ico")


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=16)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.dol = tk.StringVar()
        self.banner = tk.StringVar()
        self.out = tk.StringVar()
        self.title = tk.StringVar()
        self.subtitle = tk.StringVar(value="Games Loader")
        self.stretch = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready.")

        r = 0
        ttk.Label(self, text="DOL → ISO  ·  GameCube bootable disc builder",
                  font=("Segoe UI", 13, "bold")).grid(
                      row=r, column=0, columnspan=3, sticky="w", pady=(0, 12))

        r += 1
        self._file_row(r, "DOL file:", self.dol, self._pick_dol)
        r += 1
        self._file_row(r, "Banner (optional):", self.banner, self._pick_banner)
        r += 1
        ttk.Label(self, text="empty = uses the tool's default banner",
                  foreground="#666").grid(row=r, column=1, columnspan=2,
                                          sticky="w", pady=(0, 6))
        r += 1
        self._file_row(r, "Save .iso to:", self.out, self._pick_out, save=True)

        r += 1
        ttk.Label(self, text="Title:").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(self, textvariable=self.title).grid(row=r, column=1,
                                                      sticky="ew", pady=3)
        ttk.Checkbutton(self, text="Stretch banner", variable=self.stretch).grid(
            row=r, column=2, sticky="w", padx=(8, 0))
        r += 1
        ttk.Label(self, text="Subtitle:").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(self, textvariable=self.subtitle).grid(row=r, column=1,
                                                         columnspan=2, sticky="ew",
                                                         pady=3)

        r += 1
        self.btn = ttk.Button(self, text="Generate .iso", command=self._generate)
        self.btn.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(14, 6))

        r += 1
        self.bar = ttk.Progressbar(self, mode="indeterminate")
        self.bar.grid(row=r, column=0, columnspan=3, sticky="ew")
        r += 1
        ttk.Label(self, textvariable=self.status, foreground="#0a7").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _file_row(self, r, label, var, cmd, save=False):
        ttk.Label(self, text=label).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(self, textvariable=var).grid(row=r, column=1, sticky="ew", pady=3)
        ttk.Button(self, text="…", width=3, command=cmd).grid(
            row=r, column=2, sticky="w", padx=(8, 0))

    def _pick_dol(self):
        p = filedialog.askopenfilename(title="Select .dol",
                                       filetypes=[("GameCube DOL", "*.dol"),
                                                  ("All files", "*.*")])
        if not p:
            return
        self.dol.set(p)
        if not self.out.get():
            self.out.set(os.path.splitext(p)[0] + ".iso")
        if not self.title.get():
            self.title.set(os.path.splitext(os.path.basename(p))[0])

    def _pick_banner(self):
        p = filedialog.askopenfilename(
            title="Select banner image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp"),
                       ("All files", "*.*")])
        if p:
            self.banner.set(p)

    def _pick_out(self):
        p = filedialog.asksaveasfilename(title="Save .iso", defaultextension=".iso",
                                         filetypes=[("ISO", "*.iso")])
        if p:
            self.out.set(p)

    def _generate(self):
        dol = self.dol.get().strip()
        out = self.out.get().strip()
        if not dol or not os.path.isfile(dol):
            messagebox.showerror("Error", "Select a valid .dol file.")
            return
        if not out:
            messagebox.showerror("Error", "Choose where to save the .iso.")
            return
        banner = self.banner.get().strip() or DEFAULT_BANNER
        if not os.path.isfile(banner):
            messagebox.showerror("Error", f"Banner not found:\n{banner}")
            return
        if not os.path.isfile(GBI_HDR):
            messagebox.showerror("Error", f"Bundled gbi.hdr is missing:\n{GBI_HDR}")
            return

        self.btn.config(state="disabled")
        self.bar.start(12)
        self.status.set("Generating…")
        threading.Thread(target=self._work,
                         args=(dol, out, banner), daemon=True).start()

    def _work(self, dol, out, banner):
        try:
            n = core.make_bootable_iso(
                dol, out, GBI_HDR,
                banner_path=banner, stretch=self.stretch.get(),
                title=self.title.get().strip(),
                subtitle=self.subtitle.get().strip())
            self.after(0, self._done, out, n, None)
        except Exception as e:                                   # noqa: BLE001
            self.after(0, self._done, out, 0, e)

    def _done(self, out, n, err):
        self.bar.stop()
        self.btn.config(state="normal")
        if err:
            self.status.set("Failed.")
            messagebox.showerror("Failed to generate .iso", str(err))
            return
        self.status.set(f"OK — {n:,} bytes written.")
        messagebox.showinfo("Done",
                            f"Bootable .iso created:\n{out}\n\n{n:,} bytes")


def run_cli(argv):
    """CLI mode (when the .exe is called with arguments). Handy for scripts and tests.
       Usage: dol2iso <input.dol> <output.iso> [banner] [--title T] [--subtitle S] [--stretch]"""
    import argparse
    import io
    if sys.stdout is None:                       # --windowed build has no console
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    ap = argparse.ArgumentParser(prog="dol2iso",
                                 description="Build a bootable GameCube .iso from a .dol.")
    ap.add_argument("dol")
    ap.add_argument("iso")
    ap.add_argument("banner", nargs="?", help="banner image (default: tool's banner)")
    ap.add_argument("--title")
    ap.add_argument("--subtitle")          # omitted = keep stock; "" = blank
    ap.add_argument("--stretch", action="store_true")
    a = ap.parse_args(argv)
    banner = a.banner or DEFAULT_BANNER
    title = a.title or os.path.splitext(os.path.basename(a.dol))[0]
    n = core.make_bootable_iso(a.dol, a.iso, GBI_HDR, banner_path=banner,
                               stretch=a.stretch, title=title, subtitle=a.subtitle)
    print(f">> .iso created: {a.iso} ({n} bytes)")
    return 0


def main():
    if len(sys.argv) > 1:
        sys.exit(run_cli(sys.argv[1:]))
    root = tk.Tk()
    root.title("DOL → ISO")
    root.minsize(560, 0)
    try:
        root.iconbitmap(default=APP_ICON)        # window / title-bar icon
    except tk.TclError:
        pass
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.update_idletasks()
    root.geometry(f"+{root.winfo_screenwidth()//2 - 280}+200")
    root.mainloop()


if __name__ == "__main__":
    main()
