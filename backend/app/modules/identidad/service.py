"""Interfaz pública de `identidad` (`CLAUDE.md` §4: un módulo usa a otro
solo a través de su `service.py`).

Expone la lectura de organización y configuración, y el alta de una
organización con su configuración en una sola operación. Sin `commit`: la
transacción la gestiona quien llama (`docs/02-arquitectura.md` §5.2); en
este change, la sesión de la siembra o de la prueba, porque todavía no
existe el bus de comandos (change 04).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.identidad import repository
from app.modules.identidad.domain.valores import (
    validar_estado_facturacion_default,
    validar_estado_organizacion,
    validar_modo_impositivo,
    validar_politica_credito_default,
)
from app.modules.identidad.models import ConfiguracionOrganizacion, Organizacion


@dataclass(frozen=True)
class DatosConfiguracionInicial:
    """Parámetros de `configuracion_organizacion` para el alta de una
    organización nueva. Los que `01` §4 marca "a definir al configurar"
    quedan explícitamente en `None` cuando así se los pase (tarea 8.3)."""

    modo_impositivo: str
    politica_credito_default: str
    estado_facturacion_default: str
    intentos_pin_max: int
    descuento_manual_habilitado: bool
    motivo_obligatorio_lista: bool
    lista_precio_default_id: UUID | None = None
    tolerancia_offline_tipo: str | None = None
    tolerancia_offline_valor: Decimal | None = None
    motivo_obligatorio_descuento: bool | None = None
    redondeo_multiplo: Decimal | None = None
    redondeo_direccion: str | None = None
    permite_consumidor_final: bool | None = None
    cliente_consumidor_final_id: UUID | None = None
    modalidad_iva_default: str | None = None
    app_version_minima: str | None = None
    desvio_reloj_max_segundos: int | None = None


def crear_organizacion_con_configuracion(
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    cuit: str | None,
    moneda: str,
    zona_horaria: str,
    estado: str,
    configuracion: DatosConfiguracionInicial,
) -> Organizacion:
    """Da de alta una organización y su fila de configuración en una sola
    operación. Valida el dominio cerrado de `estado`, `modo_impositivo`,
    `politica_credito_default` y `estado_facturacion_default` antes de
    escribir nada."""
    validar_estado_organizacion(estado)
    validar_modo_impositivo(configuracion.modo_impositivo)
    validar_politica_credito_default(configuracion.politica_credito_default)
    validar_estado_facturacion_default(configuracion.estado_facturacion_default)

    momento = reloj.now()
    organizacion_id = nuevo_id()

    organizacion = repository.crear_organizacion(
        organizacion_id,
        sesion,
        nombre=nombre,
        cuit=cuit,
        moneda=moneda,
        zona_horaria=zona_horaria,
        estado=estado,
        momento=momento,
    )
    repository.crear_configuracion(
        organizacion_id,
        sesion,
        modo_impositivo=configuracion.modo_impositivo,
        politica_credito_default=configuracion.politica_credito_default,
        estado_facturacion_default=configuracion.estado_facturacion_default,
        intentos_pin_max=configuracion.intentos_pin_max,
        descuento_manual_habilitado=configuracion.descuento_manual_habilitado,
        motivo_obligatorio_lista=configuracion.motivo_obligatorio_lista,
        lista_precio_default_id=configuracion.lista_precio_default_id,
        tolerancia_offline_tipo=configuracion.tolerancia_offline_tipo,
        tolerancia_offline_valor=configuracion.tolerancia_offline_valor,
        motivo_obligatorio_descuento=configuracion.motivo_obligatorio_descuento,
        redondeo_multiplo=configuracion.redondeo_multiplo,
        redondeo_direccion=configuracion.redondeo_direccion,
        permite_consumidor_final=configuracion.permite_consumidor_final,
        cliente_consumidor_final_id=configuracion.cliente_consumidor_final_id,
        modalidad_iva_default=configuracion.modalidad_iva_default,
        app_version_minima=configuracion.app_version_minima,
        desvio_reloj_max_segundos=configuracion.desvio_reloj_max_segundos,
        momento=momento,
    )
    return organizacion


def obtener_organizacion(organizacion_id: UUID, sesion: Session) -> Organizacion | None:
    return repository.obtener_organizacion_por_id(organizacion_id, sesion)


def obtener_configuracion(
    organizacion_id: UUID, sesion: Session
) -> ConfiguracionOrganizacion | None:
    """Lectura de la configuración de `organizacion_id` para otros módulos
    (`design.md`: `identidad.service` expone esta lectura). Nunca devuelve
    la fila de otra organización: el filtro va siempre por `organizacion_id`."""
    return repository.obtener_configuracion(organizacion_id, sesion)


def fecha_de_negocio(organizacion_id: UUID, sesion: Session, reloj: Clock) -> date | None:
    """Deriva la fecha de negocio a partir del momento actual del reloj
    inyectable y la zona horaria de la organización (TR-04). Devuelve `None`
    si la organización no tiene configuración... en realidad la zona horaria
    vive en `organizacion`, no en su configuración: se usa `organizacion.
    zona_horaria` (`docs/03` §4)."""
    organizacion = repository.obtener_organizacion_por_id(organizacion_id, sesion)
    if organizacion is None:
        return None
    momento_utc = reloj.now()
    return momento_utc.astimezone(ZoneInfo(organizacion.zona_horaria)).date()
