"""Change 18b, tarea 22.4 (`design.md` D2 y D23, ADR-056; spec `sync/lote-de-comandos`, requisito
"Los tipos que reciben secretos no entran por el lote"): `USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`
y `PIN_AUTORIZACION_PROPIO_DEFINIR` reciben un secreto (contraseña o PIN) fuera del contenido por
la clausura de su ruta. Por el lote, en cualquier modo, se rechazan con `MODO_NO_ADMITIDO_PARA_TIPO`
ANTES de reservar y de validar el contenido (que podría traer el secreto de un cliente viejo): sin
fila de `comando`, sin el contenido en los registros. Desde un dispositivo revocado se responde
`DISPOSITIVO_REVOCADO` sin fila de `comando_cuarentena` (el contenido no se guarda), mientras los
demás ítems del mismo lote sí van a cuarentena.

Reglas citadas: SYN-06, `02` §17, ADR-019, ADR-056, INV-06.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import app.main  # noqa: F401  (registra todos los handlers de producción)
from app.core.clock import FixedClock
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, ComandoCuarentena
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
SECRETO = "contrasena-que-no-debe-quedar-en-ningun-lado-9183"

CONTENIDOS: dict[str, dict[str, object]] = {
    "USUARIO_CREAR": {
        "usuario": "nuevo",
        "nombre": "Nueva Persona",
        "email": None,
        "password": SECRETO,
        "rol_id": str(uuid4()),
    },
    "PIN_AUTORIZACION_ROTAR": {"usuario_id": str(uuid4()), "pin": SECRETO},
    "PIN_AUTORIZACION_PROPIO_DEFINIR": {"pin": SECRETO, "password_actual": SECRETO},
    # Change 20b: la contraseña del restablecimiento y las dos de "Mi contraseña" (ADR-056).
    "USUARIO_CONTRASENA_RESTABLECER": {"usuario_id": str(uuid4()), "contrasena": SECRETO},
    "CONTRASENA_PROPIA_CAMBIAR": {"password_actual": SECRETO, "password_nueva": SECRETO},
}
PERMISOS_DE_LOS_TRES = frozenset(
    {"ADMIN_USUARIOS", "AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO", "VENDER", "GESTIONAR_CATALOGO"}
)


class Entorno:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=PERMISOS_DE_LOS_TRES
        )
        sesion.commit()

    def item(
        self, tipo: str, contenido: dict[str, object], *, modo: str, secuencia: int = 1
    ) -> ItemLote:
        return ItemLote(
            operation_id=uuid4(),
            tipo=tipo,
            version=1,
            modo=modo,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=secuencia,
            app_version="1.0.0",
            contenido=contenido,  # type: ignore[arg-type]
            jornada_id=None,
        )

    def lote(self, *items: ItemLote) -> list[sync_service.ResultadoItemLote]:
        return sync_service.procesar_lote(
            self.sesion,
            RELOJ,
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            items=list(items),
        )

    def cantidad(self, modelo: type) -> int:
        self.sesion.rollback()
        return int(
            self.sesion.scalar(
                select(func.count()).select_from(modelo).where(modelo.organizacion_id == self.org)
            )
            or 0
        )


@pytest.mark.parametrize("modo", ["ONLINE", "OFFLINE"])
@pytest.mark.parametrize("tipo", sorted(CONTENIDOS))
def test_syn06_un_tipo_con_secretos_se_rechaza_en_cualquier_modo_sin_dejar_rastro(
    db_session: Session, caplog: pytest.LogCaptureFixture, tipo: str, modo: str
) -> None:
    entorno = Entorno(db_session)
    item = entorno.item(tipo, CONTENIDOS[tipo], modo=modo)

    with caplog.at_level(logging.DEBUG):
        (resultado,) = entorno.lote(item)

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.cantidad(Comando) == 0
    assert entorno.cantidad(ComandoCuarentena) == 0
    assert SECRETO not in caplog.text


def test_syn06_el_rechazo_no_depende_de_que_el_contenido_sea_valido(db_session: Session) -> None:
    """Triangulación: un contenido vacío (inválido para el esquema) recibe el mismo rechazo por
    tipo y no el de contenido inválido: el tipo se descarta antes de mirar el contenido."""
    entorno = Entorno(db_session)

    (resultado,) = entorno.lote(entorno.item("USUARIO_CREAR", {}, modo="ONLINE"))

    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"


def test_syn06_dispositivo_revocado_no_guarda_el_secreto_y_los_demas_van_a_cuarentena(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session)
    db_session.execute(
        text("UPDATE dispositivo SET estado = 'REVOCADO' WHERE id = :d"),
        {"d": entorno.dispositivo_id},
    )
    db_session.commit()
    con_secreto = entorno.item("USUARIO_CREAR", CONTENIDOS["USUARIO_CREAR"], modo="OFFLINE")
    otro = entorno.item("COBRANZA_REGISTRAR", {"cualquier": "cosa"}, modo="OFFLINE", secuencia=2)

    resultados = entorno.lote(con_secreto, otro)

    assert [(r.estado, r.error_codigo) for r in resultados] == [
        ("RECHAZADO", "DISPOSITIVO_REVOCADO"),
        ("RECHAZADO", "DISPOSITIVO_REVOCADO"),
    ]
    db_session.rollback()
    en_cuarentena: list[UUID] = list(
        db_session.scalars(
            select(ComandoCuarentena.operation_id).where(
                ComandoCuarentena.organizacion_id == entorno.org
            )
        ).all()
    )
    assert en_cuarentena == [otro.operation_id]
    contenidos = db_session.scalars(select(ComandoCuarentena.contenido)).all()
    assert SECRETO not in str(contenidos)
