# La forja no lleva un paper adentro

Documento de mantenimiento. Escrito 2026-09-20, con todo medido ese día contra
`main`. Los números envejecen: **re-medilos antes de usarlos**, con los comandos
que están más abajo.

---

## La regla

`.opencode/skills/` es una forja de papers. Sirve para escribir **cualquier**
paper. Nada particular del paper que se esté escribiendo hoy puede vivir ahí
adentro: ni un id de bloque, ni un título de sección, ni el nombre de un
documento, ni el id de un paper ingerido, ni una palabra del tema, ni el patrón
con que se numeran las revisiones.

Lo que es de un paper vive en los **espacios destinados** — `proposals/`,
`experiments/`, `guidance/`, `paper/` — que están todos fuera de git salvo su
`.gitkeep`. La forja los lee; no los nombra.

---

## La analogía de la aguja, que es de lo que se trata

Llevás el auto porque no anda el testigo del combustible. El mecánico lo
arregla, pero para probar que funciona **pega la aguja en "medio tanque"** —
porque con la aguja suelta el tablero le daba error y no podía cerrar el
trabajo.

El testigo ahora anda. Y el tanque te miente para siempre.

Eso es exactamente lo que pasa cuando una skill exige algo y no da forma de
contestarle. Alguien tapa el hueco con un valor inventado para que la máquina
siga andando, y ese valor queda con cara de decisión.

**Dos defectos distintos, y conviene no mezclarlos:**

| | **la aguja** | **el cajón** |
|---|---|---|
| qué pasó | alguien **decidió** algo del paper para destrabar una máquina | eso quedó guardado en un archivo **que se reparte** |
| la pregunta | ¿quién decidió? | ¿dónde vive? |
| cómo se arregla | sacarlo, para que la skill pregunte al usarse | moverlo a la copia del paper |

Mover el archivo **no desinventa la decisión**. Si una atadura la derivó un
agente leyendo prosa, llevarla a un lugar privado la saca de lo que se reparte
y la deja siendo, igual, una decisión que tomó una máquina.

---

## Las cuatro piezas que tiene que tener cualquier declaración

Salieron de comparar dos cosas que ya existen y funcionan distinto: una atadura
—que se graba con un verbo— y un marcador de raíz —que alguien escribía por
fuera—.

```
1. MUESTRA   el estado sale en el reporte de posición, antes de chocarse
2. PREGUNTA  la negativa nombra el comando exacto y lee el disco
             para decir qué ve
3. VALIDA    al escribir, con la persona mirando — no tres pasos después,
             en otro comando, con un mensaje sin relación
4. SELLA     una edición hecha por fuera no se lee como una decisión
```

Si falta la 3, un valor equivocado entra y se descubre lejos. Si falta la 2, la
negativa es cierta e inútil. Si falta la 1, una sesión nueva no sabe dónde
está. Si falta la 4, una edición no revisada es indistinguible de una decisión
tomada.

**Sobre la 4, decilo a su fuerza real.** El sello que existe es
auto-consistencia, no criptografía: no hay secreto, y quien reproduzca la
convención puede editar y recalcular el digesto. Defiende contra una edición
**distraída**, nunca contra una **decidida**. Prometer más de lo que el
mecanismo da es peor que el hueco. Mantener eso cierto es un **test**
(`paper_marker.SEAL_STRENGTH` es una constante única, y un test exige que todas
las superficies que la citan coincidan byte a byte), no una promesa de que
alguien lo revise.

---

## Estado medido el 2026-09-20

### En las skills

```
proposal-deliberation        33
proposal-implementation      18
experimental-deliberation     9
paper-writing                 1   ← una lista de ejemplo en prosa
las otras cinco               0
```

`paper-writing` se limpió durante esta sesión. Las tres hermanas no pasaron
nunca por esto.

**Y no son solo nombres de archivo en ejemplos.** El peor:

```
proposal-deliberation/profile.ts:44        stem: "research-concept"
```

---

## La distinción que esta auditoría necesita antes que nada

**No todo nombre propio dentro de la forja es una fuga.** La forja tiene su
propia arquitectura —carpetas que ella define, versiona y exige— y apuntar a
esas carpetas por su nombre es correcto. Es la arquitectura, no el producto.

```
estructura de la forja          contenido de un paper
────────────────────────        ──────────────────────
guidance/data-paper             CREDA
guidance/paper-guide            research-concept
guidance/reference-papers       s41597-026-06758-7
proposals/  experiments/        "fixed CREDA base"
implementations/
```

