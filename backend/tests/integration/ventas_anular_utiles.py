"""Entorno de las pruebas de `VENTA_ANULAR` (change 19, grupo 7).

Hereda de `EntornoVenta` (Kiosco La Esquina con saldo de `150000.00`, Vino A con 48 botellas a
$1.050 en el depósito, lista y medios) y le suma el motivo de `ANULACION_VENTA`, quien anula y
los atajos para vender y anular por el bus (`sync_service.procesar_comando`).

Es un módulo y no un `conftest.py` por el mismo motivo que `ventas_confirmar_utiles`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from ventas_confirmar_utiles import MOMENTO_VENTA, EntornoVenta

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.ventas import commands as ventas_commands  # noqa: F401 (registra el handler)
from app.modules.ventas.models import Venta, VentaAnulacion

VENTA_ANULAR = "VENTA_ANULAR"
PERMISOS_DE_ANULADOR = frozenset({"VENDER", "ANULAR_VENTA"})
PERMISOS_DE_SUPERVISOR_DE_ANULACION = PERMISOS_DE_ANULADOR | {"LIBERAR_UBICACION"}
MOMENTO_ANULACION = MOMENTO_VENTA + timedelta(days=1)
RELOJ_ANULACION = FixedClock(MOMENTO_ANULACION)
SIN_INDICAR: Any = object()
"""`devuelve_dinero` no enviado (distinto de `None` y de `False`)."""


class EntornoAnulacion(EntornoVenta):
    """Ver el docstring del módulo."""

    def __init__(
        self,
        sesion: Session,
        *,
        permisos: frozenset[str] = PERMISOS_DE_ANULADOR,
        **opciones: Any,
    ) -> None:
        super().__init__(sesion, permisos=permisos, **opciones)
        self.motivo_anulacion_id = self.crear_motivo("ANULACION_VENTA", "Error de carga")
        sesion.commit()

    # --- armado ---------------------------------------------------------------------

    def vender_y_obtener_id(self, *lineas: dict[str, Any], **cambios: Any) -> UUID:
        comando = self.vender(*lineas, **cambios)
        assert comando.resultado is not None
        return UUID(str(comando.resultado["venta_id"]))

    def otro_usuario(self, permisos: frozenset[str]) -> tuple[UUID, UUID]:
        """`(usuario_id, dispositivo_id)` de otro usuario de la organización."""
        ids = crear_usuario_y_dispositivo(self.sesion, self.org, permisos=permisos)
        self.sesion.commit()
        return ids

    # --- comando --------------------------------------------------------------------

    def contenido_de_anulacion(
        self,
        venta_id: UUID,
        *,
        motivo_id: UUID | None = None,
        observacion: str | None = None,
        devuelve_dinero: Any = SIN_INDICAR,
    ) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "venta_id": str(venta_id),
            "motivo_id": str(motivo_id or self.motivo_anulacion_id),
            "observacion": observacion,
        }
        if devuelve_dinero is not SIN_INDICAR:
            cuerpo["devuelve_dinero"] = devuelve_dinero
        return cuerpo

    def anular(
        self,
        venta_id: UUID,
        *,
        operation_id: UUID | None = None,
        usuario_id: UUID | None = None,
        dispositivo_id: UUID | None = None,
        organizacion_id: UUID | None = None,
        contenido: dict[str, Any] | None = None,
        jornada_id: UUID | None = None,
        **opciones: Any,
    ) -> Comando:
        """Envía `VENTA_ANULAR` por el bus; los errores de dominio suben (el bus revierte)."""
        cuerpo = (
            contenido
            if contenido is not None
            else self.contenido_de_anulacion(venta_id, **opciones)
        )
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=VENTA_ANULAR,
            version=1,
            modo="ONLINE",
            organizacion_id=organizacion_id or self.org,
            usuario_id=usuario_id or self.usuario_id,
            dispositivo_id=dispositivo_id or self.dispositivo_id,
            occurred_at=MOMENTO_ANULACION,
            secuencia=1,
            app_version="1.0.0",
            contenido=cuerpo,
            jornada_id=jornada_id,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: registro.SesionDeHandler) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[no-any-return]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ_ANULACION
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ_ANULACION, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    # --- lecturas -------------------------------------------------------------------

    def venta(self, venta_id: UUID) -> Venta:
        self.sesion.expire_all()
        return self.sesion.scalars(
            select(Venta).where(Venta.organizacion_id == self.org, Venta.id == venta_id)
        ).one()

    def anulaciones_de_venta(self) -> list[VentaAnulacion]:
        self.sesion.expire_all()
        return list(
            self.sesion.scalars(
                select(VentaAnulacion).where(VentaAnulacion.organizacion_id == self.org)
            ).all()
        )

    def historia_de_costo(self, origen_tipo: str, producto_id: UUID | None = None) -> int:
        return int(
            self.sesion.scalar(
                text(
                    "SELECT count(*) FROM costo_producto_mov WHERE organizacion_id = :o "
                    "AND producto_id = :p AND origen_tipo = :t"
                ),
                {"o": self.org, "p": producto_id or self.vino_id, "t": origen_tipo},
            )
            or 0
        )

    def estado_de_cobranza(self, cobranza_id: UUID) -> str:
        self.sesion.expire_all()
        return str(
            self.sesion.scalar(
                text("SELECT estado FROM cobranza WHERE organizacion_id = :o AND id = :c"),
                {"o": self.org, "c": cobranza_id},
            )
        )

    def sin_efectos_de_anulacion(
        self, venta_id: UUID, *, stock: int, saldo: str, estado: str = "CONFIRMADA"
    ) -> None:
        """Nada quedó escrito por la anulación (INV-01): la venta sigue como estaba, sin fila de
        anulación, sin movimientos de anulación y con el stock y el saldo dados."""
        self.sesion.rollback()
        assert self.venta(venta_id).estado == estado
        assert self.anulaciones_de_venta() == []
        assert self.movimientos_de_stock("ANULACION_VENTA") == []
        assert self.movimientos("ANULACION_VENTA") == []
        assert self.movimientos("ANULACION_COBRANZA") == []
        assert self.stock() == stock
        assert str(self.saldo()) == saldo
