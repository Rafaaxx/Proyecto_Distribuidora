"""Siembra idempotente de la organización inicial (`design.md` D4).

Comando de aplicación (`python -m app.seed`), fuera de las migraciones: usa
los servicios de `identidad` y `configuracion` (no SQL suelto), para que las
validaciones de dominio se ejerciten en el mismo camino que usará el alta de
organizaciones cuando exista el bus de comandos (change 04).

Idempotencia (tarea 8.6): hoy la única forma de crear una `organizacion` es
esta siembra (el alta por comando llega en el change 04), así que la
presencia de cualquier fila en `organizacion` significa "ya sembrado" y la
siembra no toca nada. Cuando el change 04 agregue el alta de organizaciones
por comando, esta condición deja de alcanzar (podría haber organizaciones
reales que no vinieron de la siembra) y hay que reemplazarla por un marcador
explícito; señalado para revisión humana junto con D2 (no se resuelve acá
porque no hay otro camino de alta todavía).
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app import modelos  # noqa: F401 (registra todos los modelos: claves foráneas entre módulos)
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.configuracion import service as configuracion_service
from app.modules.descuentos import service as descuentos_service
from app.modules.descuentos.service import DatosDeRegla
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.permisos import (
    ADMINISTRACION,
    ADMINISTRADOR,
    CONSULTA_DIRECCION,
    SUPERVISOR_COMERCIAL,
    VENDEDOR_REPARTIDOR,
)
from app.modules.identidad.models import Organizacion
from app.modules.identidad.service import DatosConfiguracionInicial
from app.modules.stock import service as stock_service

# `01` §4, columna "Organización inicial". Los parámetros que esa columna
# marca "A definir al configurar" NO se sembran con un valor (tarea 8.3): se
# dejan como `None` explícito pasándolos a `DatosConfiguracionInicial` con su
# default (que es `None`).
NOMBRE_ORGANIZACION_INICIAL = "Organización inicial"
# `ADR-021`: resuelve la organización en el login antes de que exista un
# token. En un despliegue real, cada instancia tiene su propio slug (una
# organización por instancia, `ADR-021` Alternativas); acá se sembra uno
# fijo porque la siembra crea una sola organización.
SLUG_ORGANIZACION_INICIAL = "organizacion-inicial"
MONEDA_INICIAL = "ARS"
ZONA_HORARIA_INICIAL = "America/Argentina/Mendoza"

ALICUOTAS_INICIALES = (
    ("21%", Decimal("0.210000")),
    ("10,5%", Decimal("0.105000")),
    ("0%", Decimal("0.000000")),
)
MEDIOS_DE_PAGO_INICIALES = (
    ("Efectivo", False),
    ("Transferencia", True),
    ("Cheque", True),
    ("Billetera", False),
    ("Tarjeta", True),
)
"""(nombre, `requiere_referencia`): Transferencia, Cheque y Tarjeta piden referencia (`01` §4,
COB-02; change 17b, D5-A)."""
MOTIVOS_AJUSTE_STOCK_INICIALES = (
    "Rotura",
    "Vencimiento",
    "Muestra",
    "Consumo interno",
    "Diferencia de inventario",
    "Otro",
)
MOTIVOS_ANULACION_COMPRA_INICIALES = (
    "Error de carga",
    "Devolución al proveedor",
    "Otro",
)
"""Change 11 (CMP-05, `design.md` D8, aprobados el 2026-10-02). La migración
`c0d1e2f3a4b5` siembra los mismos nombres en las organizaciones existentes."""

MOTIVOS_ANULACION_PAGO_INICIALES = (
    "Error de carga",
    "Pago rechazado o devuelto",
    "Otro",
)
"""Change 12 (PAG-03, `design.md` D1, aprobados el 2026-10-03). La migración
`d1e2f3a4b5c6` siembra los mismos nombres en las organizaciones existentes. Sin
alguno de estos motivos la organización no podría anular un pago a proveedor
(`PAGO_PROVEEDOR_ANULAR` exige `anulacion_motivo_id`)."""

MOTIVOS_ANULACION_TRANSFERENCIA_INICIALES = ("Error de carga", "Otro")
MOTIVOS_ANULACION_AJUSTE_INICIALES = ("Error de carga", "Otro")
"""Change 14 (TR-06, `design.md` D5.3, aprobados el 2026-10-07). La migración
`f3a4b5c6d7e8` siembra los mismos nombres en las organizaciones existentes. Sin alguno de
estos motivos la organización no podría anular una transferencia ni un ajuste."""

MOTIVOS_LIBERACION_JORNADA_INICIALES = (
    "Dispositivo perdido o averiado",
    "Vendedor ausente",
    "Otro",
)
"""Change 15 (RUT-09, TR-09, `design.md` D13, aprobados el 2026-10-09). La migración
`a4b5c6d7e8f9` siembra los mismos nombres en las organizaciones existentes. Sin alguno de
estos motivos la organización no podría liberar una jornada (`JORNADA_LIBERAR` exige uno)."""

MOTIVOS_ANULACION_COBRANZA_INICIALES = (
    "Error de carga",
    "Pago rechazado o no acreditado",
    "Otro",
)
"""Change 17 (COB-05, `design.md` D6, aprobados el 2026-10-15). La migración `d7e8f9a0b1c2`
siembra los mismos nombres en las organizaciones existentes. Sin alguno de estos motivos la
organización no podría anular una cobranza (`COBRANZA_ANULAR` exige uno)."""

MOTIVOS_ANULACION_VENTA_INICIALES = (
    "Error de carga",
    "Devolución del cliente",
    "Otro",
)
"""Change 19 (VTA-20, `design.md` D12, aprobados el 2026-10-24). La migración `d9e0f1a2b3c4`
siembra los mismos nombres en las organizaciones existentes que no tengan ninguno del ámbito.
Sin alguno de estos motivos la organización no podría anular una venta (`VENTA_ANULAR` exige
uno)."""


MOTIVOS_LISTA_ANTERIOR_INICIALES = (
    "Precio acordado con el cliente",
    "Error en la lista vigente",
    "Otro",
)
"""Change 18a (PRC-21, `design.md` D6, aprobados el 2026-10-17). La migración `a2b3c4d5e6f7`
siembra los mismos nombres en las organizaciones existentes. Sin alguno de estos motivos la
organización no podría vender con otra lista o con una versión anterior cuando la configuración
exige motivo."""

MOTIVOS_DESCUENTO_MANUAL_INICIALES = (
    "Cliente frecuente",
    "Negociación por volumen",
    "Producto próximo a vencer",
    "Compensación por reclamo",
    "Otro",
)
"""Change 18b (DSC-06, `design.md` D13, aprobados el 2026-10-21). La migración `b6c7d8e9f0a1`
siembra los mismos nombres en las organizaciones existentes. Sin alguno de estos motivos la
organización no podría elegir uno cuando exige motivo en el descuento manual."""


class BaseSinMigrarError(RuntimeError):
    """La siembra corrió contra una base sin las migraciones de este change
    aplicadas (tarea 8.1: "Sembrar sobre una base sin migrar falla
    explícitamente")."""


class AdminPasswordNoDefinidaError(RuntimeError):
    """La puesta en marcha no recibió la contraseña del administrador
    inicial (tarea 8.13, `design.md` D8: ningún secreto tiene valor por
    defecto). No se crea ningún usuario ni organización cuando falta."""


def _password_administrador_desde_entorno() -> str:
    valor = os.environ.get("ADMIN_PASSWORD")
    if not valor:
        raise AdminPasswordNoDefinidaError(
            "ADMIN_PASSWORD no está definida. La puesta en marcha no puede crear el "
            "usuario administrador sin una contraseña provista (design.md D8)."
        )
    return valor


def _ya_sembrado(sesion: Session) -> bool:
    try:
        return sesion.query(Organizacion).first() is not None
    except ProgrammingError as error:
        raise BaseSinMigrarError(
            "No se pudo consultar 'organizacion': la base no tiene las migraciones "
            "de este change aplicadas. Corré `alembic upgrade head` antes de sembrar."
        ) from error


def _sembrar_organizacion(
    sesion: Session, reloj: Clock, *, nombre: str, slug: str, password_administrador: str
) -> Organizacion:
    """Crea una organización con su configuración, sus catálogos, sus cinco roles y su `admin`.
    Lo comparten la siembra inicial y la del escenario de aceptación (la segunda organización)."""
    organizacion = identidad_service.crear_organizacion_con_configuracion(
        sesion,
        reloj,
        nombre=nombre,
        slug=slug,
        cuit=None,
        moneda=MONEDA_INICIAL,
        zona_horaria=ZONA_HORARIA_INICIAL,
        estado="ACTIVA",
        configuracion=DatosConfiguracionInicial(
            # `00` §5, 11b D9: la distribuidora es monotributista; vende a precio final
            # (modo A) y no tiene modalidad de IVA al facturar (D2).
            condicion_iva="MONOTRIBUTO",
            modo_impositivo="A",
            politica_credito_default="AUTORIZAR",
            estado_facturacion_default="NO_REQUIERE",
            intentos_pin_max=5,
            descuento_manual_habilitado=True,
            motivo_obligatorio_lista=True,
            # `lista_precio_default_id` y `cliente_consumidor_final_id` quedan
            # en None: sus tablas destino llegan en los changes 13 y 07
            # (`design.md` D3, tarea 8.4).
            # Todo lo demás queda en None: "A definir al configurar" (`01` §4,
            # tarea 8.3). No se inventan valores por omisión.
        ),
    )

    for nombre, valor in ALICUOTAS_INICIALES:
        configuracion_service.crear_alicuota(
            organizacion.id, sesion, reloj, nombre=nombre, valor=valor
        )

    for nombre, requiere_referencia in MEDIOS_DE_PAGO_INICIALES:
        configuracion_service.crear_medio_pago(
            organizacion.id, sesion, reloj, nombre=nombre, requiere_referencia=requiere_referencia
        )

    for nombre in MOTIVOS_AJUSTE_STOCK_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="AJUSTE_STOCK", nombre=nombre
        )

    for nombre in MOTIVOS_ANULACION_COMPRA_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="ANULACION_COMPRA", nombre=nombre
        )

    for nombre in MOTIVOS_ANULACION_PAGO_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="ANULACION_PAGO", nombre=nombre
        )

    for nombre in MOTIVOS_ANULACION_TRANSFERENCIA_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="ANULACION_TRANSFERENCIA", nombre=nombre
        )

    for nombre in MOTIVOS_ANULACION_AJUSTE_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="ANULACION_AJUSTE", nombre=nombre
        )

    for nombre in MOTIVOS_LIBERACION_JORNADA_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="LIBERACION_JORNADA", nombre=nombre
        )

    for nombre in MOTIVOS_ANULACION_COBRANZA_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="ANULACION_COBRANZA", nombre=nombre
        )

    for nombre in MOTIVOS_ANULACION_VENTA_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="ANULACION_VENTA", nombre=nombre
        )

    for nombre in MOTIVOS_LISTA_ANTERIOR_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="LISTA_ANTERIOR", nombre=nombre
        )

    for nombre in MOTIVOS_DESCUENTO_MANUAL_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="DESCUENTO_MANUAL", nombre=nombre
        )

    roles = identidad_service.crear_plantillas_de_rol_iniciales(organizacion.id, sesion, reloj)
    identidad_service.crear_usuario_administrador_inicial(
        organizacion.id,
        sesion,
        reloj,
        rol_administrador_id=roles[ADMINISTRADOR].id,
        password=password_administrador,
    )

    return organizacion


