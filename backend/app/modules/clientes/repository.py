"""Acceso a datos de `clientes` (`docs/02-arquitectura.md` §8, `CLAUDE.md` §4).
Mismo contrato no negociable que `proveedores/repository.py` (tarea 7.1 del
change 06) y que `catalogo/repository.py` (tarea 6.1 del change 05): todo
función pública recibe `organizacion_id` como primer parámetro obligatorio y lo
usa para filtrar toda consulta
(`tests/unit/test_repositorios_organizacion_obligatoria.py`).

`guardar_con_traduccion_de_integridad` reusa la lección 6.2 del change 05: el
`flush` ocurre dentro de un `SAVEPOINT` (`begin_nested`) para que un
`IntegrityError` no deje la sesión en `DEACTIVE`, y se traduce por nombre de
índice a un error de dominio con código estable. Los dos índices que se traducen
son los parciales de D1 (`ux_cliente__codigo` y `ux_cliente__documento`): son
ellos, y no este `if`, los que separan dos altas concurrentes con el mismo dato
(INV-01).

El listado pagina por el par `(nombre, id)` y no por `nombre` solo, porque D1
deja el `nombre` SIN unicidad: un cursor de una sola columna puede repetir o
saltar filas cuando dos clientes de la organización comparten nombre.

Ninguna función borra: `cliente` no tiene borrado en ningún sentido (CLI-04,
INV-05), y el usuario de aplicación no tiene `DELETE` sobre la tabla.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.clientes.domain.errores import (
    CodigoDuplicadoError,
    DocumentoDuplicadoError,
)
from app.modules.clientes.models import Cliente

LIMITE_PAGINA_MAXIMO = 100
LIMITE_PAGINA_DEFAULT = 50

_DIGITOS = frozenset("0123456789")
_SEPARADORES = frozenset("- ")


def guardar_con_traduccion_de_integridad(
    organizacion_id: UUID, sesion: Session, mutar: Callable[[], None]
) -> None:
    """Mismo mecanismo que `proveedores.repository.guardar_con_traduccion_de_
    integridad` (lección 6.2 del 05): `mutar` DEBE ejecutar la mutación
    (`sesion.add(...)` o las asignaciones de atributos) DENTRO de este `with`,
    nunca antes de llamarlo."""
    del organizacion_id  # No filtra nada: la mutación ya trae su organización.
    try:
        with sesion.begin_nested():
            mutar()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if "ux_cliente__codigo" in mensaje:
            raise CodigoDuplicadoError(
                "Ya existe un cliente con ese código en esta organización (D1)."
            ) from error
        if "ux_cliente__documento" in mensaje:
            raise DocumentoDuplicadoError(
                "Ya existe un cliente con ese documento en esta organización (D1)."
            ) from error
        raise


# --- alta, lectura y modificación (tarea 2.1) -------------------------------


def crear_cliente(
    organizacion_id: UUID,
    sesion: Session,
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
    lista_precio_id: UUID | None,
    estado_facturacion_default: str | None,
    es_consumidor_final: bool,
    limite_credito: Decimal | None,
    politica_credito: str | None,
    tolerancia_offline_tipo: str | None,
    tolerancia_offline_valor: Decimal | None,
    estado: str,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Cliente:
    """Inserta el cliente ya validado por `clientes/domain/` y con los tres
    campos de crédito tal como llegan (nulo incluido: un nulo significa "hereda
    el de la organización", CRE-03 y CRE-06, `design.md` D8; esta capa no
    resuelve ni copia nada).

    No hay `estado` en la interfaz de negocio: el cliente nace `ACTIVO` (D7) y
    solo `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` nasce marcado. El parámetro
    existe igual porque esta capa no conoce el bus (`03` §10 exige la columna y
    su `CHECK`)."""
    cliente = Cliente(
        id=cliente_id,
        organizacion_id=organizacion_id,
        codigo=codigo,
        nombre=nombre,
        razon_social=razon_social,
        documento_tipo=documento_tipo,
        documento_numero=documento_numero,
        direccion=direccion,
        contacto=contacto,
        telefono=telefono,
        email=email,
        lista_precio_id=lista_precio_id,
        limite_credito=limite_credito,
        politica_credito=politica_credito,
        tolerancia_offline_tipo=tolerancia_offline_tipo,
        tolerancia_offline_valor=tolerancia_offline_valor,
        estado_facturacion_default=estado_facturacion_default,
        es_consumidor_final=es_consumidor_final,
        estado=estado,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(cliente))
    return cliente


def obtener_cliente_por_id(
    organizacion_id: UUID, cliente_id: UUID, sesion: Session
) -> Cliente | None:
    """El cliente de `cliente_id` en `organizacion_id`, o `None`.

    `None` no distingue "no existe" de "es de otra organización", y es
    justamente esa indistinción la que exige INV-21/SEG-07: un recurso ajeno
    responde 404, no 403. La comparación explícita de `organizacion_id` además
    de la consulta filtrada cubre el caso de un `id` que sí existe en la tabla
    pero pertenece a otra organización: el `get` por clave primaria lo
    encontraría y el filtro lo descarta."""
    cliente = sesion.get(Cliente, cliente_id)
    if cliente is None or cliente.organizacion_id != organizacion_id:
        return None
    return cliente


def obtener_cliente_por_id_para_actualizar(
    organizacion_id: UUID, cliente_id: UUID, sesion: Session
) -> Cliente | None:
    """`SELECT ... FOR UPDATE` (mismo criterio que `PROVEEDOR_MODIFICAR`, D14
    del change 06): `CLIENTE_MODIFICAR` y `CLIENTE_CREDITO_MODIFICAR` bloquean
    la fila antes de decidir y escribir, para que una segunda escritura
    concurrente del mismo cliente se serialice en vez de perder la primera."""
    consulta = (
        select(Cliente)
        .where(Cliente.organizacion_id == organizacion_id, Cliente.id == cliente_id)
        .with_for_update()
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_consumidor_final(organizacion_id: UUID, sesion: Session) -> Cliente | None:
    """El cliente marcado como consumidor final de `organizacion_id` (D4), o
    `None` si la organización todavía no lo habilitó. Filtra por organización y
    por la marca: nunca devuelve el consumidor final de otra."""
    consulta = select(Cliente).where(
        Cliente.organizacion_id == organizacion_id,
        Cliente.es_consumidor_final.is_(True),
    )
    return sesion.scalars(consulta).one_or_none()


def actualizar_cliente(
    organizacion_id: UUID,
    sesion: Session,
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
    estado: str,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Cliente | None:
    """Escribe la ficha completa y el estado (D3: la ficha nunca toca los tres
    campos de crédito). Devuelve `None` sin tocar nada si el cliente no existe
    en `organizacion_id`."""
    cliente = obtener_cliente_por_id(organizacion_id, cliente_id, sesion)
    if cliente is None:
        return None

    def _mutar() -> None:
        cliente.nombre = nombre
        cliente.codigo = codigo
        cliente.razon_social = razon_social
        cliente.documento_tipo = documento_tipo
        cliente.documento_numero = documento_numero
        cliente.direccion = direccion
        cliente.contacto = contacto
        cliente.telefono = telefono
        cliente.email = email
        cliente.estado_facturacion_default = estado_facturacion_default
        cliente.estado = estado
        cliente.actualizado_en = momento
        cliente.actualizado_por_id = actualizado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return cliente


def actualizar_credito_cliente(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cliente_id: UUID,
    limite_credito: Decimal | None,
    politica_credito: str | None,
    tolerancia_offline_tipo: str | None,
    tolerancia_offline_valor: Decimal | None,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Cliente | None:
    """Escribe SOLO los tres campos de crédito (D3) y deja la ficha y el estado
    como estaban. Un `None` se guarda como `None`: eso es "volver al
    comportamiento de la organización", no "borrar el dato" (CRE-01, CRE-03)."""
    cliente = obtener_cliente_por_id(organizacion_id, cliente_id, sesion)
    if cliente is None:
        return None

    def _mutar() -> None:
        cliente.limite_credito = limite_credito
        cliente.politica_credito = politica_credito
        cliente.tolerancia_offline_tipo = tolerancia_offline_tipo
        cliente.tolerancia_offline_valor = tolerancia_offline_valor
        cliente.actualizado_en = momento
        cliente.actualizado_por_id = actualizado_por_id

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, _mutar)
    return cliente


