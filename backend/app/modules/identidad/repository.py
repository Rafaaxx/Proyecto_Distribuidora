"""Acceso a datos de `identidad` (`docs/02-arquitectura.md` §8).

Contrato no negociable: todo método público recibe `organizacion_id` como
primer parámetro obligatorio, y lo usa para filtrar toda consulta. Para
`organizacion` (la raíz sin padre) el filtro es sobre su propio `id`: el
`organizacion_id` de un método de este repositorio siempre identifica la
organización que la operación puede tocar, sin excepción (`tests/unit/
test_repositorios_organizacion_obligatoria.py`, tarea 6.3).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.identidad.models import ConfiguracionOrganizacion, Organizacion


def crear_organizacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    nombre: str,
    cuit: str | None,
    moneda: str,
    zona_horaria: str,
    estado: str,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Organizacion:
    """Crea `organizacion`. `organizacion_id` es el `id` que tendrá la
    organización nueva: es la única operación de este repositorio donde
    `organizacion_id` nace en vez de acotar una fila existente."""
    organizacion = Organizacion(
        id=organizacion_id,
        nombre=nombre,
        cuit=cuit,
        moneda=moneda,
        zona_horaria=zona_horaria,
        estado=estado,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


def obtener_organizacion_por_id(organizacion_id: UUID, sesion: Session) -> Organizacion | None:
    return sesion.get(Organizacion, organizacion_id)


def crear_configuracion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    modo_impositivo: str,
    politica_credito_default: str,
    estado_facturacion_default: str,
    intentos_pin_max: int,
    descuento_manual_habilitado: bool,
    motivo_obligatorio_lista: bool,
    momento: datetime,
    lista_precio_default_id: UUID | None = None,
    tolerancia_offline_tipo: str | None = None,
    tolerancia_offline_valor: object | None = None,
    motivo_obligatorio_descuento: bool | None = None,
    redondeo_multiplo: object | None = None,
    redondeo_direccion: str | None = None,
    permite_consumidor_final: bool | None = None,
    cliente_consumidor_final_id: UUID | None = None,
    modalidad_iva_default: str | None = None,
    app_version_minima: str | None = None,
    desvio_reloj_max_segundos: int | None = None,
    actualizado_por_id: UUID | None = None,
) -> ConfiguracionOrganizacion:
    """Crea la única fila de `configuracion_organizacion` de `organizacion_id`.

    La restricción de unicidad la impone la base (PK = `organizacion_id`,
    tarea 3.4): una segunda llamada para la misma organización falla en el
    `flush`/`commit` con `IntegrityError`, no se valida en Python.
    """
    configuracion = ConfiguracionOrganizacion(
        organizacion_id=organizacion_id,
        modo_impositivo=modo_impositivo,
        lista_precio_default_id=lista_precio_default_id,
        politica_credito_default=politica_credito_default,
        tolerancia_offline_tipo=tolerancia_offline_tipo,
        tolerancia_offline_valor=tolerancia_offline_valor,
        descuento_manual_habilitado=descuento_manual_habilitado,
        motivo_obligatorio_descuento=motivo_obligatorio_descuento,
        motivo_obligatorio_lista=motivo_obligatorio_lista,
        redondeo_multiplo=redondeo_multiplo,
        redondeo_direccion=redondeo_direccion,
        permite_consumidor_final=permite_consumidor_final,
        cliente_consumidor_final_id=cliente_consumidor_final_id,
        estado_facturacion_default=estado_facturacion_default,
        modalidad_iva_default=modalidad_iva_default,
        intentos_pin_max=intentos_pin_max,
        app_version_minima=app_version_minima,
        desvio_reloj_max_segundos=desvio_reloj_max_segundos,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(configuracion)
    sesion.flush()
    return configuracion


def obtener_configuracion(
    organizacion_id: UUID, sesion: Session
) -> ConfiguracionOrganizacion | None:
    return sesion.get(ConfiguracionOrganizacion, organizacion_id)


def actualizar_configuracion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
    **campos: object,
) -> ConfiguracionOrganizacion | None:
    """Actualiza campos de la configuración de `organizacion_id`. Devuelve
    `None` sin tocar nada si la organización no tiene fila de configuración
    (nunca busca ni escribe en la de otra organización)."""
    configuracion = sesion.get(ConfiguracionOrganizacion, organizacion_id)
    if configuracion is None:
        return None

    for campo, valor in campos.items():
        setattr(configuracion, campo, valor)
    configuracion.actualizado_en = momento
    configuracion.actualizado_por_id = actualizado_por_id
    sesion.flush()
    return configuracion
