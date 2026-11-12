"""Change 07, grupo 3 (tareas 3.1 a 3.5): los cuatro comandos de `clientes` y
sus handlers.

No necesitan PostgreSQL. Lo que se verifica acá es todo lo que se puede
verificar sin base: el catálogo de tipos, el registro de handlers, la forma del
contenido (incluido qué se RECHAZA como malformado), que el handler tome la
organización del sobre y no del contenido, que no haga `commit`, a qué permiso
exige cada comando, y la auditoría con valor anterior y nuevo del crédito
(AUD-01). El comportamiento contra la base real -- traducción de
`IntegrityError`, idempotencia por `operation_id`, reversión de la transacción
completa -- está en `tests/integration/test_clientes_comandos.py`.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.commands.catalogo import tipo_declarado
from app.commands.registro import resolver_handler
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import DomainError
from app.modules.clientes import commands as clientes_commands
from app.modules.clientes import service as clientes_service
from app.modules.identidad import service as identidad_service

MOMENTO = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
TIPOS = (
    "CLIENTE_CREAR",
    "CLIENTE_MODIFICAR",
    "CLIENTE_CREDITO_MODIFICAR",
    "CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
)


def _sobre(**cambios: Any) -> SobreComando:
    base: dict[str, Any] = {
        "operation_id": uuid4(),
        "tipo": "CLIENTE_CREAR",
        "version": 1,
        "modo": "ONLINE",
        "organizacion_id": uuid4(),
        "usuario_id": uuid4(),
        "dispositivo_id": uuid4(),
        "occurred_at": MOMENTO,
        "secuencia": 1,
        "app_version": "1.0.0",
        "contenido": {},
    }
    base.update(cambios)
    return SobreComando(**base)


def _validar(tipo: str, contenido: dict[str, Any]) -> BaseModel:
    """Valida contra el esquema registrado, como hace el bus."""
    from app.commands.registro import validar_contenido

    return validar_contenido(resolver_handler(tipo, 1), contenido)


def _contenido_valido(tipo: str) -> dict[str, Any]:
    """Contenido mínimo que cada esquema acepta."""
    if tipo == "CLIENTE_CREAR":
        return {"nombre": "Kiosco", "direccion": "Av. San Martín 1420", "contacto": "Rocío"}
    if tipo == "CLIENTE_MODIFICAR":
        return {
            "cliente_id": str(uuid4()),
            "nombre": "Kiosco",
            "direccion": "Av. San Martín 1420",
            "contacto": "Rocío",
            "estado": "ACTIVO",
        }
    if tipo == "CLIENTE_CREDITO_MODIFICAR":
        return {"cliente_id": str(uuid4()), "limite_credito": "1000.00"}
    return {"nombre": "Consumidor final"}


class _Fila:
    """Lo mínimo que los handlers leen de lo que devuelve el servicio."""

    def __init__(self, id_: UUID) -> None:  # noqa: A002
        self.id = id_


@pytest.fixture
def sesion() -> object:
    return object()


@pytest.fixture(autouse=True)
def _permisos_concedidos(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Por defecto el usuario tiene los tres permisos; las pruebas que
    verifican la ausencia de uno pueden concentrarse en eso."""
    return monkeypatch.setattr(
        identidad_service,
        "listar_permisos_del_usuario",
        lambda *a, **k: frozenset(
            {"GESTIONAR_CLIENTES", "GESTIONAR_CREDITO", "ADMIN_CONFIGURACION"}
        ),
    )


# --- 3.1, 3.3, 3.4: catálogo y registro (D3, D4) --------------------------


@pytest.mark.parametrize("tipo", TIPOS)
def test_cada_tipo_esta_declarado_solo_online(tipo: str) -> None:
    """Los cuatro exigen `sesion` y `reloj` y no pueden encolar nada sin
    conexión, así que ninguno admite `OFFLINE` (mismo motivo que
    `proveedores/commands.py`)."""
    declarado = tipo_declarado(tipo)
    assert declarado is not None, f"{tipo} no está declarado en el catálogo."
    assert declarado.admite_online is True
    assert declarado.admite_offline is False