La de la izquierda viaja con `.gitkeep` a cualquier clon y está vacía de
contenido. La de la derecha es el paper de alguien. Una skill que nombra la
izquierda describe su propio andamio; una que nombra la derecha lleva un paper
adentro.

**La prueba:** *"si otra persona clona la forja para escribir un paper
completamente distinto, ¿este nombre le sirve o le estorba?"*

- `guidance/data-paper` → le sirve. Es donde va **su** paper de datos.
- `research-concept` → le estorba. Es el linaje del paper de otro.

**Esto ya produjo un falso positivo, y del caro.** Sin esta distinción,
`guidance/data-paper` se leyó como fuga y se reemplazó en
`paper-writing/SKILL.md` por `evidence-source` — una carpeta **que no existe en
ningún lado del repositorio**. Y una prosa que decía con precisión *"`guidance/
data-paper/` existía en este disco y no tenía `.gitkeep`"* se volvió *"la
carpeta clasificada evidence de este repositorio"*. Se hizo la documentación
**menos exacta** para esquivar un nombre que no era una fuga.

> Una auditoría que no separa la arquitectura del producto no da falsos
> negativos: da **falsos positivos**, y cada uno cambia algo que estaba bien
> por algo inventado.

### En los tests

```
513 apariciones en 54 archivos
```

Casi todas en las suites de `proposal-deliberation`. Son nombres reales usados
como datos de prueba: `research-concept-r01.md` y parientes.

---

## Los tres casos, que se arreglan distinto

**Caso 1 — `profile.ts`.** Tiene defensa escrita al lado: *"este profile es
ahora el único lugar que los nombra, y el núcleo los lee de ahí."* El motor es
genérico y el profile configura. El problema no es el patrón: es que **hay un
solo `profile.ts` por skill y sí se reparte**. El día que arranques un segundo
paper, tenés que editar la forja — cuando el modelo correcto es llenar un
espacio destinado.

**Caso 2 — `usage.md`.** Recetas de uso con tus nombres. No rompe nada:
enseña mal. Alguien clona para escribir de otra cosa y cada ejemplo le muestra
tu documento. Se arregla con nombres inventados.

**Caso 3 — `SKILL.md`.** La doctrina exige, por nombre, una carpeta tuya. Un
paper que organice su evidencia distinto no puede cumplir esa regla: no le
falta el material, le falta tu nombre de carpeta. **No se puede separar del
caso 1**, porque la prosa describe el código.

---

## El prompt, para correr skill por skill

Correr **uno por skill**, nunca uno solo para todas: el hallazgo de una skill
no debe hacer que otra se lea sucia, y el alcance grande invita a "arreglar de
paso" cosas que nadie revisó.

> Auditá **una sola skill**, `<NOMBRE>`, bajo `.opencode/skills/<NOMBRE>/`, más
> las suites que le correspondan bajo `tests/`. Solo esa. Si encontrás algo en
> otra skill, anotalo y seguí: no lo toques.
>
> **Derivá el vocabulario de producto del disco, nunca de una lista.** Los
> nombres de primer nivel bajo `proposals/`, `experiments/`, `implementations/`
> y `guidance/`. Esas carpetas están en `.gitignore`, así que `fd` y `rg`
> necesitan `-I -H` o vas a concluir que están vacías — ese error se cometió
> seis veces en este repo.
>
> Descartá las colisiones de inglés común (`data`, `paper`, `method`,
> `computation`): que un repositorio objetivo tenga una palabra no la vuelve un
> nombre de producto. Un nombre de método, un stem de documento o un id de
> paper sí lo son.
>
> **Para cada aparición, clasificá cuál de los tres casos es** —constante de
> configuración, ejemplo de manual, o doctrina— y **medí si está exigida en
> código o solo escrita**. Una doctrina que describe lo que el motor realmente
> hace es cierta: cambiarle la prosa sin cambiar el motor la vuelve mentira, y
> ese es un defecto peor que el original.
>
> Después preguntá lo que de verdad importa, que no es la fuga sino la aguja:
>
> - ¿Hay algún lugar donde la skill **exija** una declaración y **no tenga un
>   verbo que la escriba**? Si lo hay, alguien la está escribiendo por fuera y
>   la skill no valida, no sella y no muestra que falta.
> - ¿Alguna decisión sobre el paper la toma un agente leyendo prosa, en vez de
>   la persona usando la skill?
> - ¿El estado de cada espacio destinado **se ve** al preguntar dónde estamos,
>   o solo aparece cuando algo choca?
>
> **Reportá, no repares.** Por cada hallazgo: el archivo y la línea, cuál de
> los tres casos, si está exigido en código, y cuál de las cuatro piezas falta.
> Si una premisa que te dieron resulta falsa al medirla, decilo — vale más que
> un plan construido encima.
>
> Cerrá con los comandos exactos que corriste y sus resultados, para que otro
> pueda repetirlos sin creerte.

---

## Cómo re-medir

```bash
# vocabulario de producto, derivado del disco
fd -I -H -t d . proposals experiments implementations guidance --max-depth 1
fd -I -H -t f . proposals --max-depth 1