def sembrar(sesion: Session, reloj: Clock, *, password_administrador: str) -> Organizacion | None:
    """Siembra la organización inicial y sus catálogos si todavía no existe
    ninguna organización. Devuelve la organización sembrada, o `None` si ya
    estaba sembrada (no vuelve a crear ni a pisar nada existente, tarea 8.6
    y, para el administrador, tarea 8.13: "repetir la puesta en marcha no
    pisa la contraseña existente").

    `password_administrador` es obligatoria y sin valor por defecto (tarea
    8.13, `design.md` D8): si falta, falla antes de crear nada, ni siquiera
    la organización."""
    if not password_administrador:
        raise AdminPasswordNoDefinidaError(
            "password_administrador vacía: la puesta en marcha no puede crear el "
            "usuario administrador sin una contraseña provista (design.md D8)."
        )
    if _ya_sembrado(sesion):
        return None

    return _sembrar_organizacion(
        sesion,
        reloj,
        nombre=NOMBRE_ORGANIZACION_INICIAL,
        slug=SLUG_ORGANIZACION_INICIAL,
        password_administrador=password_administrador,
    )


# --- Escenario de aceptación (change 28, D14) -------------------------------------------------
#
# `python -m app.seed --escenario-aceptacion` deja lista la base del entorno de aceptación
# (`infra/aceptacion.env`, compose de producción en un proyecto aparte, descartable): la
# organización inicial con los usuarios de nombres de desarrollo, la configuración que la
# demostración necesita y una segunda organización para el control de aislamiento. Productos,
# clientes, proveedores, stock y saldos NO se siembran: los carga el criterio 1 importando
# planillas. La contraseña es de prueba y fija: SOLO para ese entorno desechable.

