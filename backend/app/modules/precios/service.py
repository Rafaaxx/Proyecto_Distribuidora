"""Interfaz pública de `precios` (`CLAUDE.md` §4: un módulo usa a otro solo a través de su
`service.py`).

Expone las escrituras de listas, reglas de margen y redondeos por categoría que usan los
handlers de `precios/commands.py` (change 13, grupo 5). Más adelante entrega a `clientes`, a
`ventas` (18a) y a `importacion` (13b) la resolución de precio y el bruto de línea.

Sin `commit`: la transacción la gestiona el bus de comandos (`CLAUDE.md` §4).

Todas las funciones reciben `organizacion_id` como primer parámetro y lo usan para filtrar.
Toda la lógica de validación vive en `precios/domain/`; acá solo se orquesta el orden de las
llamadas: bloquear la lista, leer, validar, escribir. La fila de `lista_precio` es el candado
de la lista (`design.md` D14): toda escritura de reglas o redondeos de una lista la toma
primero, y así dos escrituras de la misma lista se serializan.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock, FixedClock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.identidad import service as identidad_service
from app.modules.precios import repository
from app.modules.precios.domain.borrador import (
    ReferenciaDeCalculo,
    Senales,
    calcular_senales,
    referencia_de_precio_manual,
    validar_precio_manual,
)
from app.modules.precios.domain.errores import (
    ListaEnUsoError,
    ListaInactivaError,
    ListaSinVersionVigenteError,
    ProductoInactivoError,
    RecursoNoEncontradoError,
    SinListaAplicableError,
    VersionNoEsBorradorError,
)
from app.modules.precios.domain.listas import normalizar_nombre
from app.modules.precios.domain.precio import (
    PrecioCalculado,
    calcular_precio,
    exigir_modo_impositivo_soportado,
)
from app.modules.precios.domain.redondeo import Redondeo, redondeo_aplicable, validar_redondeo
from app.modules.precios.domain.reglas import ProductoDeRegla, Regla, resolver_regla, validar_regla
from app.modules.precios.domain.versiones import (
    VersionDeLista,
    validar_anulacion,
    validar_publicacion,
    version_vigente,
)
from app.modules.precios.models import (
    ListaPrecio,
    ListaVersion,
    PrecioItem,
    RedondeoCategoria,
    ReglaMargen,
)
from app.modules.proveedores import service as proveedores_service


def _lista_para_actualizar(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> ListaPrecio:
    """Toma el candado de la lista (D14). Una lista inexistente, o de otra organización,
    responde igual (INV-21)."""
    lista = repository.obtener_lista_para_actualizar(organizacion_id, lista_id, sesion)
    if lista is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no existe en esta organización.")
    return lista


# --- LISTA_PRECIO_CREAR y LISTA_PRECIO_MODIFICAR (PRC-01, PRC-14) -----------------------


def crear_lista(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    redondeo_multiplo: Decimal | str,
    redondeo_direccion: str,
    actor_id: UUID | None,
) -> ListaPrecio:
    """`LISTA_PRECIO_CREAR`: la lista nace activa y sin versiones, con el nombre recortado y
    el redondeo validado (`NOMBRE_INVALIDO`, `REDONDEO_INVALIDO`); el nombre repetido sin
    distinguir mayúsculas lo rechaza la base (`NOMBRE_DUPLICADO`). El identificador lo genera
    el servidor (UUIDv7)."""
    nombre_normalizado = normalizar_nombre(nombre)
    redondeo = validar_redondeo(redondeo_multiplo, redondeo_direccion)
    return repository.crear_lista(
        organizacion_id,
        sesion,
        lista_id=nuevo_id(),
        nombre=nombre_normalizado,
        redondeo_multiplo=redondeo.multiplo,
        redondeo_direccion=redondeo.direccion,
        activo=True,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


def modificar_lista(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    nombre: str,
    redondeo_multiplo: Decimal | str,
    redondeo_direccion: str,
    activo: bool,
    actor_id: UUID | None,
) -> ListaPrecio:
    """`LISTA_PRECIO_MODIFICAR`: nombre, redondeo y actividad, con las validaciones del alta.
    Cambiar el redondeo NO toca ninguna versión: rige para los borradores que se generen
    después (PRC-04, INV-11). Una lista no se borra: se desactiva.

    Una lista que es la predeterminada de la organización o que está asignada a un cliente
    no inactivo no se desactiva (`LISTA_EN_USO`, D11). Con el candado de la lista tomado
    (D14), quien la asigna (`clientes`, `FOR SHARE`) o la define predeterminada la serializa
    con esta desactivación."""
    lista = _lista_para_actualizar(organizacion_id, lista_id, sesion)
    nombre_normalizado = normalizar_nombre(nombre)
    redondeo = validar_redondeo(redondeo_multiplo, redondeo_direccion)
    if lista.activo and not activo and lista_esta_en_uso(organizacion_id, lista_id, sesion):
        raise ListaEnUsoError(
            f"La lista {lista.nombre!r} es la predeterminada de la organización o está "
            "asignada a algún cliente que no está inactivo: no se puede desactivar (D11)."
        )
    return repository.actualizar_lista(
        organizacion_id,
        sesion,
        lista,
        nombre=nombre_normalizado,
        redondeo_multiplo=redondeo.multiplo,
        redondeo_direccion=redondeo.direccion,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


# --- uso de una lista (D11 punto 3, patrón de ADR-023) --------------------------------------

VerificadorUsoDeLista = Callable[[UUID, UUID, Session], bool]
"""`funcion(organizacion_id, lista_id, sesion) -> bool`: `True` si el módulo que lo registró
usa la lista en esa organización. `precios` no importa a quien la usa (`clientes -> precios`,
nunca al revés, `02` §5.3): `clientes` registra el suyo al cargarse su `service.py`."""

# Lo puebla la importación de los módulos que llaman a `registrar_verificador_uso_de_lista`
# (mismo patrón que `catalogo_service.registrar_verificador_uso`). Las pruebas unitarias lo
# aíslan con `monkeypatch`.
_VERIFICADORES_DE_USO: dict[str, VerificadorUsoDeLista] = {}


def registrar_verificador_uso_de_lista(nombre: str, funcion: VerificadorUsoDeLista) -> None:
    """Registra `funcion` bajo `nombre` (el del módulo dueño, para que registrar dos veces el
    mismo se note)."""
    _VERIFICADORES_DE_USO[nombre] = funcion


def verificadores_de_uso_de_lista() -> frozenset[str]:
    """Los nombres de los verificadores registrados."""
    return frozenset(_VERIFICADORES_DE_USO)


def lista_esta_en_uso(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> bool:
    """`True` si la lista es la predeterminada de la organización o algún verificador
    registrado (`clientes`: asignada a un cliente no `INACTIVO`) responde `True` (D11)."""
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    if configuracion is not None and configuracion.lista_precio_default_id == lista_id:
        return True
    return any(
        funcion(organizacion_id, lista_id, sesion) for funcion in _VERIFICADORES_DE_USO.values()
    )


# --- REGLA_MARGEN_CREAR y REGLA_MARGEN_MODIFICAR (PRC-12, PRC-13, D8) -------------------


def crear_regla(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    tipo: str,
    valor: Decimal | str,
    alcance_tipo: str,
    alcance_id: UUID | None,
    actor_id: UUID | None,
) -> ReglaMargen:
    """`REGLA_MARGEN_CREAR`: la regla nace activa. Valida tipo, valor y alcance
    (`MARGEN_INVALIDO`, `ALCANCE_INVALIDO`); que la lista y la entidad del alcance existan en
    la organización lo garantizan las claves foráneas compuestas (404, INV-21); que no haya
    otra regla activa para el mismo alcance (`REGLA_DUPLICADA`, D8) lo garantizan los índices
    únicos parciales, también ante escrituras simultáneas."""
    _lista_para_actualizar(organizacion_id, lista_id, sesion)
    validada = validar_regla(tipo, valor, alcance_tipo, alcance_id)
    return repository.crear_regla(
        organizacion_id,
        sesion,
        regla_id=nuevo_id(),
        lista_id=lista_id,
        alcance_tipo=validada.alcance_tipo,
        alcance_id=validada.alcance_id,
        tipo=validada.tipo,
        valor=validada.valor,
        activo=True,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


def modificar_regla(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    regla_id: UUID,
    tipo: str,
    valor: Decimal | str,
    activo: bool,
    actor_id: UUID | None,
) -> ReglaMargen:
    """`REGLA_MARGEN_MODIFICAR`: tipo, valor y actividad, con las validaciones del alta; el
    alcance y la lista no cambian. Reactivar una regla con otra activa para el mismo alcance
    se rechaza con `REGLA_DUPLICADA`. Nunca se borra y no altera ningún precio ya generado
    (PRC-16): rige para los borradores que se generen después."""
    _lista_para_actualizar(organizacion_id, lista_id, sesion)
    regla = repository.obtener_regla_para_actualizar(organizacion_id, lista_id, regla_id, sesion)
    if regla is None:
        raise RecursoNoEncontradoError(
            f"La regla {regla_id} no existe en la lista {lista_id} de esta organización."
        )
    validada = validar_regla(tipo, valor, regla.alcance_tipo, regla.alcance_id)
    return repository.actualizar_regla(
        organizacion_id,
        sesion,
        regla,
        tipo=validada.tipo,
        valor=validada.valor,
        activo=activo,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


# --- REDONDEO_CATEGORIA_DEFINIR (PRC-14, D9) --------------------------------------------


def definir_redondeo_categoria(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    categoria_id: UUID,
    multiplo: Decimal | str,
    direccion: str,
    activo: bool,
    actor_id: UUID | None,
) -> RedondeoCategoria:
    """`REDONDEO_CATEGORIA_DEFINIR`: la sobrescritura del redondeo de una lista para una
    categoría. Como máximo hay una por lista y categoría: definirla de nuevo actualiza la
    existente. La categoría tiene que existir en la organización (404 si no, por la clave
    foránea compuesta). Una sobrescritura inactiva no se aplica."""
    _lista_para_actualizar(organizacion_id, lista_id, sesion)
    redondeo = validar_redondeo(multiplo, direccion)
    momento = reloj.now()
    existente = repository.obtener_redondeo_categoria_para_actualizar(
        organizacion_id, lista_id, categoria_id, sesion
    )
    if existente is not None:
        return repository.actualizar_redondeo_categoria(
            organizacion_id,
            sesion,
            existente,
            multiplo=redondeo.multiplo,
            direccion=redondeo.direccion,
            activo=activo,
            momento=momento,
            actualizado_por_id=actor_id,
        )
    return repository.crear_redondeo_categoria(
        organizacion_id,
        sesion,
        redondeo_id=nuevo_id(),
        lista_id=lista_id,
        categoria_id=categoria_id,
        multiplo=redondeo.multiplo,
        direccion=redondeo.direccion,
        activo=activo,
        momento=momento,
        actualizado_por_id=actor_id,
    )


# --- LISTA_GENERAR_BORRADOR y LISTA_BORRADOR_PRECIO_FIJAR (PRC-16, PRC-17, D4, D5, D7, D14) --


@dataclass(frozen=True)
class ProductoSinPrecio:
    """Un producto activo que el borrador no pudo calcular y la causa (D4):
    `SIN_PRESENTACION_DE_REFERENCIA`, `SIN_COSTO`, `SIN_REGLA` o `PRECIO_NO_POSITIVO`."""

    producto_id: UUID
    causa: str


@dataclass(frozen=True)
class ResultadoGeneracion:
    """Lo que informa `LISTA_GENERAR_BORRADOR`: el borrador, cuántos precios tiene, los
    productos sin precio y cuántos precios llevan cada señal de atención (D2, D3)."""

    version_id: UUID
    numero: int
    regenerado: bool
    cantidad_precios: int
    productos_sin_precio: tuple[ProductoSinPrecio, ...]
    precios_con_otra_regla_iva: int
    precios_con_costos_distintos: int


@dataclass(frozen=True)
class ResultadoPrecioFijado:
    """Lo que informa `LISTA_BORRADOR_PRECIO_FIJAR`: el precio que quedó en el borrador, o
    `None` si al quitar la marca manual el producto no pudo calcularse y quedó sin precio."""

    version_id: UUID
    producto_id: UUID
    precio_final: Decimal | None
    manual: bool


@dataclass(frozen=True)
class SenalesDePrecio:
    """Las señales de un precio del borrador y, si salió de un costo, de qué presentación
    (D2, D3, D7)."""

    sin_costo: bool
    margen_menor: bool
    costo_otra_regla_iva: bool
    costos_distintos_por_presentacion: bool
    presentacion_del_costo_id: UUID | None


@dataclass(frozen=True)
class _ContextoDeCalculo:
    """Lo que se necesita para calcular precios de una lista, leído una sola vez."""

    modo_impositivo: str
    computa_credito_fiscal: bool
    fecha: date
    reglas: list[Regla]
    sobrescrituras: dict[UUID, Redondeo]
    de_la_lista: Redondeo

    def regla_de(self, producto: ProductoDeRegla) -> Regla | None:
        return resolver_regla(self.reglas, producto)

    def redondeo_de(self, categoria_id: UUID) -> Redondeo:
        return redondeo_aplicable(self.de_la_lista, self.sobrescrituras.get(categoria_id))


def _contexto_de_calculo(
    organizacion_id: UUID, sesion: Session, reloj: Clock, lista: ListaPrecio
) -> _ContextoDeCalculo:
    """Las reglas, los redondeos, el modo impositivo y la fecha de negocio de la lista. Un
    modo impositivo `C` se rechaza acá, antes de calcular nada (PRC-15)."""
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    computa_credito_fiscal = identidad_service.organizacion_computa_credito_fiscal(
        organizacion_id, sesion
    )
    fecha = identidad_service.fecha_de_negocio(organizacion_id, sesion, reloj)
    if configuracion is None or computa_credito_fiscal is None or fecha is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    exigir_modo_impositivo_soportado(configuracion.modo_impositivo)
    reglas = [
        Regla(
            id=regla.id,
            alcance_tipo=regla.alcance_tipo,
            alcance_id=regla.alcance_id,
            tipo=regla.tipo,
            valor=regla.valor,
            activo=regla.activo,
        )
        for regla in repository.listar_reglas(organizacion_id, lista.id, sesion)
    ]
    sobrescrituras = {
        redondeo.categoria_id: Redondeo(redondeo.multiplo, redondeo.direccion)
        for redondeo in repository.listar_redondeos_de_categoria(organizacion_id, lista.id, sesion)
        if redondeo.activo
    }
    return _ContextoDeCalculo(
        modo_impositivo=configuracion.modo_impositivo,
        computa_credito_fiscal=computa_credito_fiscal,
        fecha=fecha,
        reglas=reglas,
        sobrescrituras=sobrescrituras,
        de_la_lista=Redondeo(lista.redondeo_multiplo, lista.redondeo_direccion),
    )


def _version_para_actualizar(
    organizacion_id: UUID, lista_id: UUID, version_id: UUID, sesion: Session
) -> ListaVersion:
    """La versión de la lista, leída con el candado de la lista ya tomado (D14). Una versión
    inexistente, de otra lista o de otra organización responde 404 (INV-21)."""
    version = repository.obtener_version(organizacion_id, lista_id, version_id, sesion)
    if version is None:
        raise RecursoNoEncontradoError(
            f"La versión {version_id} no existe en la lista {lista_id} de esta organización."
        )
    return version


def escribir_precios(
    organizacion_id: UUID,
    sesion: Session,
    version: ListaVersion,
    filas: list[PrecioItem],
    *,
    producto_ids: Collection[UUID] | None,
) -> None:
    """La función única de escritura de precios (D13, INV-11): reemplaza los precios de
    `producto_ids` de la versión (todos si es `None`) por `filas`, y exige que la versión sea
    un `BORRADOR`. Quien la llama ya tiene el candado de la lista (D14) y leyó la versión con
    él, así que el estado que se revalida acá es el definitivo: una versión publicada o
    anulada no cambia nunca."""
    if version.estado != "BORRADOR":
        raise VersionNoEsBorradorError(
            f"La versión {version.numero} de la lista está {version.estado}: una versión "
            "publicada no cambia (PRC-04, INV-11)."
        )
    repository.borrar_precios_de_version(
        organizacion_id, version.id, sesion, producto_ids=producto_ids
    )
    repository.insertar_precios(organizacion_id, sesion, filas)


def _fila_de_precio(
    organizacion_id: UUID,
    version_id: UUID,
    producto_id: UUID,
    unidades_referencia: int,
    costo: proveedores_service.CostoVigente | None,
    calculo: ReferenciaDeCalculo,
    precio_final: Decimal,
    *,
    manual: bool,
) -> PrecioItem:
    return PrecioItem(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        version_id=version_id,
        producto_id=producto_id,
        unidades_referencia=unidades_referencia,
        costo_informado_id=None if costo is None else costo.costo_informado_id,
        costo_referencia=calculo.costo_referencia,
        regla_margen_id=calculo.regla_id,
        tipo_margen=calculo.tipo_margen,
        valor_margen=calculo.valor_margen,
        precio_calculado=calculo.precio_calculado,
        precio_final=precio_final,
        manual=manual,
    )


def _precio_calculado_como_fila(
    organizacion_id: UUID,
    version_id: UUID,
    producto_id: UUID,
    costo: proveedores_service.CostoVigente,
    resultado: PrecioCalculado,
) -> PrecioItem:
    return _fila_de_precio(
        organizacion_id,
        version_id,
        producto_id,
        resultado.unidades_referencia,
        costo,
        ReferenciaDeCalculo(
            costo_referencia=resultado.costo_referencia,
            regla_id=resultado.regla_id,
            tipo_margen=resultado.tipo_margen,
            valor_margen=resultado.valor_margen,
            precio_calculado=resultado.precio_calculado,
        ),
        resultado.precio_final,
        manual=False,
    )


def _senales_de_fila(
    fila: PrecioItem, costo: proveedores_service.CostoVigente | None, computa_actual: bool
) -> Senales:
    """Las señales de un precio ya armado, con el costo vigente del que salió (D2, D3, D7)."""
    return calcular_senales(
        manual=fila.manual,
        precio_final=fila.precio_final,
        precio_calculado=fila.precio_calculado,
        computa_credito_fiscal_del_costo=None if costo is None else costo.computa_credito_fiscal,
        computa_credito_fiscal_actual=computa_actual,
        costos_distintos_por_presentacion=(
            False if costo is None else costo.costos_distintos_por_presentacion
        ),
    )


def generar_borrador(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    actor_id: UUID,
    operation_id: UUID,
) -> ResultadoGeneracion:
    """`LISTA_GENERAR_BORRADOR` (PRC-17, D4, D5, D7): crea el borrador de la lista, o regenera
    el que ya tiene, calculando el precio de cada producto activo con el costo informado
    vigente a la fecha de negocio, la regla de margen aplicable y el redondeo aplicable. Los
    precios manuales se conservan: los del propio borrador si ya existe, y si no, los de la
    versión base (D5, D7), con el costo, la regla y el calculado actualizados.

    Con el candado de la lista (D14): lista inexistente o ajena, 404; lista inactiva,
    `LISTA_INACTIVA`; modo impositivo `C`, `MODO_IMPOSITIVO_NO_SOPORTADO`. Un producto que no
    puede calcularse no recibe precio y se informa con su causa."""
    lista = _lista_para_actualizar(organizacion_id, lista_id, sesion)
    if not lista.activo:
        raise ListaInactivaError(f"La lista {lista.nombre!r} está inactiva (PRC-01).")
    contexto = _contexto_de_calculo(organizacion_id, sesion, reloj, lista)
    momento = reloj.now()

    productos = catalogo_service.listar_productos_activos_con_referencia(organizacion_id, sesion)
    costos = proveedores_service.obtener_costos_informados_vigentes(
        organizacion_id, [producto.producto_id for producto in productos], contexto.fecha, sesion
    )

    base = repository.obtener_version_base(organizacion_id, lista_id, sesion)
    borrador = repository.obtener_borrador(organizacion_id, lista_id, sesion)
    regenerado = borrador is not None
    # Los manuales se leen ANTES de reemplazar los precios: el borrador regenerado parte de sí
    # mismo (lo que se decidió en él no se deshace) y uno nuevo parte de la versión base.
    fuente = borrador if borrador is not None else base
    manuales = (
        {}
        if fuente is None
        else {
            precio.producto_id: (precio.precio_final, precio.unidades_referencia)
            for precio in repository.listar_precios_de_version(organizacion_id, fuente.id, sesion)
            if precio.manual
        }
    )
    if borrador is None:
        borrador = repository.crear_borrador(
            organizacion_id,
            sesion,
            version_id=nuevo_id(),
            lista_id=lista_id,
            numero=repository.siguiente_numero_de_version(organizacion_id, lista_id, sesion),
            version_base_id=None if base is None else base.id,
            generado_en=momento,
            creado_por_id=actor_id,
            operation_id=operation_id,
        )
    else:
        repository.actualizar_generacion(
            organizacion_id,
            sesion,
            borrador,
            version_base_id=None if base is None else base.id,
            generado_en=momento,
        )

    filas: list[PrecioItem] = []
    sin_precio: list[ProductoSinPrecio] = []
    con_otra_regla_iva = 0
    con_costos_distintos = 0
    for producto in productos:
        costo = costos.get(producto.producto_id)
        costo_base = None if costo is None else costo.costo_base
        regla = contexto.regla_de(
            ProductoDeRegla(
                producto_id=producto.producto_id,
                marca_id=producto.marca_id,
                categoria_id=producto.categoria_id,
                proveedor_id=producto.proveedor_id,
            )
        )
        manual = manuales.get(producto.producto_id)
        if manual is not None:
            # D7: se conserva el precio final y las unidades con que se fijó; el cálculo que
            # lo acompaña se actualiza con el costo y la regla de hoy.
            precio_final, unidades = manual
            fila = _fila_de_precio(
                organizacion_id,
                borrador.id,
                producto.producto_id,
                unidades,
                costo,
                referencia_de_precio_manual(costo_base, unidades, regla),
                precio_final,
                manual=True,
            )
            filas.append(fila)
            senales = _senales_de_fila(fila, costo, contexto.computa_credito_fiscal)
            con_otra_regla_iva += senales.costo_otra_regla_iva
            con_costos_distintos += senales.costos_distintos_por_presentacion
            continue
        resultado = calcular_precio(
            costo_base=costo_base,
            unidades_referencia=producto.unidades_referencia,
            regla=regla,
            redondeo=contexto.redondeo_de(producto.categoria_id),
            modo_impositivo=contexto.modo_impositivo,
        )
        if not isinstance(resultado, PrecioCalculado):
            sin_precio.append(ProductoSinPrecio(producto.producto_id, resultado.causa))
            continue
        assert costo is not None  # un precio calculado siempre salió de un costo
        fila = _precio_calculado_como_fila(
            organizacion_id, borrador.id, producto.producto_id, costo, resultado
        )
        filas.append(fila)
        senales = _senales_de_fila(fila, costo, contexto.computa_credito_fiscal)
        con_otra_regla_iva += senales.costo_otra_regla_iva
        con_costos_distintos += senales.costos_distintos_por_presentacion
    escribir_precios(organizacion_id, sesion, borrador, filas, producto_ids=None)
    return ResultadoGeneracion(
        version_id=borrador.id,
        numero=borrador.numero,
        regenerado=regenerado,
        cantidad_precios=len(filas),
        productos_sin_precio=tuple(sin_precio),
        precios_con_otra_regla_iva=con_otra_regla_iva,
        precios_con_costos_distintos=con_costos_distintos,
    )


def fijar_precio_manual(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    version_id: UUID,
    producto_id: UUID,
    precio_final: str | Decimal | None,
) -> ResultadoPrecioFijado:
    """`LISTA_BORRADOR_PRECIO_FIJAR` (D7, PRC-16): fija el precio final de un producto activo
    en el borrador, sin aplicarle el redondeo de la lista, o -con `precio_final` nulo- quita
    la marca manual y vuelve a calcularlo (si no puede calcularse, el producto queda sin
    precio). Escribe por la función única de escritura de precios (D13): una versión que no
    es un `BORRADOR` se rechaza con `VERSION_NO_ES_BORRADOR`."""
    lista = _lista_para_actualizar(organizacion_id, lista_id, sesion)
    importe = None if precio_final is None else validar_precio_manual(precio_final)
    version = _version_para_actualizar(organizacion_id, lista_id, version_id, sesion)
    if version.estado != "BORRADOR":
        raise VersionNoEsBorradorError(
            f"La versión {version.numero} de la lista está {version.estado}: una versión "
            "publicada no cambia (PRC-04, INV-11)."
        )
    producto = catalogo_service.obtener_producto(organizacion_id, producto_id, sesion)
    if producto is None:
        raise RecursoNoEncontradoError(f"El producto {producto_id} no existe en esta organización.")
    if not producto.activo:
        raise ProductoInactivoError(f"El producto {producto.nombre!r} está inactivo (CAT-05).")
    referencia = catalogo_service.obtener_referencia_de_producto(
        organizacion_id, producto_id, sesion
    )
    if referencia is None:
        raise RecursoNoEncontradoError(
            f"El producto {producto.nombre!r} no tiene presentación de referencia."
        )

    contexto = _contexto_de_calculo(organizacion_id, sesion, reloj, lista)
    costo = proveedores_service.obtener_costos_informados_vigentes(
        organizacion_id, [producto_id], contexto.fecha, sesion
    ).get(producto_id)
    costo_base = None if costo is None else costo.costo_base
    regla = contexto.regla_de(
        ProductoDeRegla(
            producto_id=producto_id,
            marca_id=producto.marca_id,
            categoria_id=producto.categoria_id,
            proveedor_id=producto.proveedor_id,
        )
    )

    fila: PrecioItem | None
    if importe is not None:
        fila = _fila_de_precio(
            organizacion_id,
            version_id,
            producto_id,
            referencia.unidades_base,
            costo,
            referencia_de_precio_manual(costo_base, referencia.unidades_base, regla),
            importe,
            manual=True,
        )
    else:
        resultado = calcular_precio(
            costo_base=costo_base,
            unidades_referencia=referencia.unidades_base,
            regla=regla,
            redondeo=contexto.redondeo_de(producto.categoria_id),
            modo_impositivo=contexto.modo_impositivo,
        )
        fila = (
            None
            if costo is None or not isinstance(resultado, PrecioCalculado)
            else _precio_calculado_como_fila(
                organizacion_id, version_id, producto_id, costo, resultado
            )
        )
    escribir_precios(
        organizacion_id,
        sesion,
        version,
        [] if fila is None else [fila],
        producto_ids=[producto_id],
    )
    return ResultadoPrecioFijado(
        version_id=version_id,
        producto_id=producto_id,
        precio_final=None if fila is None else fila.precio_final,
        manual=fila is not None and fila.manual,
    )


def senales_de_precios(
    organizacion_id: UUID, sesion: Session, version: ListaVersion, precios: list[PrecioItem]
) -> dict[UUID, SenalesDePrecio]:
    """Las señales de `precios`, de la versión `version` (un borrador), por producto (PRC-17,
    D2, D3, D7). Se derivan de lo guardado en cada precio y del costo vigente a la fecha de
    negocio de la generación de la versión, y no se almacenan."""
    if version.generado_en is None:
        return {}
    computa_actual = identidad_service.organizacion_computa_credito_fiscal(organizacion_id, sesion)
    fecha = identidad_service.fecha_de_negocio(
        organizacion_id, sesion, FixedClock(version.generado_en)
    )
    if computa_actual is None or fecha is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    costos = proveedores_service.obtener_costos_informados_vigentes(
        organizacion_id, [precio.producto_id for precio in precios], fecha, sesion
    )
    senales: dict[UUID, SenalesDePrecio] = {}
    for precio in precios:
        # Con costo informado guardado en el precio, el costo vigente a la fecha de la
        # generación es el que se usó; sin él (manual sin costo) no hay nada que señalar.
        costo = costos.get(precio.producto_id) if precio.costo_informado_id is not None else None
        calculadas = _senales_de_fila(precio, costo, computa_actual)
        senales[precio.producto_id] = SenalesDePrecio(
            sin_costo=calculadas.sin_costo,
            margen_menor=calculadas.margen_menor,
            costo_otra_regla_iva=calculadas.costo_otra_regla_iva,
            costos_distintos_por_presentacion=calculadas.costos_distintos_por_presentacion,
            presentacion_del_costo_id=None if costo is None else costo.presentacion_id,
        )
    return senales


def senales_del_borrador(
    organizacion_id: UUID, sesion: Session, *, lista_id: UUID
) -> dict[UUID, SenalesDePrecio]:
    """Las señales de cada precio del borrador de la lista; vacío si la lista no tiene
    borrador. Una lista inexistente o ajena responde 404."""
    if repository.obtener_lista(organizacion_id, lista_id, sesion) is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no existe en esta organización.")
    borrador = repository.obtener_borrador(organizacion_id, lista_id, sesion)
    if borrador is None:
        return {}
    precios = repository.listar_precios_de_version(organizacion_id, borrador.id, sesion)
    return senales_de_precios(organizacion_id, sesion, borrador, precios)


SIN_CALCULAR = "SIN_CALCULAR"
"""Un producto sin precio en el borrador que, con los datos de hoy, sí podría calcularse: el
borrador es una foto y hay que regenerarlo."""


def productos_sin_precio_del_borrador(
    organizacion_id: UUID, sesion: Session, *, lista_id: UUID
) -> list[ProductoSinPrecio]:
    """Los productos activos que el borrador de la lista no tiene, con la causa (D4): la que
    daría calcularlos hoy (`SIN_PRESENTACION_DE_REFERENCIA`, `SIN_COSTO`, `SIN_REGLA`,
    `PRECIO_NO_POSITIVO`) o `SIN_CALCULAR` si
    hoy podrían calcularse (el borrador es una foto: se regenera). Una lista inexistente o
    ajena, o sin borrador, responde 404."""
    lista = repository.obtener_lista(organizacion_id, lista_id, sesion)
    if lista is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no existe en esta organización.")
    borrador = repository.obtener_borrador(organizacion_id, lista_id, sesion)
    if borrador is None or borrador.generado_en is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no tiene borrador.")
    con_precio = repository.ids_de_productos_con_precio(organizacion_id, borrador.id, sesion)
    pendientes = [
        producto
        for producto in catalogo_service.listar_productos_activos_con_referencia(
            organizacion_id, sesion
        )
        if producto.producto_id not in con_precio
    ]
    if not pendientes:
        return []
    contexto = _contexto_de_calculo(
        organizacion_id, sesion, FixedClock(borrador.generado_en), lista
    )
    costos = proveedores_service.obtener_costos_informados_vigentes(
        organizacion_id, [producto.producto_id for producto in pendientes], contexto.fecha, sesion
    )
    sin_precio: list[ProductoSinPrecio] = []
    for producto in pendientes:
        costo = costos.get(producto.producto_id)
        resultado = calcular_precio(
            costo_base=None if costo is None else costo.costo_base,
            unidades_referencia=producto.unidades_referencia,
            regla=contexto.regla_de(
                ProductoDeRegla(
                    producto_id=producto.producto_id,
                    marca_id=producto.marca_id,
                    categoria_id=producto.categoria_id,
                    proveedor_id=producto.proveedor_id,
                )
            ),
            redondeo=contexto.redondeo_de(producto.categoria_id),
            modo_impositivo=contexto.modo_impositivo,
        )
        causa = SIN_CALCULAR if isinstance(resultado, PrecioCalculado) else resultado.causa
        sin_precio.append(ProductoSinPrecio(producto.producto_id, causa))
    return sin_precio


# --- LISTA_PUBLICAR (PRC-02, PRC-04, PRC-06, D6, D14) ---------------------------------------


@dataclass(frozen=True)
class ResultadoPublicacion:
    """Lo que informa `LISTA_PUBLICAR`: la versión publicada, su vigencia y cuántos precios
    tiene."""

    version_id: UUID
    numero: int
    vigencia_desde: datetime
    vigencia_hasta: datetime | None
    cantidad_precios: int


def _como_version_de_lista(version: ListaVersion) -> VersionDeLista:
    return VersionDeLista(
        id=version.id,
        numero=version.numero,
        estado=version.estado,
        vigencia_desde=version.vigencia_desde,
        vigencia_hasta=version.vigencia_hasta,
    )


def publicar_version(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    version_id: UUID,
    vigencia_desde: datetime | None,
    vigencia_hasta: datetime | None,
    actor_id: UUID,
) -> ResultadoPublicacion:
    """`LISTA_PUBLICAR` (PRC-02, D6): publica el borrador con su vigencia. Con el candado de
    la lista (D14), que también toman fijar un precio y regenerar: o el precio manual entra
    antes y se publica con él, o llega después y se rechaza (INV-11).

    Sin vigencia desde rige el momento de la publicación; nunca se publica hacia atrás
    (`VIGENCIA_INVALIDA`). Publicar no recalcula precios ni modifica ninguna otra versión: la
    anterior deja de ser vigente porque esta tiene mayor vigencia desde (PRC-03)."""
    lista = _lista_para_actualizar(organizacion_id, lista_id, sesion)
    if not lista.activo:
        raise ListaInactivaError(f"La lista {lista.nombre!r} está inactiva (PRC-01).")
    version = _version_para_actualizar(organizacion_id, lista_id, version_id, sesion)
    momento = reloj.now()
    cantidad_precios = repository.contar_precios_de_version(organizacion_id, version.id, sesion)
    vigencia = validar_publicacion(
        _como_version_de_lista(version),
        momento=momento,
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        vigencias_publicadas=repository.vigencias_desde_publicadas(
            organizacion_id, lista_id, sesion
        ),
        cantidad_precios=cantidad_precios,
    )
    repository.marcar_publicada(
        organizacion_id,
        sesion,
        version,
        vigencia_desde=vigencia.desde,
        vigencia_hasta=vigencia.hasta,
        publicado_por_id=actor_id,
        publicado_en=momento,
    )
    return ResultadoPublicacion(
        version_id=version.id,
        numero=version.numero,
        vigencia_desde=vigencia.desde,
        vigencia_hasta=vigencia.hasta,
        cantidad_precios=cantidad_precios,
    )


# --- LISTA_ANULAR_VERSION (PRC-05, D6, D14) -------------------------------------------------


@dataclass(frozen=True)
class ResultadoAnulacion:
    """Lo que informa `LISTA_ANULAR_VERSION`."""

    version_id: UUID
    numero: int


def anular_version(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    version_id: UUID,
    actor_id: UUID,
) -> ResultadoAnulacion:
    """`LISTA_ANULAR_VERSION` (PRC-05): anula una versión `PUBLICADA` cuya vigencia desde es
    posterior al momento. Queda `ANULADA` con usuario y momento; sus precios y vigencias no se
    borran ni se modifican (TR-06, INV-11) y una anulada no vuelve a otro estado. Con el
    candado de la lista (D14): de dos anulaciones simultáneas de la misma versión, la segunda
    ve la versión ya anulada (`VERSION_NO_PUBLICADA`)."""
    _lista_para_actualizar(organizacion_id, lista_id, sesion)
    version = _version_para_actualizar(organizacion_id, lista_id, version_id, sesion)
    momento = reloj.now()
    validar_anulacion(_como_version_de_lista(version), momento=momento)
    repository.marcar_anulada(
        organizacion_id, sesion, version, anulado_por_id=actor_id, anulado_en=momento
    )
    return ResultadoAnulacion(version_id=version.id, numero=version.numero)


# --- Resolución de precio (PRC-20, D1, D11 punto 4) -------------------------------------------
#
# Interfaz que usará el change 18a (venta). No depende de `clientes`: la lista asignada al
# cliente llega como dato. Usar otra lista o una versión anterior (PRC-21) y congelar el precio
# por línea (PRC-23) quedan para el 18a.


@dataclass(frozen=True)
class ListaAplicable:
    """La lista con la que se resuelve el precio: la asignada o la predeterminada (PRC-20)."""

    lista_id: UUID
    nombre: str


@dataclass(frozen=True)
class PrecioResuelto:
    """El precio de referencia de un producto y las unidades de referencia con que se calculó
    (guardadas en el precio, no las actuales de la presentación, D1)."""

    precio_final: Decimal
    unidades_referencia: int


@dataclass(frozen=True)
class PreciosVigentes:
    """La versión vigente a un momento y los precios pedidos de ella. Un producto pedido sin
    precio en la versión va en `productos_sin_precio`: nunca se le inventa uno (PRC-10)."""

    version_id: UUID
    numero: int
    vigencia_desde: datetime
    vigencia_hasta: datetime | None
    precios: dict[UUID, PrecioResuelto]
    productos_sin_precio: tuple[UUID, ...]


def resolver_lista_aplicable(
    organizacion_id: UUID, sesion: Session, *, lista_asignada_id: UUID | None
) -> ListaAplicable:
    """La lista aplicable (PRC-20): la asignada al cliente si la tiene y, si no, la
    predeterminada de la organización. Si la que corresponde está inactiva, o no hay
    predeterminada, `SIN_LISTA_APLICABLE`: una asignada inactiva NO cae a la predeterminada.
    Una lista asignada que no existe en la organización responde como inexistente (INV-21)."""
    if lista_asignada_id is not None:
        lista = repository.obtener_lista(organizacion_id, lista_asignada_id, sesion)
        if lista is None:
            raise RecursoNoEncontradoError(
                f"La lista {lista_asignada_id} no existe en esta organización."
            )
    else:
        configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
        predeterminada_id = None if configuracion is None else configuracion.lista_precio_default_id
        if predeterminada_id is None:
            raise SinListaAplicableError(
                "El cliente no tiene lista asignada y la organización no tiene una lista "
                "predeterminada (PRC-20)."
            )
        lista = repository.obtener_lista(organizacion_id, predeterminada_id, sesion)
        if lista is None:  # la clave foránea compuesta lo impide; se falla cerrado igual
            raise SinListaAplicableError("La lista predeterminada no existe (PRC-20).")
    if not lista.activo:
        raise SinListaAplicableError(f"La lista {lista.nombre!r} está inactiva (PRC-20).")
    return ListaAplicable(lista_id=lista.id, nombre=lista.nombre)


def resolver_precios(
    organizacion_id: UUID,
    sesion: Session,
    *,
    lista_id: UUID,
    momento: datetime,
    producto_ids: Collection[UUID] | None,
) -> PreciosVigentes:
    """Los precios de `producto_ids` (todos los de la versión si es `None`) en la versión
    vigente de la lista a `momento` (PRC-20, PRC-03, D6). Lista inexistente o ajena, 404;
    sin versión vigente, `LISTA_SIN_VERSION_VIGENTE`. Solo lectura, sin bloquear: una versión
    publicada no cambia (INV-11)."""
    if momento.tzinfo is None:
        raise ValueError("El momento de la resolución debe tener zona horaria (timestamptz).")
    if repository.obtener_lista(organizacion_id, lista_id, sesion) is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no existe en esta organización.")
    versiones = repository.listar_versiones(organizacion_id, lista_id, sesion)
    vigente = version_vigente([_como_version_de_lista(version) for version in versiones], momento)
    if vigente is None or vigente.vigencia_desde is None:
        raise ListaSinVersionVigenteError(
            f"La lista {lista_id} no tiene una versión vigente en el momento pedido (PRC-03)."
        )
    if producto_ids is None:
        filas = repository.listar_precios_de_version(organizacion_id, vigente.id, sesion)
    else:
        filas = repository.listar_precios_de_productos(
            organizacion_id, vigente.id, producto_ids, sesion
        )
    precios = {
        fila.producto_id: PrecioResuelto(
            precio_final=fila.precio_final, unidades_referencia=fila.unidades_referencia
        )
        for fila in filas
    }
    sin_precio = (
        ()
        if producto_ids is None
        else tuple(dict.fromkeys(id_ for id_ in producto_ids if id_ not in precios))
    )
    return PreciosVigentes(
        version_id=vigente.id,
        numero=vigente.numero,
        vigencia_desde=vigente.vigencia_desde,
        vigencia_hasta=vigente.vigencia_hasta,
        precios=precios,
        productos_sin_precio=sin_precio,
    )


def validar_lista_asignable(organizacion_id: UUID, sesion: Session, *, lista_id: UUID) -> None:
    """Valida la lista que `clientes` asigna a un cliente (CLI-01, D11 punto 1): una lista que
    no existe en la organización del token responde como inexistente (404, INV-21) y una
    inactiva se rechaza con `LISTA_INACTIVA`. La lee `FOR SHARE` (D14): desactivarla y
    asignarla a la vez no deja nunca un cliente activo con una lista inactiva."""
    lista = repository.obtener_lista_para_compartir(organizacion_id, lista_id, sesion)
    if lista is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no existe en esta organización.")
    if not lista.activo:
        raise ListaInactivaError(f"La lista {lista.nombre!r} está inactiva (PRC-01).")


def definir_lista_predeterminada(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    lista_id: UUID,
    actor_id: UUID,
    dispositivo_id_actor: UUID | None,
    operation_id: UUID,
) -> UUID | None:
    """`LISTA_PRECIO_PREDETERMINADA_DEFINIR` (D11 punto 2, D14): define la lista predeterminada
    de la organización y devuelve la anterior. Toma el candado de la lista (el mismo que la
    desactivación, así no se cruzan): lista inexistente o ajena, 404; lista inactiva,
    `LISTA_INACTIVA`. La escritura va por `identidad/service.py`; no modifica ninguna versión
    ni la lista asignada de ningún cliente."""
    lista = _lista_para_actualizar(organizacion_id, lista_id, sesion)
    if not lista.activo:
        raise ListaInactivaError(f"La lista {lista.nombre!r} está inactiva (PRC-01).")
    return identidad_service.definir_lista_precio_default(
        organizacion_id,
        sesion,
        reloj,
        lista_precio_id=lista_id,
        actor_id=actor_id,
        dispositivo_id_actor=dispositivo_id_actor,
        operation_id=operation_id,
    )
