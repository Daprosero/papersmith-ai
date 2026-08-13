"""El sello que ata un informe al código que lo produjo.

Un cuaderno ejecutado dice que sus celdas corrieron alguna vez, no que corrieron
contra este código. Sin sello, un informe viejo y uno recién generado se ven
idénticos, y el viejo se sigue creyendo mientras el código se mueve por debajo.

Este módulo lo estampa. El cuaderno lo imprime al final, la verificación lo
recomputa, y si no coinciden el informe es una reliquia.

Vive en el paquete del banco porque es parte de producir el informe, no de la
formulación: no implementa ninguna ecuación y por eso no declara `__provenance__`.

**Las dos mitades tienen que dar el mismo número.** Esta la escribe el destino y
la otra la recomputa la verificación, así que probar cada una contra un fixture
propio verificaría las dos mitades y nunca la unión, que es lo único que importa
acá. La forja tiene una prueba que corre las dos sobre el mismo árbol y compara.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Lo que el cuaderno imprime antes del digest. La verificación lo busca literal.
MARKER = "SOURCES-SHA256"


def source_digest(repository: Path, package: str) -> str:
    """Un hash sobre todo de lo que dependen las afirmaciones de un informe.

    Las fechas de modificación no sirven: un clon las reescribe todas con la hora
    del checkout y el orden se pierde. El contenido sí.

    Cubre el paquete del método, el del banco y los tests. El del banco entra
    porque es el módulo que renderiza las tablas y escribe las conclusiones —
    dejarlo afuera permitía corregir una conclusión y que el registro siguiera
    afirmando la vieja con la verificación en verde.
    """
    digest = hashlib.sha256()
    roots = [repository / "src" / package,
             repository / "src" / f"{package}_Benchmark",
             repository / "tests"]
    for root in roots:
        if not root.is_dir():
            continue
        for file in sorted(root.rglob("*.py")):
            if "__pycache__" in file.parts:
                continue
            digest.update(str(file.relative_to(repository)).encode("utf-8"))
            digest.update(file.read_bytes())
    return digest.hexdigest()


def stamp(repository: Path, package: str) -> str:
    """La línea que el cuaderno imprime para dejar constancia de contra qué corrió."""
    return f"{MARKER} {source_digest(repository, package)}"
