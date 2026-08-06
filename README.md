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
| `guidance/paper-guide/` | **Papers guía** — las referencias metodológicas / de estilo. `proposal-deliberation` las carga como contexto al inicio de cada deliberación. |
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

### Paso 3 — Deliberar sobre una propuesta (`proposal-deliberation`)

En **Claude Code**, invocar la skill:

```
/proposal-deliberation
```

En el primer turno carga automáticamente los Markdown de `guidance/paper-guide/`
como contexto y actúa como tutor matemático. Desde ahí se puede:

- describir una idea y pedir una primera versión,
- pedir ediciones a una propuesta gestionada,
- ejecutar el ciclo de vida de revisiones gestionadas.

Las propuestas viven en `proposals/`, una por revisión gestionada
(`research-concept-rNN.md`).

### Paso 4 — Llevar la propuesta a código (`proposal-implementation`)

En **Claude Code**, invocar la skill:

```
/proposal-implementation
```

Toma la revisión vigente y la materializa en un repositorio destino, que vive en
`implementations/` con su propio git y su propio entorno virtual. El flujo tiene
dos fases separadas:

1. **Estructura.** Si el repo trae contenido, lo lleva al layout y verifica
   —sin ejecutar nada— que cuadernos, rutas y referencias sigan resolviendo. No
   audita ni valida el código que ya estaba: es lo que hay, ordenado.
2. **Materialización.** Recién entonces implementa la matemática y la somete a
   la escalera de validación.

```
<repo>/
├── <Name>/            Notebooks/  Data/  Results/  Models/
├── src/<Package>/     una implementación por objeto matemático
├── tests/             smoke · invariantes · sintéticos · auditoría · remedios
└── pyproject.toml
```

La escalera tiene cinco niveles, del más barato al más caro: **smoke**,
**invariantes** (cada afirmación de la propuesta anclada a un test),
**sintéticos** (deterministas, semilla fija), **auditoría** (hallazgos sobre la
matemática, medidos sobre 200 configuraciones aleatorias) y **remedios** (cada
corrección propuesta validada con el mismo rigor). Un hallazgo sin remedio
validado no se reporta.

Ver el `SKILL.md` de cada skill para el contrato completo.

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

### Editar una revisión publicada a mano rompe la auditoría

Cada publicación deja un recibo en `.proposal-deliberation/receipts/` con el
sha256 del documento. La auditoría relee el archivo de `proposals/`, lo hashea y
exige que sea byte-idéntico a lo que el motor publicó
(`consistency-audit.ts`, `RECEIPT_SHA_MISMATCH`). Si se edita a mano una
revisión ya publicada, el archivo deja de coincidir con su recibo y la siguiente
operación reporta `auditStatus: FAIL`.

**No es un defecto: es la garantía funcionando.** Sin recibos el motor no puede
afirmar que una revisión es lo que dice ser, y el linaje byte-exacto deja de
tener respaldo. Quitarlos no es una opción.

**Lo que falta es una operación de re-base autorizada** — algo como
`ADOPT_MANUAL_EDIT`: "edité esta revisión a propósito, adoptá los bytes actuales
como nueva línea base", que actualice el recibo tras confirmación explícita del
investigador. Hoy no existe y la reconciliación hay que hacerla a mano. Con esa
operación, editar a mano dejaría de ser una ruptura y pasaría a ser un acto
declarado.

### El directorio de estado está hardcodeado

El nombre `.proposal-deliberation` aparece literal en 11 puntos de 7 archivos
del motor (`derived-state-store.ts`, `consistency-audit.ts`,
`lifecycle-state-store.ts`, …). En ejecución no rompe nada, pero cualquier
cambio de nombre obliga a tocarlos uno por uno. Se resuelve con un único
`stateRoot(root)`; es higiene, no urgencia.

---

## Tests

```bash
npm test   # motor de proposal-deliberation (489)
```

Lo que prueba cada cosa: `tests/` cubre **el tooling de la forja** — el motor de
deliberación y los helpers de ingestión. Los tests de una implementación
materializada viven en su repositorio destino y en ningún otro lado; borrarlo
borra sus tests.

`proposal-implementation` se validó con un arnés de escenarios propio —catorce
situaciones en las que puede caer un clon, más el ciclo completo hasta publicar
la revisión que produce un hallazgo— construido para cerrar la v1.5 y retirado
al cerrarla. Era andamiaje, no parte de la forja. Queda en la historia: el
commit que lo saca lo dice, y `git revert` lo trae de vuelta si alguna vez hay
que volver a correrlo.
