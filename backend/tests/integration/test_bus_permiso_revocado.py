"""Change 17, tarea 12.2 (`design.md` D10, D11; spec `sistema/pipeline-de-comandos`, requisito "Un
permiso faltante rechaza el comando en modo ONLINE", y spec `sync/lote-de-comandos`, requisito "La
baja de un usuario no cierra el canal de su cola pendiente"): el paso 4 de `02` §6.3 en el lote.

- En modo `OFFLINE` el bus compara con los permisos que el usuario tiene al sincronizar: si falta
  el permiso del tipo, o el usuario o su rol están inactivos (se evalúan sin permisos), el comando
  sigue y queda `ACEPTADO_CON_OBSERVACIONES` con `PERMISO_REVOCADO` (permiso y motivo
  `PERMISO_QUITADO` | `USUARIO_INACTIVO` | `ROL_INACTIVO`). El handler recibe el modo y no vuelve a
  exigir el permiso.
- En modo `ONLINE` por el lote nada cambia: el handler rechaza y el lote sigue.

Tipo de prueba aislado por `monkeypatch`, con el mismo manejo de permisos que un handler real
(`cobranzas/commands.py`). El camino de punta a punta con `COBRANZA_REGISTRAR` y la renovación de
sesión está en `test_cobranzas_offline.py` (grupo 13) y en la clase final de este archivo.

Reglas citadas: SYN-10, SYN-05, SYN-04, SYN-09, INV-06, INV-17, SEG-06 y ADR-028 (D9.3-B, D9.4-A).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

from app.commands import catalogo, registro
from app.commands.catalogo import OperacionObservable
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

MOMENTO = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
TIPO = "PRUEBA_PERMISO_OFFLINE"
TIPO_SIN_OPERACION = "PRUEBA_PERMISO_OFFLINE_SIN_OPERACION"
PERMISO = "REGISTRAR_COBRANZA"

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


class _Esquema(BaseModel):
    resultado: str = "ACEPTADO"


def _handler(
    sobre: SobreComando, contenido: _Esquema, *, sesion: object, reloj: object
) -> tuple[str, dict[str, object] | None, str | None]:
    """Como un handler real: con conexión exige el permiso; sin conexión no lo vuelve a exigir
    (lo comparó el bus)."""
    if sobre.modo == "ONLINE":
        permitidos = identidad_service.listar_permisos_del_usuario(
            sobre.organizacion_id,
            sobre.usuario_id,
            sesion,  # type: ignore[arg-type]
        )
        if PERMISO not in permitidos:
            raise PermisoRequeridoError(f"Falta el permiso {PERMISO}.")
    if contenido.resultado == "RECHAZADO":
        return "RECHAZADO", None, "RECHAZADO_DE_PRUEBA"
    return "ACEPTADO", {"operacion_id": str(sobre.operation_id)}, None


@pytest.fixture(autouse=True)
def _catalogo_y_registro_aislados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo(
        TIPO,
        admite_online=True,
        admite_offline=True,
        permisos=(PERMISO,),
        operacion_offline=OperacionObservable("OPERACION_DE_PRUEBA", "operacion_id"),
    )
    registro.registrar_handler(TIPO, 1, _Esquema)(_handler)
    catalogo.declarar_tipo(
        TIPO_SIN_OPERACION, admite_online=True, admite_offline=True, permisos=(PERMISO,)
    )
    registro.registrar_handler(TIPO_SIN_OPERACION, 1, _Esquema)(_handler)


class Entorno:
    """Una organización con un vendedor, su dispositivo y su jornada `ABIERTA`."""

    def __init__(self, sesion: Session, *, con_permiso: bool = True) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=frozenset({PERMISO}) if con_permiso else frozenset()
        )
        self.jornada_id = crear_jornada_sql(
            sesion,
            self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            ubicacion_id=crear_ubicacion_sql(sesion, self.org, requiere_toma=True),
        )
        sesion.commit()

    def quitar_permiso(self) -> None:
        self.sesion.execute(
            text("DELETE FROM rol_permiso WHERE organizacion_id = :o AND permiso_codigo = :p"),
            {"o": self.org, "p": PERMISO},
        )
        self.sesion.commit()

    def inactivar_usuario(self) -> None:
        self.sesion.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"),
            {"u": self.usuario_id},
        )
        self.sesion.commit()

    def inactivar_rol(self) -> None:
        self.sesion.execute(
            text("UPDATE rol SET activo = false WHERE organizacion_id = :o"), {"o": self.org}
        )
        self.sesion.commit()

    def item(
        self,
        secuencia: int = 1,
        *,
        modo: str = "OFFLINE",
        tipo: str = TIPO,
        resultado: str = "ACEPTADO",
        operation_id: UUID | None = None,
    ) -> ItemLote:
        return ItemLote(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo=modo,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=secuencia,
            app_version="1.0.0",
            contenido={"resultado": resultado},
            jornada_id=self.jornada_id,
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

    def observaciones(self, operation_id: UUID) -> list[Observacion]:
        self.sesion.rollback()
        comando = self.sesion.scalar(
            select(Comando).where(
                Comando.organizacion_id == self.org, Comando.operation_id == operation_id
            )
        )
        if comando is None:
            return []
        return list(
            self.sesion.scalars(
                select(Observacion).where(
                    Observacion.organizacion_id == self.org, Observacion.comando_id == comando.id
                )
            ).all()
        )


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


# --- permiso quitado (SYN-10, SYN-05, INV-17) -------------------------------------------------


def test_syn10_un_permiso_quitado_acepta_el_comando_offline_con_permiso_revocado(
    entorno: Entorno,
) -> None:
    """Escenario "Un permiso quitado no rechaza un comando sin conexión" (SYN-10, SYN-05,
    INV-17): el comando se procesa, queda aceptado con la observación y su detalle."""
    entorno.quitar_permiso()
    item = entorno.item()

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert resultado.resultado == {"operacion_id": str(item.operation_id)}
    (observacion,) = entorno.observaciones(item.operation_id)
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert observacion.detalle == {"permiso": PERMISO, "motivo": "PERMISO_QUITADO"}
    assert observacion.estado == "PENDIENTE"
    assert observacion.operacion_tipo == "OPERACION_DE_PRUEBA"
    assert observacion.operacion_id == item.operation_id


def test_un_usuario_que_nunca_tuvo_el_permiso_tambien_queda_con_permiso_quitado(
    db_session: Session,
) -> None:
    """D11-A, triangulación: sin foto en el servidor, "nunca lo tuvo" y "se lo quitaron" son lo
    mismo: se acepta igual (SYN-05) con `PERMISO_REVOCADO`."""
    entorno = Entorno(db_session, con_permiso=False)
    item = entorno.item()

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = entorno.observaciones(item.operation_id)
    assert observacion.detalle == {"permiso": PERMISO, "motivo": "PERMISO_QUITADO"}


def test_un_permiso_dado_despues_de_abrir_la_jornada_vale(db_session: Session) -> None:
    """D11-A: se compara con lo vigente al sincronizar, no con lo que había al abrir."""
    entorno = Entorno(db_session, con_permiso=False)
    db_session.execute(
        text(
            "INSERT INTO rol_permiso (organizacion_id, rol_id, permiso_codigo) "
            "SELECT organizacion_id, rol_id, :p FROM usuario WHERE id = :u"
        ),
        {"p": PERMISO, "u": entorno.usuario_id},
    )
    db_session.commit()
    item = entorno.item()

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO"
    assert entorno.observaciones(item.operation_id) == []


# --- usuario y rol inactivos (ADR-028 D9.3-B, D9.4-A) -----------------------------------------


def test_adr028_un_usuario_inactivo_se_acepta_con_el_motivo_usuario_inactivo(
    entorno: Entorno,
) -> None:
    """Escenario "Un usuario dado de baja con cola pendiente": el lote no se rechaza y el comando
    `OFFLINE` queda aceptado con `PERMISO_REVOCADO` y el motivo `USUARIO_INACTIVO`."""
    entorno.inactivar_usuario()
    item = entorno.item()

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = entorno.observaciones(item.operation_id)
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert observacion.detalle == {"permiso": PERMISO, "motivo": "USUARIO_INACTIVO"}


def test_adr028_un_rol_inactivo_se_acepta_con_el_motivo_rol_inactivo(entorno: Entorno) -> None:
    """Escenario "Un rol desactivado" (D9.4-A)."""
    entorno.inactivar_rol()
    item = entorno.item()

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (observacion,) = entorno.observaciones(item.operation_id)
    assert observacion.detalle == {"permiso": PERMISO, "motivo": "ROL_INACTIVO"}


def test_un_usuario_y_un_rol_inactivos_informan_el_usuario_primero(entorno: Entorno) -> None:
    """Triangulación: con las dos causas, el motivo es el del usuario (el mismo orden que la
    renovación de sesión, `_motivo_sesion_deshabilitada`)."""
    entorno.inactivar_usuario()
    entorno.inactivar_rol()
    item = entorno.item()

    entorno.lote(item)

    (observacion,) = entorno.observaciones(item.operation_id)
    assert observacion.detalle == {"permiso": PERMISO, "motivo": "USUARIO_INACTIVO"}


# --- con el permiso, sin observación (SYN-10) ---------------------------------------------


def test_con_el_permiso_no_hay_observacion(entorno: Entorno) -> None:
    """Escenario "Con el permiso no hay observación"."""
    item = entorno.item()

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "ACEPTADO"
    assert entorno.observaciones(item.operation_id) == []


# --- ONLINE por el lote: nada cambia (SEG-06) -------------------------------------------------


def test_seg06_online_por_el_lote_sin_permiso_se_rechaza_y_el_lote_sigue(
    entorno: Entorno,
) -> None:
    """Escenario "Un usuario sin el permiso no ejecuta el comando": con conexión se rechaza (el
    handler lanza 403) y no queda ningún efecto; el ítem siguiente del lote se procesa."""
    entorno.quitar_permiso()
    sin_permiso = entorno.item(1, modo="ONLINE")
    sin_conexion = entorno.item(2, modo="OFFLINE")

    resultados = entorno.lote(sin_permiso, sin_conexion)

    por_id = {r.operation_id: r for r in resultados}
    assert por_id[sin_permiso.operation_id].estado == "RECHAZADO"
    assert por_id[sin_permiso.operation_id].error_codigo == "PERMISO_REQUERIDO"
    assert entorno.observaciones(sin_permiso.operation_id) == []
    assert por_id[sin_conexion.operation_id].estado == "ACEPTADO_CON_OBSERVACIONES"


def test_online_de_un_usuario_inactivo_se_rechaza_y_el_lote_sigue(entorno: Entorno) -> None:
    """Escenario "Comando con conexión de un usuario dado de baja": ADR-028, SEG-06."""
    entorno.inactivar_usuario()
    online = entorno.item(1, modo="ONLINE")
    offline = entorno.item(2, modo="OFFLINE")

    resultados = entorno.lote(online, offline)

    por_id = {r.operation_id: r for r in resultados}
    assert por_id[online.operation_id].estado == "RECHAZADO"
    assert por_id[offline.operation_id].estado == "ACEPTADO_CON_OBSERVACIONES"


# --- lo que el bus no hace ----------------------------------------------------------------


def test_un_comando_offline_rechazado_por_el_handler_no_deja_permiso_revocado(
    entorno: Entorno,
) -> None:
    """SYN-04: un resultado rechazado no deja observaciones, aunque el permiso falte."""
    entorno.quitar_permiso()
    item = entorno.item(resultado="RECHAZADO")

    (resultado,) = entorno.lote(item)

    assert resultado.estado == "RECHAZADO"
    assert entorno.observaciones(item.operation_id) == []


def test_inv06_el_doble_envio_devuelve_el_mismo_resultado_sin_otra_observacion(
    entorno: Entorno,
) -> None:
    """INV-06, SYN-09: el reenvío del mismo comando no vuelve a ejecutar el handler ni duplica
    la observación."""
    entorno.quitar_permiso()
    item = entorno.item()

    (primero,) = entorno.lote(item)
    (segundo,) = entorno.lote(item)

    assert (segundo.estado, segundo.resultado) == (primero.estado, primero.resultado)
    assert len(entorno.observaciones(item.operation_id)) == 1


def test_sin_operacion_declarada_la_observacion_se_anota_sobre_el_comando(
    entorno: Entorno,
) -> None:
    """Un tipo que no declara su operación observable deja `PERMISO_REVOCADO` sobre el comando
    mismo: la observación nunca se pierde."""
    entorno.quitar_permiso()
    item = entorno.item(tipo=TIPO_SIN_OPERACION)

    entorno.lote(item)

    (observacion,) = entorno.observaciones(item.operation_id)
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert observacion.operacion_tipo == "COMANDO"
