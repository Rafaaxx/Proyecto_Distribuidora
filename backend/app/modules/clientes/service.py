"""Interfaz pública de `clientes` (`CLAUDE.md` §4: un módulo usa a otro solo a
través de su `service.py`).

Expone el alta, la modificación de ficha, la modificación de crédito y las
lecturas (tarea 2.2), más la habilitación del consumidor final, que es la única
función que escribe fuera de este módulo (D4, tarea 2.3): llama al setter de
`identidad/service.py` en la misma sesión para que el cliente y la
configuración de la organización queden en la misma transacción.

Sin `commit`: la transacción la gestiona el bus de comandos
(`clientes/commands.py`, grupo 3) o quien llama en pruebas (`CLAUDE.md` §4).

Todas las funciones reciben `organizacion_id` como primer parámetro y lo usan
para filtrar, y ninguna devuelve o acepta un lote: la sincronización del change
10 las invoca fila por fila (`design.md` D9, `docs/02-arquitectura.md` §8).

Toda la lógica de validación vive en `clientes/domain/`; acá solo se orquesta
el orden de las llamadas: leer con bloqueo, validar, escribir. Este módulo no
declara catálogos propios ni lanza errores propios -- los errores que se dejan
propagar son los de `domain/errores.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.clientes import repository
from app.modules.clientes.domain.credito import (
    limite_de_consumidor_final,
    validar_credito_de_consumidor_final,
    validar_limite_credito,
    validar_politica_credito,
    validar_tolerancia_offline,
)
from app.modules.clientes.domain.errores import (
    ConfiguracionDeOrganizacionAusenteError,
    ConsumidorFinalYaHabilitadoError,
    RecursoNoEncontradoError,
)
from app.modules.clientes.domain.estado import (
    validar_estado,
    validar_estado_facturacion_default,
    validar_transicion,
)
from app.modules.clientes.domain.ficha import (
    normalizar_codigo,
    normalizar_contacto,
    normalizar_direccion,
    normalizar_documento,
    normalizar_nombre,
)
from app.modules.clientes.models import Cliente
from app.modules.identidad import service as identidad_service
from app.modules.precios import service as precios_service


class _Conservar:
    """Tipo del marcador `CONSERVAR_LISTA`: "el campo no vino", distinto de `None` (quitar)."""


CONSERVAR_LISTA = _Conservar()

# Ficha genérica del cliente "consumidor final" (CLI-03, `design.md` D4).
# El comando de habilitación no admite campos de ficha, pero `direccion` y
# `contacto` son `NOT NULL` (`03` §10, CLI-01), así que el servicio aporta
# valores neutros y fijos en vez de inventar una carga. No son datos de negocio
# que alguien pueda consultar como texto libre: el nombre sí lo elige quien
# ejecuta el comando.
_DIRECCION_CONSUMIDOR_FINAL = "Sin domicilio"
_CONTACTO_CONSUMIDOR_FINAL = "Consumidor final"


def _importe_para_auditoria(valor: Decimal | None) -> str | None:
    """Un importe de `auditoria.antes`/`despues` viaja como texto, no como `Decimal`.

    `antes` y `despues` son columnas `jsonb` (`03` §4, AUD-02) y JSON no tiene
    tipo decimal: un `Decimal` crudo no lo serializa el driver —el INSERT falla
    con `TypeError` al bindar el parámetro—, y degradado a número volvería del
    otro lado como `float`, que es justo lo que INV-03 prohíbe. Los importes
    viajan como string en JSON, igual que en la API (`CLAUDE.md` §4), con los
    dos decimales que les dio la validación del dominio (D6).

    `None` sigue siendo `None`: un campo en nulo es un dato del antes y del
    después, no una cadena vacía.
    """
    return None if valor is None else str(valor)


# --- verificador de uso de listas de precios (change 13, D11, patrón de ADR-023) --------


def _lista_asignada_a_cliente_no_inactivo(
    organizacion_id: UUID, lista_id: UUID, sesion: Session
) -> bool:
    return repository.lista_asignada_a_cliente_no_inactivo(organizacion_id, lista_id, sesion)


precios_service.registrar_verificador_uso_de_lista(
    "clientes", _lista_asignada_a_cliente_no_inactivo
)


# --- alta (D7: nace `ACTIVO`; D3: sin campos de crédito) -------------------


def crear_cliente(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    codigo: str | None,
    razon_social: str | None,
    documento_tipo: str | None,
    documento_numero: str | None,
    direccion: str,
    contacto: str,
    telefono: str | None,
    email: str | None,
    estado_facturacion_default: str | None,
    actor_id: UUID | None,
    lista_precio_id: UUID | None = None,
) -> Cliente:
    """`CLIENTE_CREAR`.

    Los tres campos de crédito no están entre los parámetros y salen en `None`:
    el crédito se modifica con otro comando, bajo otro permiso (D3, CRE-03), y
    `None` significa "hereda el de la organización", no "cero" (D8). El estado
    tampoco está: el cliente nace `ACTIVO` (D7) y la máquina de estados corre
    desde la primera modificación.

    El estado `ACTIVO` se pasa al repositorio porque la columna es `NOT NULL` y
    la interfaz de negocio de la tabla lo exige (`03` §10); acá no es elegible.

    `lista_precio_id` (opcional, `None` = la predeterminada de la organización, PRC-20) se
    valida por `precios/service.py` (change 13, D11): 404 si no existe en la organización,
    `LISTA_INACTIVA` si está inactiva.
    """
    documento = normalizar_documento(documento_tipo, documento_numero)
    estado_facturacion = validar_estado_facturacion_default(estado_facturacion_default)
    if lista_precio_id is not None:
        precios_service.validar_lista_asignable(organizacion_id, sesion, lista_id=lista_precio_id)
    return repository.crear_cliente(
        organizacion_id,
        sesion,
        cliente_id=nuevo_id(),
        nombre=normalizar_nombre(nombre),
        codigo=normalizar_codigo(codigo),
        razon_social=razon_social,
        documento_tipo=None if documento is None else documento.tipo,
        documento_numero=None if documento is None else documento.numero,
        direccion=normalizar_direccion(direccion),
        contacto=normalizar_contacto(contacto),
        telefono=telefono,
        email=email,
        lista_precio_id=lista_precio_id,
        estado_facturacion_default=estado_facturacion,
        es_consumidor_final=False,
        limite_credito=None,
        politica_credito=None,
        tolerancia_offline_tipo=None,
        tolerancia_offline_valor=None,
        estado="ACTIVO",
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


# --- modificación de ficha (D7, máquina de estados de `01` §18) -----------


def modificar_cliente(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cliente_id: UUID,
    nombre: str,
    codigo: str | None,
    razon_social: str | None,
    documento_tipo: str | None,
    documento_numero: str | None,
    direccion: str,
    contacto: str,
    telefono: str | None,
    email: str | None,
    estado_facturacion_default: str | None,
    lista_precio_id: UUID | None | _Conservar,
    estado: str,
    actor_id: UUID | None,
    tiene_operaciones: bool = False,
    verificar_operaciones: Callable[[], bool] | None = None,
) -> Cliente:
    """`CLIENTE_MODIFICAR`.

    Orden (D14 del change 06, mismo criterio que `PROVEEDOR_MODIFICAR`): leer
    la fila con `FOR UPDATE` antes de decidir y de escribir, para que dos
    modificaciones concurrentes del mismo cliente se serialicen en vez de que
    la segunda pise a la primera. Un `None` de la lectura es un cliente
    inexistente en esta organización, y también puede ser un cliente de otra
    (INV-21): se responde igual.

    CLI-06 (ADR-030) se decide con dos entradas. `tiene_operaciones` es un dato
    que ya sabe quien llama. `verificar_operaciones` es una consulta que este
    servicio hace DESPUÉS de bloquear la fila del cliente y SOLO si el cliente
    está `INACTIVO` (es la única salida que CLI-06 gobierna): desde el change 08
    el handler pasa `cuentas_corrientes_service.cuenta_tiene_movimientos`, así una
    reactivación concurrente con un saldo inicial se serializa (`design.md` D6 y
    D8 del change 08). Es un callable y no un dato porque la fila tiene que estar
    tomada cuando se pregunta, y el bloqueo ocurre acá adentro.

    La escritura no incluye los tres campos de crédito (D3): la ficha y el
    crédito son dos comandos con dos permisos distintos.

    `lista_precio_id` reemplaza la lista asignada: un id la asigna, `None` la quita (el
    cliente vuelve a la predeterminada de la organización, PRC-20) y `CONSERVAR_LISTA` (el
    campo no vino) la deja como estaba. La lista resultante se valida por `precios/service.py`
    cuando es distinta de la que ya tenía o cuando el cliente queda activo, de modo que un
    cliente activo nunca tiene una lista inactiva (D11) sin obligar a cambiar una lista ya
    asignada para corregir otro dato de un cliente inactivo.
    """
    cliente = repository.obtener_cliente_por_id_para_actualizar(organizacion_id, cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe en esta organización.")

    documento = normalizar_documento(documento_tipo, documento_numero)
    estado_facturacion = validar_estado_facturacion_default(estado_facturacion_default)
    operaciones = tiene_operaciones or (
        cliente.estado == "INACTIVO"
        and verificar_operaciones is not None
        and verificar_operaciones()
    )
    estado_validado = validar_transicion(
        cliente.estado,
        estado,
        tiene_operaciones=operaciones,
        es_consumidor_final=cliente.es_consumidor_final,
    )
    lista_resultante = (
        cliente.lista_precio_id if isinstance(lista_precio_id, _Conservar) else lista_precio_id
    )
    if lista_resultante is not None and (
        lista_resultante != cliente.lista_precio_id or estado_validado != "INACTIVO"
    ):
        precios_service.validar_lista_asignable(organizacion_id, sesion, lista_id=lista_resultante)

    actualizado = repository.actualizar_cliente(
        organizacion_id,
        sesion,
        cliente_id=cliente_id,
        nombre=normalizar_nombre(nombre),
        codigo=normalizar_codigo(codigo),
        razon_social=razon_social,
        documento_tipo=None if documento is None else documento.tipo,
        documento_numero=None if documento is None else documento.numero,
        direccion=normalizar_direccion(direccion),
        contacto=normalizar_contacto(contacto),
        telefono=telefono,
        email=email,
        estado_facturacion_default=estado_facturacion,
        lista_precio_id=lista_resultante,
        estado=estado_validado,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    assert actualizado is not None
    return actualizado


# --- modificación de crédito (CRE-01, CRE-03, CRE-06, D3, D8) -------------


def modificar_credito_cliente(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    cliente_id: UUID,
    limite_credito: Decimal | None,
    politica_credito: str | None,
    tolerancia_offline_tipo: str | None,
    tolerancia_offline_valor: Decimal | None,
    actor_id: UUID | None,
    operation_id: UUID | None = None,
    dispositivo_id: UUID | None = None,
) -> Cliente:
    """`CLIENTE_CREDITO_MODIFICAR`.

    Los tres campos se validan y se guardan TAL COMO LLEGAN (D8): un `None` se
    guarda como `None` y significa "hereda el de la organización" (CRE-03,
    CRE-06). La herencia NO se resuelve acá ni se copia el valor de la
    organización: se aplica cuando se evalúa el crédito, en el change 18b.

    La validación del consumidor final va PRIMERO y con los valores sin
    normalizar, porque `CLI-03` no depende de cómo se haya escrito el dato: el
    consumidor final no tiene crédito propio, se escriba como se escriba.

    La auditoría con valor anterior y nuevo (AUD-01) se escribe ACÁ y no en el
    handler por una razón concreta: la fila ya está leída con `FOR UPDATE`, así
    que el `antes` que se registra es el valor anterior real. Releerlo desde el
    handler dejaría una ventana en la que otra transacción could've cambiado el
    crédito, y la auditoría registraría un `antes` que nunca llegó a existir.
    Va DESPUÉS de la escritura y sin `commit`, así que si el bus revierte la
    transacción se revierte también la auditoría (INV-01). `operation_id` y
    `dispositivo_id` correlacionan la fila con el comando que la originó, igual
    que la auditoría genérica de `sync/service.py`.
    """
    cliente = repository.obtener_cliente_por_id_para_actualizar(organizacion_id, cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe en esta organización.")

    validar_credito_de_consumidor_final(
        cliente.es_consumidor_final,
        limite_credito,
        politica_credito,
        tolerancia_offline_tipo,
        tolerancia_offline_valor,
    )

    limite_validado = validar_limite_credito(limite_credito)
    politica_validada = validar_politica_credito(politica_credito)
    tipo_validado, valor_validado = validar_tolerancia_offline(
        tolerancia_offline_tipo, tolerancia_offline_valor
    )

    antes: dict[str, object] = {
        "limite_credito": _importe_para_auditoria(cliente.limite_credito),
        "politica_credito": cliente.politica_credito,
        "tolerancia_offline_tipo": cliente.tolerancia_offline_tipo,
        "tolerancia_offline_valor": _importe_para_auditoria(cliente.tolerancia_offline_valor),
    }
    momento = reloj.now()

    actualizado = repository.actualizar_credito_cliente(
        organizacion_id,
        sesion,
        cliente_id=cliente_id,
        limite_credito=limite_validado,
        politica_credito=politica_validada,
        tolerancia_offline_tipo=tipo_validado,
        tolerancia_offline_valor=valor_validado,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    assert actualizado is not None

    identidad_service.registrar_auditoria(
        organizacion_id,
        sesion,
        reloj,
        accion="CLIENTE_CREDITO_MODIFICAR",
        entidad="cliente",
        entidad_id=cliente_id,
        ocurrido_en=momento,
        usuario_id=actor_id,
        dispositivo_id=dispositivo_id,
        antes=antes,
        despues={
            "limite_credito": _importe_para_auditoria(limite_validado),
            "politica_credito": politica_validada,
            "tolerancia_offline_tipo": tipo_validado,
            "tolerancia_offline_valor": _importe_para_auditoria(valor_validado),
        },
        operation_id=operation_id,
        origen="COMANDO",
    )
    return actualizado


# --- lecturas (tarea 2.2) --------------------------------------------------


def obtener_cliente_por_id(
    organizacion_id: UUID, cliente_id: UUID, sesion: Session
) -> Cliente | None:
    return repository.obtener_cliente_por_id(organizacion_id, cliente_id, sesion)


def obtener_consumidor_final(organizacion_id: UUID, sesion: Session) -> Cliente | None:
    return repository.obtener_consumidor_final(organizacion_id, sesion)


def buscar_clientes_por_codigo(
    organizacion_id: UUID, codigo: str, sesion: Session
) -> list[Cliente]:
    """Lectura pública para la importación (change 10, `design.md` D4): clientes de la
    organización con ese código, sin distinguir mayúsculas ni espacios al borde, en
    cualquier estado."""
    return repository.buscar_clientes_por_codigo(organizacion_id, codigo, sesion)


def buscar_clientes_por_documento(
    organizacion_id: UUID, documento: str, sesion: Session
) -> list[Cliente]:
    """Lectura pública para la importación (change 10, `design.md` D4): clientes de la
    organización con ese documento (se compara en dígitos, CLI-05), en cualquier
    estado."""
    return repository.buscar_clientes_por_documento(organizacion_id, documento, sesion)


def listar_clientes(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    estado: str | None = None,
) -> tuple[list[Cliente], str | None]:
    """`estado` es un FILTRO, no el estado de una fila, y llega de un query
    string: se valida contra el catálogo cerrado con `validar_estado`, que
    lanza `ESTADO_INVALIDO` (422) si el valor no existe.

    Antes esto era un `assert`, y sobre una ruta HTTP eso es un 500: un
    `?estado=BORRADO` no es una petición válida que hay que reportar, es
    entrada no confiable de la que hay que desconfiar. El `assert` solo vale
    para invariantes internas, no para datos que llegan de afuera (CLI-02)."""
    if estado is not None:
        validar_estado(estado)
    return repository.listar_clientes_paginado(
        organizacion_id, sesion, limite=limite, cursor=cursor, texto=texto, estado=estado
    )


# --- consumidor final (D4, ADR-029, tarea 2.3) ----------------------------


def configurar_consumidor_final(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    actor_id: UUID | None,
) -> Cliente:
    """`CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` (D4, ADR-029).

    Hace las dos escrituras en la MISMA sesión, y por lo tanto en la misma
    transacción: el cliente marcado y la configuración que lo apunta. No hay
    estado intermedio en el que exista el cliente sin la referencia ni la
    referencia sin el cliente. La transacción la cierra el bus; si algo falla,
    las dos escrituras se revierten juntas (INV-01).

    El permiso es `ADMIN_CONFIGURACION` y no `GESTIONAR_CLIENTES` porque el
    comando escribe la configuración de la organización (`01` §4). Lo exige el
    handler de `clientes/commands.py`, que es donde `02` §6.3 paso 4 ubica la
    validación de permisos por comando; el ratchet de
    `test_ratchet_permiso_por_ruta.py` (tarea 4.2) lo sigue teniendo que
    verificar cuando la API aparezca en el grupo 4.

    El cliente se busca primero para rechazar el segundo intento con
    `CONSUMIDOR_FINAL_YA_HABILITADO` ANTES de crear nada (INV-01): el
    `cliente_consumidor_final_id` de la configuración también serviría para
    saberlo, pero el cliente es la fuente que la base garantiza única.

    El nombre se normaliza ANTES de esa lectura, para que un contenido
    malformado se rechace sin tocar la base: la spec del escenario "Nombre
    vacío" tiene como GIVEN una organización sin consumidor final, y una
    validación que leyera antes de validar no cumpliría ese GIVEN ni dejaría
    claro que nada se consultó.
    """
    nombre_normalizado = normalizar_nombre(nombre)

    ya_habilitado = repository.obtener_consumidor_final(organizacion_id, sesion)
    if ya_habilitado is not None:
        raise ConsumidorFinalYaHabilitadoError(
            "La organización ya tiene un cliente consumidor final habilitado (D4, CLI-03)."
        )

    cliente = repository.crear_cliente(
        organizacion_id,
        sesion,
        cliente_id=nuevo_id(),
        nombre=nombre_normalizado,
        codigo=None,
        razon_social=None,
        documento_tipo=None,
        documento_numero=None,
        direccion=_DIRECCION_CONSUMIDOR_FINAL,
        contacto=_CONTACTO_CONSUMIDOR_FINAL,
        telefono=None,
        email=None,
        lista_precio_id=None,
        estado_facturacion_default=None,
        es_consumidor_final=True,
        limite_credito=limite_de_consumidor_final(),
        politica_credito=None,
        tolerancia_offline_tipo=None,
        tolerancia_offline_valor=None,
        estado="ACTIVO",
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    configuracion = identidad_service.configurar_consumidor_final(
        organizacion_id,
        sesion,
        reloj,
        cliente_consumidor_final_id=cliente.id,
        actor_id=actor_id,
    )
    if configuracion is None:
        # El setter devuelve `None` cuando la organización no tiene fila de
        # configuración, y lo hace sin tocar nada. Sin este chequeo el bus
        # confirmaría un cliente marcado como consumidor final sin el par de
        # configuración detrás: el estado intermedio que D4 prohíbe, que no se
        # detectaría hasta el bootstrap del change 21 (SYN-11). Lanzando acá, la
        # reversión del bus se lleva también el cliente recién creado.
        raise ConfiguracionDeOrganizacionAusenteError(
            "La organización no tiene configuración: no hay fila a la que apuntar "
            "el cliente consumidor final (D4, ADR-029)."
        )
    return cliente
