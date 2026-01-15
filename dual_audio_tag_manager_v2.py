import sys, os, base64
from PyQt6.QtWidgets import (
    QApplication, QWidget, QTreeView, QLabel,
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QSplitter, QGroupBox, QMenuBar
)
from PyQt6.QtGui import QPixmap, QFileSystemModel, QAction
from PyQt6.QtCore import Qt, QSettings
from mutagen import File
from mutagen.id3 import ID3, APIC
from mutagen.flac import Picture

from PyQt6.QtCore import QTimer

AUDIO_EXT = (".mp3", ".flac", ".ogg", ".m4a")

# ------------------ TAGS ------------------

def get_tags(audio, path):
    data = {
        "title":"", "artist":"", "album":"", "date":"",
        "track":"", "genre":"", "comment":"",
        "albumartist":"", "composer":""
    }
    try:
        if path.lower().endswith(".mp3"):
            tags = ID3(path)
            data["title"] = tags.get("TIT2","")
            data["artist"] = tags.get("TPE1","")
            data["album"] = tags.get("TALB","")
            data["date"] = tags.get("TDRC","")
            data["track"] = tags.get("TRCK","")
            data["genre"] = tags.get("TCON","")
            data["comment"] = tags.get("COMM::eng","")
            data["albumartist"] = tags.get("TPE2","")
            data["composer"] = tags.get("TCOM","")
        elif path.lower().endswith(".flac") or path.lower().endswith(".ogg"):
            for k in data:
                if k.upper() in audio:
                    data[k] = audio[k.upper()][0]
        elif path.lower().endswith(".m4a"):
            data["title"] = audio.get("©nam",[""])[0]
            data["artist"] = audio.get("©ART",[""])[0]
            data["album"] = audio.get("©alb",[""])[0]
            data["date"] = audio.get("©day",[""])[0]
            data["track"] = str(audio.get("trkn",[""])[0])
            data["genre"] = audio.get("©gen",[""])[0]
            data["comment"] = audio.get("©cmt",[""])[0]
            data["albumartist"] = audio.get("aART",[""])[0]
            data["composer"] = audio.get("©wrt",[""])[0]
    except:
        pass
    for k in data:
        data[k] = str(data[k])
    return data

# ------------------ COVER ------------------

def extract_cover(audio, path):
    try:
        if path.lower().endswith(".mp3"):
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    return tag.data
        elif path.lower().endswith(".flac"):
            if audio.pictures:
                return audio.pictures[0].data
        elif path.lower().endswith(".ogg"):
            pics = audio.get("metadata_block_picture")
            if pics:
                return base64.b64decode(pics[0])
        elif path.lower().endswith(".m4a"):
            if "covr" in audio:
                return audio["covr"][0]
    except:
        pass
    return None

# ------------------ INSPECTOR ------------------

