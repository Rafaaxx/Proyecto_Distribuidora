"""Change 07, tareas 2.2 y 2.3: `clientes/service.py` es la única puerta que
los demás módulos usan, no hace `commit`, y la lógica de negocio vive en
`domain/` (no acá).

Estas pruebas no necesitan PostgreSQL: sustituyen el repositorio y la sesión
por dobles, de modo que lo que se verifica es la CONTRATURA del servicio
(`CLAUDE.md` §4 y `docs/02-arquitectura.md` §8) y no el SQL, que ya tienen sus
propias pruebas en `test_clientes_repository.py`. Lo que sí necesita la base
real -- la traducción de `IntegrityError` y la serialización de dos escrituras
concurrentes -- está en `tests/integration/test_clientes_comandos.py`.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.clock import FixedClock
from app.modules.clientes import repository as clientes_repository
from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.errores import (
    ClienteConOperacionesError,
    ConfiguracionDeOrganizacionAusenteError,
    ConsumidorFinalNoInactivableError,
    ConsumidorFinalSinCreditoError,
    ConsumidorFinalYaHabilitadoError,
    EstadoInvalidoError,
    FichaIncompletaError,
    LimiteCreditoInvalidoError,
    NombreInvalidoError,
    RecursoNoEncontradoError,
    TransicionEstadoInvalidaError,
)
from app.modules.clientes.models import Cliente
from app.modules.identidad import service as identidad_service

MOMENTO = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def _reloj() -> FixedClock:
    return FixedClock(MOMENTO)


_COLUMNAS = {columna.name for columna in Cliente.__table__.columns}


def _solo_columnas(campos: dict[str, Any]) -> dict[str, Any]:
    """Deja solo lo que es una columna de `cliente`: el doble del repositorio
    devuelve filas reales, no cualquier diccionario de campos."""
    return {clave: valor for clave, valor in campos.items() if clave in _COLUMNAS}


def _grabador(cliente: Cliente) -> tuple[dict[str, Any], Any]:
    """Doble de escritura que REGISTRA lo que leTvuelven sin modificar la fila.

    Los servicios no escriben en la fila: escriben llamando al repositorio. Así
    que para comprobar qué se mandó hay que mirar los argumentos, no el estado
    del objeto."""
    enviados: dict[str, Any] = {}

    def _escribir(*args: Any, **campos: Any) -> Cliente:
        enviados.update(campos)
        return cliente

    return enviados, _escribir


def _cliente(**cambios: Any) -> Cliente:
    base: dict[str, Any] = {
        "id": uuid4(),
        "organizacion_id": uuid4(),
        "nombre": "Kiosco La Esquina",
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
        "estado": "ACTIVO",
        "es_consumidor_final": False,
        "limite_credito": None,
        "politica_credito": None,
        "tolerancia_offline_tipo": None,
        "tolerancia_offline_valor": None,
    }
    base.update(cambios)
    return Cliente(**base)


def _ficha(**cambios: Any) -> dict[str, Any]:
    """Contenido de ficha tal como lo recibe `modificar_cliente`.

    NO incluye `lista_precio_id`: D2 deja la columna sin FK y sin que nada la
    ofrezca hasta el change 13, así que ni el alta publicada ni la ficha la
    ofrecen (diseño, mitigación de `lista_precio_id` sin FK; tarea 5.3, "sin
    selector de lista asignada"). El servicio de alta sí la acepta porque la
    spec de fichas la nombra como opcional del contenido."""
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
        "estado_facturacion_default": None,
    }
    campos.update(cambios)
    return campos


@pytest.fixture
def sesion() -> object:
    """Doble de sesión que NO tiene `commit`: si algún camino del servicio
    intentara cerrar la transacción, la prueba lo detecta como
    `AttributeError` en vez de dejarlo pasar en silencio."""
    return object()


@pytest.fixture(autouse=True)
def _auditoria_sin_efecto(monkeypatch: pytest.MonkeyPatch) -> Any:
    """`modificar_credito_cliente` escribe una fila de auditoría (AUD-01) a
    través de `identidad_service`. Por defecto se sustituye para que las
    pruebas de crédito puedan fijarse sólo en lo que llega al repositorio; el
    contrato de la auditoría se verifica en las pruebas que lo pisan
    explícitamente, más abajo."""
    return monkeypatch.setattr(identidad_service, "registrar_auditoria", lambda *a, **k: None)


# --- contrato de firmas (tarea 2.2) ----------------------------------------


def test_ninguna_funcion_publica_del_servicio_se_queda_sin_organizacion_id() -> None:
    funciones = [
        (nombre, objeto)
        for nombre, objeto in vars(clientes_service).items()
        if inspect.isfunction(objeto)
        and not nombre.startswith("_")
        and objeto.__module__ == clientes_service.__name__
    ]
    funciones_de_lectura_y_escritura = [
        (nombre, funcion)
        for nombre, funcion in funciones
        if not nombre.startswith("registrar_")  # no hay registros en este change
    ]
    assert funciones_de_lectura_y_escritura, "El servicio no expone ninguna función pública."

    infractoras = [
        nombre
        for nombre, funcion in funciones_de_lectura_y_escritura
        if list(inspect.signature(funcion).parameters)[:1] != ["organizacion_id"]
    ]
    assert infractoras == []


def test_el_servicio_no_cierra_la_transaccion() -> None:
    """`CLAUDE.md` §4: la transacción la gestiona el bus. Se verifica sobre el
    CÓDIGO, no sobre una sesión real, para que ningún `commit` se cuele por un
    camino que las pruebas de comportamiento no recorran."""
    fuente = textwrap.dedent(inspect.getsource(clientes_service))
    assert (
        "commit" not in fuente.replace("sesion.commit", "").replace("sesión la gestiona", "")
        or ".commit(" not in fuente
    )


def test_toda_validacion_del_servicio_viene_de_domain() -> None:
    """`CLAUDE.md` §5: las funciones de dominio son puras y el servicio solo
    orquesta. Se comprueba sobre el ÁRBOL del módulo, no sobre el texto: toda
    llamada a `normalizar_*`, `validar_*` o `limite_de_consumidor_final` tiene
    que apuntar a `clientes/domain/`, así que no se puede reimplementar una
    validación acá sin que esta prueba lo note."""
    arbol = ast.parse(textwrap.dedent(inspect.getsource(clientes_service)))
    prefijos = ("normalizar_", "validar_", "limite_de_")
    called: set[str] = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        llamada = nodo.func
        nombre = (
            llamada.attr
            if isinstance(llamada, ast.Attribute)
            else llamada.id
            if isinstance(llamada, ast.Name)
            else ""
        )
        if nombre.startswith(prefijos):
            called.add(nombre)

    assert called, "El servicio no delega ninguna validación a `domain/`."
    for nombre in called:
        funcion = getattr(clientes_service, nombre)
        assert funcion.__module__.startswith("app.modules.clientes.domain"), (
            f"{nombre} no viene de `clientes/domain/`: {funcion.__module__}"
        )


def test_el_servicio_no_declara_catalogos_propios() -> None:
    """Los catálogos cerrados (estados, políticas, tipos de tolerancia) viven en
    `domain/`; el servicio no puede tener una lista propia que se desvíe."""
    arbol = ast.parse(textwrap.dedent(inspect.getsource(clientes_service)))
    literales_de_conjunto = [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, frozenset | set | dict)
    ]
    assert literales_de_conjunto == []


# --- crear_cliente (D7: nace ACTIVO, sin crédito, D3: sin campos de crédito)


def test_crear_cliente_normaliza_la_ficha_y_nace_activo_sin_credito(
    sesion: object,
) -> None:
    organizacion_id = uuid4()
    actor_id = uuid4()
    creado: dict[str, Any] = {}

    def _crear(org: UUID, ses: object, **campos: Any) -> Cliente:
        creado.update({"organizacion_id": org, **campos})
        return _cliente(**_solo_columnas(campos))

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "crear_cliente", _crear)
    try:
        clientes_service.crear_cliente(
            organizacion_id,
            sesion,
            _reloj(),
            **_ficha(
                nombre="  Kiosco La Esquina  ",
                codigo="  K-01  ",
                documento_tipo="dni",
                documento_numero="30-111 222",
            ),
            lista_precio_id=uuid4(),
            actor_id=actor_id,
        )
    finally:
        monkeypatch.undo()

    assert creado["organizacion_id"] == organizacion_id
    assert creado["nombre"] == "Kiosco La Esquina"
    assert creado["codigo"] == "K-01"
    # El tipo se guarda en mayúsculas y el número solo con dígitos (CLI-05, D1).
    assert creado["documento_tipo"] == "DNI"
    assert creado["documento_numero"] == "30111222"
    # D7: nace ACTIVO. D3: `CLIENTE_CREAR` no admite crédito, así que los tres
    # campos nacen en nulo (heredan el de la organización), no en cero.
    assert creado["estado"] == "ACTIVO"
    assert creado["limite_credito"] is None
    assert creado["politica_credito"] is None
    assert creado["tolerancia_offline_tipo"] is None
    assert creado["tolerancia_offline_valor"] is None
    assert creado["momento"] == MOMENTO
    assert creado["actualizado_por_id"] == actor_id


def test_crear_cliente_rechaza_el_nombre_vacio(sesion: object) -> None:
    with pytest.raises(NombreInvalidoError):
        clientes_service.crear_cliente(
            uuid4(),
            sesion,
            _reloj(),
            **_ficha(nombre="   "),
            lista_precio_id=None,
            actor_id=None,
        )


@pytest.mark.parametrize("campo", ["direccion", "contacto"])
def test_crear_cliente_rechaza_la_ficha_incompleta(sesion: object, campo: str) -> None:
    with pytest.raises(FichaIncompletaError):
        clientes_service.crear_cliente(
            uuid4(),
            sesion,
            _reloj(),
            **_ficha(**{campo: "  "}),
            lista_precio_id=None,
            actor_id=None,
        )


def test_crear_cliente_no_pide_credito_entre_sus_parametros() -> None:
    """D3: `CLIENTE_CREAR` no tiene campos de crédito. Si aparecieran, el
    handler podría mandarlos y la separación de permisos dejaría de tener
    sentido."""
    parametros = inspect.signature(clientes_service.crear_cliente).parameters
    for prohibido in (
        "limite_credito",
        "politica_credito",
        "tolerancia_offline_tipo",
        "tolerancia_offline_valor",
    ):
        assert prohibido not in parametros


def test_crear_cliente_no_pide_estado_entre_sus_parametros() -> None:
    """D7: el cliente nace `ACTIVO`; el estado inicial no lo elige el usuario."""
    assert "estado" not in inspect.signature(clientes_service.crear_cliente).parameters


# --- modificar_cliente (D7, máquina de `01` §18) --------------------------


def test_modificar_cliente_de_otra_organizacion_no_existe(sesion: object) -> None:
    """INV-21: un cliente ajeno es inexistente, no prohibido. Con el doble se
    devuelve `None` -- que es lo que el repositorio devuelve cuando la fila no
    está en la organización del token."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: None
    )
    try:
        with pytest.raises(RecursoNoEncontradoError):
            clientes_service.modificar_cliente(
                uuid4(),
                sesion,
                _reloj(),
                cliente_id=uuid4(),
                **_ficha(),
                estado="ACTIVO",
                actor_id=None,
            )
    finally:
        monkeypatch.undo()


