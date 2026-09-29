"""Change 07, tarea 2.1: `clientes/repository.py` recibe `organizacion_id`
como primer parámetro en TODA función pública, y TODA consulta que arma filtra
por `organizacion_id` (INV-02, `docs/02-arquitectura.md` §8, `CLAUDE.md` §4).

Estas pruebas no necesitan PostgreSQL: inspeccionan la consulta que el
repositorio construye (escrita en el dialecto de PostgreSQL) en vez de
ejecutarla. Es el mismo criterio que `test_repositorios_organizacion_
obligatoria.py` para las firmas, extendido a lo que el repositorio realmente
filtra y a los filtros de listado (texto, estado) y a la paginación por cursor
con orden estable (D1: el `nombre` NO es único, así que el cursor son dos
columnas).

El comportamiento contra la base real (índice parcial que separa dos altas
concurrentes, `INACTIVO` appearing en el listado) se prueba en
`tests/integration/test_clientes_comandos.py` y
`tests/integration/test_clientes_migracion.py`, que necesitan PostgreSQL real.
"""

from __future__ import annotations

import contextlib
import inspect
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Select, operators
from sqlalchemy.sql.elements import BooleanClauseList, Grouping

from app.modules.clientes import repository as clientes_repository
from app.modules.clientes.models import Cliente


class _SesionEspia:
    """Sesión que NO toca la base: registra lo que se le agrega y la consulta
    que se le pasa a `scalars`, y devuelve filas preparadas.

    Lo que se verifica acá es la CONSULTA, no el resultado de ejecutarla: si la
    fila que devuelve el espía ya viene filtrada, entonces el filtro que
    importa es el que quedó escrito en el `WHERE`."""

    def __init__(self, filas: list[Cliente] | None = None) -> None:
        self.filas = filas or []
        self.agregadas: list[object] = []
        self.consultas: list[Select[Any]] = []
        self.flushes = 0

    def add(self, fila: object) -> None:
        self.agregadas.append(fila)

    def flush(self) -> None:
        self.flushes += 1

    def begin_nested(self) -> contextlib.AbstractContextManager[None]:
        return contextlib.nullcontext()

    def scalars(self, consulta: Select[Any]) -> _ResultadoEspia:
        self.consultas.append(consulta)
        return _ResultadoEspia(self.filas)

    def get(self, modelo: type[object], clave: object) -> Cliente | None:
        self.consultas.append(select(Cliente))
        return next((fila for fila in self.filas if fila.id == clave), None)


class _ResultadoEspia:
    def __init__(self, filas: list[Cliente]) -> None:
        self._filas = filas

    def all(self) -> list[Cliente]:
        return list(self._filas)

    def one_or_none(self) -> Cliente | None:
        return self._filas[0] if self._filas else None


_DIALECTO = postgresql.dialect()


def _sql(consulta: Select[Any]) -> str:
    return str(consulta.compile(dialect=_DIALECTO))


def _where(consulta: Select[Any]) -> str:
    """Solo el `WHERE`, sin las columnas del `SELECT`. Hace falta porque
    `cliente.estado` aparece igual entre las columnas proyectadas y entre un
    filtro por estado, y `cliente.organizacion_id` en las dos."""
    whereclause = consulta.whereclause
    if whereclause is None:
        return ""
    return str(whereclause.compile(dialect=_DIALECTO))


def _parametros(consulta: Select[Any]) -> dict[str, Any]:
    return dict(consulta.compile(dialect=_DIALECTO).params)


def _cliente(**cambios: Any) -> Cliente:
    base: dict[str, Any] = {
        "id": uuid4(),
        "organizacion_id": uuid4(),
        "nombre": "Kiosco La Esquina",
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
        "estado": "ACTIVO",
        "es_consumidor_final": False,
    }
    base.update(cambios)
    return Cliente(**base)