class AudioInspector(QWidget):
    def __init__(self):
        super().__init__()
        self.cover = QLabel()
        self.cover.setMinimumSize(120,120)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.current_pixmap = None

    def resize_cover(self):
        if self.current_pixmap:
            self.cover.setPixmap(
                self.current_pixmap.scaled(
                    self.cover.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )

    def show_audio(self, path):
        self.text.clear()
        self.cover.clear()
        self.current_pixmap = None

        if not path or not path.lower().endswith(AUDIO_EXT):
            return

        audio = File(path)
        if not audio:
            return

        tags = get_tags(audio, path)
        img = extract_cover(audio, path)

        if img:
            pix = QPixmap()
            pix.loadFromData(img)
            self.current_pixmap = pix
            self.resize_cover()

        info = f"""
Archivo: {os.path.basename(path)}

Título: {tags["title"]}
Intérprete: {tags["artist"]}
Álbum: {tags["album"]}
Año: {tags["date"]}
Pista: {tags["track"]}
Género: {tags["genre"]}
Comentario: {tags["comment"]}
Intérprete del álbum: {tags["albumartist"]}
Compositor: {tags["composer"]}
"""
        self.text.setText(info)

# ------------------ PANEL ------------------

class Panel(QWidget):
    def __init__(self):
        super().__init__()

        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.model.directoryLoaded.connect(self.on_directory_loaded)
        self.model.setNameFilters(["*.mp3","*.flac","*.ogg","*.m4a"])
        self.model.setNameFilterDisables(False)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self.model.rootPath()))
        self.tree.clicked.connect(self.on_select)

        # Hacer que la columna "Name" sea grande
        self.tree.setColumnWidth(0, 400)   # Name
        self.tree.setColumnWidth(1, 80)    # Size
        self.tree.setColumnWidth(2, 100)   # Type
        self.tree.setColumnWidth(3, 120)   # Date Modified  

        header = self.tree.header()
        header.setStretchLastSection(False)

        # Name grande por defecto, pero movible por el usuario
        header.setSectionResizeMode(0, header.ResizeMode.Interactive)

        # Las otras columnas fijas
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)

        self.inspector = AudioInspector()
        self.inspector.cover.resizeEvent = lambda e: self.inspector.resize_cover()

        files_box = QGroupBox("Administrador de archivos")
        fl = QVBoxLayout(files_box); fl.addWidget(self.tree)

        cover_box = QGroupBox("Administrador de imágenes de carátula")
        cl = QVBoxLayout(cover_box); cl.addWidget(self.inspector.cover, alignment=Qt.AlignmentFlag.AlignCenter)

        tags_box = QGroupBox("Administrador de tags")
        tl = QVBoxLayout(tags_box); tl.addWidget(self.inspector.text)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(files_box)
        self.splitter.addWidget(cover_box)
        self.splitter.addWidget(tags_box)
        self.splitter.setSizes([500,150,250])

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)

    def on_directory_loaded(self, path):
        if hasattr(self, "pending_scroll"):
            self.tree.verticalScrollBar().setValue(self.pending_scroll)
            del self.pending_scroll

    def on_select(self, index):
        path = self.model.filePath(index)
        self.current_file = path
        self.inspector.show_audio(path)

    def save_columns(self, settings, prefix):
        header = self.tree.header()
        settings.setValue(prefix + "_name_width", header.sectionSize(0))

    def restore_columns(self, settings, prefix):
        w = settings.value(prefix + "_name_width")
        if w:
            self.tree.setColumnWidth(0, int(w))


# ------------------ About ------------------

from PyQt6.QtWidgets import QDialog
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

class AboutDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acerca de")
        self.resize(500, 300)

        texto = QLabel()
        texto.setWordWrap(True)   # ← esto es lo que faltaba
        texto.setText("""
<b>Dual Audio Tag Manager</b><br><br>

<i>Herramienta para comparar y sincronizar carátulas y etiquetas entre dos colecciones de audio.</i><br><br>

Dual Audio Tag Manager es una herramienta diseñada para comparar y sincronizar metadatos y carátulas entre dos colecciones de audio.
Permite navegar bibliotecas completas de música, visualizar etiquetas y portadas, y copiar carátulas entre archivos MP3, FLAC, OGG y M4A,
facilitando la recuperación de información perdida después de procesos de edición o normalización de audio.<br><br>

<b>Desarrollador:</b><br>
Washington Indacochea Delgado<br><br>

<b>Correo:</b><br>
<a href="mailto:linuxfrontier@proton.me">linuxfrontier@proton.me</a><br><br>

<b>Licencia:</b><br>
GPL 3
""")

        texto.setOpenExternalLinks(True)

        layout = QVBoxLayout(self)
        layout.addWidget(texto)



