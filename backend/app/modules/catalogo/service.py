"""Interfaz pública de `catalogo` (`CLAUDE.md` §4: un módulo usa a otro
solo a través de su `service.py`).

Expone alta/modificación de categorías y marcas, alta/modificación de
productos y presentaciones, cambio de la presentación de referencia, y las
lecturas que otros módulos necesitan (tarea 7.7). Sin `commit`: la
transacción la gestiona el bus de comandos (`catalogo/commands.py`, grupo
8) o quien llame en pruebas (`CLAUDE.md` §4).

D2 (`design.md`, aprobado 2026-09-22): puerto de "verificadores de uso"
para CAT-04/INV-18. `catalogo` no depende de ningún módulo que registre
operaciones (`02` §5.3: "catalogo sin dependencias de negocio"); en su
lugar, expone `registrar_verificador_uso` para que esos módulos (06, 11,
18a) se anoten al arrancar, igual que `app/commands/registro.py` con los
handlers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.catalogo import repository
from app.modules.catalogo.domain.errores import (
    AlicuotaInactivaError,
    CategoriaConProductosActivosError,
    CategoriaInactivaError,
    MarcaInactivaError,
    ProveedorInactivoError,
    RecursoNoEncontradoError,
)
from app.modules.catalogo.domain.nombres import (
    normalizar_codigo,
    normalizar_nombre,
    normalizar_nombres_de_presentaciones,
    normalizar_unidad_base,
)
from app.modules.catalogo.domain.presentaciones import (
    DatosPresentacion as DatosPresentacion,  # re-exportado: lo usa `importacion` (change 10)
)
from app.modules.catalogo.domain.presentaciones import (
    validar_alta_presentaciones,
    validar_modificacion_presentacion,
    validar_nueva_referencia,
    validar_unidades_base,
)
from app.modules.catalogo.models import Categoria, Marca, Presentacion, Producto
from app.modules.configuracion import service as configuracion_service

# --- D2: puerto de verificadores de uso (CAT-04, INV-18) -------------------

VerificadorUso = Callable[[UUID, UUID, Session], bool]
"""`funcion(organizacion_id, presentacion_id, sesion) -> bool` (`design.md`
D2-A): `True` si el módulo que lo registró considera "usada" esa
presentación en esa organización."""

# Puebla el arranque de la aplicación importando los módulos de negocio que
# llaman a `registrar_verificador_uso` (mismo patrón que
# `app/commands/registro.py::_REGISTRO`). Las pruebas unitarias aíslan este
# diccionario con `monkeypatch` para no depender del orden de importación
# ni filtrar registros entre pruebas.
_REGISTRO_VERIFICADORES: dict[str, VerificadorUso] = {}


def registrar_verificador_uso(nombre: str, funcion: VerificadorUso) -> None:
    """Registra `funcion` bajo `nombre` (nombre del módulo dueño, por
    ejemplo `"proveedores"` o `"ventas"`, para que un error de
    programación que registre dos veces el mismo nombre se detecte)."""
    _REGISTRO_VERIFICADORES[nombre] = funcion


def presentacion_fue_usada(organizacion_id: UUID, presentacion_id: UUID, sesion: Session) -> bool:
    """CAT-04/INV-18: `True` si ALGÚN verificador registrado responde
    `True`. Sin verificadores (este change, en producción, la lista está
    vacía) ninguna presentación está usada."""
    return any(
        funcion(organizacion_id, presentacion_id, sesion)
        for funcion in _REGISTRO_VERIFICADORES.values()
    )


# --- D9/ADR-025: puerto de consulta de proveedor ----------------------------


@dataclass(frozen=True, slots=True)
class EstadoProveedor:
    """Resultado de la consulta que `proveedores` registra en este puerto
    (`design.md` D9-A, ADR-025). Incluye `nombre` (Open Question resuelta
    opción B, 2026-09-23) para que `GET /productos/{id}` muestre el nombre
    real de un proveedor inactivo sin que `catalogo` lea la tabla
    `proveedor` ni se amplíe el permiso de `/proveedores/opciones`
    (`design.md` D8, D13)."""

    activo: bool
    nombre: str


ConsultaProveedor = Callable[[UUID, UUID, Session], "EstadoProveedor | None"]
"""`funcion(organizacion_id, proveedor_id, sesion) -> EstadoProveedor | None`
(`design.md` D9-A): `None` si el proveedor no existe en la organización."""

_CONSULTA_PROVEEDOR: ConsultaProveedor | None = None


def registrar_consulta_proveedor(funcion: ConsultaProveedor) -> None:
    """`proveedores` la registra al importar su `service.py` (tarea 8.2),
    igual que `registrar_verificador_uso` (ADR-023). Sin ciclo: `catalogo`
    nunca importa `proveedores` (`02` §5.3)."""
    global _CONSULTA_PROVEEDOR
    _CONSULTA_PROVEEDOR = funcion


def consultar_proveedor(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> EstadoProveedor | None:
    """Lectura pública (D13: la usa también la consulta de detalle de
    producto para resolver `proveedor_nombre`). Falla cerrado (D9-A) si no
    hay consulta registrada -- un error de configuración nunca deja pasar
    un proveedor sin validar."""
    if _CONSULTA_PROVEEDOR is None:
        raise RuntimeError(
            "No hay consulta de proveedor registrada (ADR-025): catalogo falla cerrado."
        )
    return _CONSULTA_PROVEEDOR(organizacion_id, proveedor_id, sesion)


def _resolver_proveedor(
    organizacion_id: UUID,
    proveedor_id: UUID,
    sesion: Session,
    *,
    proveedor_actual_id: UUID | None,
) -> None:
    """D9-A: existencia -> 404; inactivo y distinto del proveedor actual
    del producto -> `PROVEEDOR_INACTIVO`; conservar el proveedor actual
    aunque esté inactivo se acepta (D5)."""
    estado = consultar_proveedor(organizacion_id, proveedor_id, sesion)
    if estado is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )
    if not estado.activo and proveedor_id != proveedor_actual_id:
        raise ProveedorInactivoError(f"El proveedor {proveedor_id} está inactivo.")


def existen_productos_activos_de_proveedor(
    organizacion_id: UUID, proveedor_id: UUID, sesion: Session
) -> bool:
    """Lectura pública (D5, ADR-026): usada por `proveedores/service.py`
    para rechazar la desactivación de un proveedor con productos
    activos."""
    return repository.existen_productos_activos_de_proveedor(organizacion_id, proveedor_id, sesion)


def obtener_producto_para_compartir(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> Producto | None:
    """Lectura pública `FOR SHARE` (D14): usada por `COSTO_INFORMAR` para
    leer y bloquear el producto sin impedir otras lecturas concurrentes."""
    return repository.obtener_producto_por_id_para_compartir(organizacion_id, producto_id, sesion)


# --- categoria (CAT-01, CAT-05, D11) ---------------------------------------


def crear_categoria(
    organizacion_id: UUID, sesion: Session, reloj: Clock, *, nombre: str, actor_id: UUID | None
) -> Categoria:
    nombre_normalizado = normalizar_nombre(nombre)
    return repository.crear_categoria(
        organizacion_id,
        sesion,
        categoria_id=nuevo_id(),
        nombre=nombre_normalizado,
        activo=True,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


def modificar_categoria(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    categoria_id: UUID,
    nombre: str,
    activo: bool,
    actor_id: UUID | None,
) -> Categoria:
    """D11 (aprobado 2026-09-22): rechaza `CATEGORIA_CON_PRODUCTOS_ACTIVOS`
    si se intenta desactivar (transición `True -> False`) una categoría con
    productos activos. Reactivar, o mantener el mismo estado, no dispara la
    verificación."""
    categoria = repository.obtener_categoria_por_id(organizacion_id, categoria_id, sesion)
    if categoria is None:
        raise RecursoNoEncontradoError(
            f"La categoría {categoria_id} no existe en esta organización."
        )

    nombre_normalizado = normalizar_nombre(nombre)
    if (
        categoria.activo
        and not activo
        and repository.existen_productos_activos_en_categoria(organizacion_id, categoria_id, sesion)
    ):
        raise CategoriaConProductosActivosError(
            "No se puede desactivar una categoría con productos activos (CAT-01, CAT-05)."
        )

    actualizada = repository.actualizar_categoria(
        organizacion_id,
        sesion,
        categoria_id=categoria_id,
        nombre=nombre_normalizado,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    assert actualizada is not None  # ya se verificó existencia arriba.
    return actualizada


def listar_categorias(
    organizacion_id: UUID, sesion: Session, *, solo_activas: bool = False
) -> list[Categoria]:
    return repository.listar_categorias(organizacion_id, sesion, solo_activas=solo_activas)


def obtener_categoria(
    organizacion_id: UUID, categoria_id: UUID, sesion: Session
) -> Categoria | None:
    return repository.obtener_categoria_por_id(organizacion_id, categoria_id, sesion)


def buscar_categorias_por_nombre(
    organizacion_id: UUID, nombre: str, sesion: Session
) -> list[Categoria]:
    """Lectura pública para la importación (change 10, `design.md` D4): categorías de
    la organización con ese nombre, sin distinguir mayúsculas ni espacios al borde,
    activas o no (el alta rechaza después una inactiva con `CATEGORIA_INACTIVA`)."""
    return repository.buscar_categorias_por_nombre(organizacion_id, nombre, sesion)


# --- marca (CAT-01, CAT-05) -------------------------------------------------


def crear_marca(
    organizacion_id: UUID, sesion: Session, reloj: Clock, *, nombre: str, actor_id: UUID | None
) -> Marca:
    nombre_normalizado = normalizar_nombre(nombre)
    return repository.crear_marca(
        organizacion_id,
        sesion,
        marca_id=nuevo_id(),
        nombre=nombre_normalizado,
        activo=True,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


def modificar_marca(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    marca_id: UUID,
    nombre: str,
    activo: bool,
    actor_id: UUID | None,
) -> Marca:
    """Las marcas, opcionales, se desactivan libremente aun con productos
    (`design.md` D11): sin la verificación que sí aplica a categoría."""
    marca = repository.obtener_marca_por_id(organizacion_id, marca_id, sesion)
    if marca is None:
        raise RecursoNoEncontradoError(f"La marca {marca_id} no existe en esta organización.")

    nombre_normalizado = normalizar_nombre(nombre)
    actualizada = repository.actualizar_marca(
        organizacion_id,
        sesion,
        marca_id=marca_id,
        nombre=nombre_normalizado,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    assert actualizada is not None
    return actualizada


def listar_marcas(
    organizacion_id: UUID, sesion: Session, *, solo_activas: bool = False
) -> list[Marca]:
    return repository.listar_marcas(organizacion_id, sesion, solo_activas=solo_activas)


def buscar_marcas_por_nombre(organizacion_id: UUID, nombre: str, sesion: Session) -> list[Marca]:
    """Lectura pública para la importación (change 10, `design.md` D4); mismos criterios
    que `buscar_categorias_por_nombre`."""
    return repository.buscar_marcas_por_nombre(organizacion_id, nombre, sesion)


def obtener_marca(organizacion_id: UUID, marca_id: UUID, sesion: Session) -> Marca | None:
    return repository.obtener_marca_por_id(organizacion_id, marca_id, sesion)


# --- resolución de referencias del alta de producto (CAT-01, CAT-05) ------


def _resolver_categoria_activa(organizacion_id: UUID, categoria_id: UUID, sesion: Session) -> None:
    categoria = repository.obtener_categoria_por_id(organizacion_id, categoria_id, sesion)
    if categoria is None:
        raise RecursoNoEncontradoError(
            f"La categoría {categoria_id} no existe en esta organización."
        )
    if not categoria.activo:
        raise CategoriaInactivaError(f"La categoría {categoria_id} está inactiva (CAT-05).")


def _resolver_marca_activa(organizacion_id: UUID, marca_id: UUID | None, sesion: Session) -> None:
    if marca_id is None:
        return
    marca = repository.obtener_marca_por_id(organizacion_id, marca_id, sesion)
    if marca is None:
        raise RecursoNoEncontradoError(f"La marca {marca_id} no existe en esta organización.")
    if not marca.activo:
        raise MarcaInactivaError(f"La marca {marca_id} está inactiva (CAT-05).")


def _resolver_alicuota_activa(organizacion_id: UUID, alicuota_id: UUID, sesion: Session) -> None:
    alicuota = configuracion_service.obtener_alicuota_por_id(organizacion_id, alicuota_id, sesion)
    if alicuota is None:
        raise RecursoNoEncontradoError(f"La alícuota {alicuota_id} no existe en esta organización.")
    if not alicuota.activo:
        raise AlicuotaInactivaError(f"La alícuota {alicuota_id} está inactiva (CAT-05).")


# --- producto (CAT-01 a CAT-06, INV-01) ------------------------------------


def crear_producto(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    codigo: str,
    nombre: str,
    categoria_id: UUID,
    marca_id: UUID | None,
    proveedor_id: UUID,
    unidad_base: str,
    alicuota_id: UUID,
    presentaciones: list[DatosPresentacion],
    actor_id: UUID | None,
) -> tuple[Producto, list[Presentacion]]:
    """`PRODUCTO_CREAR` (spec productos-y-presentaciones): valida todo
    ANTES de escribir (código, referencias, presentaciones, proveedor) y
    escribe el producto y sus presentaciones dentro de la misma transacción
    -- si algo fallara a mitad de camino, el handler que llama a esta
    función se revierte entero (INV-01), porque quien confirma la
    transacción es el bus, no esta función."""
    codigo_normalizado = normalizar_codigo(codigo)
    nombre_normalizado = normalizar_nombre(nombre)
    unidad_base_normalizada = normalizar_unidad_base(unidad_base)
    presentaciones = normalizar_nombres_de_presentaciones(presentaciones)
    validar_alta_presentaciones(presentaciones)

    _resolver_categoria_activa(organizacion_id, categoria_id, sesion)
    _resolver_marca_activa(organizacion_id, marca_id, sesion)
    _resolver_alicuota_activa(organizacion_id, alicuota_id, sesion)
    _resolver_proveedor(organizacion_id, proveedor_id, sesion, proveedor_actual_id=None)

    momento = reloj.now()
    producto = repository.crear_producto(
        organizacion_id,
        sesion,
        producto_id=nuevo_id(),
        codigo=codigo_normalizado,
        nombre=nombre_normalizado,
        categoria_id=categoria_id,
        marca_id=marca_id,
        proveedor_id=proveedor_id,
        unidad_base=unidad_base_normalizada,
        alicuota_id=alicuota_id,
        activo=True,
        momento=momento,
        actualizado_por_id=actor_id,
    )

    filas_presentacion = [
        repository.crear_presentacion(
            organizacion_id,
            sesion,
            presentacion_id=nuevo_id(),
            producto_id=producto.id,
            nombre=datos.nombre,
            unidades_base=datos.unidades_base,
            usar_en_venta=datos.usar_en_venta,
            usar_en_compra=datos.usar_en_compra,
            es_referencia=datos.es_referencia,
            activo=True,
            momento=momento,
            actualizado_por_id=actor_id,
        )
        for datos in presentaciones
    ]
    return producto, filas_presentacion


def modificar_producto(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    producto_id: UUID,
    codigo: str,
    nombre: str,
    categoria_id: UUID,
    marca_id: UUID | None,
    proveedor_id: UUID,
    unidad_base: str,
    alicuota_id: UUID,
    activo: bool,
    actor_id: UUID | None,
) -> Producto:
    """`PRODUCTO_MODIFICAR` (estado completo deseado, `design.md` D4): no
    toca presentaciones (CAT-05: "Desactivar un producto NO DEBE cambiar el
    estado de sus presentaciones"). D9-A: conservar el proveedor actual
    aunque esté inactivo se acepta; cambiar a otro proveedor inactivo se
    rechaza (`PROVEEDOR_INACTIVO`)."""
    producto = repository.obtener_producto_por_id(organizacion_id, producto_id, sesion)
    if producto is None:
        raise RecursoNoEncontradoError(f"El producto {producto_id} no existe en esta organización.")

    codigo_normalizado = normalizar_codigo(codigo)
    nombre_normalizado = normalizar_nombre(nombre)
    unidad_base_normalizada = normalizar_unidad_base(unidad_base)
    _resolver_categoria_activa(organizacion_id, categoria_id, sesion)
    _resolver_marca_activa(organizacion_id, marca_id, sesion)
    _resolver_alicuota_activa(organizacion_id, alicuota_id, sesion)
    _resolver_proveedor(
        organizacion_id, proveedor_id, sesion, proveedor_actual_id=producto.proveedor_id
    )

    actualizado = repository.actualizar_producto(
        organizacion_id,
        sesion,
        producto_id=producto_id,
        codigo=codigo_normalizado,
        nombre=nombre_normalizado,
        categoria_id=categoria_id,
        marca_id=marca_id,
        proveedor_id=proveedor_id,
        unidad_base=unidad_base_normalizada,
        alicuota_id=alicuota_id,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    assert actualizado is not None
    return actualizado


def listar_productos_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = repository.LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    categoria_id: UUID | None = None,
    marca_id: UUID | None = None,
    activo: bool | None = None,
) -> tuple[list[Producto], str | None]:
    return repository.listar_productos_paginado(
        organizacion_id,
        sesion,
        limite=limite,
        cursor=cursor,
        texto=texto,
        categoria_id=categoria_id,
        marca_id=marca_id,
        activo=activo,
    )


def buscar_productos_por_codigo(
    organizacion_id: UUID, codigo: str, sesion: Session
) -> list[Producto]:
    """Lectura pública para la importación (change 10, `design.md` D4): productos de la
    organización con ese código, sin distinguir mayúsculas ni espacios al borde, activos
    o no. Más de uno es una ambigüedad que decide quien llama."""
    return repository.buscar_productos_por_codigo(organizacion_id, codigo, sesion)


def obtener_producto(organizacion_id: UUID, producto_id: UUID, sesion: Session) -> Producto | None:
    """Lectura pública (tarea 7.7): otros módulos (06, 09, 11, 13, 18a)
    resuelven un producto por id sin importar `catalogo.models` ni
    `catalogo.repository` directamente (`CLAUDE.md` §4)."""
    return repository.obtener_producto_por_id(organizacion_id, producto_id, sesion)


# --- presentacion (CAT-02, CAT-03, CAT-04, INV-18) -------------------------


def agregar_presentacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    producto_id: UUID,
    nombre: str,
    unidades_base: int,
    usar_en_venta: bool,
    usar_en_compra: bool,
    actor_id: UUID | None,
) -> Presentacion:
    """`PRESENTACION_AGREGAR`: nunca crea una referencia nueva (para eso
    existe `PRESENTACION_REFERENCIA_CAMBIAR`, D5) -- `es_referencia` nace
    siempre en `False`. Bloquea la fila de `producto` (D5) antes de
    escribir, para serializar con cualquier otro cambio concurrente de
    presentaciones del mismo producto."""
    nombre_normalizado = normalizar_nombre(nombre)
    validar_unidades_base(unidades_base)
    producto = repository.obtener_producto_por_id_para_actualizar(
        organizacion_id, producto_id, sesion
    )
    if producto is None:
        raise RecursoNoEncontradoError(f"El producto {producto_id} no existe en esta organización.")

    return repository.crear_presentacion(
        organizacion_id,
        sesion,
        presentacion_id=nuevo_id(),
        producto_id=producto_id,
        nombre=nombre_normalizado,
        unidades_base=unidades_base,
        usar_en_venta=usar_en_venta,
        usar_en_compra=usar_en_compra,
        es_referencia=False,
        activo=True,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


def modificar_presentacion(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    presentacion_id: UUID,
    nombre: str,
    unidades_base: int,
    usar_en_venta: bool,
    usar_en_compra: bool,
    activo: bool,
    actor_id: UUID | None,
) -> Presentacion:
    """`PRESENTACION_MODIFICAR` (CAT-03, CAT-04, INV-18): bloquea la fila
    del producto dueño (D5) antes de decidir, consulta los verificadores de
    uso (D2) y aplica `validar_modificacion_presentacion` (dominio puro,
    grupo 4)."""
    nombre_normalizado = normalizar_nombre(nombre)
    presentacion = repository.obtener_presentacion_por_id(organizacion_id, presentacion_id, sesion)
    if presentacion is None:
        raise RecursoNoEncontradoError(
            f"La presentación {presentacion_id} no existe en esta organización."
        )
    # D5: bloquea la fila de `producto` antes de decidir/escribir.
    producto_bloqueado = repository.obtener_producto_por_id_para_actualizar(
        organizacion_id, presentacion.producto_id, sesion
    )
    assert producto_bloqueado is not None  # la FK de presentacion lo garantiza.

    fue_usada = presentacion_fue_usada(organizacion_id, presentacion_id, sesion)
    validar_modificacion_presentacion(
        es_referencia=presentacion.es_referencia,
        unidades_base_actual=presentacion.unidades_base,
        unidades_base_nueva=unidades_base,
        usar_en_venta_nuevo=usar_en_venta,
        activo_nuevo=activo,
        fue_usada=fue_usada,
    )

    actualizada = repository.actualizar_presentacion(
        organizacion_id,
        sesion,
        presentacion_id=presentacion_id,
        nombre=nombre_normalizado,
        unidades_base=unidades_base,
        usar_en_venta=usar_en_venta,
        usar_en_compra=usar_en_compra,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )
    assert actualizada is not None
    return actualizada


def cambiar_referencia(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    producto_id: UUID,
    presentacion_id: UUID,
    actor_id: UUID | None,
) -> Presentacion:
    """`PRESENTACION_REFERENCIA_CAMBIAR` (CAT-03, D5): bloquea la fila del
    producto, valida que la nueva referencia esté activa y se use en venta,
    desmarca la anterior y marca la nueva, EN ESE ORDEN, dentro de la misma
    transacción (el índice parcial no es diferible)."""
    producto = repository.obtener_producto_por_id_para_actualizar(
        organizacion_id, producto_id, sesion
    )
    if producto is None:
        raise RecursoNoEncontradoError(f"El producto {producto_id} no existe en esta organización.")

    nueva = repository.obtener_presentacion_por_id(organizacion_id, presentacion_id, sesion)
    if nueva is None or nueva.producto_id != producto_id:
        raise RecursoNoEncontradoError(
            f"La presentación {presentacion_id} no existe en el producto {producto_id}."
        )
    validar_nueva_referencia(activo=nueva.activo, usar_en_venta=nueva.usar_en_venta)

    momento = reloj.now()
    repository.desmarcar_referencia(organizacion_id, producto_id, sesion, momento=momento)
    marcada = repository.marcar_referencia(
        organizacion_id, presentacion_id, sesion, momento=momento
    )
    assert marcada is not None
    return marcada


def listar_presentaciones_de_producto(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> list[Presentacion]:
    return repository.listar_presentaciones_de_producto(organizacion_id, producto_id, sesion)


def obtener_presentacion(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> Presentacion | None:
    """Lectura pública (tarea 7.7)."""
    return repository.obtener_presentacion_por_id(organizacion_id, presentacion_id, sesion)


def obtener_referencia_de_producto(
    organizacion_id: UUID, producto_id: UUID, sesion: Session
) -> Presentacion | None:
    """Lectura pública (tarea 7.7): la presentación de referencia de un
    producto, para módulos que necesitan sus unidades (visualización CAT-08,
    costeo, precios) sin importar `catalogo.repository` directamente."""
    return repository.obtener_referencia_de_producto(organizacion_id, producto_id, sesion)