@pytest.mark.parametrize("tipo", TIPOS)
def test_cada_tipo_tiene_handler_registrado_en_la_version_1(tipo: str) -> None:
    registrado = resolver_handler(tipo, 1)
    assert registrado.tipo == tipo
    assert registrado.version == 1
    assert issubclass(registrado.esquema, BaseModel)


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_esquema_rechaza_campos_desconocidos(tipo: str) -> None:
    """La spec exige que `limite_credito` en `CLIENTE_CREAR` se rechace como
    MALFORMADO. Pydantic ignora lo que no conoce por defecto, así que sin esto
    el campo se perdería en silencio y la separación de permisos (D3) no
    significaría nada."""
    esquema = resolver_handler(tipo, 1).esquema
    with pytest.raises(ValidationError):
        esquema.model_validate({"campo_que_no_existe": 1})


# --- 3.1: CLIENTE_CREAR (D7, D3, CLI-01) -----------------------------------


def test_crear_exige_nombre_direccion_y_contacto() -> None:
    esquema = resolver_handler("CLIENTE_CREAR", 1).esquema
    for obligatorio in ("nombre", "direccion", "contacto"):
        assert obligatorio in esquema.model_fields, (
            f"`{obligatorio}` es obligatorio en la ficha (CLI-01)."
        )


def test_crear_admite_los_opcionales_de_la_ficha() -> None:
    esquema = resolver_handler("CLIENTE_CREAR", 1).esquema
    for opcional in (
        "razon_social",
        "documento_tipo",
        "documento_numero",
        "telefono",
        "email",
        "codigo",
        "estado_facturacion_default",
    ):
        assert opcional in esquema.model_fields, (
            f"`{opcional}` es opcional en la ficha (spec de fichas de cliente)."
        )


@pytest.mark.parametrize("tipo", ["CLIENTE_CREAR", "CLIENTE_MODIFICAR"])
def test_los_comandos_ofrecen_la_lista_asignada_como_opcional(tipo: str) -> None:
    """Change 13, D11 punto 1: la tabla `lista_precio` existe y la clave foránea compuesta
    también, así que la ficha acepta la lista asignada (CLI-01); es opcional porque sin ella
    el cliente compra con la lista predeterminada de la organización (PRC-20). Reemplaza la
    mitigación D2 del change 07 ("no se ofrece en ningún formulario")."""
    campo = resolver_handler(tipo, 1).esquema.model_fields["lista_precio_id"]
    assert not campo.is_required(), "sin lista asignada es válido"
    assert campo.default is None


def test_crear_no_admite_campos_de_credito() -> None:
    """D3: la ficha y el crédito son dos comandos con dos permisos distintos.
    Aceptar el crédito acá dejaría la separación como decorativa."""
    esquema = resolver_handler("CLIENTE_CREAR", 1).esquema
    for prohibido in (
        "limite_credito",
        "politica_credito",
        "tolerancia_offline_tipo",
        "tolerancia_offline_valor",
    ):
        assert prohibido not in esquema.model_fields


def test_crear_no_admite_el_estado_ni_la_marca_de_consumidor_final() -> None:
    """D7: el cliente nace `ACTIVO`. CLI-03: la marca solo la pone el comando
    de habilitación."""
    esquema = resolver_handler("CLIENTE_CREAR", 1).esquema
    for prohibido in ("estado", "es_consumidor_final", "consumidor_final"):
        assert prohibido not in esquema.model_fields


def test_crear_rechaza_la_marca_de_consumidor_final_como_malformado() -> None:
    with pytest.raises(DomainError):
        _validar(
            "CLIENTE_CREAR",
            {
                "nombre": "Kiosco",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
                "es_consumidor_final": True,
            },
        )


def test_crear_rechaza_el_credito_como_malformado() -> None:
    with pytest.raises(DomainError):
        _validar(
            "CLIENTE_CREAR",
            {
                "nombre": "Kiosco",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
                "limite_credito": "150000.00",
            },
        )


# --- 3.2: CLIENTE_MODIFICAR (D7, máquina de `01` §18) ---------------------