# ------------------ MAIN ------------------

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dual Audio Tag Manager")

        self.left = Panel()
        self.right = Panel()

        self.btn = QPushButton("➡ Copiar portada ➡")
        self.btn.clicked.connect(self.copy_cover)

        menu = QMenuBar(self)
        view = menu.addMenu("Vista")
        view.addAction("Portada pequeña", lambda: self.set_cover_size(120))
        view.addAction("Portada mediana", lambda: self.set_cover_size(200))
        view.addAction("Portada grande", lambda: self.set_cover_size(350))

        help_menu = menu.addMenu("Ayuda")
        help_menu.addAction("Acerca de", self.show_about)

        content = QHBoxLayout()
        content.addWidget(self.left,5)
        mid = QVBoxLayout(); mid.addStretch(); mid.addWidget(self.btn); mid.addStretch()
        content.addLayout(mid,1)
        content.addWidget(self.right,5)

        main = QVBoxLayout(self)
        main.setMenuBar(menu)
        main.addLayout(content)

        self.settings = QSettings("Washington", "DualAudioTagManager")

        self.left.pending_scroll = int(self.settings.value("left_scroll", 0))
        self.right.pending_scroll = int(self.settings.value("right_scroll", 0))

        self.restoreGeometry(self.settings.value("main_geometry", b""))
        self.left.splitter.restoreState(self.settings.value("left_split", b""))
        self.right.splitter.restoreState(self.settings.value("right_split", b""))

        self.left.restore_columns(self.settings, "left")
        self.right.restore_columns(self.settings, "right")

        for side, panel in [("left", self.left), ("right", self.right)]:
            path = self.settings.value(f"{side}_root", "")
            if path:
                idx = panel.model.index(path)
                panel.tree.setCurrentIndex(idx)
                panel.tree.scrollTo(idx)

        # aplicar scroll DESPUÉS de que Qt termine de posicionar la vista
        QTimer.singleShot(0, self.restore_scroll)

    def restore_scroll(self):
        left = self.settings.value("left_scroll")
        right = self.settings.value("right_scroll")

        if left is not None:
            self.left.tree.verticalScrollBar().setValue(int(left))
        if right is not None:
            self.right.tree.verticalScrollBar().setValue(int(right))

    def set_cover_size(self, size):
        for p in (self.left, self.right):
            p.inspector.cover.setMinimumSize(size,size)
            p.inspector.resize_cover()

    def closeEvent(self, e):
        self.settings.setValue("main_geometry", self.saveGeometry())
        self.settings.setValue("left_split", self.left.splitter.saveState())
        self.settings.setValue("right_split", self.right.splitter.saveState())

        # Guardar la carpeta actualmente seleccionada
        left_index = self.left.tree.currentIndex()
        right_index = self.right.tree.currentIndex()

        self.settings.setValue("left_root", self.left.model.filePath(left_index))
        self.settings.setValue("right_root", self.right.model.filePath(right_index))

        # Guardar posición de scroll
        self.settings.setValue("left_scroll", self.left.tree.verticalScrollBar().value())
        self.settings.setValue("right_scroll", self.right.tree.verticalScrollBar().value())

        e.accept()

        self.left.save_columns(self.settings, "left")
        self.right.save_columns(self.settings, "right")

    def copy_cover(self):
        src = getattr(self.left,"current_file",None)
        dst = getattr(self.right,"current_file",None)
        if not src or not dst:
            return

        src_audio = File(src)
        dst_audio = File(dst)
        img = extract_cover(src_audio, src)
        if not img:
            return

        if dst.lower().endswith(".mp3"):
            tags = ID3(dst)
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img))
            tags.save()
        elif dst.lower().endswith(".flac"):
            pic = Picture(); pic.type=3; pic.mime="image/jpeg"; pic.data=img
            dst_audio.clear_pictures(); dst_audio.add_picture(pic); dst_audio.save()
        elif dst.lower().endswith(".ogg"):
            dst_audio["metadata_block_picture"]=[base64.b64encode(img).decode("ascii")]; dst_audio.save()
        elif dst.lower().endswith(".m4a"):
            dst_audio["covr"]=[img]; dst_audio.save()

        self.right.inspector.show_audio(dst)

    def show_about(self):
        dlg = AboutDialog()
        dlg.exec()


# ------------------ RUN ------------------

app = QApplication(sys.argv)
w = MainWindow()
w.showMaximized()
app.exec()
