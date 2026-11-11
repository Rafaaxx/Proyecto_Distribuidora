"""Matriz de privilegios de base de datos, tabla por tabla (change 28, tarea 1.3; D10).

Fuente de verdad de lo que `app_runtime`, `app_backup` y `app_mantenimiento` pueden hacer sobre
el esquema `public` (INV-05, ADR-020, `02` §18). `test_permisos_de_base.py` la compara con los
privilegios REALES de una base migrada (`pg_class.relacl` y `pg_attribute.attacl`, no con lo que
dicen las migraciones: un `GRANT` armado en un bucle tambien se ve) y falla nombrando tabla, rol y
privilegio que sobra o falta. Una tabla nueva sin entrada aca hace fallar la verificacion: quien la
crea declara aca, a proposito, que puede hacer cada rol con ella.

Letras de los privilegios: `S` SELECT, `I` INSERT, `U` UPDATE, `D` DELETE.

Reglas por tipo (ADR-020):

- `libro`: solo insercion (`SI`). Nunca `UPDATE` ni `DELETE` (INV-05).
- `documento`: documento confirmado, solo insercion; si cambia de estado (anulacion, rendicion,
  resolucion de una observacion) el `UPDATE` es solo de las columnas de la transicion, nunca de la
  tabla entera (`columnas_update`).
- `saldo`: saldo materializado (`SIU`); su libro lo respalda y la verificacion de consistencia lo
  compara (INV-12, INV-13).
- `maestra`: datos maestros (`SIU`), nunca `DELETE` (se desactivan).
- `operacional`: sesiones y comandos (`SIU`).
- `asociacion` y `borrador`: los unicos con `DELETE`, y cada uno con su justificacion escrita.
- `catalogo`, `resultado`, `sistema`: solo lectura para la aplicacion.

`app_backup` no tiene ACL propio en ninguna tabla: lee todo por ser miembro del rol predefinido
`pg_read_all_data` (change 27a, D11). `app_mantenimiento` tiene solo lo que sus tareas necesitan
(D3): leer lo que compara la verificacion, insertar sus resultados y borrar intentos de login.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LETRAS = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE"}


def _privilegios(letras: str) -> frozenset[str]:
    return frozenset(LETRAS[letra] for letra in letras)


@dataclass(frozen=True)
class Entrada:
    """Lo que cada rol puede hacer con una tabla."""

    tipo: str
    runtime: frozenset[str]
    mantenimiento: frozenset[str] = frozenset()
    columnas_update: frozenset[str] = frozenset()
    """`UPDATE` de `app_runtime` limitado a estas columnas (sin `UPDATE` de tabla)."""
    justificacion_delete: str | None = None
    """Obligatoria si `app_runtime` o `app_mantenimiento` pueden `DELETE`; prohibida si no."""
    notas: str = field(default="", compare=False)


def _e(
    tipo: str,
    runtime: str,
    *,
    mantenimiento: str = "",
    columnas: tuple[str, ...] = (),
    delete: str | None = None,
) -> Entrada:
    return Entrada(
        tipo=tipo,
        runtime=_privilegios(runtime),
        mantenimiento=_privilegios(mantenimiento),
        columnas_update=frozenset(columnas),
        justificacion_delete=delete,
    )


_ANULACION = ("estado", "anulacion_motivo_id")

MATRIZ: dict[str, Entrada] = {
    # --- libros: solo insercion (INV-05) -------------------------------------------------
    "auditoria": _e("libro", "SI"),
    "cuenta_movimiento": _e("libro", "SI", mantenimiento="S"),
    "stock_movimiento": _e("libro", "SI", mantenimiento="S"),
    "costo_producto_mov": _e("libro", "SI", mantenimiento="S"),
    "intento_pin_autorizacion": _e("libro", "SI"),
    "venta_linea_descuento": _e("libro", "SI"),
    "intento_login": _e(
        "libro",
        "SI",
        mantenimiento="SD",
        delete=(
            "app_mantenimiento (no app_runtime) borra los intentos de inicio de sesion de mas de "
            "24 horas: tabla de limite de intentos, sin valor contable; ADR-018, ADR-057 punto 9; "
            "change 28 D3, D7"
        ),
    ),
    # --- saldos materializados -----------------------------------------------------------
    "saldo_cuenta": _e("saldo", "SIU", mantenimiento="S"),
    "stock_saldo": _e("saldo", "SIU", mantenimiento="S"),
    "costo_producto": _e("saldo", "SIU", mantenimiento="S"),
    # --- documentos confirmados: solo insercion ------------------------------------------
    "ajuste_stock_linea": _e("documento", "SI"),
    "cobranza_anulacion": _e("documento", "SI"),
    "cobranza_medio": _e("documento", "SI"),
    "compra_linea": _e("documento", "SI"),
    "costo_informado": _e("documento", "SI"),
    "importacion": _e("documento", "SI"),
    "pago_proveedor_medio": _e("documento", "SI"),
    "rendicion": _e("documento", "SI"),
    "rendicion_linea": _e("documento", "SI"),
    "transferencia_linea": _e("documento", "SI"),
    "venta_anulacion": _e("documento", "SI"),
    "venta_linea": _e("documento", "SI"),
    # --- documentos con transicion de estado: UPDATE solo de esas columnas ---------------
    "ajuste_stock": _e("documento", "SI", columnas=(*_ANULACION, "anulado_en", "anulado_por_id")),
    "cobranza": _e("documento", "SI", columnas=("estado",)),
    "comando_cuarentena": _e(
        "documento",
        "SI",
        columnas=("comentario", "revisado_en", "revisado_por_id", "vinculo_id", "vinculo_tipo"),
    ),
    "comando_rechazado": _e(
        "documento",
        "SI",
        columnas=(
            "comentario",
            "estado",
            "resuelto_en",
            "resuelto_por_id",
            "vinculo_id",
            "vinculo_tipo",
        ),
    ),
    "compra": _e("documento", "SI", columnas=(*_ANULACION, "anulada_en", "anulada_por_id")),
    "jornada": _e(
        "documento",
        "SI",
        columnas=(
            "cerrada_en",
            "cerrada_por_id",
            "entrega_occurred_at",
            "entrega_secuencia",
            "entregada_en",
            "estado",
            "liberada_en",
            "liberada_por_id",
            "motivo_liberacion_id",
            "observacion_liberacion",
            "rendida_en",
            "rendida_por_id",
        ),
    ),
    "lista_version": _e(
        "documento",
        "SI",
        columnas=(
            "anulado_en",
            "anulado_por_id",
            "estado",
            "generado_en",
            "publicado_en",
            "publicado_por_id",
            "version_base_id",
            "vigencia_desde",
            "vigencia_hasta",
        ),
    ),
    "observacion": _e(
        "documento", "SI", columnas=("comentario", "estado", "resuelto_en", "resuelto_por_id")
    ),
    "pago_proveedor": _e("documento", "SI", columnas=(*_ANULACION, "anulado_en", "anulado_por_id")),
    "transferencia": _e("documento", "SI", columnas=(*_ANULACION, "anulada_en", "anulada_por_id")),
    "venta": _e("documento", "SI", columnas=("estado",)),
    # --- maestras: nunca DELETE ----------------------------------------------------------
    "alicuota_iva": _e("maestra", "SIU"),
    "categoria": _e("maestra", "SIU"),
    "cliente": _e("maestra", "SIU"),
    "configuracion_organizacion": _e("maestra", "SIU"),
    "dispositivo": _e("maestra", "SIU"),
    "lista_precio": _e("maestra", "SIU"),
    "marca": _e("maestra", "SIU"),
    "medio_pago": _e("maestra", "SIU"),
    "motivo": _e("maestra", "SIU"),
    "organizacion": _e("maestra", "SIU", mantenimiento="S"),
    "presentacion": _e("maestra", "SIU"),
    "producto": _e("maestra", "SIU"),
    "proveedor": _e("maestra", "SIU"),
    "redondeo_categoria": _e("maestra", "SIU"),
    "regla_descuento": _e("maestra", "SIU"),
    "regla_margen": _e("maestra", "SIU"),
    "rol": _e("maestra", "SIU"),
    "ubicacion": _e("maestra", "SIU"),
    "usuario": _e("maestra", "SIU"),
    # --- operacionales -------------------------------------------------------------------
    "comando": _e("operacional", "SIU"),
    "sesion_refresh": _e("operacional", "SIU"),
    # --- con DELETE justificado (ADR-020: tablas operacionales y de asociacion) ----------
    "rol_permiso": _e(
        "asociacion",
        "SID",
        delete=(
            "asociacion rol-permiso sin datos propios: la administracion de roles quita un "
            "permiso del rol (identidad/repository.py quitar_permiso_de_rol); la auditoria del "
            "comando conserva quien lo quito y cuando (a1b2c3d4e5f6; AUD-02)"
        ),
    ),
    "regla_descuento_alcance": _e(
        "asociacion",
        "SID",
        delete=(
            "asociacion regla-entidad sin datos propios: se reemplazan los alcances de una regla "
            "en BORRADOR (descuentos/repository.py borrar_alcances_de_borrador, unico DELETE del "
            "modulo; b5c6d7e8f9a0, ADR-050 D17)"
        ),
    ),
    "precio_item": _e(
        "borrador",
        "SIUD",
        delete=(
            "precios de una version en BORRADOR que se recalculan o se vuelven a escribir "
            "(precios/repository.py borrar_precios_de_version, solo sobre borradores); una "
            "version publicada no se toca (e2f3a4b5c6d7, change 13 D5, D13)"
        ),
    ),
    # --- solo lectura para la aplicacion -------------------------------------------------
    "permiso": _e("catalogo", "S"),
    "verificacion_consistencia": _e("resultado", "S", mantenimiento="SI"),
    "alembic_version": _e("sistema", ""),
}

ROLES_DE_SERVICIO = ("app_runtime", "app_backup", "app_mantenimiento")
DUENO = "app_migrations"
LIBROS_SIN_UPDATE_NI_DELETE = (
    "auditoria",
    "cuenta_movimiento",
    "stock_movimiento",
    "costo_producto_mov",
    "intento_login",
)
SECUENCIAS_DECLARADAS: frozenset[str] = frozenset()
"""Hoy no hay secuencias: las claves son UUID. Una secuencia nueva obliga a declararla."""


# --- comparacion ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrivilegiosReales:
    """Lo que la base dice tener, por rol y tabla (leido por `test_permisos_de_base.py`)."""

    tablas: frozenset[str]
    tabla: dict[str, dict[str, frozenset[str]]]
    """`tabla[rol][nombre_de_tabla]` = privilegios de tabla otorgados al rol."""
    columnas_update: dict[str, dict[str, frozenset[str]]]
    """`columnas_update[rol][tabla]` = columnas con `UPDATE` otorgado por columna."""
    otros_de_columna: dict[str, dict[str, frozenset[str]]]
    """`otros_de_columna[rol][tabla]` = columnas con cualquier otro privilegio por columna."""
    con_opcion_de_otorgar: dict[str, frozenset[str]]
    """`con_opcion_de_otorgar[rol]` = tablas donde el rol puede otorgar lo que tiene."""


def comparar(reales: PrivilegiosReales, matriz: dict[str, Entrada] | None = None) -> list[str]:
    """Diferencias entre la matriz y la base, una por linea: nombra tabla, rol y privilegio."""
    matriz = MATRIZ if matriz is None else matriz
    diferencias: list[str] = []

    for tabla in sorted(reales.tablas - set(matriz)):
        diferencias.append(f"{tabla}: tabla sin declarar en la matriz de permisos")
    for tabla in sorted(set(matriz) - reales.tablas):
        diferencias.append(f"{tabla}: declarada en la matriz pero no existe en la base")

    for tabla in sorted(reales.tablas & set(matriz)):
        entrada = matriz[tabla]
        esperados = {
            "app_runtime": entrada.runtime,
            "app_mantenimiento": entrada.mantenimiento,
            "app_backup": frozenset(),
        }
        for rol, esperado in esperados.items():
            real = reales.tabla.get(rol, {}).get(tabla, frozenset())
            for privilegio in sorted(real - esperado):
                diferencias.append(f"{tabla}: {rol} tiene {privilegio} y la matriz no lo declara")
            for privilegio in sorted(esperado - real):
                diferencias.append(f"{tabla}: {rol} no tiene {privilegio} y la matriz lo declara")
        real_columnas = reales.columnas_update.get("app_runtime", {}).get(tabla, frozenset())
        for columna in sorted(real_columnas - entrada.columnas_update):
            diferencias.append(
                f"{tabla}: app_runtime tiene UPDATE de la columna {columna} y la matriz no lo "
                "declara"
            )
        for columna in sorted(entrada.columnas_update - real_columnas):
            diferencias.append(
                f"{tabla}: app_runtime no tiene UPDATE de la columna {columna} y la matriz lo "
                "declara"
            )
        for rol in ROLES_DE_SERVICIO:
            extra = reales.otros_de_columna.get(rol, {}).get(tabla, frozenset())
            if extra:
                diferencias.append(
                    f"{tabla}: {rol} tiene privilegios por columna no declarados en {sorted(extra)}"
                )
            if rol != "app_runtime":
                columnas = reales.columnas_update.get(rol, {}).get(tabla, frozenset())
                if columnas:
                    diferencias.append(
                        f"{tabla}: {rol} tiene UPDATE por columna en {sorted(columnas)}"
                    )
    for rol in ROLES_DE_SERVICIO:
        for tabla in sorted(reales.con_opcion_de_otorgar.get(rol, frozenset())):
            diferencias.append(f"{tabla}: {rol} puede otorgar sus privilegios (GRANT OPTION)")
    return diferencias


def borrados_sin_justificacion(matriz: dict[str, Entrada] | None = None) -> list[str]:
    """`DELETE` declarado sin justificacion escrita, o justificacion de un `DELETE` inexistente."""
    matriz = MATRIZ if matriz is None else matriz
    problemas: list[str] = []
    for tabla, entrada in sorted(matriz.items()):
        con_delete = "DELETE" in entrada.runtime or "DELETE" in entrada.mantenimiento
        texto = (entrada.justificacion_delete or "").strip()
        if con_delete and len(texto) < 40:
            problemas.append(f"{tabla}: DELETE sin justificacion escrita")
        if not con_delete and texto:
            problemas.append(f"{tabla}: justificacion de un DELETE que la matriz no declara")
    return problemas