def test_modificar_exige_cliente_id_y_estado() -> None:
    esquema = resolver_handler("CLIENTE_MODIFICAR", 1).esquema
    for obligatorio in ("cliente_id", "nombre", "direccion", "contacto", "estado"):
        assert obligatorio in esquema.model_fields


def test_modificar_no_admite_campos_de_credito() -> None:
    esquema = resolver_handler("CLIENTE_MODIFICAR", 1).esquema
    for prohibido in (
        "limite_credito",
        "politica_credito",
        "tolerancia_offline_tipo",
        "tolerancia_offline_valor",
    ):
        assert prohibido not in esquema.model_fields


def test_modificar_rechaza_el_credito_como_malformado() -> None:
    with pytest.raises(DomainError):
        _validar(
            "CLIENTE_MODIFICAR",
            {
                "cliente_id": str(uuid4()),
                "nombre": "Kiosco",
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
                "estado": "ACTIVO",
                "politica_credito": "AUTORIZAR",
            },
        )


def test_modificar_no_admite_la_marca_de_consumidor_final() -> None:
    """CLI-03: la marca no se asigna ni se quita por la ficha."""
    esquema = resolver_handler("CLIENTE_MODIFICAR", 1).esquema
    assert "es_consumidor_final" not in esquema.model_fields


# --- 3.3: CLIENTE_CREDITO_MODIFICAR (CRE-01, CRE-03, CRE-06, AUD-01) -------


def test_credito_exige_cliente_id() -> None:
    esquema = resolver_handler("CLIENTE_CREDITO_MODIFICAR", 1).esquema
    assert "cliente_id" in esquema.model_fields
    for campo in (
        "limite_credito",
        "politica_credito",
        "tolerancia_offline_tipo",
        "tolerancia_offline_valor",
    ):
        assert campo in esquema.model_fields


def test_los_importes_del_credito_vienen_como_string_y_se_validan_como_decimal() -> None:
    """`CLAUDE.md` §4: los importes viajan como string en el JSON y se
    convierten a `Decimal` exacto, nunca a `float`."""
    contenido = _validar(
        "CLIENTE_CREDITO_MODIFICAR", {"cliente_id": str(uuid4()), "limite_credito": "150000.00"}
    )

    assert isinstance(contenido.limite_credito, Decimal)
    assert contenido.limite_credito == Decimal("150000.00")
    assert not isinstance(contenido.limite_credito, float)


def test_el_credito_acepta_los_cuatro_campos_en_nulo() -> None:
    contenido = _validar(
        "CLIENTE_CREDITO_MODIFICAR",
        {
            "cliente_id": str(uuid4()),
            "limite_credito": None,
            "politica_credito": None,
            "tolerancia_offline_tipo": None,
            "tolerancia_offline_valor": None,
        },
    )

    assert contenido.limite_credito is None


def test_el_credito_no_admite_la_ficha() -> None:
    """D3: el comando de crédito no escribe la ficha ni el estado."""
    esquema = resolver_handler("CLIENTE_CREDITO_MODIFICAR", 1).esquema
    for prohibido in ("nombre", "direccion", "contacto", "estado", "codigo", "es_consumidor_final"):
        assert prohibido not in esquema.model_fields


# --- 3.4: CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR (D4, ADR-029) ----------------


def test_consumidor_final_exige_nombre_y_nada_mas() -> None:
    esquema = resolver_handler("CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR", 1).esquema
    assert "nombre" in esquema.model_fields
    for prohibido in (
        "cliente_id",
        "limite_credito",
        "politica_credito",
        "tolerancia_offline_tipo",
        "tolerancia_offline_valor",
        "es_consumidor_final",
        "direccion",
        "contacto",
        "codigo",
        "documento_tipo",
        "documento_numero",
    ):
        assert prohibido not in esquema.model_fields, (
            f"`{prohibido}` no se admite en el comando de habilitación (D4)."
        )


def test_el_consumidor_final_rechaza_un_cliente_ya_existente_como_malformado() -> None:
    with pytest.raises(DomainError):
        _validar(
            "CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
            {"nombre": "Consumidor final", "cliente_id": str(uuid4())},
        )


