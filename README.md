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

Cada una dice qué pasa, qué podés hacer igual, qué no, y cómo se arreglaría.

### `proposal-implementation` — los archivos bajo Git LFS llegan vacíos

**Qué pasa.** Clonás un repositorio que usa Git LFS y parece completo: todas las
rutas están, todos los archivos existen. Pero cada archivo bajo LFS pesa unos cientos
de bytes — es un marcador de texto, no el archivo. Lo primero que lo abra como datos
falla con un error sobre el **formato del archivo**, que no se parece en nada a la
causa real.

**Por qué es a propósito.** El clon salta el filtro que materializa esos archivos, y
el salto queda fijado en la configuración local del clon. Los marcadores alcanzan
para reorganizar el repositorio y leer el código, y bajar gigabytes sólo para moverlos
de carpeta gasta una cuota de LFS que no vuelve.

**Qué hace la forja.** `env` te los reporta apenas termina el clon —el momento en que
la ilusión es más fuerte— y `verify` lo repite en cada pasada posterior, porque lo
único peor que no saberlo es olvidarlo. Cada marcador declara el tamaño del archivo
real, así que el reporte trae **un total, no una advertencia**. En este repositorio,
por ejemplo: 18 marcadores, **5,09 GiB** si se bajaran.

Nada del flujo los lee, ninguna prueba ni cuaderno se escribe contra ellos, y **la
descarga nunca se hace sola**: el comando se imprime en vez de ejecutarse.

**Ojo con el atajo que no existe.** Bajarlos desde la página de GitHub con el botón de
descarga **cuesta exactamente lo mismo**. GitHub cuenta todas las descargas contra el
ancho de banda del dueño del repositorio, por cualquier vía — el comando, el navegador,
y hasta el zip del código fuente si contiene esos objetos. La franquicia gratuita es de
1 GiB por mes. No hay ruta que la evite, y creer que la hay es la forma más común de
gastarse el mes sin querer.

**Qué podés hacer antes de gastarla.** Mirá lo que `probe` reporta bajo `acquisition`:
el material que el repositorio se baja, clona o desempaqueta **por su cuenta** no
cuesta cuota, y lo que salió de un entrenamiento se vuelve a producir entrenando. La
cuota se gasta sólo en lo que de verdad no existe en ningún otro lado — y si lo
necesitás, bajalo sabiendo el número. Desde ahí la verificación los ve completos y todo
sigue normal.

**Qué no hace.** No puede impedir que un cableado escrito a mano intente cargar uno —
si pasa, el error habla del formato y el reporte de `env` es donde está la razón. Y no
distingue un marcador de un archivo genuinamente corrupto: los dos se leen como
material ausente, que es la lectura conservadora.

### `proposal-deliberation` — no se puede editar el título ni la introducción

**Qué pasa.** Pedile que cambie una sección con `##` y la edita sin problema. Pedile
que cambie el **título** o el **párrafo de introducción** y no puede: el resolvedor
que ubica dónde aplicar un cambio no sabe seleccionar de forma fiable el bloque que
está antes del primer `##`.

**Qué incluye ese bloque.** El título con `#`, la introducción que le sigue, y
cualquier cosa que haya entre los dos y el primer encabezado de segundo nivel.

**Qué podés hacer y qué no.** Todo el cuerpo del documento se gestiona por el flujo
normal de revisiones. Título e introducción hay que **editarlos a mano** en el
archivo — y ojo, porque eso choca de frente con la limitación siguiente: editar a
mano una revisión ya publicada rompe la auditoría. En la práctica significa que el
título y la introducción conviene dejarlos como quedaron en la primera versión.

**Cómo se arregla.** Dándole al resolvedor identificadores explícitos para ese
bloque — algo como `document_root`, `preamble` o `front_matter` — para que se pueda
apuntar a él igual que a cualquier sección.

### `proposal-deliberation` — editar una revisión publicada a mano rompe la auditoría

**Qué pasa.** Abrís `proposals/research-concept-r14.md` en el editor, corregís una
palabra, guardás. La próxima operación de la skill reporta `auditStatus: FAIL` y no
te deja seguir.

**Por qué.** Cada publicación deja un recibo en `.proposal-deliberation/receipts/`
con el sha256 del documento. Antes de cualquier operación, la auditoría relee el
archivo, lo vuelve a hashear y exige que sea byte-idéntico a lo que el motor publicó
(`consistency-audit.ts`, `RECEIPT_SHA_MISMATCH`). Una palabra distinta cambia el
hash y el recibo deja de respaldar nada.

**No es un defecto: es la garantía funcionando.** Sin recibos el motor no puede
afirmar que una revisión sea lo que dice ser, y el linaje byte-exacto se queda sin
respaldo. Sacarlos no es una opción.

**Qué podés hacer.** Hoy, o revertís la edición manual hasta que el archivo vuelva a
coincidir, o reconciliás el recibo a mano. Lo segundo es delicado y conviene evitarlo:
un recibo actualizado sin cuidado deja al linaje afirmando algo que nadie comprobó.

**Cómo se arregla.** Con una operación de re-base autorizada — algo como
`ADOPT_MANUAL_EDIT`: *"edité esta revisión a propósito, adoptá los bytes actuales
como nueva línea base"*, que actualice el recibo tras confirmación explícita. Con
eso, editar a mano dejaría de ser una ruptura y pasaría a ser un acto declarado.

---

## Deuda de mantenimiento

No limitan a quien usa las skills; limitan a quien las modifique.

### `proposal-deliberation` — el nombre del directorio de estado está repetido

**Qué pasa.** Nada, en uso normal. La carpeta `.proposal-deliberation/` guarda la
contabilidad de la deliberación —`receipts/` y `state/`— en la raíz del repositorio,
y su nombre está escrito como texto literal en **21 puntos repartidos en 7 archivos**
del motor (`consistency-audit.ts` sola tiene 7). Los 21 dicen lo mismo, así que la
carpeta siempre se encuentra.

**Qué sí funciona.** Dos propuestas distintas conviven sin problema: tanto los
recibos como el estado se guardan en **un archivo por revisión, nombrado con el
archivo de la propuesta** (`state/research-concept-r01.md.json`). Nombres distintos,
archivos distintos, cero colisión. Un paper nuevo funciona idéntico.

**Qué no se puede.** Tener el **mismo documento bajo dos deliberaciones
independientes** — dos estados aislados sobre los mismos archivos, para explorar dos
caminos en paralelo — ni mover el estado fuera de la raíz del repositorio. Las dos
cosas necesitan que la ubicación sea configurable, y hoy no lo es.

**Y el modo de fallar es feo.** Si alguien renombra la carpeta y se olvida de uno de
los 21 lugares, no falla nada: la mitad de la contabilidad queda escribiéndose en la
carpeta vieja, en silencio, hasta que alguien nota que faltan recibos.

**Cómo se arregla.** Con un único `stateRoot(root)` del que salgan los 21. Es un
refactor chico y desbloquea las dos cosas de arriba.

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
