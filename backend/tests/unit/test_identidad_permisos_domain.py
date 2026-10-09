"""Pruebas unitarias del catálogo de permisos y las plantillas de rol
(change 03, tarea 4.4). Dominio puro, sin base de datos.

La matriz `_TABLA_DOCUMENTO` transcribe la tabla de `docs/01-dominio.md`
§19 celda por celda, de forma independiente de `PLANTILLAS_DE_ROL`, para que
la comparación tenga valor: si alguien edita una plantilla sin mirar la
tabla del documento, esta prueba lo detecta.
"""

from __future__ import annotations

from app.modules.identidad.domain.permisos import (
    ADMINISTRACION,
    ADMINISTRADOR,
    CONSULTA_DIRECCION,
    PERMISOS_DEL_CATALOGO,
    PLANTILLAS_DE_ROL,
    SUPERVISOR_COMERCIAL,
    VENDEDOR_REPARTIDOR,
)

# (código, ADM, GES, SUP, VEN, CON) -- transcripción literal de `01` §19.
_TABLA_DOCUMENTO: tuple[tuple[str, bool, bool, bool, bool, bool], ...] = (
    ("ADMIN_USUARIOS", True, False, False, False, False),
    ("ADMIN_CONFIGURACION", True, False, False, False, False),
    ("GESTIONAR_DISPOSITIVOS", True, False, True, False, False),
    ("IMPORTAR_DATOS", True, False, False, False, False),
    ("GESTIONAR_CATALOGO", True, True, False, False, False),
    ("GESTIONAR_CLIENTES", True, True, True, False, False),
    ("GESTIONAR_CREDITO", True, True, False, False, False),
    ("GESTIONAR_PROVEEDORES", True, True, False, False, False),
    ("VER_COSTOS", True, True, False, False, False),
    ("EDITAR_COSTOS", True, True, False, False, False),
    ("VER_UTILIDAD", True, True, False, False, True),
    ("GESTIONAR_LISTAS", True, True, False, False, False),
    ("PUBLICAR_LISTAS", True, False, False, False, False),
    ("USAR_LISTA_ANTERIOR", True, False, True, False, False),
    ("GESTIONAR_DESCUENTOS", True, False, False, False, False),
    ("REGISTRAR_COMPRA", True, True, False, False, False),
    ("ANULAR_COMPRA", True, True, False, False, False),
    ("REGISTRAR_PAGO_PROVEEDOR", True, True, False, False, False),
    ("ANULAR_PAGO_PROVEEDOR", True, True, False, False, False),
    ("TRANSFERIR_STOCK", True, True, True, True, False),
    # Change 14 (`design.md` D5 punto 5, `01` §19): ADM y GES. Es la fila que fija QUE
    # roles reciben el permiso; la lista vive en `permisos.py` (ADMINISTRACION) y la
    # migracion `f3a4b5c6d7e8` la deriva de `PLANTILLAS_DE_ROL`.
    ("ANULAR_TRANSFERENCIA", True, True, False, False, False),
    ("AJUSTAR_STOCK", True, True, False, False, False),
    ("PERMITIR_STOCK_NEGATIVO", True, False, False, False, False),
    ("ABRIR_JORNADA", True, False, True, True, False),
    ("RENDIR_JORNADA", True, True, True, False, False),
    ("LIBERAR_UBICACION", True, False, True, False, False),
    ("VENDER", True, False, True, True, False),
    ("ANULAR_VENTA", True, True, True, False, False),
    ("DESCUENTO_MANUAL", True, False, True, True, False),
    ("AUTORIZAR_DESCUENTO", True, False, True, False, False),
    ("SUPERAR_CREDITO", True, False, True, False, False),
    ("VENDER_CLIENTE_SUSPENDIDO", True, False, True, False, False),
    ("REGISTRAR_COBRANZA", True, True, True, True, False),
    ("ANULAR_COBRANZA", True, True, True, False, False),
    ("REVISAR_OBSERVACIONES", True, True, True, False, False),
    ("VER_REPORTES", True, True, True, False, True),
    ("VER_AUDITORIA", True, False, False, False, True),
    ("FACTURAR", True, True, False, False, False),
    ("FACTURAR_ABSORBIENDO_IVA", True, False, False, False, False),
    ("ANULAR_FACTURA", True, True, False, False, False),
)

_ROLES_EN_ORDEN = (
    ADMINISTRADOR,
    ADMINISTRACION,
    SUPERVISOR_COMERCIAL,
    VENDEDOR_REPARTIDOR,
    CONSULTA_DIRECCION,
)


def test_la_tabla_transcripta_tiene_40_filas() -> None:
    assert len(_TABLA_DOCUMENTO) == 40


def test_el_catalogo_tiene_exactamente_40_permisos_sin_duplicados() -> None:
    codigos = [permiso.codigo for permiso in PERMISOS_DEL_CATALOGO]
    assert len(codigos) == 40
    assert len(set(codigos)) == 40


def test_el_catalogo_coincide_con_los_codigos_de_la_tabla_transcripta() -> None:
    codigos_catalogo = {permiso.codigo for permiso in PERMISOS_DEL_CATALOGO}
    codigos_tabla = {fila[0] for fila in _TABLA_DOCUMENTO}
    assert codigos_catalogo == codigos_tabla


def test_cada_celda_de_cada_plantilla_coincide_con_la_tabla_del_documento() -> None:
    """Escenario "Las cinco plantillas de rol quedan disponibles al crear la
    organización": recorre las 40 * 5 celdas, una por una."""
    errores = []
    for codigo, *marcas in _TABLA_DOCUMENTO:
        for rol, marcado in zip(_ROLES_EN_ORDEN, marcas, strict=True):
            tiene_permiso = codigo in PLANTILLAS_DE_ROL[rol]
            if tiene_permiso != marcado:
                errores.append(f"{rol}/{codigo}: esperado {marcado}, da {tiene_permiso}")

    assert errores == [], errores


def test_el_administrador_tiene_los_40_permisos() -> None:
    assert PLANTILLAS_DE_ROL[ADMINISTRADOR] == {fila[0] for fila in _TABLA_DOCUMENTO}


def test_el_vendedor_no_recibe_permisos_de_costo_ni_de_utilidad() -> None:
    """Escenario "El vendedor no recibe permisos de costo ni de utilidad"."""
    permisos_vendedor = PLANTILLAS_DE_ROL[VENDEDOR_REPARTIDOR]

    assert permisos_vendedor == {
        "VENDER",
        "REGISTRAR_COBRANZA",
        "ABRIR_JORNADA",
        "TRANSFERIR_STOCK",
        "DESCUENTO_MANUAL",
    }
    assert "VER_COSTOS" not in permisos_vendedor
    assert "VER_UTILIDAD" not in permisos_vendedor