def _crear_por_repositorio(organizacion_id: UUID, sesion: _SesionEspia, **cambios: Any) -> Cliente:
    campos: dict[str, Any] = {
        "nombre": "Kiosco La Esquina",
        "codigo": None,
        "razon_social": None,
        "documento_tipo": None,
        "documento_numero": None,
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
        "telefono": None,
        "email": None,
        "lista_precio_id": None,
        "estado_facturacion_default": None,
        "es_consumidor_final": False,
        "limite_credito": None,
        "politica_credito": None,
        "tolerancia_offline_tipo": None,
        "tolerancia_offline_valor": None,
        "estado": "ACTIVO",
    }
    campos.update(cambios)
    return clientes_repository.crear_cliente(
        organizacion_id,
        sesion,  # type: ignore[arg-type]
        cliente_id=uuid4(),
        momento=None,  # type: ignore[arg-type]
        actualizado_por_id=None,
        **campos,
    )


# --- INV-02: toda consulta filtra por organización (tarea 2.1) ---------------
# Las firmas ya las verifica `test_repositorios_organizacion_obligatoria.py`
# (tarea 2.1); acá va lo que el repositorio hace con la organización.


def test_obtener_cliente_por_id_devuelve_el_cliente_de_la_misma_organizacion() -> None:
    organizacion_id = uuid4()
    objetivo = _cliente(organizacion_id=organizacion_id)
    sesion = _SesionEspia([objetivo])

    resultado = clientes_repository.obtener_cliente_por_id(
        organizacion_id,
        objetivo.id,
        sesion,  # type: ignore[arg-type]
    )

    assert resultado is objetivo


def test_obtener_cliente_por_id_compara_la_organizacion_del_raton() -> None:
    """Esta lectura va por clave primaria (`sesion.get`, mismo criterio que
    `obtener_proveedor_por_id` del change 06), así que la organización se
    comprueba sobre la fila leída y NO aparece como parámetro de la consulta.
    La comparación sigue siendo obligatoria: sin ella, un `id` válido de otra
    organización se devolvería."""
    organizacion_id = uuid4()
    sesion = _SesionEspia([_cliente(organizacion_id=uuid4())])

    resultado = clientes_repository.obtener_cliente_por_id(
        organizacion_id,
        uuid4(),
        sesion,  # type: ignore[arg-type]
    )

    assert resultado is None


def test_obtener_cliente_por_id_de_otra_organizacion_devuelve_none() -> None:
    """Un cliente de B consultado desde A no se devuelve: el filtro por
    organización va en el `WHERE`, no en un `if` de Python (INV-21, SEG-07: 404,
    no 403)."""
    cliente_de_b = _cliente(organizacion_id=uuid4())
    sesion = _SesionEspia([])

    resultado = clientes_repository.obtener_cliente_por_id(
        uuid4(),
        cliente_de_b.id,
        sesion,  # type: ignore[arg-type]
    )

    assert resultado is None


def test_obtener_cliente_por_id_para_actualizar_toma_fila_para_actualizar() -> None:
    """`FOR UPDATE` (mismo criterio que `PROVEEDOR_MODIFICAR`, D14 del 06):
    la modificación serializa contra cualquier lectura `FOR SHARE`
    concurrente."""
    organizacion_id = uuid4()
    sesion = _SesionEspia([_cliente(organizacion_id=organizacion_id)])

    clientes_repository.obtener_cliente_por_id_para_actualizar(
        organizacion_id,
        uuid4(),
        sesion,  # type: ignore[arg-type]
    )

    sql = _sql(sesion.consultas[0])
    assert "FOR UPDATE" in sql
    assert "cliente.organizacion_id" in sql


def test_obtener_consumidor_final_filtra_por_organizacion_y_por_la_marca() -> None:
    organizacion_id = uuid4()
    sesion = _SesionEspia([_cliente(organizacion_id=organizacion_id, es_consumidor_final=True)])

    clientes_repository.obtener_consumidor_final(organizacion_id, sesion)  # type: ignore[arg-type]

    sql = _sql(sesion.consultas[0])
    assert "cliente.organizacion_id" in sql
    assert "cliente.es_consumidor_final" in sql
    assert organizacion_id in _parametros(sesion.consultas[0]).values()


