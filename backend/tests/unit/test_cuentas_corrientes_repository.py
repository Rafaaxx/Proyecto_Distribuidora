"""Tarea 4.1: `cuentas_corrientes/repository.py` recibe `organizacion_id` como
primer parámetro en TODA función pública, filtra TODA consulta por
`organizacion_id` (INV-02, `CLAUDE.md` §4) y hace las sumas en SQL (nunca trae
filas a Python para sumar, `CLAUDE.md` §4, CC-04, CC-07).

No necesitan PostgreSQL: inspeccionan la sentencia que el repositorio construye
(compilada al dialecto de PostgreSQL) en lugar de ejecutarla. El comportamiento
contra la base real (bloqueo, carrera de la primera fila, FK, saldo acumulado)
se prueba en `tests/integration/test_cuentas_corrientes_service.py`.

Reglas citadas: CC-04, CC-07, INV-02, INV-13, `design.md` D6, D9, D10.
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DataError, IntegrityError

from app.modules.cuentas_corrientes import repository
from app.modules.cuentas_corrientes.domain.errores import (
    RecursoNoEncontradoError,
    SaldoFueraDeRangoError,
)
from app.modules.cuentas_corrientes.domain.estado_de_cuenta import (
    LIMITE_MAXIMO,
    codificar_cursor,
)

ORG = uuid4()
ENTIDAD = uuid4()
MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
_DIALECTO = postgresql.dialect()


class _Resultado:
    def __init__(self, filas: list[Any]) -> None:
        self._filas = filas

    def all(self) -> list[Any]:
        return list(self._filas)

    def one_or_none(self) -> Any:
        return self._filas[0] if self._filas else None

    def scalar_one(self) -> Any:
        return self._filas[0]

    def scalar_one_or_none(self) -> Any:
        return self._filas[0] if self._filas else None


class _SesionEspia:
    """Sesión que NO toca la base: registra las sentencias y lo que se agrega, y
    devuelve filas preparadas."""

    def __init__(
        self,
        filas: list[Any] | None = None,
        *,
        error_al_ejecutar: Exception | None = None,
        error_al_agregar: Exception | None = None,
    ) -> None:
        self.filas = filas or []
        self.sentencias: list[Any] = []
        self.agregadas: list[object] = []
        self.savepoints = 0
        self._error_al_ejecutar = error_al_ejecutar
        self._error_al_agregar = error_al_agregar

    def _registrar(self, sentencia: Any) -> _Resultado:
        self.sentencias.append(sentencia)
        if self._error_al_ejecutar is not None:
            raise self._error_al_ejecutar
        return _Resultado(self.filas)

    def execute(self, sentencia: Any, *args: Any, **kwargs: Any) -> _Resultado:
        return self._registrar(sentencia)

    def scalars(self, sentencia: Any) -> _Resultado:
        return self._registrar(sentencia)

    def scalar(self, sentencia: Any) -> Any:
        self._registrar(sentencia)
        return self.filas[0] if self.filas else None

    def add(self, fila: object) -> None:
        self.agregadas.append(fila)

    def flush(self) -> None:
        if self._error_al_agregar is not None:
            raise self._error_al_agregar

    @contextlib.contextmanager
    def begin_nested(self) -> Iterator[None]:
        self.savepoints += 1
        yield
        self.flush()


def _sql(sentencia: Any) -> tuple[str, dict[str, Any]]:
    compilada = sentencia.compile(dialect=_DIALECTO)
    return str(compilada), dict(compilada.params)


def _valores(parametros: dict[str, Any]) -> list[Any]:
    return list(parametros.values())


def _error_integridad(mensaje: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception(mensaje))


# --- firmas -----------------------------------------------------------------


def _publicas() -> list[tuple[str, Any]]:
    return [
        (nombre, objeto)
        for nombre, objeto in vars(repository).items()
        if inspect.isfunction(objeto)
        and not nombre.startswith("_")
        and objeto.__module__ == repository.__name__
    ]


def test_el_repositorio_expone_las_operaciones_de_la_tarea_4_1() -> None:
    nombres = {nombre for nombre, _ in _publicas()}

    assert {
        "asegurar_saldo",
        "bloquear_saldo",
        "obtener_saldo",
        "insertar_movimiento",
        "actualizar_saldo",
        "existe_movimiento",
        "suma_del_libro",
        "saldo_anterior",
        "estado_de_cuenta",
        "verificar_consistencia",
    } <= nombres


def test_toda_funcion_publica_recibe_la_organizacion_primero() -> None:
    for nombre, funcion in _publicas():
        parametros = list(inspect.signature(funcion).parameters)
        assert parametros[0] == "organizacion_id", nombre
        assert parametros[1] == "sesion", nombre


def test_no_declara_ninguna_exencion_de_organizacion_id() -> None:
    assert isinstance(repository.FUNCIONES_SIN_ORGANIZACION_ID, frozenset)
    assert not repository.FUNCIONES_SIN_ORGANIZACION_ID


# --- creación perezosa y bloqueo de la fila de saldo (D10) -------------------


def test_asegurar_saldo_inserta_en_cero_y_no_pisa_una_fila_existente() -> None:
    sesion = _SesionEspia()

    repository.asegurar_saldo(
        ORG,
        sesion,
        cuenta_tipo="CLIENTE",
        entidad_id=ENTIDAD,
        momento=MOMENTO,  # type: ignore[arg-type]
    )

    (sentencia,) = sesion.sentencias
    sql, parametros = _sql(sentencia)
    assert sql.startswith("INSERT INTO saldo_cuenta")
    assert "ON CONFLICT (organizacion_id, cuenta_tipo, entidad_id) DO NOTHING" in sql
    assert ORG in _valores(parametros)
    assert ENTIDAD in _valores(parametros)
    assert Decimal("0.00") in _valores(parametros)
    assert sesion.savepoints == 1


def test_asegurar_saldo_de_un_proveedor_lleva_el_tipo_de_cuenta() -> None:
    sesion = _SesionEspia()

    repository.asegurar_saldo(
        ORG,
        sesion,
        cuenta_tipo="PROVEEDOR",
        entidad_id=ENTIDAD,
        momento=MOMENTO,  # type: ignore[arg-type]
    )

    _, parametros = _sql(sesion.sentencias[0])
    assert "PROVEEDOR" in _valores(parametros)
    assert "CLIENTE" not in _valores(parametros)


def test_bloquear_saldo_es_un_select_for_update_filtrado_por_organizacion() -> None:
    fila = object()
    sesion = _SesionEspia([fila])

    resultado = repository.bloquear_saldo(
        ORG,
        sesion,
        cuenta_tipo="CLIENTE",
        entidad_id=ENTIDAD,  # type: ignore[arg-type]
    )

    assert resultado is fila
    sql, parametros = _sql(sesion.sentencias[0])
    assert "FOR UPDATE" in sql
    assert "saldo_cuenta.organizacion_id = " in sql
    assert ORG in _valores(parametros)
    assert ENTIDAD in _valores(parametros)


def test_bloquear_saldo_sin_fila_devuelve_none() -> None:
    sesion = _SesionEspia([])

    assert (
        repository.bloquear_saldo(ORG, sesion, cuenta_tipo="CLIENTE", entidad_id=ENTIDAD)  # type: ignore[arg-type]
        is None
    )


def test_obtener_saldo_no_bloquea_y_filtra_por_organizacion() -> None:
    sesion = _SesionEspia([Decimal("130000.00")])

    saldo = repository.obtener_saldo(ORG, sesion, cuenta_tipo="CLIENTE", entidad_id=ENTIDAD)  # type: ignore[arg-type]

    assert saldo == Decimal("130000.00")
    sql, parametros = _sql(sesion.sentencias[0])
    assert "FOR UPDATE" not in sql
    assert "saldo_cuenta.organizacion_id = " in sql
    assert ORG in _valores(parametros)


# --- traducción de la FK de D6 y del desborde numérico ------------------------


@pytest.mark.parametrize(
    "restriccion",
    [
        "fk_saldo_cuenta__cliente",
        "fk_saldo_cuenta__proveedor",
    ],
)
def test_una_fk_de_entidad_al_crear_el_saldo_se_traduce_a_404(restriccion: str) -> None:
    """D6, D7, INV-21: el libro no importa `clientes`, así que la base es quien
    dice que la entidad no existe en la organización."""
    sesion = _SesionEspia(
        error_al_ejecutar=_error_integridad(
            f'insert or update violates foreign key constraint "{restriccion}"'
        )
    )

    with pytest.raises(RecursoNoEncontradoError) as error:
        repository.asegurar_saldo(
            ORG,
            sesion,
            cuenta_tipo="CLIENTE",
            entidad_id=ENTIDAD,
            momento=MOMENTO,  # type: ignore[arg-type]
        )

    assert error.value.status_http == 404


@pytest.mark.parametrize(
    "restriccion",
    ["fk_cuenta_movimiento__cliente", "fk_cuenta_movimiento__proveedor"],
)
def test_una_fk_de_entidad_al_insertar_el_movimiento_se_traduce_a_404(restriccion: str) -> None:
    sesion = _SesionEspia(
        error_al_agregar=_error_integridad(
            f'insert or update violates foreign key constraint "{restriccion}"'
        )
    )

    with pytest.raises(RecursoNoEncontradoError):
        repository.insertar_movimiento(
            ORG,
            sesion,  # type: ignore[arg-type]
            **_movimiento(),
        )


def test_otra_violacion_de_integridad_no_se_disfraza_de_404() -> None:
    """Una FK de `dispositivo` o de `usuario` es un dato del sobre mal armado,
    no una entidad inexistente: sale tal cual."""
    sesion = _SesionEspia(
        error_al_agregar=_error_integridad(
            'insert or update violates foreign key constraint "fk_cuenta_movimiento__dispositivo"'
        )
    )

    with pytest.raises(IntegrityError):
        repository.insertar_movimiento(ORG, sesion, **_movimiento())  # type: ignore[arg-type]


def test_un_desborde_numerico_del_saldo_es_un_error_de_dominio() -> None:
    """Riesgo del diseño: el saldo acumulado no entra en `numeric(14,2)`."""
    sesion = _SesionEspia(
        error_al_ejecutar=DataError("UPDATE", {}, Exception("numeric field overflow"))
    )

    with pytest.raises(SaldoFueraDeRangoError) as error:
        repository.actualizar_saldo(
            ORG,
            sesion,  # type: ignore[arg-type]
            cuenta_tipo="CLIENTE",
            entidad_id=ENTIDAD,
            efecto=Decimal("999999999999.99"),
            momento=MOMENTO,
        )

    assert error.value.codigo == "SALDO_FUERA_DE_RANGO"


def test_otro_error_de_datos_no_se_disfraza_de_desborde() -> None:
    sesion = _SesionEspia(error_al_ejecutar=DataError("UPDATE", {}, Exception("invalid input")))

    with pytest.raises(DataError):
        repository.actualizar_saldo(
            ORG,
            sesion,  # type: ignore[arg-type]
            cuenta_tipo="CLIENTE",
            entidad_id=ENTIDAD,
            efecto=Decimal("1.00"),
            momento=MOMENTO,
        )


# --- movimiento y saldo ------------------------------------------------------


def _movimiento(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "movimiento_id": uuid4(),
        "cuenta_tipo": "CLIENTE",
        "entidad_id": ENTIDAD,
        "tipo": "SALDO_INICIAL",
        "sentido": "AUMENTA",
        "importe": Decimal("150000.00"),
        "origen_tipo": "SALDO_INICIAL",
        "origen_id": uuid4(),
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
        "usuario_id": uuid4(),
        "dispositivo_id": uuid4(),
        "operation_id": uuid4(),
    }
    valores.update(cambios)
    return valores


def test_insertar_movimiento_guarda_todos_los_datos_dentro_de_un_savepoint() -> None:
    sesion = _SesionEspia()
    datos = _movimiento()

    movimiento = repository.insertar_movimiento(ORG, sesion, **datos)  # type: ignore[arg-type]

    assert sesion.agregadas == [movimiento]
    assert sesion.savepoints == 1
    assert movimiento.organizacion_id == ORG
    assert movimiento.id == datos["movimiento_id"]
    assert movimiento.dispositivo_id == datos["dispositivo_id"]
    assert movimiento.operation_id == datos["operation_id"]
    assert movimiento.importe == Decimal("150000.00")
    assert movimiento.sentido == "AUMENTA"


def test_actualizar_saldo_suma_en_sql_y_devuelve_el_saldo_nuevo() -> None:
    sesion = _SesionEspia([Decimal("130000.00")])

    nuevo = repository.actualizar_saldo(
        ORG,
        sesion,  # type: ignore[arg-type]
        cuenta_tipo="CLIENTE",
        entidad_id=ENTIDAD,
        efecto=Decimal("-20000.00"),
        momento=MOMENTO,
    )

    assert nuevo == Decimal("130000.00")
    sql, parametros = _sql(sesion.sentencias[0])
    assert "saldo_cuenta.saldo + " in sql
    assert "RETURNING saldo_cuenta.saldo" in sql
    assert "organizacion_id = " in sql
    assert ORG in _valores(parametros)
    assert Decimal("-20000.00") in _valores(parametros)


# --- existencia de movimientos ------------------------------------------------


def test_existe_movimiento_sin_filtro_de_tipo() -> None:
    sesion = _SesionEspia([1])

    assert repository.existe_movimiento(
        ORG,
        sesion,  # type: ignore[arg-type]
        cuenta_tipo="CLIENTE",
        entidad_id=ENTIDAD,
    )

    sql, parametros = _sql(sesion.sentencias[0])
    assert "cuenta_movimiento.organizacion_id = " in sql
    assert "cuenta_movimiento.tipo" not in sql
    assert ORG in _valores(parametros)


def test_existe_movimiento_devuelve_false_si_no_hay_filas() -> None:
    sesion = _SesionEspia([])

    assert not repository.existe_movimiento(
        ORG,
        sesion,  # type: ignore[arg-type]
        cuenta_tipo="CLIENTE",
        entidad_id=ENTIDAD,
    )


def test_existe_movimiento_de_otro_tipo_excluye_el_tipo_pedido() -> None:
    """D3: "movimientos de otro tipo" es `tipo <> 'SALDO_INICIAL'`."""
    sesion = _SesionEspia([1])

    repository.existe_movimiento(
        ORG,
        sesion,  # type: ignore[arg-type]
        cuenta_tipo="CLIENTE",
        entidad_id=ENTIDAD,
        excluyendo_tipo="SALDO_INICIAL",
    )

    sql, parametros = _sql(sesion.sentencias[0])
    assert "cuenta_movimiento.tipo != " in sql
    assert "SALDO_INICIAL" in _valores(parametros)


def test_existe_movimiento_de_un_tipo_filtra_por_ese_tipo() -> None:
    sesion = _SesionEspia([1])

    repository.existe_movimiento(
        ORG,
        sesion,  # type: ignore[arg-type]
        cuenta_tipo="PROVEEDOR",
        entidad_id=ENTIDAD,
        tipo="COMPRA",
    )

    sql, parametros = _sql(sesion.sentencias[0])
    assert "cuenta_movimiento.tipo = " in sql
    assert "COMPRA" in _valores(parametros)


# --- sumas en SQL -------------------------------------------------------------


def test_la_suma_del_libro_se_hace_en_sql() -> None:
    """CC-04, INV-13: `SUM(CASE ...)` en la base."""
    sesion = _SesionEspia([Decimal("130000.00")])

    suma = repository.suma_del_libro(ORG, sesion, cuenta_tipo="CLIENTE", entidad_id=ENTIDAD)  # type: ignore[arg-type]

    assert suma == Decimal("130000.00")
    sql, parametros = _sql(sesion.sentencias[0])
    assert "sum(CASE WHEN (cuenta_movimiento.sentido = " in sql
    assert "coalesce" in sql.lower()
    assert ORG in _valores(parametros)


def test_el_saldo_anterior_suma_en_sql_lo_anterior_al_instante() -> None:
    sesion = _SesionEspia([Decimal("20000.00")])
    antes_de = datetime(2026, 3, 1, 3, 0, tzinfo=UTC)

    anterior = repository.saldo_anterior(
        ORG,
        sesion,  # type: ignore[arg-type]
        cuenta_tipo="CLIENTE",
        entidad_id=ENTIDAD,
        antes_de=antes_de,
    )

    assert anterior == Decimal("20000.00")
    sql, parametros = _sql(sesion.sentencias[0])
    assert "sum(CASE" in sql
    assert "cuenta_movimiento.occurred_at < " in sql
    assert antes_de in _valores(parametros)
    assert ORG in _valores(parametros)


# --- estado de cuenta (D9, CC-07) ---------------------------------------------


def _estado(sesion: _SesionEspia, **cambios: Any) -> Any:
    argumentos: dict[str, Any] = {
        "cuenta_tipo": "CLIENTE",
        "entidad_id": ENTIDAD,
        "desde": None,
        "hasta": None,
        "cursor": None,
        "limite": None,
    }
    argumentos.update(cambios)
    return repository.estado_de_cuenta(ORG, sesion, **argumentos)  # type: ignore[arg-type]


def test_el_estado_de_cuenta_acumula_con_una_ventana_sobre_toda_la_cuenta() -> None:
    """D9: `SUM(...) OVER (ORDER BY occurred_at, id)` calculado sobre la cuenta
    completa y filtrado después, así el acumulado es siempre el real."""
    sesion = _SesionEspia([])

    _estado(sesion, desde=datetime(2026, 3, 1, 3, 0, tzinfo=UTC))

    sql, parametros = _sql(sesion.sentencias[0])
    assert "OVER (ORDER BY cuenta_movimiento.occurred_at, cuenta_movimiento.id)" in sql
    assert ORG in _valores(parametros)
    # La ventana se calcula en la subconsulta; el filtro de período va afuera.
    posicion_ventana = sql.index("OVER (")
    assert sql.index("occurred_at >= ", posicion_ventana) > posicion_ventana


def test_el_estado_de_cuenta_pide_una_fila_de_mas_para_saber_si_hay_otra_pagina() -> None:
    sesion = _SesionEspia([])

    _estado(sesion, limite=10)

    _, parametros = _sql(sesion.sentencias[0])
    assert 11 in _valores(parametros)


@pytest.mark.parametrize(
    ("pedido", "pedido_a_la_base"),
    [(None, 51), (1000, LIMITE_MAXIMO + 1), (0, 2)],
)
def test_el_limite_del_estado_de_cuenta_se_acota(pedido: int | None, pedido_a_la_base: int) -> None:
    sesion = _SesionEspia([])

    _estado(sesion, limite=pedido)

    _, parametros = _sql(sesion.sentencias[0])
    assert pedido_a_la_base in _valores(parametros)


def test_el_estado_de_cuenta_con_cursor_compara_el_par_momento_e_id() -> None:
    sesion = _SesionEspia([])
    momento = datetime(2026, 2, 1, tzinfo=UTC)
    id_ = uuid4()

    _estado(sesion, cursor=codificar_cursor(momento, id_))

    sql, parametros = _sql(sesion.sentencias[0])
    assert "(anon_1.occurred_at, anon_1.id) > (" in sql
    assert momento in _valores(parametros)
    assert id_ in _valores(parametros)


def test_el_estado_de_cuenta_filtra_desde_y_hasta() -> None:
    sesion = _SesionEspia([])
    desde = datetime(2026, 3, 1, 3, 0, tzinfo=UTC)
    hasta = datetime(2026, 4, 1, 3, 0, tzinfo=UTC)

    _estado(sesion, desde=desde, hasta=hasta)

    sql, parametros = _sql(sesion.sentencias[0])
    assert "anon_1.occurred_at >= " in sql
    assert "anon_1.occurred_at < " in sql
    assert desde in _valores(parametros)
    assert hasta in _valores(parametros)


def test_el_estado_de_cuenta_ordena_por_momento_e_id() -> None:
    sesion = _SesionEspia([])

    _estado(sesion)

    sql, _ = _sql(sesion.sentencias[0])
    assert sql.rstrip().split("ORDER BY")[-1].split("LIMIT")[0].strip() == (
        "anon_1.occurred_at, anon_1.id"
    )


def test_una_pagina_incompleta_no_trae_cursor_siguiente() -> None:
    fila = _fila_del_estado(saldo_acumulado=Decimal("150000.00"))
    sesion = _SesionEspia([fila])

    lineas, siguiente = _estado(sesion, limite=5)

    assert [linea.saldo_acumulado for linea in lineas] == [Decimal("150000.00")]
    assert siguiente is None


def test_una_pagina_llena_devuelve_el_cursor_del_ultimo_movimiento() -> None:
    primera = _fila_del_estado(saldo_acumulado=Decimal("1.00"))
    segunda = _fila_del_estado(saldo_acumulado=Decimal("2.00"))
    sobrante = _fila_del_estado(saldo_acumulado=Decimal("3.00"))
    sesion = _SesionEspia([primera, segunda, sobrante])

    lineas, siguiente = _estado(sesion, limite=2)

    assert [linea.saldo_acumulado for linea in lineas] == [Decimal("1.00"), Decimal("2.00")]
    assert siguiente == codificar_cursor(segunda.occurred_at, segunda.id)


def _fila_del_estado(*, saldo_acumulado: Decimal) -> Any:
    class _Fila:
        pass

    fila = _Fila()
    fila.id = uuid4()  # type: ignore[attr-defined]
    fila.tipo = "SALDO_INICIAL"  # type: ignore[attr-defined]
    fila.sentido = "AUMENTA"  # type: ignore[attr-defined]
    fila.importe = Decimal("1.00")  # type: ignore[attr-defined]
    fila.origen_tipo = "SALDO_INICIAL"  # type: ignore[attr-defined]
    fila.origen_id = uuid4()  # type: ignore[attr-defined]
    fila.occurred_at = MOMENTO  # type: ignore[attr-defined]
    fila.registered_at = MOMENTO  # type: ignore[attr-defined]
    fila.usuario_id = uuid4()  # type: ignore[attr-defined]
    fila.operation_id = uuid4()  # type: ignore[attr-defined]
    fila.saldo_acumulado = saldo_acumulado  # type: ignore[attr-defined]
    return fila


# --- consistencia saldo vs libro (INV-13, 02 §7.6) ------------------------------


def test_la_verificacion_compara_en_sql_cada_saldo_con_la_suma_de_su_libro() -> None:
    sesion = _SesionEspia([])

    diferencias = repository.verificar_consistencia(ORG, sesion)  # type: ignore[arg-type]

    assert diferencias == []
    sql, parametros = _sql(sesion.sentencias[0])
    assert "FULL OUTER JOIN" in sql
    assert "sum(CASE" in sql
    assert "saldo_cuenta.organizacion_id = " in sql
    assert "cuenta_movimiento.organizacion_id = " in sql
    assert _valores(parametros).count(ORG) >= 2
    # No corrige nada: la verificación solo lee.
    assert sql.lstrip().upper().startswith("SELECT")


def test_la_verificacion_devuelve_la_cuenta_con_las_dos_sumas() -> None:
    entidad = uuid4()

    class _Fila:
        cuenta_tipo = "CLIENTE"
        entidad_id: UUID = entidad
        saldo_materializado = Decimal("999.00")
        suma_del_libro = Decimal("130000.00")

    sesion = _SesionEspia([_Fila()])

    (diferencia,) = repository.verificar_consistencia(ORG, sesion)  # type: ignore[arg-type]

    assert diferencia.cuenta_tipo == "CLIENTE"
    assert diferencia.entidad_id == entidad
    assert diferencia.saldo_materializado == Decimal("999.00")
    assert diferencia.suma_del_libro == Decimal("130000.00")
