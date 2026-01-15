

## **Problema Resuelto: Persistencia de Posición de Scroll**

### **Descripción del Problema**
Cuando un usuario navegaba por directorios profundos en el árbol de archivos y desplazaba la vista verticalmente (scroll), al cerrar y reabrir la aplicación, **no se mantenía la posición del scroll**, aunque sí se recordaba el archivo o carpeta seleccionada.

### **Análisis Técnico**

**Causa raíz**: El problema era un *race condition* en la inicialización del `QTreeView`. La secuencia era:

1. Se cargaban las carpetas (operación asíncrona)
2. Se intentaba restaurar el scroll **inmediatamente**
3. Pero si las carpetas tenían muchos archivos, estos aún no estaban completamente cargados cuando se aplicaba el scroll

### **Solución Implementada**

Se implementaron **tres mejoras clave**:

#### **1. Método especializado `save_scroll()` en la clase `Panel`**
```python
def save_scroll(self, settings, prefix):
    """Guarda la posición actual del scroll"""
    scroll_value = self.tree.verticalScrollBar().value()
    settings.setValue(f"{prefix}_scroll", scroll_value)
```

**Ventaja**: Encapsulación y reutilización del código.

#### **2. Restauración con múltiples intentos en `restore_scroll()`**
```python
def restore_scroll(self):
    def apply_scroll():
        # ... lógica de restauración ...
    
    # Intentos en diferentes momentos
    QTimer.singleShot(0, apply_scroll)    # Inmediato
    QTimer.singleShot(100, apply_scroll)  # 100ms después
    QTimer.singleShot(500, apply_scroll)  # 500ms después
```

**Ventaja**: Asegura que los datos estén cargados antes de aplicar el scroll.

#### **3. Validación de rangos**
```python
# Antes de aplicar el scroll, verificar que esté dentro del rango válido
max_left = self.left.tree.verticalScrollBar().maximum()
if 0 <= scroll_left <= max_left:
    self.left.tree.verticalScrollBar().setValue(scroll_left)
```

**Ventaja**: Previene errores si el valor guardado es mayor que el máximo actual.

### **Cambios en el Flujo**

**ANTES**:
```
Inicialización → Cargar datos → Aplicar scroll (1 intento) → Mostrar interfaz
```

**DESPUÉS**:
```
Inicialización → Cargar datos → Mostrar interfaz
                    ↓
            Aplicar scroll (3 intentos en 0, 100, 500ms)
                    ↓
           Validar rango → Aplicar si es válido
```

### **Consideraciones de Diseño**

1. **Separación de responsabilidades**: Cada `Panel` maneja su propio estado de scroll
2. **Patrón de persistencia**: Se usa `QSettings` para almacenamiento multiplataforma
3. **Defensa contra errores**: Validaciones previenen valores fuera de rango
4. **Experiencia de usuario**: El usuario ve la interfaz inmediatamente mientras se restaura el estado en segundo plano

### **Lecciones Aprendidas**

- **Timing en GUI**: Las operaciones de carga de datos pueden ser asíncronas
- **Defensive Programming**: Siempre validar valores antes de aplicarlos
- **User State Persistence**: Los usuarios valoran que la aplicación "recuerde" su estado anterior

### **Posibles Mejoras Futuras**

1. **Scroll horizontal**: Actualmente solo se persiste el scroll vertical
2. **Estado de expansión de carpetas**: Podría guardarse qué carpetas están expandidas/colapsadas
3. **Persistencia de filtros**: Guardar cualquier filtro aplicado a la vista

### **Archivos Modificados**

- `dual_audio_tag_manager_v3.py`:
  - Clase `Panel`: Añadido método `save_scroll()`
  - Clase `MainWindow`: Modificado `closeEvent()` y `restore_scroll()`

Este enfoque demuestra cómo solucionar problemas comunes de sincronización en aplicaciones PyQt6 donde la interfaz gráfica y la carga de datos ocurren en momentos diferentes.

---

## Cómo el programa recuerda la última carpeta y archivo seleccionados

Uno de los problemas más comunes en aplicaciones que usan exploradores de archivos (`QTreeView`) es que el usuario navega por muchas carpetas, selecciona un archivo, cierra el programa… y al abrirlo otra vez tiene que volver a buscar todo desde cero.

En **Dual Audio Tag Manager** este problema fue resuelto guardando **la ruta exacta del último elemento seleccionado** y restaurándolo automáticamente.

### ❌ El problema original

Al principio se intentó guardar el valor:

```python
tree.rootIndex()
```

Pero ese valor solo representa el punto inicial del árbol (por ejemplo `C:\` o “Este equipo”), no la carpeta o archivo donde el usuario estaba realmente trabajando.

Por eso el programa siempre volvía al inicio.

---

### ✅ La solución correcta

En lugar de guardar el `rootIndex`, se guarda el **elemento actualmente seleccionado**:

```python
left_index = self.left.tree.currentIndex()
right_index = self.right.tree.currentIndex()

self.settings.setValue("left_root", self.left.model.filePath(left_index))
self.settings.setValue("right_root", self.right.model.filePath(right_index))
```

Eso guarda rutas reales como por ejemplo:

```
D:\Toshiba\Música\Danilo Montero\Álbum 1998\01 - Cantaré de tu amor.mp3
```

---

### 🔁 Restaurar la posición al abrir el programa

Cuando el programa se vuelve a iniciar, se recupera esa ruta y se le indica al explorador que vuelva exactamente a ese archivo:

```python
idx = panel.model.index(path)
panel.tree.setCurrentIndex(idx)
panel.tree.scrollTo(idx)
```

Esto hace dos cosas:

* Selecciona el archivo que el usuario estaba viendo
* Hace scroll automáticamente hasta que ese archivo sea visible

---

### 🎯 Resultado

Ahora el programa:

* Vuelve a la misma carpeta
* Vuelve al mismo archivo
* Muestra ese archivo en pantalla sin que el usuario tenga que buscarlo

Es el mismo comportamiento que tienen Krusader, Dolphin o Total Commander.