def test_actualizar_cliente_de_otra_organizacion_no_escribe_nada() -> None:
    """La modificación tampoco escribe sobre un cliente ajeno: devuelve `None`
    sin haber tocado la fila (INV-21)."""
    cliente_de_b = _cliente(organizacion_id=uuid4(), nombre="Kiosco La Esquina")
    sesion = _SesionEspia([cliente_de_b])

    resultado = clientes_repository.actualizar_cliente(
        uuid4(),
        sesion,  # type: ignore[arg-type]
        cliente_id=cliente_de_b.id,
        nombre="Nombre Nuevo",
        codigo=None,
        razon_social=None,
        documento_tipo=None,
        documento_numero=None,
        direccion=cliente_de_b.direccion,
        contacto=cliente_de_b.contacto,
        telefono=None,
        email=None,
        estado_facturacion_default=None,
        estado="SUSPENDIDO",
        momento=None,  # type: ignore[arg-type]
        actualizado_por_id=None,
    )

    assert resultado is None
    assert cliente_de_b.nombre == "Kiosco La Esquina"
    assert cliente_de_b.estado == "ACTIVO"


def test_actualizar_cliente_de_la_misma_organizacion_escribe_ficha_y_estado() -> None:
    organizacion_id = uuid4()
    cliente = _cliente(organizacion_id=organizacion_id)
    sesion = _SesionEspia([cliente])

    resultado = clientes_repository.actualizar_cliente(
        organizacion_id,
        sesion,  # type: ignore[arg-type]
        cliente_id=cliente.id,
        nombre="Kiosco La Esquina",
        codigo=None,
        razon_social=None,
        documento_tipo=None,
        documento_numero=None,
        direccion=cliente.direccion,
        contacto=cliente.contacto,
        telefono=None,
        email=None,
        estado_facturacion_default=None,
        estado="SUSPENDIDO",
        momento=None,  # type: ignore[arg-type]
        actualizado_por_id=None,
    )

    assert resultado is cliente
    assert cliente.estado == "SUSPENDIDO"


def test_actualizar_credito_de_otra_organizacion_no_escribe_nada() -> None:
    cliente_de_b = _cliente(organizacion_id=uuid4(), politica_credito="RECHAZAR")
    sesion = _SesionEspia([cliente_de_b])

    resultado = clientes_repository.actualizar_credito_cliente(
        uuid4(),
        sesion,  # type: ignore[arg-type]
        cliente_id=cliente_de_b.id,
        limite_credito=Decimal("150000.00"),
        politica_credito="AUTORIZAR",
        tolerancia_offline_tipo=None,
        tolerancia_offline_valor=None,
        momento=None,  # type: ignore[arg-type]
        actualizado_por_id=None,
    )

    assert resultado is None
    assert cliente_de_b.politica_credito == "RECHAZAR"
    assert cliente_de_b.limite_credito is None


def test_actualizar_credito_cliente_solo_toca_los_tres_campos_de_credito() -> None:
    """D3: el crédito es un comando aparte; su escritura no puede pisar la
    ficha ni el estado."""
    organizacion_id = uuid4()
    cliente = _cliente(organizacion_id=organizacion_id, nombre="Kiosco La Esquina")
    sesion = _SesionEspia([cliente])

    resultado = clientes_repository.actualizar_credito_cliente(
        organizacion_id,
        sesion,  # type: ignore[arg-type]
        cliente_id=cliente.id,
        limite_credito=Decimal("150000.00"),
        politica_credito="AUTORIZAR",
        tolerancia_offline_tipo="IMPORTE",
        tolerancia_offline_valor=Decimal("25.00"),
        momento=None,  # type: ignore[arg-type]
        actualizado_por_id=None,
    )

    assert resultado is cliente
    assert cliente.limite_credito == Decimal("150000.00")
    assert cliente.politica_credito == "AUTORIZAR"
    assert cliente.tolerancia_offline_tipo == "IMPORTE"
    assert cliente.tolerancia_offline_valor == Decimal("25.00")
    # La ficha y el estado quedan como estaban.
    assert cliente.nombre == "Kiosco La Esquina"
    assert cliente.estado == "ACTIVO"