PASSWORD_DE_PRUEBA_ACEPTACION = "Aceptacion-2026"
"""Contraseña común de todos los usuarios del entorno de aceptación. No sirve fuera de él."""

SLUG_SEGUNDA_ORGANIZACION = "organizacion-dos"
NOMBRE_SEGUNDA_ORGANIZACION = "Segunda organización"

USUARIOS_DE_ACEPTACION: tuple[tuple[str, str], ...] = (
    ("admin", ADMINISTRADOR),
    ("administracion", ADMINISTRACION),
    ("ges01", ADMINISTRACION),
    ("consulta", CONSULTA_DIRECCION),
    ("supervisor", SUPERVISOR_COMERCIAL),
    ("sup01", SUPERVISOR_COMERCIAL),
    ("vendedor", VENDEDOR_REPARTIDOR),
    ("vendedor2", VENDEDOR_REPARTIDOR),
)
"""(usuario, rol): los mismos nombres que el usuario tiene en desarrollo."""

TOPE_DESCUENTO_VENDEDOR_ACEPTACION = "0.100000"
TOLERANCIA_ACEPTACION_IMPORTE = "50000.00"
NOMBRE_REGLA_VOLUMEN_ACEPTACION = "Volumen 20 cajas"
CATEGORIAS_DE_ACEPTACION = ("Vinos", "Cervezas")
"""Las planillas de productos referencian la categoría por nombre y no la crean al vuelo
(IMP-04): sin ellas el criterio 1 no podría importar los productos."""


