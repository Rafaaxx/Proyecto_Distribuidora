"""Utilidades de las pruebas de anulación de transferencias y ajustes (change 14, grupo 9).

Arma una organización con Vino A (120 a 1050) y Agua 500 (40 a 400) en el depósito, una
camioneta vacía, otro depósito, motivos de los tres ámbitos y usuarios con permisos a medida,
y despacha comandos por `sync_service.procesar_comando` (que maneja la transacción, igual
que `test_stock_transferir.py` y `test_stock_ajustar.py`). Es un módulo y no un
`conftest.py` por el mismo motivo que `stock_utiles`: `tests/integration` no es un paquete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.costeo import service as costeo_service
from app.modules.costeo.models import CostoProductoMov
from app.modules.identidad.models import Auditoria
from app.modules.stock import commands as stock_commands  # noqa: F401  (registra los handlers)
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeMovimiento, LineaDeStockInicial
from app.modules.stock.models import (
    AjusteStock,
    AjusteStockLinea,
    StockMovimiento,
    Transferencia,
    TransferenciaLinea,
)
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

TRANSFERIR = "STOCK_TRANSFERIR"
AJUSTAR = "STOCK_AJUSTAR"
ANULAR_TRANSFERENCIA = "STOCK_TRANSFERENCIA_ANULAR"
ANULAR_AJUSTE = "STOCK_AJUSTE_ANULAR"

VENDEDOR = frozenset({"TRANSFERIR_STOCK"})
ADMINISTRACION = frozenset({"TRANSFERIR_STOCK", "AJUSTAR_STOCK", "ANULAR_TRANSFERENCIA"})
ADMINISTRADOR = frozenset(
    {"TRANSFERIR_STOCK", "AJUSTAR_STOCK", "ANULAR_TRANSFERENCIA", "PERMITIR_STOCK_NEGATIVO"}
)


@dataclass(frozen=True)
class Usuario:
    id: UUID
    dispositivo_id: UUID


class Entorno:
    def __init__(self, sesion: Session, *, permisos: frozenset[str] = ADMINISTRADOR) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.admin = self.usuario(permisos)
        self.vino_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.agua_id = crear_producto_sql(sesion, self.org, nombre="Agua 500")
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.otro_deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito 2")
        self.camioneta_id = crear_ubicacion_sql(
            sesion, self.org, nombre="Camioneta 1", tipo="VEHICULO", requiere_toma=True
        )
        self.motivo_ajuste_id = self.motivo("AJUSTE_STOCK")
        self.error_de_carga_id = self.motivo("ANULACION_TRANSFERENCIA")
        self.error_de_carga_ajuste_id = self.motivo("ANULACION_AJUSTE")
        for producto_id, cantidad, costo in (
            (self.vino_id, 120, "1050"),
            (self.agua_id, 40, "400"),
        ):
            stock_service.registrar_stock_inicial(
                self.org,
                sesion,
                RELOJ,
                ubicacion_id=self.deposito_id,
                lineas=[LineaDeStockInicial(producto_id, cantidad, costo)],
                usuario_id=self.admin.id,
                dispositivo_id=self.admin.dispositivo_id,
                operation_id=uuid4(),
                occurred_at=MOMENTO,
            )
        sesion.commit()

    # --- datos ---------------------------------------------------------------------

    def usuario(self, permisos: frozenset[str]) -> Usuario:
        usuario_id, dispositivo_id = crear_usuario_y_dispositivo(
            self.sesion, self.org, permisos=permisos
        )
        self.sesion.commit()
        return Usuario(usuario_id, dispositivo_id)

    def motivo(
        self, ambito: str, *, activo: bool = True, organizacion_id: UUID | None = None
    ) -> UUID:
        motivo_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :o, :a, :n, :act, :m, :m)"
            ),
            {
                "id": motivo_id,
                "o": organizacion_id or self.org,
                "a": ambito,
                "n": f"M {uuid4().hex[:6]}",
                "act": activo,
                "m": MOMENTO,
            },
        )
        self.sesion.commit()
        return motivo_id

    def mover(self, *lineas: LineaDeMovimiento, permitir_negativo: bool = False) -> None:
        """Movimientos directos al libro (una compra, una venta) para armar la situación."""
        stock_service.registrar_movimientos(
            self.org,
            self.sesion,
            RELOJ,
            lineas=list(lineas),
            usuario_id=self.admin.id,
            dispositivo_id=self.admin.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
            permitir_negativo=permitir_negativo,
        )
        self.sesion.commit()

    def compra(self, producto_id: UUID, cantidad: int, costo: str, ubicacion_id: UUID) -> None:
        self.mover(
            LineaDeMovimiento(
                producto_id, ubicacion_id, cantidad, "COMPRA", costo, "COMPRA", uuid4()
            )
        )

    def venta(self, producto_id: UUID, cantidad: int, ubicacion_id: UUID) -> None:
        self.mover(
            LineaDeMovimiento(producto_id, ubicacion_id, -cantidad, "VENTA", None, "VENTA", uuid4())
        )

    # --- comandos --------------------------------------------------------------------

    def enviar(
        self,
        tipo: str,
        contenido: dict[str, Any],
        *,
        usuario: Usuario | None = None,
        operation_id: UUID | None = None,
        sesion: Session | None = None,
    ) -> Comando:
        quien = usuario or self.admin
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=quien.id,
            dispositivo_id=quien.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> Any:
            return registrado.funcion(  # type: ignore[call-arg]
                sobre,
                validado,
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            sesion or self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def contenido_de_transferencia(
        self, lineas: list[tuple[UUID, int]] | None = None, **cambios: object
    ) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "ubicacion_origen_id": str(self.deposito_id),
            "ubicacion_destino_id": str(self.camioneta_id),
            "lineas": [
                {"producto_id": str(p), "cantidad_base": c}
                for p, c in (lineas or [(self.vino_id, 60)])
            ],
        }
        cuerpo.update(cambios)
        return cuerpo

    def contenido_de_ajuste(
        self, lineas: list[tuple[UUID, int]] | None = None, **cambios: object
    ) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "ubicacion_id": str(self.deposito_id),
            "motivo_id": str(self.motivo_ajuste_id),
            "lineas": [
                {"producto_id": str(p), "cantidad_base": c}
                for p, c in (lineas or [(self.vino_id, -6)])
            ],
        }
        cuerpo.update(cambios)
        return cuerpo

    def transferir(
        self, lineas: list[tuple[UUID, int]] | None = None, *, usuario: Usuario | None = None
    ) -> UUID:
        comando = self.enviar(TRANSFERIR, self.contenido_de_transferencia(lineas), usuario=usuario)
        assert comando.resultado is not None
        return UUID(str(comando.resultado["transferencia_id"]))

    def ajustar(
        self, lineas: list[tuple[UUID, int]] | None = None, *, usuario: Usuario | None = None
    ) -> UUID:
        comando = self.enviar(AJUSTAR, self.contenido_de_ajuste(lineas), usuario=usuario)
        assert comando.resultado is not None
        return UUID(str(comando.resultado["ajuste_id"]))

    def anular_transferencia(
        self,
        transferencia_id: UUID,
        motivo_id: UUID | None = None,
        *,
        usuario: Usuario | None = None,
        operation_id: UUID | None = None,
    ) -> Comando:
        return self.enviar(
            ANULAR_TRANSFERENCIA,
            {
                "transferencia_id": str(transferencia_id),
                "motivo_id": str(motivo_id or self.error_de_carga_id),
            },
            usuario=usuario,
            operation_id=operation_id,
        )

    def anular_ajuste(
        self,
        ajuste_id: UUID,
        motivo_id: UUID | None = None,
        *,
        usuario: Usuario | None = None,
        operation_id: UUID | None = None,
    ) -> Comando:
        return self.enviar(
            ANULAR_AJUSTE,
            {
                "ajuste_id": str(ajuste_id),
                "motivo_id": str(motivo_id or self.error_de_carga_ajuste_id),
            },
            usuario=usuario,
            operation_id=operation_id,
        )

    # --- lecturas ----------------------------------------------------------------------

    def saldo(self, producto_id: UUID, ubicacion_id: UUID) -> int:
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
        )

    def stock_total(self, producto_id: UUID) -> int:
        costo = costeo_service.obtener_costo(self.org, self.sesion, producto_id)
        assert costo is not None
        return costo.stock_total

    def promedio(self, producto_id: UUID) -> Decimal | None:
        return costeo_service.obtener_promedio(self.org, self.sesion, producto_id)

    def historia_de_costo(self) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(CostoProductoMov)
                .where(CostoProductoMov.organizacion_id == self.org)
            )
            or 0
        )

    def movimientos(self, origen_tipo: str) -> list[StockMovimiento]:
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(
                    StockMovimiento.organizacion_id == self.org,
                    StockMovimiento.origen_tipo == origen_tipo,
                )
                .order_by(StockMovimiento.id)
            ).all()
        )

    def transferencia(self, transferencia_id: UUID) -> Transferencia:
        return self.sesion.scalars(
            select(Transferencia)
            .where(Transferencia.organizacion_id == self.org, Transferencia.id == transferencia_id)
            .execution_options(populate_existing=True)
        ).one()

    def ajuste(self, ajuste_id: UUID) -> AjusteStock:
        return self.sesion.scalars(
            select(AjusteStock)
            .where(AjusteStock.organizacion_id == self.org, AjusteStock.id == ajuste_id)
            .execution_options(populate_existing=True)
        ).one()

    def lineas_de_transferencia(self) -> list[TransferenciaLinea]:
        return list(
            self.sesion.scalars(
                select(TransferenciaLinea).where(TransferenciaLinea.organizacion_id == self.org)
            ).all()
        )

    def lineas_de_ajuste(self) -> list[AjusteStockLinea]:
        return list(
            self.sesion.scalars(
                select(AjusteStockLinea).where(AjusteStockLinea.organizacion_id == self.org)
            ).all()
        )

    def auditorias(self, operation_id: UUID) -> list[Auditoria]:
        return list(
            self.sesion.scalars(
                select(Auditoria).where(
                    Auditoria.organizacion_id == self.org, Auditoria.operation_id == operation_id
                )
            ).all()
        )

    def total_de_movimientos(self) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org)
            )
            or 0
        )