# --- listado: texto, estado y paginación por cursor (tarea 2.1) ------------


def test_listar_sin_filtros_solo_filtra_por_organizacion() -> None:
    organizacion_id = uuid4()
    sesion = _SesionEspia([])

    clientes, cursor = clientes_repository.listar_clientes_paginado(
        organizacion_id,
        sesion,  # type: ignore[arg-type]
    )

    assert clientes == []
    assert cursor is None
    where = _where(sesion.consultas[0])
    assert "cliente.organizacion_id" in where
    assert "cliente.estado" not in where


def test_listar_por_texto_busca_en_los_cuatro_campos() -> None:
    organizacion_id = uuid4()
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        organizacion_id,
        sesion,
        texto="Esquina",  # type: ignore[arg-type]
    )

    sql = _sql(sesion.consultas[0])
    for columna in (
        "cliente.nombre",
        "cliente.razon_social",
        "cliente.codigo",
        "cliente.documento_numero",
    ):
        assert columna in sql, f"El filtro por texto no cubre {columna}."


def test_listar_por_texto_con_digitos_normaliza_el_documento_a_digitos() -> None:
    """Mismo criterio que `listar_proveedores_paginado` (contrato-api.md P5):
    un texto con dígitos también compara contra el documento ya guardado solo
    con dígitos, así que `30-111 222` encuentra `30111222`."""
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        texto="30-111 222",  # type: ignore[arg-type]
    )

    assert "%30111222%" in _parametros(sesion.consultas[0]).values()


def _grupos_or_de_texto(consulta: Select[Any]) -> list[BooleanClauseList]:
    """Grupos OR de la consulta, desenvueltos del `Grouping` que SQLAlchemy
    pone alrededor de un `or_` para que no se mezcle con el AND de al lado."""
    whereclause = consulta.whereclause
    assert isinstance(whereclause, BooleanClauseList), (
        f"El WHERE debería ser una conjunción de condiciones; es {whereclause!r}."
    )
    grupos: list[BooleanClauseList] = []
    for clausula in whereclause.clauses:
        if isinstance(clausula, Grouping):
            clausula = clausula.element
        if isinstance(clausula, BooleanClauseList) and clausula.operator is operators.or_:
            grupos.append(clausula)
    return grupos


def test_el_documento_normalizado_entra_en_el_mismo_or_del_texto() -> None:
    """El parámetro anterior alcanzaba para ambos caminos, y por eso la
    prueba pasaba con el filtro roto.

    La condición de dígitos normalizados tiene que entrar EN EL GRUPO OR de los
    cuatro campos, no en un `where` aparte. Encadenar dos `where` las une con
    AND, y con AND la búsqueda no encuentra nunca nada: para `30-111 222` el
    primer grupo exige que alguna columna contenga literalmente `30-111 222`, y
    como el documento se guarda normalizado a `30111222` no hay coincidencia
    que el segundo `where` pueda rescatar. El resultado es un listado vacío en
    vez de un error visible.

    Se comprueba sobre el ÁRBOL del `whereclause`, no sobre el SQL compilado:
    el SQL de un `or_` anidado cambia según el dialecto y según la versión, y lo
    que importa es la estructura de la condición."""
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        texto="30-111 222",  # type: ignore[arg-type]
    )

    whereclause = sesion.consultas[0].whereclause
    assert isinstance(whereclause, BooleanClauseList)
    assert whereclause.operator is operators.and_, (
        "El filtro por organización y el de texto deben quedar unidos por AND."
    )

    grupos_or = _grupos_or_de_texto(sesion.consultas[0])
    assert len(grupos_or) == 1, (
        "La búsqueda por texto tiene que ser UN solo grupo OR. Varios grupos "
        "OR unidos por AND significan que el texto tiene que cumplir dos "
        "condiciones a la vez."
    )
    assert len(grupos_or[0].clauses) == 5, (
        "El grupo OR debe traer los cuatro campos más la condición de dígitos "
        f"normalizados; trae {len(grupos_or[0].clauses)}."
    )


