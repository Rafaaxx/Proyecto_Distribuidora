"""Entorno compartido de las pruebas de compras (change 11): una organización con su
proveedor, `Vino A` (Caja x6 y Botella), `Cerveza B` (Botella) y un depósito, más los
medios de pago y motivos que usan el contado y la anulación."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_presentacion_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.costeo import service as costeo_service
from app.modules.costeo.models import CostoProductoMov
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.cuentas_corrientes.models import CuentaMovimiento
from app.modules.identidad.models import Auditoria
from app.modules.proveedores import commands as proveedores_commands
from app.modules.proveedores.models import Compra, CompraLinea, PagoProveedor, PagoProveedorMedio
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeStockInicial
from app.modules.stock.models import StockMovimiento
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion

MOMENTO = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
CONFIRMAR = "COMPRA_CONFIRMAR"
ANULAR = "COMPRA_ANULAR"
_HANDLERS = {CONFIRMAR: "manejar_compra_confirmar", ANULAR: "manejar_compra_anular"}
PERMISOS = frozenset({"REGISTRAR_COMPRA"})


class Entorno:
    """Una organización con su proveedor, `Vino A` (Caja x6 y Botella), `Cerveza B`
    (Botella) y un depósito: el escenario del criterio 2 de `00` §9."""

    def __init__(self, sesion: Session, *, permisos: frozenset[str] = PERMISOS) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
        self.vino_id = crear_producto_sql(
            sesion, self.org, nombre="Vino A", proveedor_id=self.proveedor_id
        )
        self.caja_x6_id = crear_presentacion_sql(
            sesion, self.org, self.vino_id, nombre="Caja x6", unidades_base=6, es_referencia=True
        )
        self.botella_vino_id = crear_presentacion_sql(
            sesion, self.org, self.vino_id, nombre="Botella", unidades_base=1
        )
        self.cerveza_id = crear_producto_sql(
            sesion, self.org, nombre="Cerveza B", proveedor_id=self.proveedor_id
        )
        self.botella_id = crear_presentacion_sql(
            sesion, self.org, self.cerveza_id, nombre="Botella", unidades_base=1, es_referencia=True
        )
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito")
        self.efectivo_id = self.crear_medio("Efectivo", requiere_referencia=False)
        self.transferencia_id = self.crear_medio("Transferencia", requiere_referencia=True)
        self.motivo_id = self.crear_motivo("ANULACION_COMPRA", "Error de carga")
        sesion.commit()

    def crear_medio(
        self,
        nombre: str,
        *,
        requiere_referencia: bool,
        activo: bool = True,
        org: UUID | None = None,
    ) -> UUID:
        medio_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                "activo, creado_en, actualizado_en) "
                "VALUES (:id, :org, :nombre, :ref, :activo, :m, :m)"
            ),
            {
                "id": medio_id,
                "org": org or self.org,
                "nombre": nombre,
                "ref": requiere_referencia,
                "activo": activo,
                "m": MOMENTO,
            },
        )
        return medio_id

    def crear_motivo(self, ambito: str, nombre: str, *, org: UUID | None = None) -> UUID:
        motivo_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :ambito, :nombre, true, :m, :m)"
            ),
            {
                "id": motivo_id,
                "org": org or self.org,
                "ambito": ambito,
                "nombre": nombre,
                "m": MOMENTO,
            },
        )
        return motivo_id

    def linea(self, producto: str = "vino", **cambios: object) -> dict[str, Any]:
        base: dict[str, Any]
        if producto == "vino":
            base = {
                "producto_id": str(self.vino_id),
                "presentacion_id": str(self.caja_x6_id),
                "cantidad": "10",
                "valor": "6000.00",
                "incluye_iva": False,
            }
        else:
            base = {
                "producto_id": str(self.cerveza_id),
                "presentacion_id": str(self.botella_id),
                "cantidad": "60",
                "valor": "1100.00",
                "incluye_iva": False,
            }
        base.update(cambios)
        return base

    def contenido(self, **cambios: object) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "proveedor_id": str(self.proveedor_id),
            "fecha": "2026-05-10",
            "ubicacion_id": str(self.deposito_id),
            "condicion": "CREDITO",
            "total_factura": "152460.00",
            "lineas": [self.linea("vino"), self.linea("cerveza")],
        }
        cuerpo.update(cambios)
        return cuerpo

    def sobre(
        self,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        tipo: str = CONFIRMAR,
    ) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )

    def enviar(
        self,
        contenido: dict[str, Any] | None = None,
        *,
        operation_id: UUID | None = None,
        tipo: str = CONFIRMAR,
    ) -> Comando:
        sobre = self.sobre(
            contenido if contenido is not None else self.contenido(),
            operation_id=operation_id,
            tipo=tipo,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            manejador = getattr(proveedores_commands, _HANDLERS[tipo])
            return manejador(sobre, validado, sesion=sesion_protegida, reloj=RELOJ)  # type: ignore[no-any-return]

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def pagar(self, *medios: tuple[UUID, str, str | None]) -> list[dict[str, Any]]:
        """Medios de un pago de contado: `(medio_pago_id, importe, referencia)`."""
        return [
            {"medio_pago_id": str(medio), "importe": importe, "referencia": referencia}
            for medio, importe, referencia in medios
        ]

    def confirmar_contado(
        self, *medios: tuple[UUID, str, str | None], **cambios: object
    ) -> Comando:
        return self.enviar(
            self.contenido(condicion="CONTADO", medios=self.pagar(*medios), **cambios)
        )

    def anular(
        self,
        compra_id: UUID,
        *,
        operation_id: UUID | None = None,
        motivo_id: UUID | None = None,
        **cambios: object,
    ) -> Comando:
        contenido: dict[str, Any] = {
            "compra_id": str(compra_id),
            "motivo_id": str(motivo_id or self.motivo_id),
        }
        contenido.update(cambios)
        return self.enviar(contenido, operation_id=operation_id, tipo=ANULAR)

    # --- lecturas -----------------------------------------------------------------

    def pagos(self) -> list[PagoProveedor]:
        return list(
            self.sesion.scalars(
                select(PagoProveedor).where(PagoProveedor.organizacion_id == self.org)
            ).all()
        )

    def medios_de_pago(self) -> list[PagoProveedorMedio]:
        return list(
            self.sesion.scalars(
                select(PagoProveedorMedio)
                .where(PagoProveedorMedio.organizacion_id == self.org)
                .order_by(PagoProveedorMedio.importe.desc())
            ).all()
        )

    def observaciones(self) -> list[str]:
        return sorted(
            self.sesion.scalars(
                select(Observacion.codigo).where(Observacion.organizacion_id == self.org)
            ).all()
        )

    def compras(self) -> list[Compra]:
        return list(
            self.sesion.scalars(select(Compra).where(Compra.organizacion_id == self.org)).all()
        )

    def lineas(self) -> list[CompraLinea]:
        return list(
            self.sesion.scalars(
                select(CompraLinea)
                .where(CompraLinea.organizacion_id == self.org)
                .order_by(CompraLinea.orden)
            ).all()
        )

    def movimientos_de_stock(self) -> list[StockMovimiento]:
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org)
                .order_by(StockMovimiento.registered_at, StockMovimiento.id)
            ).all()
        )

    def historia_de_costo(self) -> list[CostoProductoMov]:
        return list(
            self.sesion.scalars(
                select(CostoProductoMov).where(CostoProductoMov.organizacion_id == self.org)
            ).all()
        )

    def movimientos_de_cuenta(self) -> list[CuentaMovimiento]:
        return list(
            self.sesion.scalars(
                select(CuentaMovimiento).where(CuentaMovimiento.organizacion_id == self.org)
            ).all()
        )

    def saldo_de_cuenta(self) -> Decimal:
        return cuentas_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo="PROVEEDOR", entidad_id=self.proveedor_id
        )

    def saldo(self, producto_id: UUID) -> int:
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=producto_id, ubicacion_id=self.deposito_id
        )

    def promedio(self, producto_id: UUID) -> Decimal | None:
        return costeo_service.obtener_promedio(self.org, self.sesion, producto_id)

    def stock_total(self, producto_id: UUID) -> int:
        return costeo_service.obtener_stock_totales(self.org, self.sesion).get(producto_id, 0)

    def auditorias(self, operation_id: UUID) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(Auditoria)
                .where(
                    Auditoria.organizacion_id == self.org, Auditoria.operation_id == operation_id
                )
            )
            or 0
        )

    def sembrar_stock_inicial(self, producto_id: UUID, cantidad: int, costo: str) -> None:
        stock_service.registrar_stock_inicial(
            self.org,
            self.sesion,
            RELOJ,
            ubicacion_id=self.deposito_id,
            lineas=[LineaDeStockInicial(producto_id, cantidad, costo)],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO,
        )

    def sin_efectos(self) -> None:
        """Nada quedó escrito por la compra (INV-01)."""
        self.sesion.rollback()
        assert self.compras() == []
        assert self.lineas() == []
        assert self.movimientos_de_stock() == []
        assert self.historia_de_costo() == []
        assert self.movimientos_de_cuenta() == []
        assert self.pagos() == []
        assert self.saldo_de_cuenta() == Decimal("0.00")
