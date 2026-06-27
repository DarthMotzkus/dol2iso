#!/usr/bin/env python3
"""
dol2iso_core.py — gera, em Python PURO (sem genisoimage/Docker), uma .iso GameCube
bootável a partir de um .dol, usando o apploader pré-compilado embutido no gbi.hdr.

Mecanismo (validado contra o apploader do cubeboot-tools, ppc/apploader/apploader.c):
o apploader, no boot, lê apenas:
  - setor 0      -> gbi.hdr (disc header + apploader + FST/bi2)        [system area]
  - setor 17     -> Boot Record El-Torito  -> boot_catalog_offset (LE32 @0x47)
  - boot catalog -> default entry @0x20     -> load_rba (LE32), sector_count (LE16)
  - .dol         -> em load_rba * 2048, executa
O boot NÃO depende do ISO9660 (PVD/path table/diretório); ainda assim geramos um
ISO9660 válido (monta/inspeciona normalmente) com BOOT.DOL e BOOT.CAT.

Layout de setores (2048 bytes cada):
  0..15  system area (gbi.hdr, 32768 bytes; banner/títulos opcionalmente reescritos)
  16     Primary Volume Descriptor
  17     Boot Record Volume Descriptor (El-Torito)  <- apploader exige aqui
  18     Volume Descriptor Set Terminator
  19     Path Table (LE)
  20     Path Table (BE)
  21     Root directory
  22     Boot catalog
  23..   BOOT.DOL
"""
import hashlib
import math
import struct

SECTOR = 2048
SYSTEM_AREA_SECTORS = 16
SYSTEM_AREA_SIZE = SYSTEM_AREA_SECTORS * SECTOR          # 32768

# setores fixos
LBA_PVD        = 16
LBA_BOOTREC    = 17
LBA_TERM       = 18
LBA_PT_L       = 19
LBA_PT_M       = 20
LBA_ROOT       = 21
LBA_BOOTCAT    = 22
LBA_DOL        = 23

# --- disc header (GameCube) dentro do gbi.hdr (system area) -----------------
# cubiboot (e a maioria dos loaders) usa o Game ID de 6 bytes em 0x00 como
# CHAVE de cache do banner. Se duas .iso compartilham o mesmo Game ID, o loader
# trata-as como o MESMO jogo e replica o banner de uma na outra. Por isso cada
# .iso precisa de um Game ID único.
GAMEID_OFF   = 0x00                                      # 6 bytes
GAMEID_LEN   = 6
INTNAME_OFF  = 0x20                                      # internal game name
INTNAME_LEN  = 0x3E0                                     # até 0x400
_ID36 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def derive_game_id(seed_bytes, prefix=b"DL"):
    """Game ID de 6 bytes determinístico a partir de um seed (ex.: o .dol).
    Mesmo .dol -> mesmo ID (rebuild estável); .dol diferente -> ID diferente."""
    h = int.from_bytes(hashlib.sha1(seed_bytes).digest()[:8], "big")
    tail = bytearray()
    for _ in range(GAMEID_LEN - len(prefix)):
        h, r = divmod(h, len(_ID36))
        tail.append(ord(_ID36[r]))
    return bytes(prefix) + bytes(tail)


# --- branding do banner dentro do gbi.hdr (system area) ---------------------
BNR1_OFF      = 0x43C0
PIXELDATA_OFF = 0x43E0
PIXELDATA_LEN = 96 * 32 * 2                              # 6144
BANNER_W, BANNER_H = 96, 32
DESC_OFF = 0x5BE0
DESC_FIELDS = [
    (0x00, 0x20, "title"),
    (0x20, 0x20, "subtitle"),
    (0x40, 0x40, "title"),
    (0x80, 0x40, "subtitle"),
    (0xC0, 0x80, "subtitle"),
]

