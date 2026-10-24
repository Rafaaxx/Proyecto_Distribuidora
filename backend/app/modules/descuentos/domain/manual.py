"""Evaluación del descuento manual: habilitación, permiso, motivo, tope y autorización
(DSC-06, TR-02, INV-03; `design.md` D11, D12, D14). Función pura y gemela de
`frontend/src/domain/descuentos/manual.ts`: las dos corren `shared/fixtures/calculo/
dsc-06-descuento-manual.json` (ADR-016).

Solo lee y decide: no verifica ningún PIN, no escribe ninguna autorización y no audita (eso es del
change 18b). Se evalúa UNA vez por venta con el mayor porcentaje manual que quedó aplicado en
alguna línea (`ResultadoDescuentos.porcentaje_manual_maximo`, D11): una sola resolución, con un
único motivo, cubre todas las líneas.

Orden (D12): (1) organización deshabilitada; (2) sin `DESCUENTO_MANUAL`; (3) motivo obligatorio y
ausente; (4) porcentaje <= tope aplicable -> `DENTRO_DEL_TOPE`; (5) mayor: `PERMISO_PROPIO` si el
usuario tiene `AUTORIZAR_DESCUENTO`; si no, `AUTORIZADO_POR_SUPERVISOR` con un autorizador que lo
tenga. Quien autoriza no queda limitado por su propio tope."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.core.errors import DomainError, PermisoRequeridoError
from app.modules.descuentos.domain.errores import (
    AutorizacionRequeridaError,
    AutorizadorSinPermisoError,
    DescuentoManualDeshabilitadoError,
    MotivoRequeridoError,
)
from app.modules.descuentos.domain.motor import validar_porcentaje_manual

PERMISO_DESCUENTO_MANUAL = "DESCUENTO_MANUAL"
PERMISO_AUTORIZAR_DESCUENTO = "AUTORIZAR_DESCUENTO"

Resolucion = Literal["DENTRO_DEL_TOPE", "PERMISO_PROPIO", "AUTORIZADO_POR_SUPERVISOR"]


@dataclass(frozen=True)
class Autorizador:
    """Otro usuario de la organización que autoriza, con los permisos que tiene hoy."""

    usuario_id: str
    permisos: frozenset[str]


@dataclass(frozen=True)
class ResultadoManual:
    """Lo que la venta registra (DSC-08, SEG-05): el tope que se aplicó, si hizo falta
    autorización, cómo se resolvió y quién autorizó (nulo dentro del tope)."""

    tope_aplicado: Decimal
    requirio_autorizacion: bool
    resolucion: Resolucion
    autorizador_id: str | None


def rechazos_del_descuento_manual(
    *,
    descuento_manual_habilitado: bool,
    motivo_obligatorio: bool | None,
    permisos_usuario: Collection[str],
    tope_rol: Decimal,
    tope_propio: Decimal | None,
    porcentaje_maximo: Decimal,
    motivo: str | None,
    autorizador: Autorizador | None,
) -> list[DomainError]:
    """TODOS los rechazos que el descuento manual tendría hoy, en el orden de D12
    (deshabilitado, permiso, motivo, tope/autorización), sin lanzar ninguno. Es la base de la
    venta sin conexión (change 18b, D10 punto 4, SYN-05, INV-17): cada rechazo es una causa de
    `DESCUENTO_DIFIERE` y todas se informan. Un porcentaje fuera de dominio sigue siendo
    excepción (es malformado, no una diferencia). Un autorizador enviado sin permiso da solo
    `AUTORIZADOR_SIN_PERMISO` (el tope ya está cubierto por esa causa)."""
    validar_porcentaje_manual(porcentaje_maximo, "El mayor porcentaje manual de la venta")

    rechazos: list[DomainError] = []
    if not descuento_manual_habilitado:
        rechazos.append(
            DescuentoManualDeshabilitadoError(
                "La organización no tiene habilitado el descuento manual."
            )
        )
    if PERMISO_DESCUENTO_MANUAL not in permisos_usuario:
        rechazos.append(PermisoRequeridoError(f"Falta el permiso {PERMISO_DESCUENTO_MANUAL}."))
    if motivo_obligatorio is True and not (motivo and motivo.strip()):
        rechazos.append(
            MotivoRequeridoError("La organización exige un motivo para el descuento manual.")
        )

    tope = tope_rol if tope_propio is None else tope_propio
    if porcentaje_maximo <= tope or PERMISO_AUTORIZAR_DESCUENTO in permisos_usuario:
        return rechazos
    if autorizador is None:
        rechazos.append(
            AutorizacionRequeridaError(
                "El descuento manual supera el tope y hace falta una autorización."
            )
        )
    elif PERMISO_AUTORIZAR_DESCUENTO not in autorizador.permisos:
        rechazos.append(
            AutorizadorSinPermisoError("El autorizador no tiene el permiso AUTORIZAR_DESCUENTO.")
        )
    return rechazos


def evaluar_descuento_manual(
    *,
    usuario_id: str,
    descuento_manual_habilitado: bool,
    motivo_obligatorio: bool | None,
    permisos_usuario: Collection[str],
    tope_rol: Decimal,
    tope_propio: Decimal | None,
    porcentaje_maximo: Decimal,
    motivo: str | None,
    autorizador: Autorizador | None,
) -> ResultadoManual:
    rechazos = rechazos_del_descuento_manual(
        descuento_manual_habilitado=descuento_manual_habilitado,
        motivo_obligatorio=motivo_obligatorio,
        permisos_usuario=permisos_usuario,
        tope_rol=tope_rol,
        tope_propio=tope_propio,
        porcentaje_maximo=porcentaje_maximo,
        motivo=motivo,
        autorizador=autorizador,
    )
    if rechazos:
        raise rechazos[0]

    tope = tope_rol if tope_propio is None else tope_propio
    if porcentaje_maximo <= tope:
        return ResultadoManual(tope, False, "DENTRO_DEL_TOPE", None)
    if PERMISO_AUTORIZAR_DESCUENTO in permisos_usuario:
        return ResultadoManual(tope, True, "PERMISO_PROPIO", usuario_id)
    assert autorizador is not None  # sin autorizador ya hubo rechazo
    return ResultadoManual(tope, True, "AUTORIZADO_POR_SUPERVISOR", autorizador.usuario_id)