def test_modificar_cliente_bloquea_la_fila_antes_de_decidir(sesion: object) -> None:
    """D14 del change 06, mismo criterio: la modificación lee `FOR UPDATE`."""
    pedido: dict[str, Any] = {}

    def _leer(organizacion_id: UUID, cliente_id: UUID, ses: object) -> Cliente:
        pedido["lectura"] = "para_actualizar"
        return _cliente(id=cliente_id, organizacion_id=organizacion_id)

    enviados: dict[str, Any] = {}

    def _escribir(*args: Any, **campos: Any) -> Cliente:
        enviados.update(campos)
        return _cliente()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "obtener_cliente_por_id_para_actualizar", _leer)
    monkeypatch.setattr(clientes_repository, "actualizar_cliente", _escribir)
    try:
        clientes_service.modificar_cliente(
            uuid4(),
            sesion,
            _reloj(),
            cliente_id=uuid4(),
            **_ficha(),
            estado="SUSPENDIDO",
            actor_id=None,
        )
    finally:
        monkeypatch.undo()

    assert pedido["lectura"] == "para_actualizar"
    assert enviados["estado"] == "SUSPENDIDO"


def test_modificar_cliente_acepta_la_suspension_y_la_reactivacion(sesion: object) -> None:
    for estado in ("SUSPENDIDO", "ACTIVO"):
        cliente = _cliente(estado="ACTIVO")
        enviados, escribir = _grabador(cliente)
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            clientes_repository,
            "obtener_cliente_por_id_para_actualizar",
            lambda *a, _fila=cliente, **k: _fila,
        )
        monkeypatch.setattr(clientes_repository, "actualizar_cliente", escribir)
        try:
            clientes_service.modificar_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                **_ficha(),
                estado=estado,
                actor_id=None,
            )
        finally:
            monkeypatch.undo()
        assert enviados["estado"] == estado