def sembrar_escenario_aceptacion(sesion: Session, reloj: Clock) -> bool:
    """Siembra el escenario de aceptación sobre una base migrada, por los servicios de cada
    módulo. Repetible: un paso ya hecho no se repite ni se pisa. Devuelve `True` si creó algo y
    `False` si todo estaba (la segunda corrida no cambia nada). Sin `commit`."""
    creo = _sembrar_primera_organizacion_de_aceptacion(sesion, reloj)
    segunda = identidad_service.resolver_organizacion_por_slug(SLUG_SEGUNDA_ORGANIZACION, sesion)
    if segunda is None:
        _sembrar_organizacion(
            sesion,
            reloj,
            nombre=NOMBRE_SEGUNDA_ORGANIZACION,
            slug=SLUG_SEGUNDA_ORGANIZACION,
            password_administrador=PASSWORD_DE_PRUEBA_ACEPTACION,
        )
        creo = True
    return creo


def _sembrar_primera_organizacion_de_aceptacion(sesion: Session, reloj: Clock) -> bool:
    organizacion = identidad_service.resolver_organizacion_por_slug(
        SLUG_ORGANIZACION_INICIAL, sesion
    )
    if organizacion is None:
        organizacion = _sembrar_organizacion(
            sesion,
            reloj,
            nombre=NOMBRE_ORGANIZACION_INICIAL,
            slug=SLUG_ORGANIZACION_INICIAL,
            password_administrador=PASSWORD_DE_PRUEBA_ACEPTACION,
        )
    org_id = organizacion.id
    # Marcador de "ya sembrado el escenario": el último usuario de la lista.
    ultimo, _ = USUARIOS_DE_ACEPTACION[-1]
    if identidad_repository.obtener_usuario_por_nombre_usuario(org_id, ultimo, sesion):
        return False

    roles = {rol.nombre: rol for rol in identidad_repository.listar_roles(org_id, sesion)}
    admin = identidad_repository.obtener_usuario_por_nombre_usuario(org_id, "admin", sesion)
    assert admin is not None  # lo crea `_sembrar_organizacion`
    for nombre_usuario, rol in USUARIOS_DE_ACEPTACION:
        if identidad_repository.obtener_usuario_por_nombre_usuario(org_id, nombre_usuario, sesion):
            continue
        identidad_service.crear_usuario(
            org_id,
            sesion,
            reloj,
            usuario=nombre_usuario,
            nombre=nombre_usuario,
            email=None,
            password=PASSWORD_DE_PRUEBA_ACEPTACION,
            rol_id=roles[rol].id,
            actor_id=admin.id,
        )

    ubicaciones = stock_service.listar_ubicaciones(
        org_id, sesion, activo=None, cursor=None, limite=None
    ).ubicaciones
    if not ubicaciones:
        for nombre, tipo, requiere_toma in (
            ("Depósito central", "DEPOSITO", False),
            ("Camioneta 1", "VEHICULO", True),
        ):
            stock_service.crear_ubicacion(
                org_id,
                sesion,
                reloj,
                nombre=nombre,
                tipo=tipo,
                requiere_toma=requiere_toma,
                actor_id=admin.id,
            )

    existentes = {c.nombre for c in catalogo_service.listar_categorias(org_id, sesion)}
    for nombre in CATEGORIAS_DE_ACEPTACION:
        if nombre not in existentes:
            catalogo_service.crear_categoria(
                org_id, sesion, reloj, nombre=nombre, actor_id=admin.id
            )

    identidad_service.configurar_credito_organizacion(
        org_id,
        sesion,
        reloj,
        politica="AUTORIZAR",
        tolerancia_tipo="IMPORTE",
        tolerancia_valor=TOLERANCIA_ACEPTACION_IMPORTE,
        actor_id=admin.id,
        dispositivo_id_actor=None,
        operation_id=nuevo_id(),
    )
    identidad_service.definir_tope_descuento_de_rol(
        org_id,
        sesion,
        reloj,
        rol_id=roles[VENDEDOR_REPARTIDOR].id,
        tope_nuevo=TOPE_DESCUENTO_VENDEDOR_ACEPTACION,
        actor_id=admin.id,
        dispositivo_id_actor=None,
        operation_id=nuevo_id(),
    )
    regla = descuentos_service.crear_regla(
        org_id,
        sesion,
        reloj,
        datos=DatosDeRegla(
            nombre=NOMBRE_REGLA_VOLUMEN_ACEPTACION,
            tipo="VOLUMEN_OPERACION",
            medida="CAJAS_EQUIVALENTES",
            operador="GTE",
            umbral="20",
            accion_tipo="PORCENTAJE",
            accion_valor="0.050000",
            prioridad=1,
            acumulable=False,
            alcances=[],
            vigencia_desde=None,
            vigencia_hasta=None,
        ),
        actor_id=admin.id,
    )
    descuentos_service.activar_regla(org_id, sesion, reloj, regla_id=regla.id, actor_id=admin.id)
    return True


