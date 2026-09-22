"""Change 04, grupo 12 (tarea 12.3, `02` §17): el registro de un lote de
sincronización informa su tamaño.

Nivel de servicio (`sync_service.procesar_lote`) con Postgres real -- mismo
arnés que `tests/integration/test_bus_lote_sincronizacion.py` (grupo 8): un
tipo de comando de prueba aislado por `monkeypatch`, organización/usuario/
dispositivo reales. El cableado de contexto de comando (operation_id por
ítem, duración/resultado/reintentos por comando) ya está cubierto a nivel
unitario en `tests/unit/test_logging_contexto_comando.py`; acá se cubre
específicamente lo que solo existe a nivel de `procesar_lote`: el tamaño del
lote completo.

Spec: `sistema/logging-estructurado`, escenario "El registro de un lote
informa su tamaño".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.commands import catalogo, registro
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-de-prueba-grupo-12"


class _EsquemaPrueba(BaseModel):
    resultado: Literal["ACEPTADO", "RECHAZADO"] = "ACEPTADO"


def _handler_prueba(
    sobre: SobreComando, contenido: _EsquemaPrueba
) -> tuple[str, dict[str, object] | None, str | None]:
    if contenido.resultado == "RECHAZADO":
        return "RECHAZADO", None, "RECHAZADO_DE_PRUEBA"
    return "ACEPTADO", {}, None


@pytest.fixture(autouse=True)
def _logger_sync_habilitado() -> None:
    """Descubrimiento (grupo 12, ver `tests/unit/test_logging_contexto_
    comando.py::captura_sync`): si `tests/unit/test_import_linter_bus_de_
    comandos.py` corrió antes en la misma sesión de pytest, su
    `logging.config.dictConfig` interno deja `.disabled = True` en el
    logger `app.sync` -- eso corta `caplog` de raíz (`Logger.handle`
    comprueba `self.disabled` ANTES de sus handlers), sin importar nivel ni
    propagación. Se fuerza `False` acá para que estas pruebas no dependan
    del orden de recolección de otros archivos de la suite completa."""
    logging.getLogger("app.sync").disabled = False


@pytest.fixture(autouse=True)
def _catalogo_y_registro_aislados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo("PRUEBA_LOTE_G12", admite_online=True, admite_offline=True)
    registro.registrar_handler("PRUEBA_LOTE_G12", 1, _EsquemaPrueba)(_handler_prueba)


def _crear_organizacion(sesion: Session, *, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba grupo 12",
        slug=slug,
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
    return organizacion


def _crear_usuario_y_dispositivo(sesion: Session, organizacion_id: UUID) -> tuple[UUID, UUID]:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Vendedor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"vendedor-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo=f"P{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _item(*, usuario_id: UUID, dispositivo_id: UUID, secuencia: int) -> ItemLote:
    return ItemLote(
        operation_id=uuid4(),
        tipo="PRUEBA_LOTE_G12",
        version=1,
        modo="ONLINE",
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido={"resultado": "ACEPTADO"},
    )


class TestUnaAplicacionDesactualizadaPuedeVaciarSuCola:
    """Change 04, grupo 12, tarea 12.4 (`design.md` D9, `02` §6.6).

    Alcance decidido para este grupo: SOLO el contrato de "no rechazo" --
    un lote con ítems de una app cuyo `app_version` es anterior a
    `Settings.app_version_minima` configurada se sigue procesando sin
    rechazo. El backend NO implementa bloqueo real de "operaciones nuevas"
    para apps desactualizadas en este grupo (eso es responsabilidad del
    frontend, grupo 13): por eso ninguna línea de producción cambia para
    que esta prueba pase -- ya pasa hoy, y esta prueba fija ese contrato
    para que un cambio futuro que agregue el bloqueo real no lo rompa por
    accidente sin darse cuenta de que está cambiando de alcance.

    Spec `sistema/salud-y-version`, escenario "Una aplicación desactualizada
    puede vaciar su cola"."""

    def test_un_item_con_app_version_anterior_a_la_minima_se_procesa_igual(
        self, db_session: Session
    ) -> None:
        # La versión mínima configurada ni siquiera es consultada por
        # `procesar_lote`/`procesar_comando` en este grupo -- se construye
        # acá solo para documentar el escenario tal como lo describe la
        # spec (un dispositivo "desactualizado" respecto de ella).
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://u:p@localhost:5432/db",
            jwt_secret="secreto-de-prueba-version-minima",
            app_version_minima="9.9.9",
        )

        organizacion = _crear_organizacion(
            db_session, slug=f"org-app-desactualizada-{uuid4().hex[:8]}"
        )
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        item_de_app_vieja = ItemLote(
            operation_id=uuid4(),
            tipo="PRUEBA_LOTE_G12",
            version=1,
            modo="ONLINE",
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="0.1.0",  # muy anterior a la mínima configurada arriba
            contenido={"resultado": "ACEPTADO"},
        )

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item_de_app_vieja],
        )

        assert len(resultados) == 1
        assert resultados[0].estado == "ACEPTADO"
        assert resultados[0].error_codigo is None


class TestElRegistroDeUnLoteInformaSuTamano:
    def test_un_lote_de_tres_comandos_informa_tamano_tres(
        self, db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-tamano-lote-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        items = [
            _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=i) for i in range(1, 4)
        ]

        with caplog.at_level(logging.INFO, logger="app.sync"):
            sync_service.procesar_lote(
                db_session,
                FixedClock(MOMENTO),
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                items=items,
            )

        registros_de_lote = [
            r for r in caplog.records if getattr(r, "lote_tamano", None) is not None
        ]
        assert registros_de_lote, "procesar_lote debe emitir un registro con el tamaño del lote"
        assert registros_de_lote[0].lote_tamano == 3

    def test_un_lote_vacio_informa_tamano_cero(
        self, db_session: Session, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Triangulación: un lote sin ítems también informa su tamaño (0),
        no se omite el registro por estar vacío."""
        organizacion = _crear_organizacion(db_session, slug=f"org-tamano-vacio-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        with caplog.at_level(logging.INFO, logger="app.sync"):
            sync_service.procesar_lote(
                db_session,
                FixedClock(MOMENTO),
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo,
                items=[],
            )

        registros_de_lote = [
            r for r in caplog.records if getattr(r, "lote_tamano", None) is not None
        ]
        assert registros_de_lote
        assert registros_de_lote[0].lote_tamano == 0
