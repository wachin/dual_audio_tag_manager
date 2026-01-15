# 🎵 Dual Audio Tag Manager

**Dual Audio Tag Manager** es una herramienta de escritorio diseñada para comparar y sincronizar carátulas y etiquetas (tags) entre dos colecciones de archivos de audio.

Es ideal cuando:
- Se pierde la portada al editar audios con programas como Audacity.
- Se tienen dos copias de una biblioteca (original y editada).
- Se quiere copiar carátulas de una colección a otra.

Funciona con:
- MP3  
- FLAC  
- OGG  
- M4A (AAC / ALAC)

Y está pensada para trabajar con **dos paneles**, como un administrador de archivos tipo Krusader o Total Commander.

---

## 🧠 ¿Qué hace este programa?

El programa muestra:

|          Panel izquierdo           |           Panel derecho           |
| ---------------------------------- | --------------------------------- |
| Colección original (con carátulas) | Colección editada (sin carátulas) |

Debajo de cada panel se ve:
- La imagen de la carátula
- El título
- El intérprete
- El álbum
- El año
- El género
- El compositor
- Y más

Luego, con el botón **“Copiar portada”**, se puede copiar la imagen del lado izquierdo al archivo del lado derecho.

---

## 🖥 Requisitos

Necesitas tener instalado:

- **Python 3.10 o superior**
- **pip** (gestor de paquetes de Python)

---

## 📦 Librerías que usa el programa

El programa utiliza:

- PyQt6 → para la interfaz gráfica  
- mutagen → para leer y escribir etiquetas de audio  
- pillow → para manejar imágenes  

Se instalan automáticamente con `pip`.

---

## 🪟 Cómo usarlo en Windows

### 1️⃣ Instalar Python

Descárgalo de:

[https://www.python.org](https://www.python.org)

Durante la instalación marca:
> ✔ Add Python to PATH (puede ver un tutorial que hice sobre [ello](https://washingtonindacochea.blogspot.com/2024/08/como-instalar-python-en-windows-10.html))

---

### 2️⃣ Abrir la consola
Presiona:

```
Win + R
```

escribe:

```
cmd
```

y presiona Enter.

---

### 3️⃣ Ir a la carpeta del programa
Ejemplo:

```bash
cd C:\PortableApps\dual_tag_editor
```

(Usa la carpeta donde guardaste `dual_audio_tag_manager.py`)

---

### 4️⃣ Instalar las librerías

```bash
pip install PyQt6 mutagen pillow
```

---

### 5️⃣ Ejecutar el programa

```bash
python dual_audio_tag_manager.py
```

---

## 🐧 Cómo usarlo en Linux (MX Linux, Ubuntu, Debian, etc)

### 1️⃣ Instalar Python y pip
python ya viene instalado en estos sistemas Linux, pero igual este es el comando:

```bash
sudo apt install python3 
```

---

### 2️⃣ Instalar las librerías

```bash
sudo apt install python3-pyqt6 python3-mutagen python3-pillow
```

---

### 3️⃣ Ejecutar el programa

Ve a la carpeta donde está el archivo y ejecuta:

```bash
python dual_audio_tag_manager.py
```

---

## 🗂 Dónde guarda la configuración

El programa recuerda:

* El tamaño de la ventana
* El tamaño de los paneles
* Las carpetas abiertas

Esto se guarda automáticamente:

| Sistema | Ubicación                                                                |
| ------- | ------------------------------------------------------------------------ |
| Windows | `C:\Users\TU_USUARIO\AppData\Roaming\Washington\DualAudioTagManager.ini` |
| Linux   | `~/.config/Washington/DualAudioTagManager.conf`                          |

---

## 📜 Licencia

Este programa es **Software Libre** bajo licencia:

> **GNU General Public License v3 (GPL 3)**

Puedes:

* Usarlo
* Modificarlo
* Compartirlo
  Siempre que respetes la licencia.

---

## 👨‍💻 Desarrollador

**Washington Indacochea Delgado**
📧 [linuxfrontier@proton.me](mailto:linuxfrontier@proton.me)

---

## ❤️ Nota final

Este programa fue creado para resolver un problema real:

> Recuperar carátulas perdidas después de editar audios

¡Disfrútalo!

---

