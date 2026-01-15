## 🧭 Barra de rutas tipo Explorador de Windows (Breadcrumb Bar)

Dual Audio Tag Manager incluye una **barra de rutas interactiva**, similar a la del Explorador de Windows o Dolphin en Linux, que muestra la ubicación actual del archivo o carpeta seleccionados y permite navegar a cualquier directorio anterior con un solo clic.

Ejemplo visual:

```
C:  >  Users  >  wachi  >  OneDrive  >  Música  >  Volumen de fe
```

Cada segmento es un botón clicable.

---

### ❌ El problema original (antes de que funcionara bien)

Al momento de desarrollarla la barra mostraba correctamente la ruta, pero al hacer clic en un directorio intermedio (por ejemplo `OneDrive`) **no llevaba a esa carpeta**.

Esto sucedía porque en Windows:

```
C:
```

no es una ruta válida.
La ruta correcta es:

```
C:\
```

El sistema de archivos de Windows exige la barra invertida (`\`) después de la letra de unidad.

El código estaba construyendo rutas como:

```
C:
C:\Users
C:\Users\wachi
```

Y cuando se hacía clic en `OneDrive`, Qt intentaba ir a:

```
C:Users\wachi\OneDrive
```

que es una ruta inválida.

---

### ✅ La solución

La solución fue detectar que el primer elemento de la ruta es una **unidad de Windows** (`C:`, `F:`, etc.) y convertirlo correctamente en una ruta real agregando `\`.

El algoritmo corregido construye las rutas así:

```
C:\ 
C:\Users
C:\Users\wachi
C:\Users\wachi\OneDrive
C:\Users\wachi\OneDrive\Música
```

De esta forma, cada botón apunta a una carpeta válida del sistema.

Esto también funciona automáticamente con:

* Discos externos (`F:\`, `G:\`)
* Memorias USB
* Linux (`/home/usuario/Música`)

---

### 🔁 Navegación al hacer clic

Cuando el usuario hace clic en un segmento de la barra:

1. Se construye la ruta correspondiente
2. Se convierte en un índice del sistema de archivos de Qt
3. El explorador (`QTreeView`) se mueve exactamente a esa carpeta
4. La vista hace scroll hasta mostrarla

Esto se hace con:

```python
idx = model.index(path)
tree.setCurrentIndex(idx)
tree.scrollTo(idx)
```

---

### 🎯 Resultado

Ahora el usuario puede:

* Ver exactamente dónde está
* Saltar a cualquier carpeta anterior
* Navegar discos internos y externos
* Usar la aplicación como un explorador de archivos real

Esto hace que Dual Audio Tag Manager tenga una experiencia de usuario al nivel de:

* Explorador de Windows
* Dolphin
* Krusader
* Total Commander

---
