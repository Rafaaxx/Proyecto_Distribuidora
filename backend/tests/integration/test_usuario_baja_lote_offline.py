"""Change 20b, tarea 3.2: tras la baja real de un usuario (`USUARIO_BAJA`), el teléfono con jornada
abierta entrega su cola por el lote y el bus la acepta con `PERMISO_REVOCADO`
(motivo `USUARIO_INACTIVO`); nunca se rechaza por reglas de negocio.

El comportamiento del bus ya está cubierto con un tipo de prueba en `test_bus_permiso_revocado.py`
(change 17) y con la venta y la cobranza reales en `test_ventas_offline.py` y
`test_cobranzas_offline.py`. Acá se agrega solo lo que faltaba: que el estado `INACTIVO` lo deje el
comando real y no un `UPDATE` a mano.

Reglas citadas: SYN-05, SYN-10, INV-17, ADR-028 D9.3-B, ADR-052.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import Entorno as EntornoDeCobranzas
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_cobranzas_offline import _enviar as _enviar_cobranza
from test_ventas_offline import Ruta
from ventas_confirmar_utiles import MOMENTO_VENTA, RELOJ_VENTA, EntornoVenta

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.sync import service as sync_service
from app.modules.sync.models import Observacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


def _dar_de_baja_con_el_comando_real(sesion: Session, org: UUID, usuario_id: UUID) -> None:
    """Un administrador de la organización da de baja a `usuario_id` por el bus."""
    administrador_id, dispositivo_id = crear_usuario_y_dispositivo(
        sesion, org, permisos=frozenset({"ADMIN_USUARIOS"})
    )
    sesion.commit()
    sobre = SobreComando(
        operation_id=uuid4(),
        tipo="USUARIO_BAJA",
        version=1,
        modo="ONLINE",
        organizacion_id=org,
        usuario_id=administrador_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO_VENTA,
        secuencia=1,
        app_version="1.0.0",
        contenido={"usuario_id": str(usuario_id), "observacion": None},
    )
    handler = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido = registro.validar_contenido(handler, sobre.contenido)

    def _ejecutar(sesion_protegida: Any) -> Any:
        return handler.funcion(sobre, contenido, sesion=sesion_protegida, reloj=RELOJ_VENTA)

    comando = sync_service.procesar_comando(
        sesion,
        RELOJ_VENTA,
        sobre=sobre,
        huella=calcular_huella(sobre.contenido),
        ejecutar_handler=_ejecutar,
    )
    assert comando.estado == "ACEPTADO", comando.resultado


def _observaciones(sesion: Session, org: UUID) -> list[Observacion]:
    sesion.rollback()
    return list(sesion.scalars(select(Observacion).where(Observacion.organizacion_id == org)).all())


def test_syn10_la_venta_sin_conexion_de_un_dado_de_baja_se_acepta_con_permiso_revocado(
    db_session: Session,
) -> None:
    entorno = EntornoVenta(db_session)
    ruta = Ruta(entorno)
    _dar_de_baja_con_el_comando_real(db_session, entorno.org, entorno.usuario_id)

    _, resultado = ruta.enviar()

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (venta,) = entorno.ventas()
    permiso_revocado = [
        o for o in _observaciones(db_session, entorno.org) if o.codigo == "PERMISO_REVOCADO"
    ]
    assert len(permiso_revocado) == 1
    assert permiso_revocado[0].detalle == {"permiso": "VENDER", "motivo": "USUARIO_INACTIVO"}
    assert (permiso_revocado[0].operacion_tipo, permiso_revocado[0].operacion_id) == (
        "VENTA",
        venta.id,
    )


def test_syn10_la_cobranza_sin_conexion_de_un_dado_de_baja_se_acepta_con_permiso_revocado(
    db_session: Session,
) -> None:
    entorno = EntornoDeCobranzas(db_session)
    jornada = entorno.crear_jornada()
    _dar_de_baja_con_el_comando_real(db_session, entorno.org, entorno.usuario_id)

    resultado = _enviar_cobranza(entorno, entorno.contenido(), jornada_id=jornada)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    assert len(entorno.cobranzas()) == 1
    (observacion,) = _observaciones(db_session, entorno.org)
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert observacion.detalle == {"permiso": "REGISTRAR_COBRANZA", "motivo": "USUARIO_INACTIVO"}
