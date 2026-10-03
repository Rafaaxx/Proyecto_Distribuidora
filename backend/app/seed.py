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

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.modules.configuracion import service as configuracion_service
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.permisos import ADMINISTRADOR
from app.modules.identidad.models import Organizacion
from app.modules.identidad.service import DatosConfiguracionInicial

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
MEDIOS_DE_PAGO_INICIALES = ("Efectivo", "Transferencia", "Cheque", "Billetera", "Tarjeta")
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

    organizacion = identidad_service.crear_organizacion_con_configuracion(
        sesion,
        reloj,
        nombre=NOMBRE_ORGANIZACION_INICIAL,
        slug=SLUG_ORGANIZACION_INICIAL,
        cuit=None,
        moneda=MONEDA_INICIAL,
        zona_horaria=ZONA_HORARIA_INICIAL,
        estado="ACTIVA",
        configuracion=DatosConfiguracionInicial(
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

    for nombre in MEDIOS_DE_PAGO_INICIALES:
        configuracion_service.crear_medio_pago(
            organizacion.id, sesion, reloj, nombre=nombre, requiere_referencia=False
        )

    for nombre in MOTIVOS_AJUSTE_STOCK_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="AJUSTE_STOCK", nombre=nombre
        )

    for nombre in MOTIVOS_ANULACION_COMPRA_INICIALES:
        configuracion_service.crear_motivo(
            organizacion.id, sesion, reloj, ambito="ANULACION_COMPRA", nombre=nombre
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


def main() -> None:
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
