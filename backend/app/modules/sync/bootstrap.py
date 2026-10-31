"""El bootstrap del dispositivo (change 21; `design.md` D1 a D9; `02` §6, §13; ADR-006, SYN-11).

Compone UNA respuesta con todo lo que el vendedor necesita para operar sin conexión, leyendo SOLO
por el `service.py` de cada módulo (D1: `sync ──► todos`). Lo hace en una única transacción
`REPEATABLE READ READ ONLY` (D3, excepción de solo lectura a `02` §7.1, ADR-062): el stock, los
saldos, los precios y las reglas corresponden al mismo instante. No escribe nada: ni comando, ni
auditoría, ni cambio.

Nada de lo que sale de acá lleva costos, márgenes, contraseñas ni PIN: de los autorizadores solo
baja la derivación PBKDF2 (hash, sal e iteraciones, D8). Solo se registran en el log los tamaños
de cada sección, nunca valores (`02` §17).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import DomainError
from app.modules.catalogo import service as catalogo_service
from app.modules.clientes import service as clientes_service
from app.modules.configuracion import service as configuracion_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.descuentos import service as descuentos_service
from app.modules.identidad import service as identidad_service
from app.modules.precios import service as precios_service
from app.modules.stock import service as stock_service
from app.modules.sync.schemas import (
    AlcanceBootstrap,
    AlicuotaBootstrap,
    AutorizadorBootstrap,
    BootstrapResponse,
    CatalogosBootstrap,
    ClienteBootstrap,
    ConfiguracionBootstrap,
    ContextoVentaBootstrap,
    CreditoBootstrap,
    DescuentoManualBootstrap,
    JornadaBootstrap,
    ListaBootstrap,
    MedioPagoBootstrap,
    MotivoBootstrap,
    NotaBootstrap,
    NumeracionBootstrap,
    PrecioBootstrap,
    PresentacionBootstrap,
    ProductoBootstrap,
    ReglaDescuentoBootstrap,
    SesionBootstrap,
    StockBootstrap,
    UsuarioBootstrap,
    VersionBootstrap,
)

logger = logging.getLogger(__name__)

PERMISO_VENDER = "VENDER"
PERMISO_USAR_LISTA_ANTERIOR = "USAR_LISTA_ANTERIOR"
_PERMISO_DESCUENTO_MANUAL = "DESCUENTO_MANUAL"
_PERMISO_AUTORIZAR_DESCUENTO = "AUTORIZAR_DESCUENTO"
_PERMISO_SUPERAR_CREDITO = "SUPERAR_CREDITO"
_CERO = "0.00"


class BootstrapSinJornadaError(DomainError):
    """El usuario no tiene una jornada `ABIERTA` propia en el dispositivo del token (RUT-03,
    `design.md` D2). Reutiliza el código estable `JORNADA_REQUERIDA` del bus (SYN-10) con 409:
    la petición es válida pero el estado de la jornada no lo permite."""

    codigo = "JORNADA_REQUERIDA"
    status_http = 409


def _texto(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)


def _abrir_foto_coherente(sesion: Session) -> None:
    """Cierra la transacción implícita que abrió la autenticación (solo leyó) y abre otra
    `REPEATABLE READ READ ONLY` (D3). `SET TRANSACTION` debe ser lo primero que se ejecuta en la
    transacción; vale solo para ella, así que no queda ningún ajuste en la conexión."""
    sesion.rollback()
    sesion.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))


def generar_bootstrap(
    sesion: Session,
    reloj: Clock,
    *,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    entre_secciones: Callable[[str], None] | None = None,
) -> BootstrapResponse:
    """La foto completa de `organizacion_id` para `usuario_id` en `dispositivo_id` (D2, D9).

    Sin jornada `ABIERTA` propia en ese dispositivo, `BootstrapSinJornadaError` (409). Cada
    sección se filtra por el permiso del momento (D2): contexto de venta y autorizadores con
    `VENDER`; versiones anteriores de lista con `USAR_LISTA_ANTERIOR`.

    `entre_secciones(nombre)` es un gancho de prueba: se llama antes de leer cada sección, para
    que una prueba de concurrencia inyecte una pausa y confirme otra transacción en medio."""

    def pausa(seccion: str) -> None:
        if entre_secciones is not None:
            entre_secciones(seccion)

    _abrir_foto_coherente(sesion)
    try:
        ahora = reloj.now()
        pausa("jornada")
        jornada = stock_service.jornada_abierta_con_ubicacion_de(
            organizacion_id, sesion, usuario_id=usuario_id, dispositivo_id=dispositivo_id
        )
        if jornada is None:
            raise BootstrapSinJornadaError(
                "Hace falta una jornada abierta propia en este dispositivo para bajar los datos."
            )
        permisos = identidad_service.listar_permisos_del_usuario(
            organizacion_id, usuario_id, sesion
        )
        puede_vender = PERMISO_VENDER in permisos

        pausa("sesion")
        usuario = identidad_service.obtener_usuario_para_dispositivo(
            organizacion_id, usuario_id, sesion
        )
        numeracion = identidad_service.obtener_numeracion_de_dispositivo(
            organizacion_id, sesion, dispositivo_id=dispositivo_id
        )
        ubicaciones = stock_service.nombres_de_ubicaciones(
            organizacion_id, sesion, {jornada.ubicacion_id}
        )
        if usuario is None or numeracion is None:
            # La sesión autenticada los garantiza (INV-21); se falla cerrado igual.
            raise BootstrapSinJornadaError("La sesión del dispositivo no es válida.")

        pausa("configuracion")
        configuracion = _configuracion(sesion, organizacion_id)
        contexto = _contexto_venta(sesion, organizacion_id, usuario_id) if puede_vender else None

        pausa("catalogos")
        catalogos, valores_de_alicuota = _catalogos(sesion, organizacion_id)

        pausa("productos")
        productos = _productos(sesion, organizacion_id, valores_de_alicuota)

        pausa("clientes")
        clientes_de_la_foto = clientes_service.listar_clientes_para_dispositivo(
            organizacion_id, sesion
        )
        saldos = cuentas_corrientes_service.saldos_de_clientes(organizacion_id, sesion)
        cartera = set(clientes_service.listar_cartera(organizacion_id, usuario_id, sesion))
        clientes = [
            ClienteBootstrap(
                id=c.id,
                codigo=c.codigo,
                nombre=c.nombre,
                razon_social=c.razon_social,
                documento_tipo=c.documento_tipo,
                documento_numero=c.documento_numero,
                direccion=c.direccion,
                telefono=c.telefono,
                estado=c.estado,
                lista_precio_id=c.lista_precio_id,
                es_consumidor_final=c.es_consumidor_final,
                # "vacía = todos" (`01` §19, ADR-060).
                en_cartera=not cartera or c.id in cartera,
                saldo=str(saldos.get(c.id, Decimal(_CERO))),
                credito=CreditoBootstrap(
                    limite=_texto(c.credito.limite),
                    politica=c.credito.politica,
                    tolerancia_tipo=c.credito.tolerancia_tipo,
                    tolerancia_valor=_texto(c.credito.tolerancia_valor),
                ),
            )
            for c in clientes_de_la_foto
        ]

        pausa("listas")
        listas = _listas(
            sesion,
            organizacion_id,
            ahora=ahora,
            con_anteriores=PERMISO_USAR_LISTA_ANTERIOR in permisos,
            lista_asignada_ids={
                c.lista_precio_id for c in clientes_de_la_foto if c.lista_precio_id is not None
            },
            producto_ids=[p.id for p in productos],
        )

        pausa("reglas_descuento")
        reglas = _reglas_de_descuento(sesion, organizacion_id, ahora)

        pausa("stock")
        stock = [
            StockBootstrap(producto_id=producto_id, cantidad_base=cantidad)
            for producto_id, cantidad in sorted(
                stock_service.stock_de_ubicacion_para_vender(
                    organizacion_id, sesion, ubicacion_id=jornada.ubicacion_id
                ).items(),
                key=lambda par: str(par[0]),
            )
        ]

        pausa("autorizadores")
        autorizadores = (
            [
                AutorizadorBootstrap(
                    id=a.usuario_id,
                    nombre=a.nombre,
                    permisos=sorted(a.permisos),
                    pin_hash=a.pin_hash,
                    pin_sal=a.pin_sal,
                    iteraciones=a.iteraciones,
                )
                for a in identidad_service.listar_autorizadores_con_derivacion(
                    organizacion_id, sesion, excluir_usuario_id=usuario_id
                )
            ]
            if puede_vender
            else []
        )

        respuesta = BootstrapResponse(
            generado_en=ahora,
            sesion=SesionBootstrap(
                usuario=UsuarioBootstrap(
                    id=usuario.id, nombre=usuario.nombre, usuario=usuario.usuario
                ),
                permisos=sorted(permisos),
                jornada=JornadaBootstrap(
                    id=jornada.jornada_id,
                    ubicacion_id=jornada.ubicacion_id,
                    ubicacion_nombre=ubicaciones.get(jornada.ubicacion_id),
                    abierta_en=jornada.abierta_en,
                ),
                numeracion=NumeracionBootstrap(
                    prefijo=numeracion.prefijo, ultimo_correlativo=numeracion.ultimo_correlativo
                ),
            ),
            configuracion=configuracion,
            contexto_venta=contexto,
            catalogos=catalogos,
            productos=productos,
            clientes=clientes,
            listas=listas,
            reglas_descuento=reglas,
            stock=stock,
            autorizadores=autorizadores,
        )
    finally:
        # Termina la transacción de solo lectura: no hay nada que confirmar.
        sesion.rollback()
    logger.info(
        "bootstrap generado",
        extra={
            "productos": len(productos),
            "clientes": len(clientes),
            "listas": len(listas),
            "reglas_descuento": len(reglas),
            "stock": len(stock),
            "autorizadores": len(autorizadores),
        },
    )
    return respuesta


def _configuracion(sesion: Session, organizacion_id: UUID) -> ConfiguracionBootstrap:
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    if organizacion is None or configuracion is None:
        raise BootstrapSinJornadaError("La organización no tiene configuración.")
    return ConfiguracionBootstrap(
        organizacion_id=organizacion.id,
        nombre=organizacion.nombre,
        cuit=organizacion.cuit,
        moneda=organizacion.moneda,
        zona_horaria=organizacion.zona_horaria,
        condicion_iva=configuracion.condicion_iva,
        modo_impositivo=configuracion.modo_impositivo,
        politica_credito=configuracion.politica_credito_default,
        tolerancia_tipo=configuracion.tolerancia_offline_tipo,
        tolerancia_valor=_texto(configuracion.tolerancia_offline_valor),
        permite_consumidor_final=configuracion.permite_consumidor_final,
        consumidor_final_id=configuracion.cliente_consumidor_final_id,
        estado_facturacion_default=configuracion.estado_facturacion_default,
        intentos_pin_max=configuracion.intentos_pin_max,
        motivo_obligatorio_lista=configuracion.motivo_obligatorio_lista,
        nota=NotaBootstrap(
            domicilio=configuracion.nota_venta_domicilio,
            telefono=configuracion.nota_venta_telefono,
            muestra_saldo=configuracion.nota_venta_muestra_saldo,
        ),
    )


def _contexto_venta(
    sesion: Session, organizacion_id: UUID, usuario_id: UUID
) -> ContextoVentaBootstrap | None:
    """Tope, permisos y habilitaciones de quien vende (DSC-06, SYN-11): la misma regla que el
    contexto de venta de `ventas` (tope propio, si no el del rol), sin depender de ese módulo."""
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    usuario = identidad_service.obtener_datos_para_descuento_manual(
        organizacion_id, usuario_id, sesion
    )
    if configuracion is None or usuario is None:
        return None
    tiene_permiso = _PERMISO_DESCUENTO_MANUAL in usuario.permisos
    tope = (
        (usuario.tope_rol if usuario.tope_propio is None else usuario.tope_propio)
        if tiene_permiso
        else None
    )
    return ContextoVentaBootstrap(
        descuento_manual=DescuentoManualBootstrap(
            habilitado=configuracion.descuento_manual_habilitado,
            motivo_obligatorio=configuracion.motivo_obligatorio_descuento is True,
            tiene_permiso=tiene_permiso,
            tope=_texto(tope),
            puede_autorizar=_PERMISO_AUTORIZAR_DESCUENTO in usuario.permisos,
        ),
        puede_superar_credito=_PERMISO_SUPERAR_CREDITO in usuario.permisos,
    )


def _catalogos(
    sesion: Session, organizacion_id: UUID
) -> tuple[CatalogosBootstrap, dict[UUID, Decimal]]:
    medios = sorted(
        configuracion_service.listar_medios_pago_activos(organizacion_id, sesion),
        key=lambda m: (m.nombre.lower(), str(m.id)),
    )
    motivos = sorted(
        configuracion_service.listar_motivos_activos(organizacion_id, sesion),
        key=lambda m: (m.ambito, m.nombre.lower(), str(m.id)),
    )
    alicuotas = sorted(
        configuracion_service.listar_alicuotas_activas(organizacion_id, sesion),
        key=lambda a: (a.valor, str(a.id)),
    )
    catalogos = CatalogosBootstrap(
        medios_pago=[
            MedioPagoBootstrap(id=m.id, nombre=m.nombre, requiere_referencia=m.requiere_referencia)
            for m in medios
        ],
        motivos=[MotivoBootstrap(id=m.id, ambito=m.ambito, nombre=m.nombre) for m in motivos],
        alicuotas=[
            AlicuotaBootstrap(id=a.id, nombre=a.nombre, valor=str(a.valor)) for a in alicuotas
        ],
    )
    return catalogos, {a.id: a.valor for a in alicuotas}


def _productos(
    sesion: Session, organizacion_id: UUID, valores_de_alicuota: dict[UUID, Decimal]
) -> list[ProductoBootstrap]:
    productos: list[ProductoBootstrap] = []
    for producto in catalogo_service.listar_productos_para_dispositivo(organizacion_id, sesion):
        valor = valores_de_alicuota.get(producto.alicuota_id)
        if valor is None:
            alicuota = configuracion_service.obtener_alicuota_por_id(
                organizacion_id, producto.alicuota_id, sesion
            )
            valor = None if alicuota is None else alicuota.valor
        referencia = next((p for p in producto.presentaciones if p.es_referencia), None)
        productos.append(
            ProductoBootstrap(
                id=producto.producto_id,
                codigo=producto.codigo,
                nombre=producto.nombre,
                categoria_id=producto.categoria_id,
                marca_id=producto.marca_id,
                alicuota_id=producto.alicuota_id,
                alicuota_valor=str(valor if valor is not None else Decimal("0")),
                presentacion_referencia_id=None
                if referencia is None
                else referencia.presentacion_id,
                presentaciones=[
                    PresentacionBootstrap(
                        id=p.presentacion_id,
                        nombre=p.nombre,
                        unidades_base=p.unidades_base,
                        es_referencia=p.es_referencia,
                    )
                    for p in producto.presentaciones
                ],
            )
        )
    return productos


def _listas(
    sesion: Session,
    organizacion_id: UUID,
    *,
    ahora: datetime,
    con_anteriores: bool,
    lista_asignada_ids: set[UUID],
    producto_ids: list[UUID],
) -> list[ListaBootstrap]:
    """D5: sin `USAR_LISTA_ANTERIOR`, la predeterminada y las asignadas a los clientes bajados con
    vigente y programadas; con el permiso, todas las listas activas con las históricas (PRC-21)."""
    lista_ids = (
        None
        if con_anteriores
        else precios_service.listas_aplicables_a_clientes(
            organizacion_id, sesion, lista_asignada_ids=lista_asignada_ids
        )
    )
    listas = precios_service.listas_para_dispositivo(
        organizacion_id,
        sesion,
        momento=ahora,
        lista_ids=lista_ids,
        producto_ids=producto_ids,
        con_historicas=con_anteriores,
    )
    return [
        ListaBootstrap(
            id=lista.lista_id,
            nombre=lista.nombre,
            es_predeterminada=lista.es_predeterminada,
            versiones=[
                VersionBootstrap(
                    id=v.version_id,
                    numero=v.numero,
                    estado=v.estado,
                    vigencia_desde=v.vigencia_desde,
                    vigencia_hasta=v.vigencia_hasta,
                    precios=[
                        PrecioBootstrap(
                            producto_id=p.producto_id,
                            precio_referencia=str(p.precio_referencia),
                            unidades_referencia=p.unidades_referencia,
                        )
                        for p in v.precios
                    ],
                )
                for v in sorted(lista.versiones, key=lambda v: v.numero)
            ],
        )
        for lista in listas
    ]


def _reglas_de_descuento(
    sesion: Session, organizacion_id: UUID, ahora: datetime
) -> list[ReglaDescuentoBootstrap]:
    return [
        ReglaDescuentoBootstrap(
            id=UUID(item.regla.id),
            nombre=item.nombre,
            tipo=item.regla.tipo,
            medida=item.regla.medida,
            operador=item.regla.operador,
            umbral=str(item.regla.umbral),
            accion_tipo=item.regla.accion_tipo,
            accion_porcentaje=_texto(item.regla.accion_porcentaje),
            accion_importe=_texto(item.regla.accion_importe),
            acumulable=item.regla.acumulable,
            prioridad=item.regla.prioridad,
            vigencia_desde=item.vigencia_desde,
            vigencia_hasta=item.vigencia_hasta,
            alcances=[
                AlcanceBootstrap(tipo=a.tipo, entidad_id=UUID(a.entidad_id))
                for a in item.regla.alcances
            ],
        )
        for item in descuentos_service.reglas_para_dispositivo(organizacion_id, sesion, ahora)
    ]