# --- listado (D9, `docs/02-arquitectura.md` §11) ----------------------------


def _codificar_cursor(nombre: str, id_: UUID) -> str:
    valor = f"{nombre}|{id_}"
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def _decodificar_cursor(cursor: str) -> tuple[str, UUID]:
    valor = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    nombre, id_ = valor.rsplit("|", 1)
    return nombre, UUID(id_)


def _digitos(texto: str) -> str:
    return "".join(caracter for caracter in texto if caracter in _DIGITOS)


def buscar_clientes_por_codigo(
    organizacion_id: UUID, codigo: str, sesion: Session
) -> list[Cliente]:
    """Clientes de la organización con ese código, sin distinguir mayúsculas ni
    espacios al borde, en cualquier estado (change 10, `design.md` D4)."""
    clave = codigo.strip().lower()
    if not clave:
        return []
    consulta = (
        select(Cliente)
        .where(
            Cliente.organizacion_id == organizacion_id,
            func.lower(func.btrim(Cliente.codigo)) == clave,
        )
        .order_by(Cliente.id)
    )
    return list(sesion.scalars(consulta).all())


def buscar_clientes_por_documento(
    organizacion_id: UUID, documento: str, sesion: Session
) -> list[Cliente]:
    """Clientes de la organización cuyo documento coincide con esos dígitos (el número
    se guarda normalizado a dígitos, CLI-05), en cualquier estado (change 10, D4)."""
    digitos = _digitos(documento)
    if not digitos:
        return []
    consulta = (
        select(Cliente)
        .where(Cliente.organizacion_id == organizacion_id, Cliente.documento_numero == digitos)
        .order_by(Cliente.id)
    )
    return list(sesion.scalars(consulta).all())