# --- 3.5: los handlers (D7 de `04`) ---------------------------------------


@pytest.mark.parametrize("nombre", [f"manejar_{t.lower()}" for t in TIPOS])
def test_cada_comando_tiene_su_handler_con_la_plantilla_de_04(nombre: str) -> None:
    """Un tipo de comando por escritura ya existente en `service.py`, un
    esquema versión 1, y un handler de pocas líneas que llama al servicio."""
    funcion = getattr(clientes_commands, nombre)
    parametros = list(inspect.signature(funcion).parameters)
    assert parametros[:2] == ["sobre", "contenido"]
    for palabra_clave in ("sesion", "reloj"):
        assert palabra_clave in parametros


@pytest.mark.parametrize("nombre", [f"manejar_{t.lower()}" for t in TIPOS])
def test_ningun_handler_cierra_la_transaccion(nombre: str) -> None:
    """`CLAUDE.md` §4: la transacción la gestiona el bus
    (`sync/service.py::procesar_comando`), que la revierte entera si el handler
    lanza."""
    fuente = inspect.getsource(getattr(clientes_commands, nombre))
    assert ".commit(" not in fuente
    assert ".rollback(" not in fuente


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_handler_toma_la_organizacion_del_sobre(tipo: str) -> None:
    """INV-21, TR-08: al servicio le llega la organización del sobre. Ningún
    esquema de comando declara `organizacion_id`, así que el contenido
    estructuralmente no puede elegir la organización."""
    organizacion_del_sobre = uuid4()
    organizaciones: list[UUID] = []

    def _registrar(org: UUID, *args: Any, **kwargs: Any) -> Any:
        organizaciones.append(org)
        return _Fila(uuid4())

    nombre_del_servicio = {
        "CLIENTE_CREAR": "crear_cliente",
        "CLIENTE_MODIFICAR": "modificar_cliente",
        "CLIENTE_CREDITO_MODIFICAR": "modificar_credito_cliente",
        "CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR": "configurar_consumidor_final",
    }[tipo]

    validado = _validar(tipo, _contenido_valido(tipo))
    assert "organizacion_id" not in type(validado).model_fields

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_service, nombre_del_servicio, _registrar)
    try:
        resolver_handler(tipo, 1).funcion(
            _sobre(tipo=tipo, organizacion_id=organizacion_del_sobre),
            validado,
            sesion=object(),
            reloj=FixedClock(MOMENTO),
        )
    finally:
        monkeypatch.undo()

    assert organizaciones == [organizacion_del_sobre]


@pytest.mark.parametrize("tipo", TIPOS)
def test_ningun_comando_acepta_una_organizacion_del_contenido(tipo: str) -> None:
    """El caso fuerte de INV-21: un cliente ajeno que se cuela en el contenido
    no se ignora en silencio ni se aplica, se rechaza el comando entero como
    MALFORMADO y no se toca la base."""
    called: list[Any] = []
    monkeypatch = pytest.MonkeyPatch()
    for nombre in (
        "crear_cliente",
        "modificar_cliente",
        "modificar_credito_cliente",
        "configurar_consumidor_final",
    ):
        monkeypatch.setattr(clientes_service, nombre, lambda *a, **k: called.append(a))

    with pytest.raises(DomainError) as excepcion:
        _validar(tipo, {**_contenido_valido(tipo), "organizacion_id": str(uuid4())})

    assert excepcion.value.codigo == "CONTENIDO_DE_COMANDO_INVALIDO"
    assert called == []
    monkeypatch.undo()


