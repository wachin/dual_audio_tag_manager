#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dual Audio Tag Manager
Aplicación multiplataforma (Windows/Linux) en PyQt6 para comparar dos colecciones
de música y copiar carátulas y metadatos entre archivos.

- Doble panel tipo Total Commander/Krusader
- QTreeView con QFileSystemModel filtrando audio
- Barra de ruta tipo Explorer (breadcrumb clicable) con soporte para discos Windows (C:, F:, etc)
- Vista previa de carátula embebida
- Vista de tags: Título, Artista, Álbum, Año, Pista, Género, Comentario, Álbum Artista, Compositor
- Botón para copiar carátula (izq -> der)
- Botón para copiar tags (izq -> der) (requisito “copiar metadatos entre ellas”)
- Persistencia de estado (carpetas, seleccionado, scroll, columnas, splitter, ventana, maximizado)
- Configuración en .ini usando QSettings IniFormat UserScope
- Modo oscuro profesional (incluye QSS para checkboxes en tablas + palette Link/LinkVisited)

Licencia: GPL3
"""

from __future__ import annotations

import base64
import os
import sys
import traceback
import ctypes

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import (
    Qt,
    QDir,
    QSettings,
    QSize,
    QTimer,
    QModelIndex,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QIcon,
    QPixmap,
    QPalette,
    QColor,
    QFileSystemModel,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeView,
    QLabel,
    QPushButton,
    QMessageBox,
    QSplitter,
    QToolButton,
    QSizePolicy,
    QFrame,
    QHeaderView,
    QFormLayout,
    QScrollArea,
    QMenu,
)

# ---------- Backend: lectura/escritura de tags y carátulas (mutagen) ----------
# Nota: mutagen es muy práctico para manejar múltiples formatos.
try:
    from mutagen import File as MFile
    from mutagen.id3 import ID3, APIC, ID3NoHeaderError
    from mutagen.flac import FLAC, Picture
    from mutagen.oggvorbis import OggVorbis
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.easyid3 import EasyID3
except Exception as e:
    MFile = None
    _MUTAGEN_IMPORT_ERROR = e
else:
    _MUTAGEN_IMPORT_ERROR = None


AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".m4a"}

CANON_FIELDS = [
    ("title", "Título"),
    ("artist", "Artista"),
    ("album", "Álbum"),
    ("year", "Año"),
    ("track", "Pista"),
    ("genre", "Género"),
    ("comment", "Comentario"),
    ("albumartist", "Álbum Artista"),
    ("composer", "Compositor"),
]

def list_windows_drives() -> list[str]:
    """
    Devuelve ['C:\\', 'D:\\', 'F:\\', ...] de forma confiable en Windows.
    """
    drives = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                drives.append(f"{chr(65+i)}:\\")
    except Exception:
        # Fallback simple
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            p = f"{letter}:\\"
            if os.path.exists(p):
                drives.append(p)
    return drives


def list_linux_mount_points() -> list[str]:
    """
    Lista puntos de montaje comunes en Linux.
    """
    candidates = ["/", "/mnt", "/media", "/run/media"]
    out = []
    for c in candidates:
        if os.path.isdir(c):
            out.append(c)
            # añadir subdirectorios (montajes típicos)
            try:
                for name in sorted(os.listdir(c)):
                    full = os.path.join(c, name)
                    if os.path.isdir(full):
                        out.append(full)
            except Exception:
                pass
    # quitar duplicados manteniendo orden
    seen = set()
    uniq = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def list_roots_for_platform() -> list[str]:
    if os.name == "nt":
        return list_windows_drives()
    return list_linux_mount_points()


def is_audio_file(path: str) -> bool:
    try:
        return Path(path).suffix.lower() in AUDIO_EXTS and Path(path).is_file()
    except Exception:
        return False


def guess_mime_from_bytes(data: bytes) -> str:
    # Muy simple: reconocer JPEG/PNG por firma.
    if data.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg"


def get_audio_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    return ext.lstrip(".")


def safe_str(x) -> str:
    if x is None:
        return ""
    if isinstance(x, (list, tuple)):
        if not x:
            return ""
        return str(x[0])
    return str(x)


def _mutagen_load(path: str):
    if _MUTAGEN_IMPORT_ERROR is not None:
        raise RuntimeError(f"mutagen no está disponible: {_MUTAGEN_IMPORT_ERROR}")
    audio = MFile(path)
    if audio is None:
        raise RuntimeError("No se pudo abrir el archivo (formato no soportado o corrupto).")
    return audio


def get_cover_bytes(path: str) -> Optional[Tuple[bytes, str]]:
    """
    Devuelve (bytes, mime) de la carátula embebida, o None si no hay.
    Soporta MP3, FLAC, OGG Vorbis (METADATA_BLOCK_PICTURE), M4A/MP4.
    """
    kind = get_audio_kind(path)

    if kind == "mp3":
        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            return None
        apics = id3.getall("APIC")
        if not apics:
            return None
        data = apics[0].data
        mime = apics[0].mime or guess_mime_from_bytes(data)
        return data, mime

    if kind == "flac":
        fl = FLAC(path)
        if not fl.pictures:
            return None
        pic = fl.pictures[0]
        mime = pic.mime or guess_mime_from_bytes(pic.data)
        return pic.data, mime

    if kind == "ogg":
        og = OggVorbis(path)
        # En Vorbis, las imágenes suelen ir en METADATA_BLOCK_PICTURE (base64 de FLAC Picture)
        b64 = None
        for k in ("metadata_block_picture", "METADATA_BLOCK_PICTURE"):
            if k in og.tags:
                vals = og.tags.get(k)
                if vals:
                    b64 = vals[0]
                    break
        if not b64:
            return None
        try:
            raw = base64.b64decode(b64)
            pic = Picture(raw)
            mime = pic.mime or guess_mime_from_bytes(pic.data)
            return pic.data, mime
        except Exception:
            return None

    if kind == "m4a":
        mp = MP4(path)
        covr = mp.tags.get("covr") if mp.tags else None
        if not covr:
            return None
        cover = covr[0]
        data = bytes(cover)
        # mutagen indica formato en MP4Cover.imageformat
        mime = "image/png" if getattr(cover, "imageformat", None) == MP4Cover.FORMAT_PNG else "image/jpeg"
        return data, mime

    return None


def set_cover_bytes(path: str, data: bytes, mime: str) -> None:
    """
    Escribe carátula embebida en el archivo destino.
    Limpia carátulas previas y deja una principal.
    """
    kind = get_audio_kind(path)

    if kind == "mp3":
        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            id3 = ID3()
        # Limpiar APIC existentes
        for frame in id3.getall("APIC"):
            id3.delall("APIC")
            break
        id3.add(
            APIC(
                encoding=3,   # UTF-8
                mime=mime or guess_mime_from_bytes(data),
                type=3,       # Cover (front)
                desc="Cover",
                data=data,
            )
        )
        id3.save(path)
        return

    if kind == "flac":
        fl = FLAC(path)
        fl.clear_pictures()
        pic = Picture()
        pic.type = 3
        pic.mime = mime or guess_mime_from_bytes(data)
        pic.desc = "Cover"
        pic.data = data
        fl.add_picture(pic)
        fl.save()
        return

    if kind == "ogg":
        og = OggVorbis(path)
        pic = Picture()
        pic.type = 3
        pic.mime = mime or guess_mime_from_bytes(data)
        pic.desc = "Cover"
        pic.data = data
        b64 = base64.b64encode(pic.write()).decode("ascii")
        # limpiar ambos keys posibles
        for k in ("metadata_block_picture", "METADATA_BLOCK_PICTURE"):
            if k in og.tags:
                del og.tags[k]
        og.tags["METADATA_BLOCK_PICTURE"] = [b64]
        og.save()
        return

    if kind == "m4a":
        mp = MP4(path)
        if mp.tags is None:
            mp.add_tags()
        fmt = MP4Cover.FORMAT_PNG if (mime or "").lower().endswith("png") else MP4Cover.FORMAT_JPEG
        mp.tags["covr"] = [MP4Cover(data, imageformat=fmt)]
        mp.save()
        return

    raise RuntimeError("Formato no soportado para escribir carátula.")


def get_tags(path: str) -> Dict[str, str]:
    """
    Retorna tags en campos canónicos:
    title, artist, album, year, track, genre, comment, albumartist, composer
    """
    kind = get_audio_kind(path)
    out = {k: "" for k, _ in CANON_FIELDS}

    if kind == "mp3":
        # EasyID3 maneja mapeo de frames comunes.
        try:
            audio = EasyID3(path)
        except Exception:
            audio = EasyID3()
        out["title"] = safe_str(audio.get("title"))
        out["artist"] = safe_str(audio.get("artist"))
        out["album"] = safe_str(audio.get("album"))
        out["year"] = safe_str(audio.get("date")) or safe_str(audio.get("year"))
        out["track"] = safe_str(audio.get("tracknumber"))
        out["genre"] = safe_str(audio.get("genre"))
        out["comment"] = safe_str(audio.get("comment"))
        out["albumartist"] = safe_str(audio.get("albumartist"))
        out["composer"] = safe_str(audio.get("composer"))
        return out

    if kind == "flac":
        fl = FLAC(path)
        tags = fl.tags or {}
        out["title"] = safe_str(tags.get("TITLE"))
        out["artist"] = safe_str(tags.get("ARTIST"))
        out["album"] = safe_str(tags.get("ALBUM"))
        out["year"] = safe_str(tags.get("DATE"))
        out["track"] = safe_str(tags.get("TRACKNUMBER"))
        out["genre"] = safe_str(tags.get("GENRE"))
        out["comment"] = safe_str(tags.get("COMMENT"))
        out["albumartist"] = safe_str(tags.get("ALBUMARTIST"))
        out["composer"] = safe_str(tags.get("COMPOSER"))
        return out

    if kind == "ogg":
        og = OggVorbis(path)
        tags = og.tags or {}
        # VorbisComment suele ser case-insensitive; mutagen entrega keys normalizadas en el dict.
        def g(key: str) -> str:
            # intentar variantes
            for k in (key, key.upper(), key.lower()):
                if k in tags:
                    return safe_str(tags.get(k))
            return ""
        out["title"] = g("TITLE")
        out["artist"] = g("ARTIST")
        out["album"] = g("ALBUM")
        out["year"] = g("DATE")
        out["track"] = g("TRACKNUMBER")
        out["genre"] = g("GENRE")
        out["comment"] = g("COMMENT")
        out["albumartist"] = g("ALBUMARTIST")
        out["composer"] = g("COMPOSER")
        return out

    if kind == "m4a":
        mp = MP4(path)
        tags = mp.tags or {}
        out["title"] = safe_str(tags.get("\xa9nam"))
        out["artist"] = safe_str(tags.get("\xa9ART"))
        out["album"] = safe_str(tags.get("\xa9alb"))
        out["year"] = safe_str(tags.get("\xa9day"))
        trkn = tags.get("trkn")
        if trkn and isinstance(trkn, list) and trkn and isinstance(trkn[0], tuple):
            out["track"] = str(trkn[0][0]) if trkn[0][0] else ""
        else:
            out["track"] = ""
        out["genre"] = safe_str(tags.get("\xa9gen"))
        out["comment"] = safe_str(tags.get("\xa9cmt"))
        out["albumartist"] = safe_str(tags.get("aART"))
        out["composer"] = safe_str(tags.get("\xa9wrt"))
        return out

    return out


def set_tags(path: str, tags_in: Dict[str, str]) -> None:
    """
    Escribe tags desde el dict canónico.
    Respeta campos vacíos: si está vacío, limpia ese tag del destino.
    """
    kind = get_audio_kind(path)

    def norm(v: str) -> str:
        return (v or "").strip()

    t = {k: norm(tags_in.get(k, "")) for k, _ in CANON_FIELDS}

    if kind == "mp3":
        try:
            audio = EasyID3(path)
        except Exception:
            audio = EasyID3()
        def set_or_del(key: str, val: str):
            if val:
                audio[key] = [val]
            else:
                if key in audio:
                    del audio[key]

        set_or_del("title", t["title"])
        set_or_del("artist", t["artist"])
        set_or_del("album", t["album"])
        # Usamos "date" para año
        set_or_del("date", t["year"])
        set_or_del("tracknumber", t["track"])
        set_or_del("genre", t["genre"])
        set_or_del("comment", t["comment"])
        set_or_del("albumartist", t["albumartist"])
        set_or_del("composer", t["composer"])

        audio.save(path)
        return

    if kind == "flac":
        fl = FLAC(path)
        if fl.tags is None:
            fl.add_tags()

        def set_or_del(key: str, val: str):
            if val:
                fl.tags[key] = [val]
            else:
                if key in fl.tags:
                    del fl.tags[key]

        set_or_del("TITLE", t["title"])
        set_or_del("ARTIST", t["artist"])
        set_or_del("ALBUM", t["album"])
        set_or_del("DATE", t["year"])
        set_or_del("TRACKNUMBER", t["track"])
        set_or_del("GENRE", t["genre"])
        set_or_del("COMMENT", t["comment"])
        set_or_del("ALBUMARTIST", t["albumartist"])
        set_or_del("COMPOSER", t["composer"])

        fl.save()
        return

    if kind == "ogg":
        og = OggVorbis(path)
        if og.tags is None:
            og.add_tags()

        def set_or_del(key: str, val: str):
            # VorbisComment usa keys típicamente en MAYÚSCULAS.
            k = key.upper()
            if val:
                og.tags[k] = [val]
            else:
                if k in og.tags:
                    del og.tags[k]

        set_or_del("TITLE", t["title"])
        set_or_del("ARTIST", t["artist"])
        set_or_del("ALBUM", t["album"])
        set_or_del("DATE", t["year"])
        set_or_del("TRACKNUMBER", t["track"])
        set_or_del("GENRE", t["genre"])
        set_or_del("COMMENT", t["comment"])
        set_or_del("ALBUMARTIST", t["albumartist"])
        set_or_del("COMPOSER", t["composer"])

        og.save()
        return

    if kind == "m4a":
        mp = MP4(path)
        if mp.tags is None:
            mp.add_tags()

        def set_or_del(key: str, val):
            if val is None or val == "" or (isinstance(val, list) and not val):
                if key in mp.tags:
                    del mp.tags[key]
            else:
                mp.tags[key] = val

        set_or_del("\xa9nam", [t["title"]] if t["title"] else "")
        set_or_del("\xa9ART", [t["artist"]] if t["artist"] else "")
        set_or_del("\xa9alb", [t["album"]] if t["album"] else "")
        set_or_del("\xa9day", [t["year"]] if t["year"] else "")
        # track: (tracknum, total) - aquí solo tracknum
        if t["track"].isdigit():
            set_or_del("trkn", [(int(t["track"]), 0)])
        else:
            set_or_del("trkn", "")
        set_or_del("\xa9gen", [t["genre"]] if t["genre"] else "")
        set_or_del("\xa9cmt", [t["comment"]] if t["comment"] else "")
        set_or_del("aART", [t["albumartist"]] if t["albumartist"] else "")
        set_or_del("\xa9wrt", [t["composer"]] if t["composer"] else "")

        mp.save()
        return

    raise RuntimeError("Formato no soportado para escribir tags.")


# ---------- UI: Breadcrumb bar ----------
class BreadcrumbBar(QWidget):
    """
    Barra de ruta tipo Explorer: C:\ > Users > Usuario > Música > Álbum
    Cada segmento es clicable.

    Emite pathClicked(str) con la ruta absoluta del segmento.
    """
    pathClicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(2)
        self._path = ""

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setPath(self, path: str):
        path = os.path.abspath(path) if path else ""
        if self._path == path:
            return
        self._path = path
        self._rebuild()

    def path(self) -> str:
        return self._path

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _is_windows_path(self, p: str) -> bool:
        # Detectar si parece ruta Windows: "C:\" o "C:/" o UNC "\\server\share"
        if p.startswith("\\\\"):
            return True
        if len(p) >= 2 and p[1] == ":":
            return True
        return False

    def _segments(self, path: str) -> Tuple[str, list]:
        """
        Retorna (root_segment, [rest...]) donde root_segment es:
        - Windows drive "C:\"
        - UNC "\\server\share\"
        - Linux "/" (root)
        """
        if not path:
            return "", []

        if self._is_windows_path(path):
            pw = PureWindowsPath(path)
            # UNC: \\server\share\folder...
            if str(pw).startswith("\\\\"):
                parts = pw.parts  # ('\\\\server\\share\\', 'folder', ...)
                root = parts[0]  # '\\\\server\\share\\'
                rest = list(parts[1:])
                return root, rest
            # Drive: ('C:\\', 'Users', ...)
            parts = pw.parts
            root = parts[0]  # 'C:\\'
            rest = list(parts[1:])
            return root, rest

        pp = PurePosixPath(path)
        parts = pp.parts  # ('/', 'home', 'user', ...)
        root = parts[0] if parts else "/"
        rest = list(parts[1:]) if len(parts) > 1 else []
        return root, rest

    def _join(self, root: str, rest: list) -> str:
        if self._is_windows_path(root) or root.startswith("\\\\"):
            # Usar PureWindowsPath para recomponer
            if root.startswith("\\\\"):
                # root ya contiene el share completo
                p = PureWindowsPath(root)
                for seg in rest:
                    p = p / seg
                return str(p)
            else:
                p = PureWindowsPath(root)
                for seg in rest:
                    p = p / seg
                return str(p)
        else:
            p = PurePosixPath(root)
            for seg in rest:
                p = p / seg
            return str(p)

    def _make_btn(self, text: str, full_path: str) -> QToolButton:
        b = QToolButton(self)
        b.setText(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setAutoRaise(True)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        b.clicked.connect(lambda: self.pathClicked.emit(full_path))
        return b

    def _make_sep(self) -> QLabel:
        lab = QLabel(">", self)
        lab.setContentsMargins(4, 0, 4, 0)
        lab.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lab.setObjectName("BreadcrumbSep")
        return lab

    def _rebuild(self):
        self._clear()
        if not self._path or not os.path.exists(self._path):
            # Mostrar algo simple
            empty = QLabel("", self)
            self._layout.addWidget(empty, 1)
            return

        root, rest = self._segments(self._path)
        acc = []  # acumulados desde root

        # Botón root (drive o "/")
        full_root = self._join(root, [])
        root_text = root.rstrip("\\/") if (root.endswith("\\") or root.endswith("/")) else root
        if not root_text:
            root_text = root

        self._layout.addWidget(self._make_btn(root_text, full_root))

        # Resto de segmentos
        for i, seg in enumerate(rest):
            self._layout.addWidget(self._make_sep())
            acc.append(seg)
            full = self._join(root, acc)
            self._layout.addWidget(self._make_btn(seg, full))

        self._layout.addStretch(1)


# ---------- UI: Panel (izquierdo/derecho) ----------
@dataclass
class PanelState:
    root_path: str = ""
    selected_file: str = ""
    vscroll: int = 0
    header_sizes: Tuple[int, int, int, int] = (250, 120, 120, 120)
    splitter_sizes: Tuple[int, int] = (600, 260)


class AudioPanel(QWidget):
    """
    Un panel completo: breadcrumb + QTreeView + info (carátula + tags)
    """
    selectionChanged = pyqtSignal()

    def _rebuild_roots_menu(self):
        self.roots_menu.clear()
        roots = list_roots_for_platform()

        if not roots:
            act = self.roots_menu.addAction("(sin unidades)")
            act.setEnabled(False)
            return

        for r in roots:
            label = r
            act = self.roots_menu.addAction(label)
            act.triggered.connect(lambda checked=False, path=r: self.set_root_path(path))

    def __init__(self, settings: QSettings, key_prefix: str, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.key_prefix = key_prefix

        self.model = QFileSystemModel(self)
        self.model.setRootPath(QDir.rootPath())
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Files)

        # Filtrar extensiones de audio
        filters = ["*.mp3", "*.flac", "*.ogg", "*.m4a"]
        self.model.setNameFilters(filters)
        self.model.setNameFilterDisables(False)

        self.tree = QTreeView(self)
        self.tree.setModel(self.model)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.doubleClicked.connect(self._on_double_clicked)
        self.tree.selectionModel().selectionChanged.connect(lambda *_: self._on_selection_changed())

        # Vista tipo “explorer”: mostrar columnas típicas (Name, Size, Type, Date Modified)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        self.breadcrumb = BreadcrumbBar(self)
        self.breadcrumb.pathClicked.connect(self.set_root_path)

        # Info inferior: carátula + tags
        self.cover_label = QLabel(self)
        self.cover_label.setMinimumSize(120, 120)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.cover_label.setObjectName("CoverPreview")
        self.cover_label.setText("Sin carátula")

        self.tags_widget = QWidget(self)
        self.tags_form = QFormLayout(self.tags_widget)
        self.tags_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.tags_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.tag_value_labels: Dict[str, QLabel] = {}

        for key, label in CANON_FIELDS:
            v = QLabel("", self.tags_widget)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.setWordWrap(True)
            v.setObjectName("TagValue")
            self.tag_value_labels[key] = v
            self.tags_form.addRow(QLabel(label + ":", self.tags_widget), v)

        info_container = QWidget(self)
        info_layout = QHBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(10)
        info_layout.addWidget(self.cover_label, 0)

        # Tags con scroll (por si hay textos largos)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.tags_widget)
        info_layout.addWidget(scroll, 1)

        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(info_container)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Barra superior: botón Unidades + breadcrumb
        topbar = QWidget(self)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(0, 0, 0, 0)
        topbar_layout.setSpacing(6)

        self.btn_roots = QToolButton(self)

        self.btn_roots.setText("🖴")
        self.btn_roots.setToolTip("Unidades / Discos")

        self.btn_roots.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self.roots_menu = QMenu(self)

        self.btn_roots.setMenu(self.roots_menu)
        self.btn_roots.aboutToShow = None  # no existe en QToolButton, así que hacemos esto:
        self.roots_menu.aboutToShow.connect(self._rebuild_roots_menu)
        self._rebuild_roots_menu()

        topbar_layout.addWidget(self.btn_roots, 0)
        topbar_layout.addWidget(self.breadcrumb, 1)

        layout.addWidget(topbar, 0)
        layout.addWidget(self.splitter, 1)

        # Estado actual
        self._cover_target_size = 220  # se ajusta desde menú “Tamaño carátula”
        self._last_loaded_file = ""

    def set_cover_size(self, px: int):
        self._cover_target_size = max(80, int(px))
        self._refresh_cover(self.selected_file_path())

    def set_root_path(self, path: str):
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            return
        idx = self.model.index(path)
        if idx.isValid():
            self.tree.setRootIndex(idx)
            self.breadcrumb.setPath(path)

    def root_path(self) -> str:
        idx = self.tree.rootIndex()
        return self.model.filePath(idx) if idx.isValid() else QDir.rootPath()

    def selected_file_path(self) -> str:
        idxs = self.tree.selectionModel().selectedRows()
        if not idxs:
            return ""
        p = self.model.filePath(idxs[0])
        return p if is_audio_file(p) else ""

    def _on_double_clicked(self, index: QModelIndex):
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.set_root_path(path)

    def _on_selection_changed(self):
        f = self.selected_file_path()
        self._refresh_info(f)
        self.selectionChanged.emit()

    def _refresh_info(self, file_path: str):
        self._refresh_cover(file_path)
        self._refresh_tags(file_path)

    def _refresh_cover(self, file_path: str):
        self.cover_label.setText("Sin carátula")
        self.cover_label.setPixmap(QPixmap())

        if not file_path:
            return

        try:
            cover = get_cover_bytes(file_path)
            if not cover:
                self.cover_label.setText("Sin carátula")
                return
            data, _mime = cover
            pix = QPixmap()
            if not pix.loadFromData(data):
                self.cover_label.setText("Carátula inválida")
                return
            scaled = pix.scaled(
                QSize(self._cover_target_size, self._cover_target_size),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.cover_label.setPixmap(scaled)
        except Exception:
            self.cover_label.setText("Error al leer carátula")

    def _refresh_tags(self, file_path: str):
        for key, _ in CANON_FIELDS:
            self.tag_value_labels[key].setText("")

        if not file_path:
            return

        try:
            tags = get_tags(file_path)
            for key, _ in CANON_FIELDS:
                self.tag_value_labels[key].setText(tags.get(key, ""))
        except Exception:
            # Mantener vacío; no romper UI.
            pass

    # -------- Persistencia --------
    def save_state(self):
        prefix = self.key_prefix
        self.settings.setValue(f"{prefix}/root_path", self.root_path())
        self.settings.setValue(f"{prefix}/selected_file", self.selected_file_path())

        # Scroll vertical
        vs = self.tree.verticalScrollBar().value()
        self.settings.setValue(f"{prefix}/vscroll", int(vs))

        # Ancho de columnas
        header = self.tree.header()
        sizes = [header.sectionSize(i) for i in range(min(4, header.count()))]
        self.settings.setValue(f"{prefix}/header_sizes", sizes)

        # Splitter interno
        self.settings.setValue(f"{prefix}/splitter_sizes", self.splitter.sizes())

    def restore_state(self, default_path: str):
        prefix = self.key_prefix

        root_path = self.settings.value(f"{prefix}/root_path", default_path, type=str)
        if not root_path or not os.path.isdir(root_path):
            root_path = default_path

        self.set_root_path(root_path)

        # Header sizes
        sizes = self.settings.value(f"{prefix}/header_sizes", None)
        if isinstance(sizes, list) and sizes:
            header = self.tree.header()
            for i, w in enumerate(sizes[: min(4, header.count())]):
                try:
                    header.resizeSection(i, int(w))
                except Exception:
                    pass

        # Splitter sizes
        sp = self.settings.value(f"{prefix}/splitter_sizes", None)
        if isinstance(sp, list) and len(sp) >= 2:
            try:
                self.splitter.setSizes([int(sp[0]), int(sp[1])])
            except Exception:
                pass

        # Selección + scroll: aplicar luego de que Qt procese layout/model
        selected_file = self.settings.value(f"{prefix}/selected_file", "", type=str)
        vscroll = self.settings.value(f"{prefix}/vscroll", 0)
        try:
            vscroll = int(vscroll)
        except Exception:
            vscroll = 0

        def apply_late():
            # seleccionar archivo si está dentro del root actual
            if selected_file and os.path.exists(selected_file):
                idx = self.model.index(selected_file)
                if idx.isValid():
                    self.tree.setCurrentIndex(idx)
                    self.tree.scrollTo(idx, QTreeView.ScrollHint.PositionAtCenter)
            self.tree.verticalScrollBar().setValue(vscroll)
            # refrescar carátula/tags
            self._refresh_info(self.selected_file_path())

        QTimer.singleShot(0, apply_late)


# ---------- Tema oscuro profesional (palette + QSS crítico) ----------
def apply_dark_theme(app: QApplication):
    pal = QPalette()

    window = QColor(30, 30, 30)
    base = QColor(24, 24, 24)
    alt_base = QColor(32, 32, 32)
    text = QColor(220, 220, 220)
    disabled = QColor(140, 140, 140)
    button = QColor(45, 45, 45)

    # Base
    pal.setColor(QPalette.ColorRole.Window, window)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    pal.setColor(QPalette.ColorRole.Text, text)

    # Botones
    pal.setColor(QPalette.ColorRole.Button, button)
    pal.setColor(QPalette.ColorRole.ButtonText, text)

    # Tooltips
    pal.setColor(QPalette.ColorRole.ToolTipBase, base)
    pal.setColor(QPalette.ColorRole.ToolTipText, text)

    # Selección
    pal.setColor(QPalette.ColorRole.Highlight, QColor(90, 90, 90))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    # Links (CRÍTICO por tu requisito)
    pal.setColor(QPalette.ColorRole.Link, QColor(90, 160, 255))
    pal.setColor(QPalette.ColorRole.LinkVisited, QColor(190, 130, 255))

    # Disabled (sin MenuText, porque no existe en Qt6)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)

    app.setPalette(pal)

    # QSS (incluye tus requisitos críticos)
    qss = """
    QWidget {
        font-size: 10.5pt;
    }

    QTreeView {
        border: 1px solid rgba(255,255,255,0.08);
        background: palette(Base);
        alternate-background-color: palette(AlternateBase);
    }

    QLabel#CoverPreview {
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 6px;
        padding: 6px;
        background: rgba(255,255,255,0.03);
    }

    QLabel#TagValue {
        color: palette(Text);
    }

    QLabel#BreadcrumbSep {
        color: rgba(255,255,255,0.55);
    }

    QToolButton {
        padding: 2px 6px;
        border-radius: 6px;
        color: palette(ButtonText);
    }
    QToolButton:hover {
        background: rgba(255,255,255,0.08);
    }

    /* CRÍTICO: indicadores de checkbox en tablas (QTableView/QTableWidget) */
    QTableView::indicator:unchecked {
        width: 14px;
        height: 14px;
        border: 1px solid rgba(255,255,255,0.40);
        background: rgba(180,180,180,0.25);
        border-radius: 3px;
    }
    QTableView::indicator:checked {
        width: 14px;
        height: 14px;
        border: 1px solid rgba(255,255,255,0.40);
        background: rgba(80, 200, 120, 0.85);
        border-radius: 3px;
    }
    QTableWidget::indicator:unchecked {
        width: 14px;
        height: 14px;
        border: 1px solid rgba(255,255,255,0.40);
        background: rgba(180,180,180,0.25);
        border-radius: 3px;
    }
    QTableWidget::indicator:checked {
        width: 14px;
        height: 14px;
        border: 1px solid rgba(255,255,255,0.40);
        background: rgba(80, 200, 120, 0.85);
        border-radius: 3px;
    }

    /* Refuerzo específico para Windows: menú y botones */
    QMenuBar {
        background-color: rgb(30,30,30);
        color: rgb(220,220,220);
    }
    QMenuBar::item:selected {
        background: rgba(255,255,255,0.12);
    }
    QMenu {
        background-color: rgb(30,30,30);
        color: rgb(220,220,220);
    }
    QMenu::item:selected {
        background-color: rgba(255,255,255,0.15);
    }
    QPushButton {
        color: rgb(220,220,220);
    }
    """
    app.setStyleSheet(qss)


def apply_light_theme(app: QApplication):
    # Volver a estilo “del sistema” (sin forzar). Palette por defecto + limpiar QSS.
    app.setStyleSheet("")
    app.setPalette(app.style().standardPalette())


# ---------- Ventana principal ----------
class MainWindow(QMainWindow):
    APP_NAME = "Dual Audio Tag Manager"

    def __init__(self):
        super().__init__()

        # QSettings en IniFormat y UserScope (CRÍTICO)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "")
        self.settings = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                                  "DualAudioTagManager", "DualAudioTagManager")

        self.setWindowTitle(self.APP_NAME)
        self.setMinimumSize(1100, 650)

        # Layout principal: splitter horizontal (panel izq / panel der)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        default_music = str(Path.home() / "Music")
        if not os.path.isdir(default_music):
            default_music = str(Path.home())

        self.left_panel = AudioPanel(self.settings, "left", self)
        self.right_panel = AudioPanel(self.settings, "right", self)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)

        # Zona central + botones de acción
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(6, 6, 6, 6)
        central_layout.setSpacing(6)

        central_layout.addWidget(self.splitter, 1)

        actions_row = QHBoxLayout()
        actions_row.addStretch(1)

        self.btn_copy_cover = QPushButton("Copiar carátula  ⟵  Izq → Der", self)
        self.btn_copy_tags = QPushButton("Copiar tags  ⟵  Izq → Der", self)
        self.btn_copy_cover.clicked.connect(self.copy_cover_left_to_right)
        self.btn_copy_tags.clicked.connect(self.copy_tags_left_to_right)

        actions_row.addWidget(self.btn_copy_cover)
        actions_row.addWidget(self.btn_copy_tags)

        central_layout.addLayout(actions_row, 0)

        self.setCentralWidget(central)

        # Menú
        self._build_menu()

        # Tamaño de carátula (default: mediana)
        self.cover_sizes = {
            "pequeña": 140,
            "mediana": 220,
            "grande": 320,
        }
        self.current_cover_size_key = "mediana"
        self._apply_cover_size_to_panels()

        # Tema (default: oscuro ON para garantizar legibilidad y cumplir requisitos)
        self.dark_mode_enabled = True

        # Restaurar estado (incluye maximizado y geometría)
        self._restore_window_state(default_music)

        # Conectar cambios para refrescar botones
        self.left_panel.selectionChanged.connect(self._update_action_buttons)
        self.right_panel.selectionChanged.connect(self._update_action_buttons)
        self._update_action_buttons()

    # -------- Menú --------
    def _build_menu(self):
        menu_view = self.menuBar().addMenu("Vista")
        menu_help = self.menuBar().addMenu("Ayuda")

        # Submenú tamaño carátula
        size_menu = QMenu("Tamaño de carátula", self)
        menu_view.addMenu(size_menu)

        self.act_size_small = QAction("Pequeña", self, checkable=True)
        self.act_size_med = QAction("Mediana", self, checkable=True)
        self.act_size_big = QAction("Grande", self, checkable=True)
        self.act_size_med.setChecked(True)

        for act in (self.act_size_small, self.act_size_med, self.act_size_big):
            size_menu.addAction(act)
            act.triggered.connect(self._on_cover_size_action)

        # Tema oscuro
        self.act_dark = QAction("Tema oscuro", self, checkable=True)
        self.act_dark.setChecked(False)
        self.act_dark.triggered.connect(self._toggle_dark_mode)
        menu_view.addAction(self.act_dark)

        # Acerca de
        act_about = QAction("Acerca de", self)
        act_about.triggered.connect(self.show_about)
        menu_help.addAction(act_about)

    def _on_cover_size_action(self):
        # “radio” manual
        sender = self.sender()
        for act in (self.act_size_small, self.act_size_med, self.act_size_big):
            act.setChecked(act is sender)

        if sender is self.act_size_small:
            self.current_cover_size_key = "pequeña"
        elif sender is self.act_size_big:
            self.current_cover_size_key = "grande"
        else:
            self.current_cover_size_key = "mediana"

        self._apply_cover_size_to_panels()
        self._save_ui_prefs()

    def _apply_cover_size_to_panels(self):
        px = self.cover_sizes.get(self.current_cover_size_key, 220)
        self.left_panel.set_cover_size(px)
        self.right_panel.set_cover_size(px)

    def _toggle_dark_mode(self, checked: bool):
        self.dark_mode_enabled = bool(checked)
        if self.dark_mode_enabled:
            apply_dark_theme(QApplication.instance())
        else:
            apply_light_theme(QApplication.instance())
        self._save_ui_prefs()

    # -------- Copiar carátula / tags --------
    def _selected_pair(self) -> Tuple[str, str]:
        left = self.left_panel.selected_file_path()
        right = self.right_panel.selected_file_path()
        return left, right

    def _update_action_buttons(self):
        left, right = self._selected_pair()
        ok = bool(left and right and os.path.exists(left) and os.path.exists(right))
        self.btn_copy_cover.setEnabled(ok)
        self.btn_copy_tags.setEnabled(ok)

    def copy_cover_left_to_right(self):
        left, right = self._selected_pair()
        if not left or not right:
            return

        try:
            cover = get_cover_bytes(left)
            if not cover:
                QMessageBox.information(self, "Carátula", "El archivo del panel izquierdo no tiene carátula embebida.")
                return
            data, mime = cover
            set_cover_bytes(right, data, mime)
            # refrescar panel derecho
            self.right_panel._refresh_info(right)
            QMessageBox.information(self, "Carátula", "Carátula copiada correctamente (Izq → Der).")
        except Exception as e:
            self._show_error("Error al copiar carátula", e)

    def copy_tags_left_to_right(self):
        left, right = self._selected_pair()
        if not left or not right:
            return

        try:
            tags = get_tags(left)
            set_tags(right, tags)
            # refrescar panel derecho
            self.right_panel._refresh_info(right)
            QMessageBox.information(self, "Metadatos", "Tags copiados correctamente (Izq → Der).")
        except Exception as e:
            self._show_error("Error al copiar tags", e)

    # -------- About --------
    def show_about(self):
        # Enlaces usando QPalette::Link y LinkVisited (NO Highlight, NO colores fijos).
        # QLabel tomará palette(Link) si está en rich text.
        about = QMessageBox(self)
        about.setWindowTitle("Acerca de")
        about.setIcon(QMessageBox.Icon.Information)

        # Email y licencia
        name = self.APP_NAME
        email = "linuxfrontier@proton.me"
        lic = "GPL"

        # Rich text con links (sin colores fijos).
        txt = (
            f"<b>{name}</b><br>"
            f"Gestor de carátulas y metadatos en doble panel.<br><br>"
            f"Email: <a href='mailto:{email}'>{email}</a><br>"
            f"Licencia: {lic}<br>"
        )
        about.setTextFormat(Qt.TextFormat.RichText)
        about.setText(txt)
        about.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        about.setDefaultButton(QMessageBox.StandardButton.Ok)

        # Forzar que los links usen palette Link/LinkVisited (ya está en el tema oscuro).
        about.exec()

    # -------- Persistencia / Restauración --------
    def _save_ui_prefs(self):
        self.settings.setValue("ui/dark_mode", self.dark_mode_enabled)
        self.settings.setValue("ui/cover_size", self.current_cover_size_key)

    def _restore_ui_prefs(self):
        dark = self.settings.value("ui/dark_mode", False, type=bool)
        self.dark_mode_enabled = dark
        self.act_dark.setChecked(self.dark_mode_enabled)

        if self.dark_mode_enabled:
            apply_dark_theme(QApplication.instance())
        else:
            apply_light_theme(QApplication.instance())

        size_key = self.settings.value("ui/cover_size", "mediana", type=str)
        if size_key in self.cover_sizes:
            self.current_cover_size_key = size_key
        # reflejar en acciones
        self.act_size_small.setChecked(self.current_cover_size_key == "pequeña")
        self.act_size_med.setChecked(self.current_cover_size_key == "mediana")
        self.act_size_big.setChecked(self.current_cover_size_key == "grande")
        self._apply_cover_size_to_panels()

    def _restore_window_state(self, default_music: str):
        # UI prefs (tema y tamaño carátula)
        self._restore_ui_prefs()

        # Splitter principal
        sp = self.settings.value("main/splitter_sizes", None)
        if isinstance(sp, list) and len(sp) >= 2:
            try:
                self.splitter.setSizes([int(sp[0]), int(sp[1])])
            except Exception:
                pass

        # Restaurar panels
        self.left_panel.restore_state(default_music)
        self.right_panel.restore_state(default_music)

        # Geometría ventana / maximizado
        geom = self.settings.value("main/geometry", None)
        state = self.settings.value("main/windowState", None)
        was_max = self.settings.value("main/maximized", True)

        if geom is not None:
            try:
                self.restoreGeometry(geom)
            except Exception:
                pass
        if state is not None:
            try:
                self.restoreState(state)
            except Exception:
                pass

        # Por requisito: abrir maximizado por defecto
        if str(was_max).lower() in ("true", "1", "yes"):
            QTimer.singleShot(0, self.showMaximized)
        else:
            QTimer.singleShot(0, self.show)

    def closeEvent(self, event):
        try:
            # Guardar panels
            self.left_panel.save_state()
            self.right_panel.save_state()

            # Splitter principal
            self.settings.setValue("main/splitter_sizes", self.splitter.sizes())

            # Ventana
            self.settings.setValue("main/geometry", self.saveGeometry())
            self.settings.setValue("main/windowState", self.saveState())
            self.settings.setValue("main/maximized", self.isMaximized())

            # UI prefs
            self._save_ui_prefs()

            self.settings.sync()
        except Exception:
            pass
        super().closeEvent(event)

    # -------- Utilidades --------
    def _show_error(self, title: str, exc: Exception):
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(title)
        msg.setText(str(exc))
        msg.setDetailedText(details)
        msg.exec()


# ---------- main ----------
def main():
    app = QApplication(sys.argv)

    # Icono opcional (si lo quieres luego, puedes añadir un .ico/.png y cargarlo aquí)
    # app.setWindowIcon(QIcon("icon.png"))

    w = MainWindow()
    # w.showMaximized()  # ya lo maneja la restauración con default maximizado
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
