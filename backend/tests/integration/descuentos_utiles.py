"""Entorno compartido de las pruebas de `descuentos` (change 16): el de `precios` (una
organización con su usuario, un producto con categoría y marca, y los atajos para enviar los
comandos por el bus) con los permisos de descuentos y los atajos de las reglas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from precios_utiles import AUSENTE, MOMENTO, RELOJ
from precios_utiles import Entorno as EntornoDePrecios
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.descuentos import commands as _descuentos_commands  # noqa: F401 (registra)
from app.modules.descuentos.models import ReglaDescuento, ReglaDescuentoAlcance

__all__ = [
    "ACTIVAR",
    "AUSENTE",
    "CREAR",
    "MODIFICAR",
    "MOMENTO",
    "PAUSAR",
    "PERMISOS",
    "RELOJ",
    "Entorno",
    "regla_valida",
]

CREAR = "REGLA_DESCUENTO_CREAR"
MODIFICAR = "REGLA_DESCUENTO_MODIFICAR"
ACTIVAR = "REGLA_DESCUENTO_ACTIVAR"
PAUSAR = "REGLA_DESCUENTO_PAUSAR"

PERMISOS = frozenset({"GESTIONAR_DESCUENTOS"})


def regla_valida(**cambios: Any) -> dict[str, Any]:
    """El contenido de `REGLA_DESCUENTO_CREAR` de "cajas equivalentes >= 20 -> 5%", sobre toda
    la venta; `cambios` pisa cualquier campo."""
    contenido: dict[str, Any] = {
        "nombre": "Volumen 20 cajas",
        "tipo": "VOLUMEN_OPERACION",
        "medida": "CAJAS_EQUIVALENTES",
        "operador": "GTE",
        "umbral": "20",
        "accion_tipo": "PORCENTAJE",
        "accion_valor": "0.050000",
        "prioridad": 1,
        "acumulable": False,
        "alcances": [],
    }
    contenido.update(cambios)
    return contenido


class Entorno(EntornoDePrecios):
    """Como el de `precios`, con un usuario que tiene `GESTIONAR_DESCUENTOS`."""

    def __init__(self, sesion: Session, *, permisos: frozenset[str] = PERMISOS) -> None:
        super().__init__(sesion, permisos=permisos)

    # --- comandos --------------------------------------------------------------------

    def crear_regla_descuento(self, **cambios: Any) -> UUID:
        comando = self.enviar(CREAR, regla_valida(**cambios))
        assert comando.resultado is not None
        return UUID(str(comando.resultado["regla_id"]))

    def activar_regla(self, regla_id: UUID, *, operation_id: UUID | None = None) -> Any:
        return self.enviar(ACTIVAR, {"regla_id": str(regla_id)}, operation_id=operation_id)

    def pausar_regla(self, regla_id: UUID, *, operation_id: UUID | None = None) -> Any:
        return self.enviar(PAUSAR, {"regla_id": str(regla_id)}, operation_id=operation_id)

    # --- lecturas de lo escrito --------------------------------------------------------

    def reglas_de_descuento(self, *, org: UUID | None = None) -> list[ReglaDescuento]:
        consulta = select(ReglaDescuento).where(ReglaDescuento.organizacion_id == (org or self.org))
        return list(
            self.sesion.scalars(
                consulta.order_by(ReglaDescuento.creado_en, ReglaDescuento.id).execution_options(
                    populate_existing=True
                )
            )
        )

    def regla_de_descuento(self, regla_id: UUID) -> ReglaDescuento:
        return self.sesion.scalars(
            select(ReglaDescuento)
            .where(ReglaDescuento.organizacion_id == self.org, ReglaDescuento.id == regla_id)
            .execution_options(populate_existing=True)
        ).one()

    def alcances_de(self, regla_id: UUID) -> list[ReglaDescuentoAlcance]:
        consulta = select(ReglaDescuentoAlcance).where(
            ReglaDescuentoAlcance.organizacion_id == self.org,
            ReglaDescuentoAlcance.regla_id == regla_id,
        )
        return list(
            self.sesion.scalars(
                consulta.order_by(
                    ReglaDescuentoAlcance.alcance_tipo, ReglaDescuentoAlcance.alcance_id
                ).execution_options(populate_existing=True)
            )
        )