def _main_escenario_aceptacion() -> None:
    settings = Settings()  # type: ignore[call-arg]
    engine = crear_engine(settings.database_url)
    factory: sessionmaker[Session] = crear_session_factory(engine)
    with factory() as sesion:
        try:
            creo = sembrar_escenario_aceptacion(sesion, SystemClock())
        except ProgrammingError as error:
            sesion.rollback()
            print(
                "error: la base no tiene las migraciones aplicadas. Corré `alembic upgrade head`.",
                file=sys.stderr,
            )
            raise SystemExit(1) from error
        sesion.commit()
    print(
        "Escenario de aceptación sembrado."
        if creo
        else "El escenario de aceptación ya estaba sembrado: no se hizo nada."
    )


def main() -> None:
    if "--escenario-aceptacion" in sys.argv[1:]:
        _main_escenario_aceptacion()
        return
    try:
        password_administrador = _password_administrador_desde_entorno()
    except AdminPasswordNoDefinidaError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    settings = Settings()  # type: ignore[call-arg]
    engine = crear_engine(settings.database_url)
    factory: sessionmaker[Session] = crear_session_factory(engine)
    reloj = SystemClock()

    with factory() as sesion:
        try:
            resultado = sembrar(sesion, reloj, password_administrador=password_administrador)
        except BaseSinMigrarError as error:
            sesion.rollback()
            print(f"error: {error}", file=sys.stderr)
            raise SystemExit(1) from error

        sesion.commit()

    if resultado is None:
        print("La organización inicial ya estaba sembrada: no se hizo nada.")
    else:
        print(f"Organización inicial sembrada: {resultado.id}")


if __name__ == "__main__":
    main()
