"""Change 06, tarea 9.3: integración de los handlers de `proveedores` con
el bus real (`sync_service.procesar_comando`, PostgreSQL real). Mismo
criterio que `test_catalogo_commands_bus.py` (change 05, tarea 8.3): por
cada uno de los tres tipos (`PROVEEDOR_CREAR`, `PROVEEDOR_MODIFICAR`,
`COSTO_INFORMAR`) se confirma (1) aceptado con una sola fila de auditoría y
reenvío idéntico sin duplicar, (2) mismo `operation_id` con contenido
distinto -> `COMANDO_INCONSISTENTE`, (3) un error de dominio revierte la
reserva (sin fila de auditoría, sin fila de `comando`) y permite
reintentar con el mismo `operation_id` corregido."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import agregar_configuracion
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.catalogo import repository as catalogo_repository
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Auditoria, Organizacion
from app.modules.proveedores import commands as proveedores_commands
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores.domain.errores import (
    NombreDuplicadoError,
    ProveedorConProductosActivosError,
    ProveedorNoCorrespondeError,
)
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


def _crear_organizacion(sesion: Session) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba proveedores",
        slug=f"org-proveedores-{uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    agregar_configuracion(sesion, organizacion.id)
    return organizacion


def _crear_usuario_y_dispositivo(sesion: Session, organizacion_id: UUID) -> tuple[UUID, UUID]:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Gestor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"gestor-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash="hash",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo=f"B{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _sobre(
    *,
    tipo: str,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    contenido: dict[str, object],
) -> SobreComando:
    return SobreComando(
        operation_id=operation_id,
        tipo=tipo,
        version=1,
        modo="ONLINE",
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido,  # type: ignore[arg-type]
    )


def _contar_auditoria(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Auditoria).where(Auditoria.operation_id == operation_id)
    )


def _reserva_de_comando(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    )


def _procesar(
    sesion: Session,
    sobre: SobreComando,
    *,
    handler: object,
    contenido_cls: object,
) -> Comando:
    huella = calcular_huella(sobre.contenido)
    contenido_validado = contenido_cls.model_validate(sobre.contenido)  # type: ignore[attr-defined]

    def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return handler(  # type: ignore[operator]
            sobre, contenido_validado, sesion=sesion_protegida, reloj=RELOJ
        )

    return sync_service.procesar_comando(
        sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
    )


def _crear_alicuota(sesion: Session, organizacion_id: UUID) -> AlicuotaIva:
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        nombre="21%",
        valor="0.210000",
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    sesion.add(alicuota)
    return alicuota


# --- PROVEEDOR_CREAR --------------------------------------------------------


class TestProveedorCrearContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="PROVEEDOR_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "nombre": "Distribuidora Sur",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
            },
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=proveedores_commands.manejar_proveedor_crear,
            contenido_cls=proveedores_commands.ProveedorCrearContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=proveedores_commands.manejar_proveedor_crear,
            contenido_cls=proveedores_commands.ProveedorCrearContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        proveedores, _ = proveedores_repository_listar(db_session, organizacion.id)
        assert [p.nombre for p in proveedores] == ["Distribuidora Sur"]

    def test_mismo_operation_id_con_contenido_distinto_es_inconsistente(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        operation_id = uuid4()
        primero = _sobre(
            tipo="PROVEEDOR_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "nombre": "Distribuidora Sur",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
            },
        )
        _procesar(
            db_session,
            primero,
            handler=proveedores_commands.manejar_proveedor_crear,
            contenido_cls=proveedores_commands.ProveedorCrearContenidoV1,
        )

        segundo = _sobre(
            tipo="PROVEEDOR_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "nombre": "Distribuidora Norte",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
            },
        )
        with pytest.raises(ComandoInconsistenteError):
            _procesar(
                db_session,
                segundo,
                handler=proveedores_commands.manejar_proveedor_crear,
                contenido_cls=proveedores_commands.ProveedorCrearContenidoV1,
            )

        proveedores, _ = proveedores_repository_listar(db_session, organizacion.id)
        assert [p.nombre for p in proveedores] == ["Distribuidora Sur"]

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        _procesar(
            db_session,
            _sobre(
                tipo="PROVEEDOR_CREAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                operation_id=uuid4(),
                contenido={
                    "nombre": "Distribuidora Sur",
                    "cuit": None,
                    "contacto": None,
                    "telefono": None,
                    "email": None,
                },
            ),
            handler=proveedores_commands.manejar_proveedor_crear,
            contenido_cls=proveedores_commands.ProveedorCrearContenidoV1,
        )

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="PROVEEDOR_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "nombre": "Distribuidora Sur",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
            },
        )
        with pytest.raises(NombreDuplicadoError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=proveedores_commands.manejar_proveedor_crear,
                contenido_cls=proveedores_commands.ProveedorCrearContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0

        sobre_corregido = _sobre(
            tipo="PROVEEDOR_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "nombre": "Distribuidora Norte",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
            },
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=proveedores_commands.manejar_proveedor_crear,
            contenido_cls=proveedores_commands.ProveedorCrearContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


def proveedores_repository_listar(sesion: Session, organizacion_id: UUID):
    return proveedores_repository.listar_proveedores_paginado(organizacion_id, sesion)


# --- PROVEEDOR_MODIFICAR ----------------------------------------------------


class TestProveedorModificarContraElBus:
    def _crear_proveedor(self, sesion: Session, organizacion_id: UUID, *, nombre: str):
        return proveedores_repository.crear_proveedor(
            organizacion_id,
            sesion,
            proveedor_id=nuevo_id(),
            nombre=nombre,
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            activo=True,
            momento=MOMENTO,
        )

    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        proveedor = self._crear_proveedor(db_session, organizacion.id, nombre="Distribuidora Sur")
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="PROVEEDOR_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "proveedor_id": str(proveedor.id),
                "nombre": "Distribuidora Sur S.A.",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
                "activo": True,
            },
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=proveedores_commands.manejar_proveedor_modificar,
            contenido_cls=proveedores_commands.ProveedorModificarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=proveedores_commands.manejar_proveedor_modificar,
            contenido_cls=proveedores_commands.ProveedorModificarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        actualizado, _ = proveedores_repository_listar(db_session, organizacion.id)
        assert actualizado[0].nombre == "Distribuidora Sur S.A."

    def test_mismo_operation_id_con_contenido_distinto_es_inconsistente(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        proveedor = self._crear_proveedor(db_session, organizacion.id, nombre="Distribuidora Sur")
        db_session.commit()

        operation_id = uuid4()
        primero = _sobre(
            tipo="PROVEEDOR_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "proveedor_id": str(proveedor.id),
                "nombre": "Distribuidora Sur S.A.",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
                "activo": True,
            },
        )
        _procesar(
            db_session,
            primero,
            handler=proveedores_commands.manejar_proveedor_modificar,
            contenido_cls=proveedores_commands.ProveedorModificarContenidoV1,
        )

        segundo = _sobre(
            tipo="PROVEEDOR_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "proveedor_id": str(proveedor.id),
                "nombre": "Otro nombre",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
                "activo": True,
            },
        )
        with pytest.raises(ComandoInconsistenteError):
            _procesar(
                db_session,
                segundo,
                handler=proveedores_commands.manejar_proveedor_modificar,
                contenido_cls=proveedores_commands.ProveedorModificarContenidoV1,
            )

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        """`PROVEEDOR_CON_PRODUCTOS_ACTIVOS` (D5/ADR-026): desactivar un
        proveedor con un producto activo se rechaza; reintentando el mismo
        `operation_id` sin cambiar `activo` (conservarlo) se acepta."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        proveedor = self._crear_proveedor(db_session, organizacion.id, nombre="Distribuidora Sur")
        categoria = catalogo_repository.crear_categoria(
            organizacion.id,
            db_session,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        alicuota = _crear_alicuota(db_session, organizacion.id)
        catalogo_repository.crear_producto(
            organizacion.id,
            db_session,
            producto_id=nuevo_id(),
            codigo="VA-PROV-001",
            nombre="Vino A",
            categoria_id=categoria.id,
            marca_id=None,
            proveedor_id=proveedor.id,
            unidad_base="botella",
            alicuota_id=alicuota.id,
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="PROVEEDOR_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "proveedor_id": str(proveedor.id),
                "nombre": "Distribuidora Sur",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
                "activo": False,
            },
        )
        with pytest.raises(ProveedorConProductosActivosError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=proveedores_commands.manejar_proveedor_modificar,
                contenido_cls=proveedores_commands.ProveedorModificarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0

        sobre_corregido = _sobre(
            tipo="PROVEEDOR_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "proveedor_id": str(proveedor.id),
                "nombre": "Distribuidora Sur",
                "cuit": None,
                "contacto": None,
                "telefono": None,
                "email": None,
                "activo": True,
            },
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=proveedores_commands.manejar_proveedor_modificar,
            contenido_cls=proveedores_commands.ProveedorModificarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


# --- COSTO_INFORMAR ---------------------------------------------------------


class TestCostoInformarContraElBus:
    def _preparar_proveedor_y_producto(
        self, sesion: Session, organizacion_id: UUID
    ) -> tuple[UUID, UUID, UUID]:
        proveedor = proveedores_repository.crear_proveedor(
            organizacion_id,
            sesion,
            proveedor_id=nuevo_id(),
            nombre="Distribuidora Sur",
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            activo=True,
            momento=MOMENTO,
        )
        categoria = catalogo_repository.crear_categoria(
            organizacion_id,
            sesion,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        alicuota = _crear_alicuota(sesion, organizacion_id)
        producto = catalogo_repository.crear_producto(
            organizacion_id,
            sesion,
            producto_id=nuevo_id(),
            codigo="VA-COSTO-001",
            nombre="Vino A",
            categoria_id=categoria.id,
            marca_id=None,
            proveedor_id=proveedor.id,
            unidad_base="botella",
            alicuota_id=alicuota.id,
            activo=True,
            momento=MOMENTO,
        )
        presentacion = catalogo_repository.crear_presentacion(
            organizacion_id,
            sesion,
            presentacion_id=nuevo_id(),
            producto_id=producto.id,
            nombre="Botella",
            unidades_base=1,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=True,
            activo=True,
            momento=MOMENTO,
        )
        return proveedor.id, producto.id, presentacion.id

    def _contenido(
        self, *, proveedor_id: UUID, producto_id: UUID, presentacion_id: UUID, valor: str
    ) -> dict[str, object]:
        return {
            "proveedor_id": str(proveedor_id),
            "costos": [
                {
                    "producto_id": str(producto_id),
                    "presentacion_id": str(presentacion_id),
                    "valor": valor,
                    "incluye_iva": False,
                    "bonificacion": "0",
                    "vigencia_desde": date(2026, 1, 1).isoformat(),
                    "observacion": None,
                }
            ],
        }

    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        proveedor_id, producto_id, presentacion_id = self._preparar_proveedor_y_producto(
            db_session, organizacion.id
        )
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="COSTO_INFORMAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido=self._contenido(
                proveedor_id=proveedor_id,
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor="100.00",
            ),
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=proveedores_commands.manejar_costo_informar,
            contenido_cls=proveedores_commands.CostoInformarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=proveedores_commands.manejar_costo_informar,
            contenido_cls=proveedores_commands.CostoInformarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1

    def test_mismo_operation_id_con_contenido_distinto_es_inconsistente(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        proveedor_id, producto_id, presentacion_id = self._preparar_proveedor_y_producto(
            db_session, organizacion.id
        )
        db_session.commit()

        operation_id = uuid4()
        primero = _sobre(
            tipo="COSTO_INFORMAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido=self._contenido(
                proveedor_id=proveedor_id,
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor="100.00",
            ),
        )
        _procesar(
            db_session,
            primero,
            handler=proveedores_commands.manejar_costo_informar,
            contenido_cls=proveedores_commands.CostoInformarContenidoV1,
        )

        segundo = _sobre(
            tipo="COSTO_INFORMAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido=self._contenido(
                proveedor_id=proveedor_id,
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor="150.00",
            ),
        )
        with pytest.raises(ComandoInconsistenteError):
            _procesar(
                db_session,
                segundo,
                handler=proveedores_commands.manejar_costo_informar,
                contenido_cls=proveedores_commands.CostoInformarContenidoV1,
            )

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        """D3: el proveedor del costo debe ser el proveedor ACTUAL del
        producto -- un proveedor distinto (aunque válido y activo) dispara
        `PROVEEDOR_NO_CORRESPONDE`; reintentando el mismo `operation_id`
        con el proveedor correcto se acepta."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        proveedor_id, producto_id, presentacion_id = self._preparar_proveedor_y_producto(
            db_session, organizacion.id
        )
        otro_proveedor = proveedores_repository.crear_proveedor(
            organizacion.id,
            db_session,
            proveedor_id=nuevo_id(),
            nombre="Otro proveedor",
            cuit=None,
            contacto=None,
            telefono=None,
            email=None,
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="COSTO_INFORMAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido=self._contenido(
                proveedor_id=otro_proveedor.id,
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor="100.00",
            ),
        )
        with pytest.raises(ProveedorNoCorrespondeError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=proveedores_commands.manejar_costo_informar,
                contenido_cls=proveedores_commands.CostoInformarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0

        sobre_corregido = _sobre(
            tipo="COSTO_INFORMAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido=self._contenido(
                proveedor_id=proveedor_id,
                producto_id=producto_id,
                presentacion_id=presentacion_id,
                valor="100.00",
            ),
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=proveedores_commands.manejar_costo_informar,
            contenido_cls=proveedores_commands.CostoInformarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"