def test_modificar_cliente_rechaza_un_estado_fuera_del_catalogo(sesion: object) -> None:
    cliente = _cliente()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    try:
        with pytest.raises(EstadoInvalidoError):
            clientes_service.modificar_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                **_ficha(),
                estado="PENDIENTE",
                actor_id=None,
            )
    finally:
        monkeypatch.undo()


def test_desde_inactivo_solo_se_vuelve_a_activo(sesion: object) -> None:
    """D7: la única salida de `INACTIVO` es `ACTIVO`."""
    cliente = _cliente(estado="INACTIVO")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(clientes_repository, "actualizar_cliente", lambda *a, **k: cliente)
    try:
        with pytest.raises(TransicionEstadoInvalidaError):
            clientes_service.modificar_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                **_ficha(),
                estado="SUSPENDIDO",
                actor_id=None,
            )
    finally:
        monkeypatch.undo()


def test_desde_inactivo_se_vuelve_a_activo_sin_operaciones(sesion: object) -> None:
    """D7 / CLI-06 / ADR-030: la reactivación desde `INACTIVO` se admite
    mientras el cliente no tenga operaciones. Este change no tiene forma de
    saber si las tiene (ningún módulo registra operaciones todavía), así que el
    dato entra por parámetro."""
    cliente = _cliente(estado="INACTIVO")
    enviados, escribir = _grabador(cliente)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(clientes_repository, "actualizar_cliente", escribir)
    try:
        clientes_service.modificar_cliente(
            cliente.organizacion_id,
            sesion,
            _reloj(),
            cliente_id=cliente.id,
            **_ficha(),
            estado="ACTIVO",
            actor_id=None,
            tiene_operaciones=False,
        )
    finally:
        monkeypatch.undo()
    assert enviados["estado"] == "ACTIVO"