def test_el_handler_devuelve_el_identificador_del_cliente_como_string(
    sesion: object,
) -> None:
    cliente_id = uuid4()
    sobre = _sobre()
    contenido = _validar(
        "CLIENTE_CREAR",
        {"nombre": "Kiosco", "direccion": "Av. San Martín 1420", "contacto": "Rocío"},
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(clientes_service, "crear_cliente", lambda *a, **k: _Fila(cliente_id))
    try:
        estado, resultado, huella = clientes_commands.manejar_cliente_crear(
            sobre, contenido, sesion=sesion, reloj=FixedClock(MOMENTO)
        )
    finally:
        monkeypatch.undo()

    assert estado == "ACEPTADO"
    assert resultado == {"cliente_id": str(cliente_id)}
    assert huella is None


# --- permisos: los exige el handler (SEG-06, `02` §6.3 paso 4) ------------
#
# `sync/api.py` deja asentado que la validación de permisos POR COMANDO es
# responsabilidad del handler resuelto por `app.commands.registro`, porque un
# lote puede traer tipos distintos y no hay un permiso único que declarar en la
# ruta. El catálogo de tipos de comando no modela permisos, así que el handler
# es el punto donde se puede comprobar.


PERMISOS_POR_COMANDO = {
    "CLIENTE_CREAR": "GESTIONAR_CLIENTES",
    "CLIENTE_MODIFICAR": "GESTIONAR_CLIENTES",
    "CLIENTE_CREDITO_MODIFICAR": "GESTIONAR_CREDITO",
    "CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR": "ADMIN_CONFIGURACION",
}


@pytest.mark.parametrize(("tipo", "permiso"), sorted(PERMISOS_POR_COMANDO.items()))
def test_cada_comando_declara_su_permiso_requerido(tipo: str, permiso: str) -> None:
    """D3 separa `GESTIONAR_CLIENTES` de `GESTIONAR_CREDITO`; D4 sube la
    habilitación del consumidor final a `ADMIN_CONFIGURACION` porque escribe la
    configuración de la organización."""
    fuente = inspect.getsource(getattr(clientes_commands, f"manejar_{tipo.lower()}"))
    assert permiso in fuente, f"{tipo} no menciona su permiso {permiso}."


@pytest.mark.parametrize(("tipo", "permiso"), sorted(PERMISOS_POR_COMANDO.items()))
def test_sin_el_permiso_el_comando_se_rechaza_con_403_sin_efectos(
    tipo: str, permiso: str, sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-01: el rechazo ocurre ANTES de tocar la base, así que no hay cliente
    creado ni configuración cambiada."""
    monkeypatch.setattr(
        identidad_service, "listar_permisos_del_usuario", lambda *a, **k: frozenset()
    )
    escritos: list[Any] = []
    for nombre in (
        "crear_cliente",
        "modificar_cliente",
        "modificar_credito_cliente",
        "configurar_consumidor_final",
    ):
        monkeypatch.setattr(clientes_service, nombre, lambda *a, **k: escritos.append(a))

    handler = resolver_handler(tipo, 1).funcion
    with pytest.raises(DomainError) as excepcion:
        handler(
            _sobre(tipo=tipo),
            _validar(tipo, _contenido_valido(tipo)),
            sesion=sesion,
            reloj=FixedClock(MOMENTO),
        )

    assert excepcion.value.codigo == "PERMISO_REQUERIDO"
    assert excepcion.value.status_http == 403
    assert escritos == []


def test_quien_tiene_gestionar_clientes_no_puede_tocar_el_credito(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El escenario de verificación manual 7.1: un rol con
    `GESTIONAR_CLIENTES` pero sin `GESTIONAR_CREDITO` no ve la sección de
    crédito y su escritura responde 403."""
    monkeypatch.setattr(
        identidad_service,
        "listar_permisos_del_usuario",
        lambda *a, **k: frozenset({"GESTIONAR_CLIENTES"}),
    )
    handler = resolver_handler("CLIENTE_CREDITO_MODIFICAR", 1).funcion
    contenido = _validar("CLIENTE_CREDITO_MODIFICAR", {"cliente_id": str(uuid4())})

    with pytest.raises(DomainError) as excepcion:
        handler(
            _sobre(tipo="CLIENTE_CREDITO_MODIFICAR"),
            contenido,
            sesion=sesion,
            reloj=FixedClock(MOMENTO),
        )

    assert excepcion.value.codigo == "PERMISO_REQUERIDO"


def test_quien_no_tiene_gestionar_clientes_no_puede_crear_clientes(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        identidad_service,
        "listar_permisos_del_usuario",
        lambda *a, **k: frozenset({"GESTIONAR_CREDITO"}),
    )
    handler = resolver_handler("CLIENTE_CREAR", 1).funcion

    with pytest.raises(DomainError) as excepcion:
        handler(
            _sobre(tipo="CLIENTE_CREAR"),
            _validar("CLIENTE_CREAR", _contenido_valido("CLIENTE_CREAR")),
            sesion=sesion,
            reloj=FixedClock(MOMENTO),
        )

    assert excepcion.value.codigo == "PERMISO_REQUERIDO"


# --- 3.3, AUD-01: auditoría con valor anterior y nuevo --------------------


def test_el_credito_audita_el_valor_anterior_y_el_nuevo(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AUD-01: cambiar el crédito es un evento que hay que poder reconstruir,
    así que la auditoría lleva el `antes` y el `después` de los tres campos."""
    cliente_id = uuid4()
    anterior = {
        "limite_credito": Decimal("50000.00"),
        "politica_credito": "ADVERTIR",
        "tolerancia_offline_tipo": None,
        "tolerancia_offline_valor": None,
    }
    audits: list[dict[str, Any]] = []

    class _Cliente:
        id = cliente_id
        es_consumidor_final = False

        def __init__(self) -> None:
            for campo, valor in anterior.items():
                setattr(self, campo, valor)

    def _leer_para_actualizar(*args: Any, **kwargs: Any) -> Any:
        return _Cliente()

    def _escribir(*args: Any, **kwargs: Any) -> Any:
        cliente = _Cliente()
        cliente.limite_credito = kwargs.get("limite_credito")
        cliente.politica_credito = kwargs.get("politica_credito")
        return cliente

    def _auditar(*args: Any, **kwargs: Any) -> None:
        audits.append(kwargs)

    monkeypatch.setattr(
        clientes_service.repository, "obtener_cliente_por_id_para_actualizar", _leer_para_actualizar
    )
    monkeypatch.setattr(clientes_service.repository, "actualizar_credito_cliente", _escribir)
    monkeypatch.setattr(identidad_service, "registrar_auditoria", _auditar)

    contenido = _validar(
        "CLIENTE_CREDITO_MODIFICAR",
        {
            "cliente_id": str(cliente_id),
            "limite_credito": "150000.00",
            "politica_credito": "AUTORIZAR",
        },
    )
    clientes_commands.manejar_cliente_credito_modificar(
        _sobre(tipo="CLIENTE_CREDITO_MODIFICAR"),
        contenido,
        sesion=sesion,
        reloj=FixedClock(MOMENTO),
    )

    assert len(audits) == 1
    auditoria = audits[0]
    assert auditoria["antes"] == {
        "limite_credito": "50000.00",
        "politica_credito": "ADVERTIR",
        "tolerancia_offline_tipo": None,
        "tolerancia_offline_valor": None,
    }, (
        "Los importes van como string: `antes`/`despues` se escriben en "
        "columnas `jsonb` y JSON no tiene tipo decimal (INV-03)."
    )
    assert auditoria["despues"] == {
        "limite_credito": "150000.00",
        "politica_credito": "AUTORIZAR",
        "tolerancia_offline_tipo": None,
        "tolerancia_offline_valor": None,
    }


def test_la_auditoria_del_credito_va_con_el_operation_id_del_sobre(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La auditoría tiene que poder correlacionarse con el comando que la
    originó, igual que la genérica que escribe `sync/service.py`."""
    cliente_id = uuid4()
    operation_id = uuid4()
    audits: list[dict[str, Any]] = []

    class _Cliente:
        id = cliente_id
        es_consumidor_final = False
        limite_credito = None
        politica_credito = None
        tolerancia_offline_tipo = None
        tolerancia_offline_valor = None

    monkeypatch.setattr(
        clientes_service.repository,
        "obtener_cliente_por_id_para_actualizar",
        lambda *a, **k: _Cliente(),
    )
    monkeypatch.setattr(
        clientes_service.repository, "actualizar_credito_cliente", lambda *a, **k: _Cliente()
    )
    monkeypatch.setattr(identidad_service, "registrar_auditoria", lambda *a, **k: audits.append(k))

    sobre = _sobre(tipo="CLIENTE_CREDITO_MODIFICAR", operation_id=operation_id)
    contenido = _validar("CLIENTE_CREDITO_MODIFICAR", {"cliente_id": str(cliente_id)})
    clientes_commands.manejar_cliente_credito_modificar(
        sobre, contenido, sesion=sesion, reloj=FixedClock(MOMENTO)
    )

    assert audits[0]["operation_id"] == operation_id
    assert audits[0]["origen"] == "COMANDO"


def test_la_auditoria_del_credito_no_se_registra_si_la_escritura_falla(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-01: si la escritura se revierte, la auditoría se revierte con ella.
    Por eso se audita DESPUÉS de escribir y la transacción es la del bus."""
    cliente_id = uuid4()
    audits: list[dict[str, Any]] = []

    class _Cliente:
        id = cliente_id
        es_consumidor_final = False
        limite_credito = None
        politica_credito = None
        tolerancia_offline_tipo = None
        tolerancia_offline_valor = None

    def _fallar(*args: Any, **kwargs: Any) -> Any:
        raise DomainError("No se pudo escribir el crédito.")

    monkeypatch.setattr(
        clientes_service.repository,
        "obtener_cliente_por_id_para_actualizar",
        lambda *a, **k: _Cliente(),
    )
    monkeypatch.setattr(clientes_service.repository, "actualizar_credito_cliente", _fallar)
    monkeypatch.setattr(identidad_service, "registrar_auditoria", lambda *a, **k: audits.append(k))

    contenido = _validar("CLIENTE_CREDITO_MODIFICAR", {"cliente_id": str(cliente_id)})
    with pytest.raises(DomainError):
        clientes_commands.manejar_cliente_credito_modificar(
            _sobre(tipo="CLIENTE_CREDITO_MODIFICAR"),
            contenido,
            sesion=sesion,
            reloj=FixedClock(MOMENTO),
        )

    assert audits == []


# --- change 13, ajuste A: PUT conserva la lista si el campo no viene -------


def _lista_pasada_por_el_handler(
    sesion: object, monkeypatch: pytest.MonkeyPatch, contenido: dict[str, Any]
) -> object:
    """Corre `CLIENTE_MODIFICAR` y devuelve lo que el handler le pasó al servicio como
    `lista_precio_id`."""
    recibido: dict[str, Any] = {}

    def _modificar(*args: Any, **kwargs: Any) -> _Fila:
        recibido.update(kwargs)
        return _Fila(kwargs["cliente_id"])

    monkeypatch.setattr(clientes_service, "modificar_cliente", _modificar)
    handler = resolver_handler("CLIENTE_MODIFICAR", 1).funcion
    handler(
        _sobre(tipo="CLIENTE_MODIFICAR"),
        _validar("CLIENTE_MODIFICAR", contenido),
        sesion=sesion,
        reloj=FixedClock(MOMENTO),
    )
    return recibido["lista_precio_id"]


def test_modificar_sin_el_campo_lista_la_conserva(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    contenido = _contenido_valido("CLIENTE_MODIFICAR")
    contenido.pop("lista_precio_id", None)

    lista = _lista_pasada_por_el_handler(sesion, monkeypatch, contenido)

    assert lista is clientes_service.CONSERVAR_LISTA


def test_modificar_con_lista_nula_la_quita(sesion: object, monkeypatch: pytest.MonkeyPatch) -> None:
    contenido = {**_contenido_valido("CLIENTE_MODIFICAR"), "lista_precio_id": None}

    lista = _lista_pasada_por_el_handler(sesion, monkeypatch, contenido)

    assert lista is None


def test_modificar_con_un_id_de_lista_la_asigna(
    sesion: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    lista_id = uuid4()
    contenido = {**_contenido_valido("CLIENTE_MODIFICAR"), "lista_precio_id": str(lista_id)}

    lista = _lista_pasada_por_el_handler(sesion, monkeypatch, contenido)

    assert lista == lista_id