def test_un_texto_sin_digitos_no_agrega_la_condicion_de_documento() -> None:
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        texto="Esquina",  # type: ignore[arg-type]
    )

    grupos_or = _grupos_or_de_texto(sesion.consultas[0])
    assert len(grupos_or) == 1
    assert len(grupos_or[0].clauses) == 4


def test_listar_por_estado_filtra_por_esa_columna() -> None:
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        estado="SUSPENDIDO",  # type: ignore[arg-type]
    )

    where = _where(sesion.consultas[0])
    assert "cliente.organizacion_id" in where
    assert "cliente.estado" in where


def test_listar_ordena_por_nombre_y_por_id_para_que_el_orden_sea_estable() -> None:
    """D1: el `nombre` NO es único, así que un cursor de una sola columna puede
    saltar o repetir filas cuando dos clientes comparten nombre. El cursor
    empareja `(nombre, id)`."""
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(uuid4(), sesion)  # type: ignore[arg-type]

    sql = _sql(sesion.consultas[0])
    assert "ORDER BY cliente.nombre, cliente.id" in sql


def test_listar_con_cursor_compara_el_par_nombre_id() -> None:
    sesion = _SesionEspia([])
    cursor = clientes_repository._codificar_cursor("Kiosco La Esquina", uuid4())  # noqa: SLF001

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        cursor=cursor,  # type: ignore[arg-type]
    )

    assert "(cliente.nombre, cliente.id) >" in _sql(sesion.consultas[0])


def test_listar_pide_una_fila_mas_para_saber_si_hay_siguiente_pagina() -> None:
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        limite=25,  # type: ignore[arg-type]
    )

    assert 26 in _parametros(sesion.consultas[0]).values()


def test_listar_devuelve_cursor_solo_cuando_hay_una_fila_de_mas() -> None:
    organizacion_id = uuid4()
    filas = [_cliente(organizacion_id=organizacion_id) for _ in range(3)]

    pagina, cursor = clientes_repository.listar_clientes_paginado(
        organizacion_id,
        _SesionEspia(filas),
        limite=2,  # type: ignore[arg-type]
    )
    assert len(pagina) == 2
    assert cursor is not None

    pagina, cursor = clientes_repository.listar_clientes_paginado(
        organizacion_id,
        _SesionEspia(filas[:2]),
        limite=2,  # type: ignore[arg-type]
    )
    assert len(pagina) == 2
    assert cursor is None


def test_el_cursor_va_y_vuelve_sin_perder_acentos_ni_nulos() -> None:
    identificador = uuid4()
    cursor = clientes_repository._codificar_cursor("Kiosco Ñandú Á", identificador)  # noqa: SLF001

    nombre, id_ = clientes_repository._decodificar_cursor(cursor)  # noqa: SLF001

    assert nombre == "Kiosco Ñandú Á"
    assert id_ == identificador


def test_el_limite_de_pagina_se_acota_al_maximo() -> None:
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        limite=clientes_repository.LIMITE_PAGINA_MAXIMO + 500,  # type: ignore[arg-type]
    )

    assert clientes_repository.LIMITE_PAGINA_MAXIMO + 1 in _parametros(sesion.consultas[0]).values()