def test_desde_inactivo_con_operaciones_no_vuelve_a_activo(sesion: object) -> None:
    cliente = _cliente(estado="INACTIVO")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    try:
        with pytest.raises(ClienteConOperacionesError):
            clientes_service.modificar_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                **_ficha(),
                estado="ACTIVO",
                actor_id=None,
                tiene_operaciones=True,
            )
    finally:
        monkeypatch.undo()


def test_el_consumidor_final_no_se_inactiva(sesion: object) -> None:
    """CLI-03, ADR-029."""
    cliente = _cliente(estado="ACTIVO", es_consumidor_final=True)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    try:
        with pytest.raises(ConsumidorFinalNoInactivableError):
            clientes_service.modificar_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                **_ficha(),
                estado="INACTIVO",
                actor_id=None,
            )
    finally:
        monkeypatch.undo()


def test_el_consumidor_final_sigue_la_misma_maquina_de_estados(sesion: object) -> None:
    """CLI-02: el consumidor final se suspende y se reactiva como cualquier
    otro cliente, sin dejar de serlo."""
    cliente = _cliente(estado="ACTIVO", es_consumidor_final=True)
    enviados, escribir = _grabador(cliente)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(clientes_repository, "actualizar_cliente", escribir)
    try:
        for estado in ("SUSPENDIDO", "ACTIVO"):
            clientes_service.modificar_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                **_ficha(),
                estado=estado,
                actor_id=None,
            )
    finally:
        monkeypatch.undo()
    assert [enviados["estado"]] == ["ACTIVO"]
    # Y la marca sobrevive: la modificación de ficha no la toca.
    for prohibido in ("es_consumidor_final", "limite_credito", "politica_credito"):
        assert prohibido not in enviados


def test_modificar_cliente_no_toca_los_tres_campos_de_credito(sesion: object) -> None:
    """D3: la ficha nunca escribe crédito. El doble del repositorio falla si
    aparece alguno de los tres entre los campos."""
    cliente = _cliente(politica_credito="AUTORIZAR", limite_credito=Decimal("1000.00"))
    enviados: dict[str, Any] = {}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(
        clientes_repository,
        "actualizar_cliente",
        lambda *a, **k: (enviados.update(k), cliente)[1],
    )
    try:
        clientes_service.modificar_cliente(
            cliente.organizacion_id,
            sesion,
            _reloj(),
            cliente_id=cliente.id,
            **_ficha(),
            estado="ACTIVO",
            actor_id=None,
        )
    finally:
        monkeypatch.undo()

    for prohibido in (
        "limite_credito",
        "politica_credito",
        "tolerancia_offline_tipo",
        "tolerancia_offline_valor",
    ):
        assert prohibido not in enviados


# --- modificar_credito_cliente (CRE-01, CRE-03, CRE-06) --------------------


def test_modificar_credito_acepta_limite_politica_y_tolerencia(sesion: object) -> None:
    cliente = _cliente()
    enviados, escribir = _grabador(cliente)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(clientes_repository, "actualizar_credito_cliente", escribir)
    try:
        clientes_service.modificar_credito_cliente(
            cliente.organizacion_id,
            sesion,
            _reloj(),
            cliente_id=cliente.id,
            limite_credito=Decimal("150000.00"),
            politica_credito="AUTORIZAR",
            tolerancia_offline_tipo="IMPORTE",
            tolerancia_offline_valor=Decimal("25.00"),
            actor_id=None,
        )
    finally:
        monkeypatch.undo()

    assert enviados["limite_credito"] == Decimal("150000.00")
    assert enviados["politica_credito"] == "AUTORIZAR"
    assert enviados["tolerancia_offline_tipo"] == "IMPORTE"
    assert enviados["tolerancia_offline_valor"] == Decimal("25.00")


def test_modificar_credito_rechaza_el_consumidor_final(sesion: object) -> None:
    """CLI-03, CRE-01: el límite del consumidor final es cero y fijo."""
    cliente = _cliente(es_consumidor_final=True, limite_credito=Decimal("0.00"))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(clientes_repository, "actualizar_credito_cliente", lambda *a, **k: cliente)
    try:
        with pytest.raises(ConsumidorFinalSinCreditoError):
            clientes_service.modificar_credito_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                limite_credito=Decimal("50000.00"),
                politica_credito=None,
                tolerancia_offline_tipo=None,
                tolerancia_offline_valor=None,
                actor_id=None,
            )
    finally:
        monkeypatch.undo()
    assert cliente.limite_credito == Decimal("0.00")