# fuga por skill
for d in .opencode/skills/*/; do
  s=$(basename "$d"); [ "${s:0:1}" = "_" ] && continue
  n=$(rg -c -w '<palabras derivadas arriba>' "$d" 2>/dev/null \
      | awk -F: '{x+=$2} END{print x+0}')
  [ "$n" != "0" ] && printf '  %-30s %s\n' "$s" "$n"
done

# el guard que ya existe, y su punto ciego
cd tests && ../.venv/bin/python -m unittest \
  test_proposal_implementation.ForgeVocabularyDerivedGuardTests
```

**El punto ciego del guard, que importa:** deriva su lista de palabras
prohibidas leyendo **solo** `implementations/`. Los nombres que viven en
`proposals/` y `guidance/` le fueron invisibles hasta que se lo ensanchó. Por
eso catorce líneas entraron a contratos que se reparten con la suite en verde.
Si volvés a encontrar fugas que el guard no ve, **revisá de dónde deriva su
lista antes que la fuga misma**.

Y otro punto ciego suyo: **inspecciona comentarios y docstrings de los tests,
nunca los literales de código.** Una palabra prohibida en un comentario la ve;
la misma palabra como dato de una aserción, no.

---

## Cómo esta auditoría puede dar limpio sin serlo

Tres formas de mentir sin querer, las tres vistas en un solo día de trabajo.

**Un artefacto puede afirmar algo que el código no hace.** Cuatro documentos
—dos diseños, una tabla de archivos y una tarea tildada— afirmaban
comportamientos que no existían. **A los cuatro los encontró un cambio
posterior yendo a apoyarse ahí. Ninguno lo encontró su propia verificación.**

La causa es siempre la misma: un documento no se ejecuta. Se escribe la
intención, no se implementa, y nadie lo nota porque nada lo corre.

> **Regla:** no heredes ninguna afirmación de un artefacto anterior sin volver
> a medirla. Si vas a apoyarte en que algo funciona, corrélo.

**Una tarea puede estar tildada y hecha a medias.** Una tarea decía *"…echoed
by every corpus-reading verb"*, estaba marcada `[x]`, y pasó verify y archive.
El campo existía en el objeto, los tests que lo consumían pasaban, y **ningún
verbo lo imprimía**. Nadie corrió los tres verbos a mirar la salida.

> **Regla:** la prueba de que algo se ve es **correr el verbo y leer lo que
> imprime**. Afirmar que un campo existe en un objeto es exactamente el test
> que dejó pasar ese tilde falso.

**El informe de la auditoría puede repetir lo que le contaron.** Un verificador
que resume el informe del que implementó no verifica nada.

> **Regla:** exigí los comandos exactos y sus salidas. Y para las mutaciones,
> que las haya **corrido**, no leído: una mutación descrita y una ejecutada se
> leen igual en un informe.

---

## Trampas de operación, para quien corra el barrido

Ninguna es sobre el código; todas costaron una corrida perdida o un diagnóstico
falso.

- **`fd` y `rg` respetan `.gitignore`.** Este repo ignora `implementations/*`,
  `proposals/`, `experiments/`, `paper/*` y `guidance/*/*`. Sin `-I -H` vas a
  concluir que están vacías. Pasó seis veces.
- **El banco completo no entra en una sola corrida.** Tarda más que el límite
  de primer plano, y en segundo plano lo mata la memoria. Va en tandas,
  **secuenciales, nunca en paralelo** — dos tandas a la vez se pisan en
  `implementations/` y producen una falla que no existe.
- **Una corrida de `test_proposal_implementation` cortada a la mitad deja un
  directorio huérfano** `implementations/_smokebox_*` que pone en rojo la
  siguiente. Borralo y volvé a correr antes de anotar un número.
- **Una mutación del mismo tamaño puede reusar el `.pyc` viejo**, así que el
  código mutado nunca corre y el candado se lee vivo estando muerto. Purgá el
  bytecode.
- **`git diff --stat` no prueba que una mutación corrió** sobre un archivo no
  versionado: no muestra nada. Afirmá el conteo del ancla.
- **Los agentes terminan y no siempre commitean.** Tres unidades en un día
  reportaron listo con el trabajo suelto en el árbol, y hubo que recuperarlo a
  mano. Revisá `git status` antes de creer que una unidad cerró.
- **Contar líneas de motor es contar `scripts/`**, no la carpeta de la skill.
  Meter `SKILL.md` en la cuenta infla el número — me pasó, y reporté 323 donde
  eran 289.

---

## El molde, que ya está construido y embarcado

El cambio `the-skill-writes-the-declaration-it-demands` está archivado bajo
`openspec/changes/archive/2026-09-20-…` y **ya corre**. Implementa las cuatro
piezas para los dos marcadores de `paper-writing`. Lo que sigue está medido
contra el código embarcado, no contra su diseño.

### El verbo

```
paper_cli.py mark revisions --root <raiz> --revision-prefix <p> --ordinal-digits <n> [--unsealed]
paper_cli.py mark class     --folder <carpeta> --class <clase>              [--unsealed]
```

Un verbo, dos modos, uno por tipo de marcador. Su propia raíz, no un modo
colgado de otro verbo que escribe en otro archivo.

### Las cuatro piezas, como quedaron

**MUESTRA.** El reporte de posición trae el estado de cada espacio destinado,
con **un solo vocabulario** en las dos mitades:

```
proposals        declared-unsealed
experiments      undeclared          ← visible antes de chocarse
implementation   n/a                 ← es repositorio, no lleva declaración
data-paper       declared-unsealed
```

`n/a` y `undeclared` no son lo mismo: uno no corresponde, el otro falta. Si se
mezclan, alguien va a intentar declarar algo que no lleva declaración.

**PREGUNTA.** La negativa nombra el comando exacto y lee el disco para decir
qué ve. Los dos lugares que la lanzan comparten **un solo constructor**, así
que la identidad del mensaje es estructural y no una coincidencia de un texto
copiado.

**VALIDA al escribir.** Declarar tres dígitos teniendo archivos de dos se
rechaza en el momento, con la persona mirando. Antes entraba y aparecía mucho
después, en otro comando, con un mensaje sin relación.

**SELLA.** Un módulo único es dueño del sello — no dos ideas de qué significa
sellar. Y se verifica **dentro de los lectores**, nunca en el reporte: si se
verificara al reportar sería el décimo guard de este repo alcanzable solo desde
un verbo de solo-lectura. Sus mutaciones corren por `write` y `validate`.

### La propiedad de migración, que hay que preservar

**Lo viejo se sigue leyendo.** Los cinco marcadores que existían antes del
sello —`proposals/` y las cuatro carpetas de `guidance/`— reportan
`declared-unsealed` y no rompen nada. Un cambio que obligue a re-declarar todo
frena el paper.

### El modo de reversión, que es menos obvio de lo que parece

`--unsealed` escribe la gramática anterior al sello. Hace falta porque **los
dos lectores rechazan una clave desconocida**: si alguien revierte el cambio
sin más, los marcadores sellados quedan **ilegibles**, no meramente sin sellar.
La reversión se hace corriendo el verbo mientras el código todavía existe,
nunca con un editor.

---

## Cuando se aborden las tres hermanas

Ese es el molde, y el orden importa: **el `profile.ts` deja de nombrar, hay
dónde declararlo, y hay un verbo que lo escribe — las tres juntas.**

Si se mueven los valores sin construir el verbo, se repite la cerradura sin
llave que ya se construyó dos veces en este repositorio y hubo que corregir
después en los dos casos.

---

## Lo que este documento no cubre

- Qué hacer con el `profile.ts` como concepto: si un único lugar sancionado
  donde una skill nombre un paper es aceptable o no, es una decisión del dueño,
  no un defecto a reparar de oficio.
- Las suites de `proposal-deliberation` (513 apariciones) son el volumen más
  grande y el trabajo más mecánico; conviene medirlas aparte de las skills.
- Hay un test en `remote-execution` que falla solo cuando corre en el mismo
  proceso que otros catorce módulos, y pasa aislado. Es un artefacto de
  aislamiento, no una fuga, pero aparece en los barridos y conviene saberlo.