# data fixa p/ os campos do ISO (determinístico, sem relógio)
_DIR_DATETIME = bytes([125, 1, 1, 0, 0, 0, 0])           # 2025-01-01 00:00:00 GMT
_NO_DATE = b"0000000000000000\x00"                       # 16x '0' + tz 0


def _be16(n):  return struct.pack(">H", n)
def _le16(n):  return struct.pack("<H", n)
def _both16(n): return struct.pack("<H", n) + struct.pack(">H", n)
def _both32(n): return struct.pack("<I", n) + struct.pack(">I", n)


# --------------------------------------------------------------------------- #
# Banner: imagem qualquer -> 96x32 RGB5A3 GX-tiled
# --------------------------------------------------------------------------- #
def _to_rgb5a3(r, g, b, a):
    if a >= 0xE0:
        return 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
    return ((a >> 5) << 12) | ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)


def image_to_banner(path, stretch=False):
    """Converte uma imagem (qualquer formato/tamanho) no pixelData RGB5A3 96x32."""
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", (BANNER_W, BANNER_H), (0, 0, 0, 0))
    if stretch:
        canvas = img.resize((BANNER_W, BANNER_H), Image.LANCZOS)
    else:
        fit = img.copy()
        fit.thumbnail((BANNER_W, BANNER_H), Image.LANCZOS)
        canvas.paste(fit, ((BANNER_W - fit.width) // 2,
                           (BANNER_H - fit.height) // 2))
    px = canvas.load()
    out = bytearray()
    for ty in range(0, BANNER_H, 4):                     # tiles 4x4: cima->baixo
        for tx in range(0, BANNER_W, 4):                 #           esq->dir
            for yy in range(4):
                for xx in range(4):
                    r, g, b, a = px[tx + xx, ty + yy]
                    out += struct.pack(">H", _to_rgb5a3(r, g, b, a))
    assert len(out) == PIXELDATA_LEN, len(out)
    return bytes(out)


def brand_system_area(gbi_bytes, banner_path=None, stretch=False,
                      title=None, subtitle=None, game_id=None):
    """Devolve uma cópia do gbi.hdr (32768 bytes) com banner/títulos reescritos.

    game_id: 6 bytes para o Game ID do disco (chave de cache do banner no
    cubiboot). None = mantém o ID do gbi.hdr stock (causa colisão entre .iso!)."""
    buf = bytearray(gbi_bytes)
    if len(buf) != SYSTEM_AREA_SIZE:
        raise ValueError(f"gbi.hdr must be {SYSTEM_AREA_SIZE} bytes, got {len(buf)}")
    if buf[BNR1_OFF:BNR1_OFF + 4] != b"BNR1":
        raise ValueError("BNR1 magic not at 0x43C0 — unexpected gbi.hdr")

    if game_id is not None:
        gid = bytes(game_id)[:GAMEID_LEN].ljust(GAMEID_LEN, b"\x00")
        buf[GAMEID_OFF:GAMEID_OFF + GAMEID_LEN] = gid
        # nome interno do jogo: ajuda o loader a diferenciar/rotular os discos
        if title:
            buf[INTNAME_OFF:INTNAME_OFF + INTNAME_LEN] = b"\x00" * INTNAME_LEN
            enc = title.encode("ascii", "replace")[:INTNAME_LEN - 1]
            buf[INTNAME_OFF:INTNAME_OFF + len(enc)] = enc

    if banner_path:
        buf[PIXELDATA_OFF:PIXELDATA_OFF + PIXELDATA_LEN] = \
            image_to_banner(banner_path, stretch)

    # None  -> não mexe no campo (mantém o texto do gbi.hdr stock)
    # ""    -> limpa o campo (deixa em branco)
    # texto -> grava o texto
    vals = {"title": title, "subtitle": subtitle}
    for off, length, key in DESC_FIELDS:
        text = vals.get(key)
        if text is None:
            continue
        base = DESC_OFF + off
        buf[base:base + length] = b"\x00" * length
        enc = text.encode("ascii", "replace")[:length - 1]
        buf[base:base + len(enc)] = enc
    return bytes(buf)


# --------------------------------------------------------------------------- #
# Estruturas ISO9660 / El-Torito
# --------------------------------------------------------------------------- #
def _dir_record(extent_lba, data_len, flags, file_id):
    fi_len = len(file_id)
    total = 33 + fi_len
    total += total & 1                                   # pad p/ par
    rec = bytearray()
    rec.append(total)
    rec.append(0)                                        # ext attr len
    rec += _both32(extent_lba)
    rec += _both32(data_len)
    rec += _DIR_DATETIME
    rec.append(flags)
    rec.append(0)                                        # file unit size
    rec.append(0)                                        # interleave gap
    rec += _both16(1)                                    # vol seq number
    rec.append(fi_len)
    rec += file_id
    if len(rec) < total:
        rec += b"\x00" * (total - len(rec))
    return bytes(rec)


def _build_pvd(total_sectors, path_table_size):
    buf = bytearray(SECTOR)
    buf[0] = 1
    buf[1:6] = b"CD001"
    buf[6] = 1
    buf[8:40] = b" " * 32                                # system id
    vid = b"DOL2ISO"
    buf[40:72] = vid + b" " * (32 - len(vid))            # volume id
    buf[80:88] = _both32(total_sectors)                  # volume space size
    buf[120:124] = _both16(1)                            # volume set size
    buf[124:128] = _both16(1)                            # volume seq number
    buf[128:132] = _both16(SECTOR)                       # logical block size
    buf[132:140] = _both32(path_table_size)
    buf[140:144] = struct.pack("<I", LBA_PT_L)           # type-L path table
    buf[148:152] = struct.pack(">I", LBA_PT_M)           # type-M path table
    buf[156:190] = _dir_record(LBA_ROOT, SECTOR, 0x02, b"\x00")  # root dir record
    for a, b in ((190, 318), (318, 446), (446, 574), (574, 702)):
        buf[a:b] = b" " * (b - a)                        # set/pub/prep/app id
    for a, b in ((702, 739), (739, 776), (776, 813)):
        buf[a:b] = b" " * (b - a)                        # copyright/abstract/biblio
    buf[813:830] = _NO_DATE                              # creation
    buf[830:847] = _NO_DATE                              # modification
    buf[847:864] = _NO_DATE                              # expiration
    buf[864:881] = _NO_DATE                              # effective
    buf[881] = 1                                         # file structure version
    return bytes(buf)


def _build_boot_record():
    buf = bytearray(SECTOR)
    buf[0] = 0
    buf[1:6] = b"CD001"
    buf[6] = 1
    bsid = b"EL TORITO SPECIFICATION"
    buf[7:7 + len(bsid)] = bsid                          # boot_system_id (até 0x27)
    buf[71:75] = struct.pack("<I", LBA_BOOTCAT)          # boot_catalog_offset @0x47
    return bytes(buf)


def _build_terminator():
    buf = bytearray(SECTOR)
    buf[0] = 255
    buf[1:6] = b"CD001"
    buf[6] = 1
    return bytes(buf)


def _build_path_table(big_endian):
    rec = bytearray()
    rec.append(1)                                        # len dir id (root = 1)
    rec.append(0)                                        # ext attr len
    if big_endian:
        rec += struct.pack(">I", LBA_ROOT)
        rec += struct.pack(">H", 1)                      # parent number
    else:
        rec += struct.pack("<I", LBA_ROOT)
        rec += struct.pack("<H", 1)
    rec.append(0)                                        # dir id (root)
    rec.append(0)                                        # pad p/ par
    return bytes(rec)                                    # 10 bytes


def _build_root_dir(dol_size):
    data = bytearray()
    data += _dir_record(LBA_ROOT, SECTOR, 0x02, b"\x00")          # "."
    data += _dir_record(LBA_ROOT, SECTOR, 0x02, b"\x01")          # ".."
    data += _dir_record(LBA_BOOTCAT, SECTOR, 0x00, b"BOOT.CAT;1")
    data += _dir_record(LBA_DOL, dol_size, 0x00, b"BOOT.DOL;1")
    return bytes(data)


def _build_boot_catalog(dol_size):
    cat = bytearray(SECTOR)
    # validation entry
    ve = bytearray(32)
    ve[0] = 1                                            # header id
    ve[1] = 0                                            # platform id (x86; ignorado)
    ve[30] = 0x55
    ve[31] = 0xAA
    s = sum(struct.unpack("<16H", bytes(ve))) & 0xFFFF
    struct.pack_into("<H", ve, 28, (-s) & 0xFFFF)        # checksum
    cat[0:32] = ve
    # default entry @0x20
    de = bytearray(32)
    de[0] = 0x88                                         # bootable
    de[1] = 0                                            # no emulation
    struct.pack_into("<H", de, 2, 0)                     # load segment
    sector_count = math.ceil(dol_size / 512)
    if sector_count > 0xFFFF:
        raise ValueError(".dol too large for El-Torito (16-bit sector_count; "
                         "max ~32 MB)")
    struct.pack_into("<H", de, 6, sector_count)
    struct.pack_into("<I", de, 8, LBA_DOL)              # load_rba
    cat[0x20:0x40] = de
    return bytes(cat)


def _pad(data, size):
    if len(data) > size:
        raise ValueError("data larger than the sector")
    return data + b"\x00" * (size - len(data))


# --------------------------------------------------------------------------- #
# API principal
# --------------------------------------------------------------------------- #
def build_iso(dol_bytes, system_area, out_path):
    """Escreve a .iso bootável em out_path. system_area = gbi.hdr (32768 bytes)."""
    if len(system_area) != SYSTEM_AREA_SIZE:
        raise ValueError("system_area (gbi.hdr) must be 32768 bytes")
    dol_size = len(dol_bytes)
    if dol_size == 0:
        raise ValueError(".dol is empty")

    dol_sectors = math.ceil(dol_size / SECTOR)
    total_sectors = LBA_DOL + dol_sectors
    pt = _build_path_table(False)

    with open(out_path, "wb") as f:
        f.write(system_area)                                     # 0..15
        f.write(_build_pvd(total_sectors, len(pt)))              # 16
        f.write(_build_boot_record())                            # 17
        f.write(_build_terminator())                             # 18
        f.write(_pad(_build_path_table(False), SECTOR))          # 19
        f.write(_pad(_build_path_table(True), SECTOR))           # 20
        f.write(_pad(_build_root_dir(dol_size), SECTOR))         # 21
        f.write(_build_boot_catalog(dol_size))                   # 22
        f.write(_pad(dol_bytes, dol_sectors * SECTOR))           # 23..
    return total_sectors * SECTOR


def make_bootable_iso(dol_path, out_path, gbi_path,
                      banner_path=None, stretch=False,
                      title=None, subtitle=None, game_id=None):
    """Conveniência: lê arquivos, aplica branding, gera a .iso. Retorna bytes escritos.

    game_id: None = gera automaticamente um ID único a partir do conteúdo do .dol
    (cada jogo recebe um ID estável e distinto, evitando colisão de banner no
    cubiboot). Passe 6 bytes/str para forçar um ID específico."""
    with open(dol_path, "rb") as f:
        dol_bytes = f.read()
    with open(gbi_path, "rb") as f:
        gbi_bytes = f.read()
    if game_id is None:
        game_id = derive_game_id(dol_bytes)
    elif isinstance(game_id, str):
        game_id = game_id.encode("ascii", "replace")
    system_area = brand_system_area(gbi_bytes, banner_path, stretch,
                                    title, subtitle, game_id=game_id)
    return build_iso(dol_bytes, system_area, out_path)