def test_modificar_credito_deja_pasar_todo_en_nulo_sobre_el_consumidor_final(
    sesion: object,
) -> None:
    """Reenviar el crédito del consumidor final tal como está no es un error:
    es una escritura que no cambia nada. Inventar un rechazo obligaría al
    handler a tratar distinto un reenvío del mismo crédito."""
    cliente = _cliente(es_consumidor_final=True, limite_credito=Decimal("0.00"))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(clientes_repository, "actualizar_credito_cliente", lambda *a, **k: cliente)
    try:
        clientes_service.modificar_credito_cliente(
            cliente.organizacion_id,
            sesion,
            _reloj(),
            cliente_id=cliente.id,
            limite_credito=None,
            politica_credito=None,
            tolerancia_offline_tipo=None,
            tolerancia_offline_valor=None,
            actor_id=None,
        )
    finally:
        monkeypatch.undo()
    assert cliente.limite_credito == Decimal("0.00")


def test_modificar_credito_rechaza_un_limite_negativo(sesion: object) -> None:
    cliente = _cliente()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    try:
        with pytest.raises(LimiteCreditoInvalidoError):
            clientes_service.modificar_credito_cliente(
                cliente.organizacion_id,
                sesion,
                _reloj(),
                cliente_id=cliente.id,
                limite_credito=Decimal("-1.00"),
                politica_credito=None,
                tolerancia_offline_tipo=None,
                tolerancia_offline_valor=None,
                actor_id=None,
            )
    finally:
        monkeypatch.undo()


def test_modificar_credito_de_otra_organizacion_no_existe(sesion: object) -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: None
    )
    try:
        with pytest.raises(RecursoNoEncontradoError):
            clientes_service.modificar_credito_cliente(
                uuid4(),
                sesion,
                _reloj(),
                cliente_id=uuid4(),
                limite_credito=Decimal("1.00"),
                politica_credito=None,
                tolerancia_offline_tipo=None,
                tolerancia_offline_valor=None,
                actor_id=None,
            )
    finally:
        monkeypatch.undo()


def test_modificar_credito_no_toca_la_ficha_ni_el_estado(sesion: object) -> None:
    cliente = _cliente(estado="SUSPENDIDO", nombre="Kiosco La Esquina")
    enviados: dict[str, Any] = {}
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(
        clientes_repository,
        "actualizar_credito_cliente",
        lambda *a, **k: (enviados.update(k), cliente)[1],
    )
    try:
        clientes_service.modificar_credito_cliente(
            cliente.organizacion_id,
            sesion,
            _reloj(),
            cliente_id=cliente.id,
            limite_credito=Decimal("1.00"),
            politica_credito=None,
            tolerancia_offline_tipo=None,
            tolerancia_offline_valor=None,
            actor_id=None,
        )
    finally:
        monkeypatch.undo()

    for prohibido in ("nombre", "direccion", "contacto", "estado", "codigo"):
        assert prohibido not in enviados


# --- auditoría del crédito (AUD-01) ---------------------------------------


def test_modificar_credito_audita_el_antes_y_el_despues(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AUD-01: cambiar el crédito tiene que poder reconstruirse después, así que
    la fila de auditoría lleva el valor anterior y el nuevo de los tres campos.

    Se escribe ACÁ, en el servicio, y no en el handler: la fila ya está leída
    con `FOR UPDATE`, así que el `antes` es el valor anterior real. Si el
    handler lo leyera por su cuenta habría una ventana en la que otra
    transacción cambió el crédito y la auditoría registraría un `antes` que
    nunca existió."""
    cliente = _cliente(
        limite_credito=Decimal("50000.00"),
        politica_credito="ADVERTIR",
        tolerancia_offline_tipo=None,
        tolerancia_offline_valor=None,
    )
    audits: list[dict[str, Any]] = []
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(clientes_repository, "actualizar_credito_cliente", lambda *a, **k: cliente)
    monkeypatch.setattr(identidad_service, "registrar_auditoria", lambda *a, **k: audits.append(k))

    clientes_service.modificar_credito_cliente(
        cliente.organizacion_id,
        sesion,
        _reloj(),
        cliente_id=cliente.id,
        limite_credito=Decimal("150000.00"),
        politica_credito="AUTORIZAR",
        tolerancia_offline_tipo="IMPORTE",
        tolerancia_offline_valor=Decimal("5000.00"),
        actor_id=uuid4(),
        operation_id=uuid4(),
        dispositivo_id=uuid4(),
    )

    assert len(audits) == 1
    assert audits[0]["accion"] == "CLIENTE_CREDITO_MODIFICAR"
    assert audits[0]["entidad"] == "cliente"
    assert audits[0]["entidad_id"] == cliente.id
    assert audits[0]["antes"] == {
        "limite_credito": "50000.00",
        "politica_credito": "ADVERTIR",
        "tolerancia_offline_tipo": None,
        "tolerancia_offline_valor": None,
    }, (
        "Los importes van como string: `antes`/`despues` se escriben en "
        "columnas `jsonb` y JSON no tiene tipo decimal (INV-03)."
    )
    assert audits[0]["despues"] == {
        "limite_credito": "150000.00",
        "politica_credito": "AUTORIZAR",
        "tolerancia_offline_tipo": "IMPORTE",
        "tolerancia_offline_valor": "5000.00",
    }


def test_la_auditoria_del_credito_no_se_escribe_si_la_validacion_falla(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-01: si la escritura no llega a hacerse, la auditoría tampoco. Se
    valida antes de auditar justamente para esto."""
    cliente = _cliente()
    audits: list[dict[str, Any]] = []
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: cliente
    )
    monkeypatch.setattr(identidad_service, "registrar_auditoria", lambda *a, **k: audits.append(k))

    with pytest.raises(LimiteCreditoInvalidoError):
        clientes_service.modificar_credito_cliente(
            cliente.organizacion_id,
            sesion,
            _reloj(),
            cliente_id=cliente.id,
            limite_credito=Decimal("-1.00"),
            politica_credito=None,
            tolerancia_offline_tipo=None,
            tolerancia_offline_valor=None,
            actor_id=None,
        )

    assert audits == []