def test_un_limite_menor_uno_no_deja_la_paginacion_sin_filas() -> None:
    sesion = _SesionEspia([])

    clientes_repository.listar_clientes_paginado(
        uuid4(),
        sesion,
        limite=0,  # type: ignore[arg-type]
    )

    assert 2 in _parametros(sesion.consultas[0]).values()


# --- traducción de `IntegrityError` (D1: la base separa las altas concurrentes)


def test_un_documento_repetido_se_traduce_a_error_de_dominio() -> None:
    from sqlalchemy.exc import IntegrityError

    from app.modules.clientes.domain.errores import DocumentoDuplicadoError

    def _fallar() -> None:
        raise IntegrityError(
            "INSERT", {}, Exception('duplicate key value: "ux_cliente__documento"')
        )

    with pytest.raises(DocumentoDuplicadoError):
        clientes_repository.guardar_con_traduccion_de_integridad(
            uuid4(),
            _SesionEspia(),
            _fallar,  # type: ignore[arg-type]
        )


def test_un_codigo_repetido_se_traduce_a_error_de_dominio() -> None:
    from sqlalchemy.exc import IntegrityError

    from app.modules.clientes.domain.errores import CodigoDuplicadoError

    def _fallar() -> None:
        raise IntegrityError("INSERT", {}, Exception('duplicate key value: "ux_cliente__codigo"'))

    with pytest.raises(CodigoDuplicadoError):
        clientes_repository.guardar_con_traduccion_de_integridad(
            uuid4(),
            _SesionEspia(),
            _fallar,  # type: ignore[arg-type]
        )


def test_una_integrity_error_no_reconocida_sube_sin_traducirse() -> None:
    """Un `IntegrityError` que no sea de estos dos índices NO se traduce: se
    deja subir para no tapar un fallo de infraestructura con un error de
    dominio que mentiría sobre la causa."""
    from sqlalchemy.exc import IntegrityError

    def _fallar() -> None:
        raise IntegrityError("INSERT", {}, Exception("fk_cliente__organizacion"))

    with pytest.raises(IntegrityError):
        clientes_repository.guardar_con_traduccion_de_integridad(
            uuid4(),
            _SesionEspia(),
            _fallar,  # type: ignore[arg-type]
        )


# --- alta: la fila nace con la organización del parámetro -------------------


def test_crear_cliente_agrega_la_fila_con_la_organizacion_del_primer_parametro() -> None:
    organizacion_id = uuid4()
    sesion = _SesionEspia()

    cliente = _crear_por_repositorio(
        organizacion_id, sesion, documento_tipo="DNI", documento_numero="30111222"
    )

    assert len(sesion.agregadas) == 1
    assert sesion.agregadas[0] is cliente
    assert cliente.organizacion_id == organizacion_id
    assert cliente.estado == "ACTIVO"
    assert cliente.es_consumidor_final is False


def test_crear_cliente_puede_nacer_marcado_como_consumidor_final() -> None:
    """D4: la marca la pone `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`, no
    `CLIENTE_CREAR`, pero el repositorio no distingue: solo guarda lo que le
    pasó el servicio."""
    sesion = _SesionEspia()

    cliente = _crear_por_repositorio(
        uuid4(), sesion, es_consumidor_final=True, limite_credito=Decimal("0.00")
    )

    assert cliente.es_consumidor_final is True
    assert cliente.limite_credito == Decimal("0.00")


# --- helpers de cursor: no dependen de la base -----------------------------


def test_el_repositorio_no_expone_una_sesion_por_defecto() -> None:
    """Ninguna función pública acepta `sesion` antes que `organizacion_id` ni
    con valor por defecto: el ratchet de firmas de arriba ya lo cubre, esta
    prueba es la versión legible del mismo contrato para `crear_cliente`."""
    parametros = inspect.signature(clientes_repository.crear_cliente).parameters
    assert list(parametros)[:2] == ["organizacion_id", "sesion"]
    assert parametros["sesion"].default is inspect.Parameter.empty
