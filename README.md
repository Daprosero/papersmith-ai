# papersmith-ai

Una forja de papers: ingiere PDFs de referencia a Markdown de alta fidelidad y
legible por un agente (ecuaciones en LaTeX, tablas en Markdown, figuras como
archivos) y luego delibera sobre propuestas de papers matemáticos. La ingesta
corre **localmente** con [Marker](https://github.com/datalab-to/marker).

---

## 1. Instalar las dependencias

Se necesitan tres cosas: **Python 3.10–3.13**, el binario **`llama-server`** (el
motor de OCR de la ingesta — no es un paquete de pip; es `llama.cpp`, **no
Ollama**) y los **paquetes de Python**.

> **La primera corrida descarga un modelo.** En la primera ingesta, Marker
> descarga desde Hugging Face los pesos de los modelos de Surya —OCR y layout,
> **~1.5 GB**— y los cachea en `~/.cache/huggingface`. No se descarga nada al
> instalar: el modelo llega en la primera corrida real y, de ahí en más, todo
> funciona offline. `llama.cpp` es el **motor**; los archivos `.gguf` de Surya
> son el **modelo** que ese motor ejecuta. Surya detecta `llama-server` en el
> `PATH` automáticamente; no hay que apuntar a ningún modelo a mano.

### `llama-server` (motor de OCR, requerido)

| SO | Cómo |
|----|------|
| macOS | `brew install llama.cpp` |
| Windows | Descargar un build `llama-*-bin-win-*.zip` de <https://github.com/ggml-org/llama.cpp/releases>, extraerlo y agregar la carpeta (con `llama-server.exe`) al `PATH`. `winget`/`scoop` también pueden tenerlo. |
| Linux | `brew install llama.cpp`, el paquete de la distribución, o un build de release. |

Si no está en el `PATH`, definir `LLAMA_CPP_BINARY` con la ruta completa al
binario. Verificar con `llama-server --version` (macOS/Linux) o
`where llama-server` (Windows).

### Python 3.12

macOS: `brew install python@3.12`. Windows: instalar desde
<https://www.python.org/downloads/> (marcar "Add to PATH").

## 2. Crear el entorno virtual

El motor vive en un entorno virtual aislado para no tocar el Python del sistema.

**macOS / Linux:**

```bash
python3.12 -m venv .claude/skills/paper-ingestion/.venv
source .claude/skills/paper-ingestion/.venv/bin/activate
pip install -r .claude/skills/paper-ingestion/requirements.txt
```

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .claude\skills\paper-ingestion\.venv
.claude\skills\paper-ingestion\.venv\Scripts\Activate.ps1
pip install -r .claude\skills\paper-ingestion\requirements.txt
```

El entorno solo necesita existir: la skill lo usa internamente, no hace falta
activarlo a mano. (Recordatorio: la primera ingesta descarga los modelos de
Surya, ~1.5 GB, cacheados a partir de ahí.)

> Sin `.env` ni claves de API. La ingesta es completamente local y keyless.

---

## Cómo funciona — el orden

### Paso 1 — Colocar cada PDF en la carpeta según su rol

| Carpeta | Qué va acá |
|---------|------------|
| `guidance/paper-guide/` | **Papers guía** — las referencias metodológicas / de estilo. `paper-proposal` las carga como contexto al inicio de cada deliberación. |
| `guidance/reference-papers/` | **Corpus de referencia** — papers de apoyo, ingeridos a Markdown para consulta. No se cargan automáticamente en la deliberación. |
| `guidance/data/` (paper del dataset) | **⏳ Pendiente — todavía no conectado.** El paper que describe la base de datos de la investigación. Planeado; dejar para más adelante. |

### Paso 2 — Ingerir los PDFs (PDF → Markdown)

En **Claude Code**, invocar la skill:

```
/paper-ingestion
```

(o simplemente pedir: *"ingerí los papers"*). Por cada PDF **suelto**, crea una
carpeta con el nombre del paper, mueve el PDF adentro y escribe un `<nombre>.md`
liviano (texto + LaTeX + tablas, con la bibliografía quitada) junto con las
imágenes de las figuras:

```
guidance/reference-papers/computers-13-00176-v2-1/
├── computers-13-00176-v2-1.pdf
├── computers-13-00176-v2-1.md
└── _page_4_Figure_2.jpeg   (figuras que el .md referencia)
```

Un **PDF suelto** (directamente en una carpeta raíz) está pendiente; un paper
que ya está dentro de su carpeta se saltea. Para re-ingerir, borrar la carpeta
del paper (dejando el PDF suelto) y volver a ejecutar la skill. La configuración
vive en `papersmith.yaml` (`source_roots`, `mode`, `strip_references`).

### Paso 3 — Deliberar sobre una propuesta (`paper-proposal`)

En **Claude Code**, invocar la skill:

```
/paper-proposal
```

En el primer turno carga automáticamente los Markdown de `guidance/paper-guide/`
como contexto y actúa como tutor matemático. Desde ahí se puede:

- describir una idea y pedir una primera versión,
- pedir ediciones a una propuesta gestionada,
- ejecutar el ciclo de vida de revisiones gestionadas.

Las propuestas viven en `proposals/`. Ver el `SKILL.md` de cada skill para el
contrato completo.

---

## Limitaciones conocidas

### Edición por locus: el bloque raíz del documento

El resolvedor de locus actual localiza y modifica correctamente las secciones
encabezadas por `##`, pero **no puede seleccionar de forma fiable el bloque raíz
del documento** situado antes del primer encabezado de segundo nivel.

Ese bloque raíz incluye:

- el título principal `#`;
- la introducción inmediatamente posterior;
- cualquier contenido situado entre el título principal y el primer `##`.

Como consecuencia, en la versión actual los cambios sobre el **título** y la
**introducción** pueden requerir **edición manual**, mientras que las secciones
encabezadas por `##` sí pueden gestionarse mediante el flujo normal de revisión.

### Mejora prevista (segunda iteración)

El resolvedor podría ampliarse con identificadores explícitos para el bloque
raíz, por ejemplo:

```text
document_root
preamble
front_matter
```

---

## Tests

```bash
npm test
```