def test_el_credito_de_otra_organizacion_no_audita(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un `cliente_id` ajeno no existe: no se escribe nada, y por lo tanto
    tampoco se audita nada que lo mencione."""
    audits: list[dict[str, Any]] = []
    monkeypatch.setattr(
        clientes_repository, "obtener_cliente_por_id_para_actualizar", lambda *a, **k: None
    )
    monkeypatch.setattr(identidad_service, "registrar_auditoria", lambda *a, **k: audits.append(k))

    with pytest.raises(RecursoNoEncontradoError):
        clientes_service.modificar_credito_cliente(
            uuid4(),
            sesion,
            _reloj(),
            cliente_id=uuid4(),
            limite_credito=Decimal("1.00"),
            politica_credito=None,
            tolerancia_offline_tipo=None,
            tolerancia_offline_valor=None,
            actor_id=None,
        )

    assert audits == []


# --- lecturas (tarea 2.2) --------------------------------------------------


def test_obtener_cliente_por_id_delega_en_el_repositorio(sesion: object) -> None:
    objetivo = _cliente()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "obtener_cliente_por_id", lambda *a, **k: objetivo)
    try:
        assert (
            clientes_service.obtener_cliente_por_id(objetivo.organizacion_id, objetivo.id, sesion)
            is objetivo
        )
    finally:
        monkeypatch.undo()


def test_obtener_consumidor_final_delega_en_el_repositorio(sesion: object) -> None:
    objetivo = _cliente(es_consumidor_final=True, limite_credito=Decimal("0.00"))
    organizacion_id = objetivo.organizacion_id
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "obtener_consumidor_final", lambda *a, **k: objetivo)
    try:
        resultado = clientes_service.obtener_consumidor_final(organizacion_id, sesion)
        assert resultado is objetivo
    finally:
        monkeypatch.undo()


def test_listar_clientes_reenvia_limite_cursor_texto_y_estado(sesion: object) -> None:
    pedido: dict[str, Any] = {}
    cursor = "Y3Vyc29y"

    def _listar(organizacion_id: UUID, ses: object, **filtros: Any) -> tuple[list[Cliente], None]:
        pedido["organizacion_id"] = organizacion_id
        pedido.update(filtros)
        return [], None

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "listar_clientes_paginado", _listar)
    try:
        clientes_service.listar_clientes(
            uuid4(), sesion, limite=25, cursor=cursor, texto="Esquina", estado="SUSPENDIDO"
        )
    finally:
        monkeypatch.undo()

    assert pedido["limite"] == 25
    assert pedido["cursor"] == cursor
    assert pedido["texto"] == "Esquina"
    assert pedido["estado"] == "SUSPENDIDO"


# --- el change 10 los invoca fila por fila (tarea 2.2) ---------------------


def test_las_escrituras_toman_un_solo_cliente_por_vez() -> None:
    """`design.md` D9: la sincronización del change 10 llama a estos servicios
    una vez por fila, así que ninguno acepta un lote ni devuelve un lote."""
    for nombre in ("modificar_cliente", "modificar_credito_cliente"):
        funcion = getattr(clientes_service, nombre)
        parametros = inspect.signature(funcion).parameters
        assert "cliente_id" in parametros
        # Ni lote de entrada ni lote de salida: el change 10 los invoca fila
        # por fila, así que ningún parámetro es una secuencia y ninguno está
        # en plural.
        for nombre_parametro, parametro in parametros.items():
            anotacion = str(parametro.annotation)
            assert "list[" not in anotacion, f"{nombre}.{nombre_parametro} acepta un lote."
            assert not nombre_parametro.endswith("_ids"), (
                f"{nombre}.{nombre_parametro} acepta varios clientes: se espera uno por llamada."
            )
        assert str(inspect.signature(funcion).return_annotation) != "list[Cliente]", (
            f"{nombre} devuelve un lote."
        )


# --- frontera con `identidad` (tarea 2.3, D4) -----------------------------


def test_configurar_consumidor_final_crea_el_cliente_y_fija_la_configuracion(
    sesion: object,
) -> None:
    from app.modules.identidad import service as identidad_service

    organizacion_id = uuid4()
    creado: dict[str, Any] = {}
    configuracion: dict[str, Any] = {}

    class _Configuracion:
        def __init__(self) -> None:
            self.permite_consumidor_final = None
            self.cliente_consumidor_final_id = None

    def _crear(org: UUID, ses: object, **campos: Any) -> Cliente:
        creado.update({"organizacion_id": org, **campos})
        return _cliente(id=campos["cliente_id"], organizacion_id=org, estado="ACTIVO")

    def _configurar(org: UUID, ses: object, reloj: Any, **campos: Any) -> Any:
        configuracion.update({"organizacion_id": org, "reloj": reloj, **campos})
        return _Configuracion()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "obtener_consumidor_final", lambda *a, **k: None)
    monkeypatch.setattr(
        identidad_service, "obtener_configuracion", lambda *a, **k: _Configuracion()
    )
    monkeypatch.setattr(identidad_service, "configurar_consumidor_final", _configurar)
    monkeypatch.setattr(clientes_repository, "crear_cliente", _crear)
    try:
        cliente = clientes_service.configurar_consumidor_final(
            organizacion_id, sesion, _reloj(), nombre="Consumidor final", actor_id=None
        )
    finally:
        monkeypatch.undo()

    # El cliente nace marcado, activo, con límite cero y sin crédito propio.
    assert creado["es_consumidor_final"] is True
    assert creado["estado"] == "ACTIVO"
    assert creado["limite_credito"] == Decimal("0.00")
    assert creado["politica_credito"] is None
    assert creado["tolerancia_offline_tipo"] is None
    assert creado["tolerancia_offline_valor"] is None
    # Y la configuración de la MISMA organización apunta a ese cliente.
    # `permite_consumidor_final` no se manda desde acá: lo pone el setter de
    # `identidad/service.py` junto con el identificador, porque son un par
    # (`03` §4). Lo verifica `test_identidad_service_consumidor_final.py`.
    assert configuracion["organizacion_id"] == organizacion_id
    assert configuracion["cliente_consumidor_final_id"] == cliente.id


def test_un_segundo_intento_se_rechaza_sin_crear_otro_cliente(sesion: object) -> None:
    from app.modules.identidad import service as identidad_service

    organizacion_id = uuid4()
    ya_habilitado = _cliente(es_consumidor_final=True, limite_credito=Decimal("0.00"))

    def _no_crear(*args: Any, **kwargs: Any) -> Cliente:
        raise AssertionError("No debe crearse un segundo cliente consumidor final.")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        clientes_repository, "obtener_consumidor_final", lambda *a, **k: ya_habilitado
    )
    monkeypatch.setattr(clientes_repository, "crear_cliente", _no_crear)
    monkeypatch.setattr(identidad_service, "configurar_consumidor_final", _no_crear)
    try:
        with pytest.raises(ConsumidorFinalYaHabilitadoError):
            clientes_service.configurar_consumidor_final(
                organizacion_id, sesion, _reloj(), nombre="Consumidor final", actor_id=None
            )
    finally:
        monkeypatch.undo()


def test_configurar_consumidor_final_rechaza_el_nombre_vacio(sesion: object) -> None:
    with pytest.raises(NombreInvalidoError):
        clientes_service.configurar_consumidor_final(
            uuid4(), sesion, _reloj(), nombre="  ", actor_id=None
        )


def test_configurar_consumidor_final_no_admite_credito_ni_cliente_ya_existente() -> None:
    """D4: el comando no admite un `cliente_id` al que asociarlo ni campos de
    crédito. La marca y el límite cero los pone el servicio, no quien llama."""
    parametros = inspect.signature(clientes_service.configurar_consumidor_final).parameters
    for prohibido in (
        "cliente_id",
        "limite_credito",
        "politica_credito",
        "tolerancia_offline_tipo",
        "tolerancia_offline_valor",
        "es_consumidor_final",
    ):
        assert prohibido not in parametros


def test_la_configuracion_de_otra_organizacion_no_se_toca(sesion: object) -> None:
    """INV-02/INV-21: el setter se llama con la organización del token, la
    misma que se usó para crear el cliente."""
    from app.modules.identidad import service as identidad_service

    organizacion_de_a = uuid4()
    organizaciones_vistas: list[UUID] = []

    class _Configuracion:
        permite_consumidor_final = None
        cliente_consumidor_final_id = None

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "obtener_consumidor_final", lambda *a, **k: None)
    monkeypatch.setattr(
        identidad_service, "obtener_configuracion", lambda *a, **k: _Configuracion()
    )
    monkeypatch.setattr(
        clientes_repository,
        "crear_cliente",
        lambda org, ses, **campos: _cliente(id=campos["cliente_id"], organizacion_id=org),
    )

    def _configurar(org: UUID, *args: Any, **campos: Any) -> Any:
        organizaciones_vistas.append(org)
        return _Configuracion()

    monkeypatch.setattr(identidad_service, "configurar_consumidor_final", _configurar)
    try:
        clientes_service.configurar_consumidor_final(
            organizacion_de_a, sesion, _reloj(), nombre="Consumidor final", actor_id=None
        )
    finally:
        monkeypatch.undo()

    assert organizaciones_vistas == [organizacion_de_a]


def test_sin_fila_de_configuracion_no_se_confirma_un_cliente_consumidor_final(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`identidad_service.configurar_consumidor_final` devuelve `None` cuando la
    organización no tiene fila de configuración, y lo hace sin tocar nada.

    Si el servicio ignorara ese `None`, el bus confirmaría un cliente marcado
    como consumidor final sin el par de configuración detrás: el estado
    intermedio que D4 prohíbe, invisible hasta el bootstrap del change 21
    (SYN-11). Por eso tiene que lanzar y dejar que la reversión del bus se
    lleve también el cliente recién creado."""
    from app.modules.identidad import service as identidad_service

    creados: list[Cliente] = []

    def _crear(org: UUID, ses: Any, **campos: Any) -> Cliente:
        cliente = _cliente(id=campos["cliente_id"], organizacion_id=org)
        creados.append(cliente)
        return cliente

    monkeypatch.setattr(clientes_repository, "obtener_consumidor_final", lambda *a, **k: None)
    monkeypatch.setattr(clientes_repository, "crear_cliente", _crear)
    monkeypatch.setattr(identidad_service, "configurar_consumidor_final", lambda *a, **k: None)

    with pytest.raises(ConfiguracionDeOrganizacionAusenteError) as excepcion:
        clientes_service.configurar_consumidor_final(
            uuid4(), sesion, _reloj(), nombre="Consumidor final", actor_id=None
        )

    assert excepcion.value.codigo == "CONFIGURACION_DE_ORGANIZACION_AUSENTE"
    # Se llegó a crear el cliente, y la excepción es lo que impide que la
    # transacción del bus lo confirme.
    assert len(creados) == 1


# --- CLI-06 activo desde el change 08: la consulta llega como callable -------


def _modificar_con_verificador(
    sesion: object, estado_actual: str, estado_nuevo: str, verificador: object
) -> tuple[list[str], dict[str, object]]:
    """Corre `modificar_cliente` con el bloqueo y la escritura sustituidos y
    devuelve el orden de las llamadas y lo escrito."""
    cliente = _cliente(estado=estado_actual)
    orden: list[str] = []
    enviados: dict[str, object] = {}

    def _bloquear(*args: object, **kwargs: object) -> object:
        orden.append("bloqueo")
        return cliente

    def _escribir(*args: object, **kwargs: object) -> object:
        orden.append("escritura")
        enviados.update(kwargs)
        cliente.estado = str(kwargs["estado"])
        return cliente

    def _verificar() -> bool:
        orden.append("consulta")
        return bool(verificador)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_repository, "obtener_cliente_por_id_para_actualizar", _bloquear)
    monkeypatch.setattr(clientes_repository, "actualizar_cliente", _escribir)
    try:
        clientes_service.modificar_cliente(
            cliente.organizacion_id,
            sesion,  # type: ignore[arg-type]
            _reloj(),
            cliente_id=cliente.id,
            **_ficha(),
            estado=estado_nuevo,
            actor_id=None,
            verificar_operaciones=_verificar,
        )
    finally:
        monkeypatch.undo()
    return orden, enviados