def listar_clientes_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    estado: str | None = None,
) -> tuple[list[Cliente], str | None]:
    """Listado paginado por cursor del par `(nombre, id)` (tarea 2.1, D1: el
    nombre no es único, así que el orden necesita el desempate por `id` para que
    cada cliente aparezca exactamente una vez).

    `texto` busca por nombre, razón social, código o número de documento. Un
    texto con al menos un dígito también compara contra el documento
    normalizado a solo dígitos -- ya guardado así, porque `dominio/ficha.py`
    normaliza antes de escribir -- así que `30-111 222` encuentra `30111222`
    (mismo criterio que `listar_proveedores_paginado`, contrato-api.md P5).

    `estado` filtra por la columna exacta; el catálogo cerrado lo valida
    `dominio/estado.py` y lo repite el `CHECK` de la base."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)

    consulta = select(Cliente).where(Cliente.organizacion_id == organizacion_id)
    if cursor is not None:
        nombre_cursor, id_cursor = _decodificar_cursor(cursor)
        consulta = consulta.where(tuple_(Cliente.nombre, Cliente.id) > (nombre_cursor, id_cursor))
    if texto is not None and texto != "":
        patron_texto = f"%{texto}%"
        digitos = _digitos(texto)
        # Los dígitos normalizados entran EN EL MISMO grupo OR que el resto, no
        # en un `.where()` aparte. Encadenar dos `.where()` las une con AND, y
        # con AND la búsqueda no encuentra nada: para `30-111 222` el primer
        # grupo exige que alguna columna contenga literalmente `30-111 222`, y
        # como el documento se guarda normalizado a `30111222` no hay coincidencia
        # que el segundo `where` pueda rescatar. Mismo criterio que
        # `proveedores/repository.py`, que mete los dos patrones en un solo
        # `or_`.
        condiciones = [
            Cliente.nombre.ilike(patron_texto),
            Cliente.razon_social.ilike(patron_texto),
            Cliente.codigo.ilike(patron_texto),
            Cliente.documento_numero.ilike(patron_texto),
        ]
        if digitos:
            condiciones.append(Cliente.documento_numero.ilike(f"%{digitos}%"))
        consulta = consulta.where(or_(*condiciones))
    if estado is not None:
        consulta = consulta.where(Cliente.estado == estado)
    consulta = consulta.order_by(Cliente.nombre, Cliente.id).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        ultima = pagina[-1]
        cursor_siguiente: str | None = _codificar_cursor(ultima.nombre, ultima.id)
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Sin excepción (mismo criterio que `catalogo.repository.FUNCIONES_SIN_
ORGANIZACION_ID` y `proveedores.repository.FUNCIONES_SIN_ORGANIZACION_ID`):
`clientes` no tiene ningún catálogo global propio -- toda función pública
recibe `organizacion_id` primero."""
