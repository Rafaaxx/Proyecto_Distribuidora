"""Change 28, tarea 5.2 (D12; `docs/02-arquitectura.md` §15; `docs/04-roadmap-changes.md` §13).

Ratchet de cobertura de invariantes: lee la tabla de `docs/01-dominio.md` §20 y falla nombrando
cada invariante que ninguna prueba cita por ID en las carpetas que corre la CI, salvo INV-09 e
INV-20, eximidos por nombre y con su razón (pertenecen al módulo de facturación, fuera de la
etapa 1). Un invariante nuevo en la tabla sin prueba pone en rojo esta prueba.

Se busca sin correr nada: lectura de texto de los archivos de prueba (`.py`, `.ts`, `.tsx`,
`.json`). Este archivo no cuenta como prueba de ninguno (se excluye de la búsqueda).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

RAIZ_DEL_REPO = Path(__file__).resolve().parents[3]
DOCUMENTO_DE_DOMINIO = RAIZ_DEL_REPO / "docs" / "01-dominio.md"

CARPETAS_DE_PRUEBAS = (
    RAIZ_DEL_REPO / "backend" / "tests" / "unit",
    RAIZ_DEL_REPO / "backend" / "tests" / "integration",
    RAIZ_DEL_REPO / "backend" / "tests" / "concurrency",
    RAIZ_DEL_REPO / "backend" / "tests" / "properties",
    RAIZ_DEL_REPO / "backend" / "tests" / "infra",
    RAIZ_DEL_REPO / "backend" / "tests" / "fixtures_compartidos",
    RAIZ_DEL_REPO / "frontend" / "tests" / "unit",
)

EXTENSIONES_DE_PRUEBAS = frozenset({".py", ".ts", ".tsx", ".json"})
CARPETAS_IGNORADAS = frozenset({"__pycache__", "node_modules", ".pytest_cache"})

INVARIANTES_EXIMIDOS: Mapping[str, str] = {
    "INV-09": (
        "El importe facturado de una venta pertenece al módulo de facturación (FAC-01, FAC-07), "
        "fuera de la etapa 1 (docs/04 §13)."
    ),
    "INV-20": (
        "Facturar nunca vuelve a generar la deuda de la mercadería: pertenece al módulo de "
        "facturación (FAC-01), fuera de la etapa 1 (docs/04 §13)."
    ),
}

_FILA_DE_INVARIANTE = re.compile(r"^\|\s*(INV-\d{2})\s*\|", re.MULTILINE)


def invariantes_de_la_tabla(texto: str) -> list[str]:
    """Los ID de la tabla de `## 20. Invariantes`, en orden (D12)."""
    inicio = re.search(r"^## 20\.[^\n]*$", texto, re.MULTILINE)
    if inicio is None:
        return []
    resto = texto[inicio.end() :]
    siguiente = re.search(r"^## ", resto, re.MULTILINE)
    seccion = resto[: siguiente.start()] if siguiente else resto
    return _FILA_DE_INVARIANTE.findall(seccion)


def _patron_del_id(invariante: str) -> re.Pattern[str]:
    """`INV-05` también se cita como `inv05`, `INV_05` o `INV 05`, pero nunca como parte de otro
    número (`INV-050`) ni de otra palabra (`PREINV-05`)."""
    numero = invariante.removeprefix("INV-")
    return re.compile(rf"(?<![A-Za-z0-9])INV[-_ ]?{numero}(?!\d)", re.IGNORECASE)


def _archivos_de_prueba(carpetas: Iterable[Path]) -> Iterable[Path]:
    for carpeta in carpetas:
        if not carpeta.is_dir():
            continue
        for archivo in sorted(carpeta.rglob("*")):
            if (
                archivo.is_file()
                and archivo.suffix in EXTENSIONES_DE_PRUEBAS
                and not CARPETAS_IGNORADAS.intersection(archivo.parts)
            ):
                yield archivo


def invariantes_sin_prueba(
    invariantes: Iterable[str],
    carpetas: Iterable[Path],
    *,
    eximidos: Mapping[str, str],
    excluir: frozenset[Path] = frozenset(),
) -> list[str]:
    """Los invariantes (sin los eximidos) que ningún archivo de `carpetas` cita por ID."""
    pendientes = {i: _patron_del_id(i) for i in invariantes if i not in eximidos}
    for archivo in _archivos_de_prueba(carpetas):
        if not pendientes:
            break
        if archivo.resolve() in excluir:
            continue
        texto = archivo.read_text(encoding="utf-8", errors="ignore")
        for invariante in [i for i, patron in pendientes.items() if patron.search(texto)]:
            del pendientes[invariante]
    return list(pendientes)


ESTE_ARCHIVO = frozenset({Path(__file__).resolve()})


def test_la_tabla_de_la_seccion_20_trae_los_21_invariantes() -> None:
    """Lee el documento real: los 21 invariantes, en orden, sin los de otras secciones."""
    invariantes = invariantes_de_la_tabla(DOCUMENTO_DE_DOMINIO.read_text(encoding="utf-8"))

    assert invariantes == [f"INV-{n:02d}" for n in range(1, 22)]


def test_la_tabla_se_lee_solo_de_la_seccion_20() -> None:
    texto = (
        "## 19. Otra\n\n| INV-99 | no es de la sección |\n\n"
        "## 20. Invariantes\n\n| ID | Invariante |\n| --- | --- |\n"
        "| INV-01 | uno |\n| INV-02 | dos |\n\n"
        "## 21. Efectos\n\n| INV-98 | tampoco |\n"
    )

    assert invariantes_de_la_tabla(texto) == ["INV-01", "INV-02"]
    assert invariantes_de_la_tabla("sin sección") == []


def test_los_eximidos_son_inv09_e_inv20_cada_uno_con_su_razon() -> None:
    """Escenario 'Una excepción declarada': solo esos dos, por nombre, con razón escrita."""
    assert set(INVARIANTES_EXIMIDOS) == {"INV-09", "INV-20"}
    assert all("facturación" in razon for razon in INVARIANTES_EXIMIDOS.values())


def test_cada_invariante_de_la_etapa_1_tiene_una_prueba_que_lo_cita_por_id() -> None:
    """Escenario 'Cada invariante de la etapa 1 tiene una prueba que lo cita': falla nombrando
    los que no tienen ninguna, en las carpetas que corre la CI."""
    invariantes = invariantes_de_la_tabla(DOCUMENTO_DE_DOMINIO.read_text(encoding="utf-8"))

    sin_prueba = invariantes_sin_prueba(
        invariantes,
        CARPETAS_DE_PRUEBAS,
        eximidos=INVARIANTES_EXIMIDOS,
        excluir=ESTE_ARCHIVO,
    )

    assert sin_prueba == [], (
        f"Invariantes de docs/01 §20 sin ninguna prueba que los cite: {sin_prueba}"
    )


def test_un_invariante_sin_prueba_se_nombra(tmp_path: Path) -> None:
    """Escenario 'Un invariante sin prueba hace fallar la verificación' (datos de prueba)."""
    (tmp_path / "test_a.py").write_text("def test_inv01_algo():\n    pass\n", encoding="utf-8")
    (tmp_path / "otra.ts").write_text("// INV-03: tercero\n", encoding="utf-8")

    sin_prueba = invariantes_sin_prueba(
        ["INV-01", "INV-02", "INV-03", "INV-04"], [tmp_path], eximidos={}
    )

    assert sin_prueba == ["INV-02", "INV-04"]


def test_un_eximido_no_se_informa_aunque_no_tenga_prueba(tmp_path: Path) -> None:
    (tmp_path / "test_a.py").write_text("# INV-01\n", encoding="utf-8")

    sin_prueba = invariantes_sin_prueba(
        ["INV-01", "INV-09"], [tmp_path], eximidos={"INV-09": "facturación"}
    )

    assert sin_prueba == []


def test_un_id_dentro_de_otro_numero_o_palabra_no_cuenta(tmp_path: Path) -> None:
    """INV-1 no es INV-10, INV-210 no es INV-21 y `PREINV-05` no es INV-05."""
    (tmp_path / "test_a.py").write_text("# INV-1 INV-210 PREINV-05 INV-100\n", encoding="utf-8")

    sin_prueba = invariantes_sin_prueba(["INV-10", "INV-21", "INV-05"], [tmp_path], eximidos={})

    assert sin_prueba == ["INV-10", "INV-21", "INV-05"]


def test_las_formas_de_citar_un_id_cuentan(tmp_path: Path) -> None:
    (tmp_path / "test_a.py").write_text(
        "def test_inv21_x():\n    pass\n# INV_05\n# inv-06 y INV 07\n", encoding="utf-8"
    )

    sin_prueba = invariantes_sin_prueba(
        ["INV-21", "INV-05", "INV-06", "INV-07", "INV-08"], [tmp_path], eximidos={}
    )

    assert sin_prueba == ["INV-08"]


def test_el_archivo_excluido_y_las_carpetas_ignoradas_no_cuentan(tmp_path: Path) -> None:
    propio = tmp_path / "test_propio.py"
    propio.write_text("# INV-01 INV-02\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.ts").write_text("// INV-02\n", encoding="utf-8")

    sin_prueba = invariantes_sin_prueba(
        ["INV-01", "INV-02"], [tmp_path], eximidos={}, excluir=frozenset({propio.resolve()})
    )

    assert sin_prueba == ["INV-01", "INV-02"]