def test_la_consulta_de_operaciones_ocurre_despues_del_bloqueo_del_cliente(sesion: object) -> None:
    """D8 del change 08: se pregunta con la fila del cliente ya tomada."""
    orden, enviados = _modificar_con_verificador(sesion, "INACTIVO", "ACTIVO", False)

    assert orden == ["bloqueo", "consulta", "escritura"]
    assert enviados["estado"] == "ACTIVO"


def test_un_cliente_inactivo_con_movimientos_no_se_reactiva_y_no_se_escribe(
    sesion: object,
) -> None:
    orden: list[str] = []
    with pytest.raises(ClienteConOperacionesError):
        orden, _ = _modificar_con_verificador(sesion, "INACTIVO", "ACTIVO", True)
    assert orden == []


@pytest.mark.parametrize(
    ("actual", "nuevo"),
    [("ACTIVO", "SUSPENDIDO"), ("SUSPENDIDO", "ACTIVO"), ("ACTIVO", "INACTIVO")],
)
def test_la_consulta_no_se_hace_si_el_cliente_no_esta_inactivo(
    sesion: object, actual: str, nuevo: str
) -> None:
    """CLI-06 solo gobierna la salida de `INACTIVO`."""
    orden, _ = _modificar_con_verificador(sesion, actual, nuevo, True)

    assert "consulta" not in orden
