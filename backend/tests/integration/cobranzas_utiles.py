"""Entorno compartido de las pruebas de cobranzas (change 17): una organización con su usuario y
dispositivo (con los permisos que se pidan), `Kiosco La Esquina` con saldo de `150000.00`, los
medios de pago "Efectivo" y "Transferencia" (esta exige referencia) y el motivo de anulación.

Los comandos se procesan por `sync_service.procesar_comando`, que maneja la transacción (mismo
criterio que `compras_utiles.py`)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.cobranzas import commands as cobranzas_commands  # noqa: F401 (registra el handler)
from app.modules.cobranzas.models import Cobranza, CobranzaAnulacion, CobranzaMedio
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.cuentas_corrientes.models import CuentaMovimiento
from app.modules.identidad.models import Auditoria
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion

MOMENTO = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
REGISTRAR = "COBRANZA_REGISTRAR"
ANULAR = "COBRANZA_ANULAR"
PERMISOS_DE_COBRANZA = frozenset({"REGISTRAR_COBRANZA"})
PERMISOS_DE_ANULACION = frozenset({"REGISTRAR_COBRANZA", "ANULAR_COBRANZA"})


class Entorno:
    """Una organización con `Kiosco La Esquina` (saldo `150000.00`) y los medios y motivos de
    una cobranza."""

    def __init__(
        self,
        sesion: Session,
        *,
        permisos: frozenset[str] = PERMISOS_DE_COBRANZA,
        saldo_inicial: str | None = "150000.00",
    ) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        self.cliente_id = crear_cliente(sesion, self.org, nombre="Kiosco La Esquina")
        self.efectivo_id = self.crear_medio("Efectivo", requiere_referencia=False)
        self.transferencia_id = self.crear_medio("Transferencia", requiere_referencia=True)
        self.motivo_id = self.crear_motivo("ANULACION_COBRANZA", "Error de carga")
        if saldo_inicial is not None:
            self.cargar_saldo_inicial(self.cliente_id, saldo_inicial)
        sesion.commit()

    # --- armado de datos ------------------------------------------------------------

    def cargar_saldo_inicial(self, cliente_id: UUID, importe: str) -> None:
        cuentas_service.registrar_saldo_inicial(
            self.org,
            self.sesion,
            RELOJ,
            cuenta_tipo="CLIENTE",
            entidad_id=cliente_id,
            importe=importe,
            sentido="AUMENTA",
            occurred_at=MOMENTO,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
        )

    def crear_cliente(self, **cambios: Any) -> UUID:
        return crear_cliente(self.sesion, self.org, **cambios)

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

    def crear_motivo(
        self, ambito: str, nombre: str, *, org: UUID | None = None, activo: bool = True
    ) -> UUID:
        motivo_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :ambito, :nombre, :activo, :m, :m)"
            ),
            {
                "id": motivo_id,
                "org": org or self.org,
                "ambito": ambito,
                "nombre": nombre,
                "activo": activo,
                "m": MOMENTO,
            },
        )
        return motivo_id

    def desactivar_medio(self, medio_id: UUID) -> None:
        self.sesion.execute(
            text("UPDATE medio_pago SET activo = false WHERE organizacion_id = :o AND id = :m"),
            {"o": self.org, "m": medio_id},
        )
        self.sesion.commit()

    def crear_jornada(self, *, estado: str = "ABIERTA", **cambios: Any) -> UUID:
        """Una jornada del usuario y el dispositivo del entorno (o de quien se indique)."""
        valores: dict[str, Any] = {
            "usuario_id": self.usuario_id,
            "dispositivo_id": self.dispositivo_id,
            "ubicacion_id": crear_ubicacion_sql(self.sesion, self.org, requiere_toma=True),
        }
        valores.update(cambios)
        jornada_id = crear_jornada_sql(self.sesion, self.org, estado=estado, **valores)
        self.sesion.commit()
        return jornada_id

    def crear_otro_usuario_con_jornada(self) -> UUID:
        """Una jornada `ABIERTA` de OTRO usuario y otro dispositivo de la misma organización."""
        usuario_id, dispositivo_id = crear_usuario_y_dispositivo(
            self.sesion, self.org, permisos=PERMISOS_DE_COBRANZA
        )
        return self.crear_jornada(usuario_id=usuario_id, dispositivo_id=dispositivo_id)

    # --- comandos -------------------------------------------------------------------

    def medios(self, *medios: tuple[UUID, str, str | None]) -> list[dict[str, Any]]:
        """Medios de una cobranza: `(medio_pago_id, importe, referencia)`."""
        return [
            {"medio_pago_id": str(medio), "importe": importe, "referencia": referencia}
            for medio, importe, referencia in medios
        ]

    def contenido(self, **cambios: object) -> dict[str, Any]:
        """El contenido de `COBRANZA_REGISTRAR`: `50000.00` en efectivo y transferencia."""
        cuerpo: dict[str, Any] = {
            "cobranza_id": str(uuid4()),
            "cliente_id": str(self.cliente_id),
            "importe": "50000.00",
            "medios": self.medios(
                (self.efectivo_id, "30000.00", None),
                (self.transferencia_id, "20000.00", "0042"),
            ),
        }
        cuerpo.update(cambios)
        return cuerpo

    def sobre(
        self,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        tipo: str = REGISTRAR,
        jornada_id: UUID | None = None,
        organizacion_id: UUID | None = None,
    ) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=organizacion_id or self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
            jornada_id=jornada_id,
        )

    def enviar(
        self,
        contenido: dict[str, Any] | None = None,
        *,
        operation_id: UUID | None = None,
        tipo: str = REGISTRAR,
        jornada_id: UUID | None = None,
    ) -> Comando:
        sobre = self.sobre(
            contenido if contenido is not None else self.contenido(),
            operation_id=operation_id,
            tipo=tipo,
            jornada_id=jornada_id,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: registro.SesionDeHandler) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[no-any-return]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def registrar(self, **cambios: object) -> Comando:
        return self.enviar(self.contenido(**cambios))

    def registrar_y_obtener_id(self, **cambios: object) -> UUID:
        """Registra una cobranza y devuelve su identificador."""
        cobranza_id = uuid4()
        self.registrar(cobranza_id=str(cobranza_id), **cambios)
        return cobranza_id

    def anular(
        self,
        cobranza_id: UUID,
        *,
        motivo_id: UUID | None = None,
        observacion: str | None = None,
        operation_id: UUID | None = None,
    ) -> Comando:
        """`COBRANZA_ANULAR`; sin `observacion` no la manda."""
        contenido: dict[str, Any] = {
            "cobranza_id": str(cobranza_id),
            "motivo_id": str(motivo_id or self.motivo_id),
        }
        if observacion is not None:
            contenido["observacion"] = observacion
        return self.enviar(contenido, operation_id=operation_id, tipo=ANULAR)

    def sembrar_cobranza_de_venta(self, importe: str = "10000.00") -> UUID:
        """Una cobranza de origen `VENTA` escrita por SQL (la venta llega en el change 18a)."""
        cobranza_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO cobranza (id, organizacion_id, cliente_id, venta_id, origen, "
                "importe, estado, operation_id, usuario_id, dispositivo_id, occurred_at, "
                "registered_at) VALUES (:id, :org, :cli, :venta, 'VENTA', :imp, 'CONFIRMADA', "
                ":op, :usu, :dis, :m, :m)"
            ),
            {
                "id": cobranza_id,
                "org": self.org,
                "cli": self.cliente_id,
                "venta": uuid4(),
                "imp": importe,
                "op": uuid4(),
                "usu": self.usuario_id,
                "dis": self.dispositivo_id,
                "m": MOMENTO,
            },
        )
        self.sesion.commit()
        return cobranza_id

    def estado_de(self, cobranza_id: UUID) -> str:
        self.sesion.expire_all()
        return str(
            self.sesion.scalar(
                select(Cobranza.estado).where(
                    Cobranza.organizacion_id == self.org, Cobranza.id == cobranza_id
                )
            )
        )

    def auditoria_de(self, operation_id: UUID) -> list[Auditoria]:
        return list(
            self.sesion.scalars(
                select(Auditoria).where(
                    Auditoria.organizacion_id == self.org, Auditoria.operation_id == operation_id
                )
            ).all()
        )

    # --- lecturas -------------------------------------------------------------------

    def cobranzas(self) -> list[Cobranza]:
        return list(
            self.sesion.scalars(
                select(Cobranza)
                .where(Cobranza.organizacion_id == self.org)
                .order_by(Cobranza.occurred_at, Cobranza.id)
            ).all()
        )

    def medios_de_cobranza(self, cobranza_id: UUID | None = None) -> list[CobranzaMedio]:
        consulta = select(CobranzaMedio).where(CobranzaMedio.organizacion_id == self.org)
        if cobranza_id is not None:
            consulta = consulta.where(CobranzaMedio.cobranza_id == cobranza_id)
        return list(self.sesion.scalars(consulta.order_by(CobranzaMedio.orden)).all())

    def anulaciones(self) -> list[CobranzaAnulacion]:
        return list(
            self.sesion.scalars(
                select(CobranzaAnulacion).where(CobranzaAnulacion.organizacion_id == self.org)
            ).all()
        )

    def movimientos(self, tipo: str | None = None) -> list[CuentaMovimiento]:
        consulta = select(CuentaMovimiento).where(CuentaMovimiento.organizacion_id == self.org)
        if tipo is not None:
            consulta = consulta.where(CuentaMovimiento.tipo == tipo)
        return list(self.sesion.scalars(consulta.order_by(CuentaMovimiento.registered_at)).all())

    def saldo(self, cliente_id: UUID | None = None) -> Decimal:
        return cuentas_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo="CLIENTE", entidad_id=cliente_id or self.cliente_id
        )

    def observaciones(self) -> list[str]:
        return sorted(
            self.sesion.scalars(
                select(Observacion.codigo).where(Observacion.organizacion_id == self.org)
            ).all()
        )

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

    def sin_efectos(self) -> None:
        """Nada quedó escrito por la cobranza (INV-01): ni cobranza, ni medios, ni movimiento de
        cobranza, y el saldo sigue en lo que cargó el entorno."""
        self.sesion.rollback()
        assert self.cobranzas() == []
        assert self.medios_de_cobranza() == []
        assert self.movimientos("COBRANZA") == []
        assert self.anulaciones() == []
