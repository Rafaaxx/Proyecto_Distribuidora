"""Ruta de escritura de `cuentas_corrientes` (change 08, grupo 6, tarea 6.1;
`design.md` D1, D5, D14).

`POST /cuentas-corrientes/saldos-iniciales` es la ruta DEDICADA de
`SALDO_INICIAL_REGISTRAR` (`ONLINE`): mismo patrón que `proveedores/api.py` y
`clientes/api.py`, porque el despacho genérico de `POST /sync/comandos` no ejecuta
handlers `ONLINE` (deuda nominada al change 17). Declara `requiere_comando_online`
(exige `Operation-Id`, SYN-01/TR-07; permiso `IMPORTAR_DATOS`, D1) y delega en
`sync_service.procesar_comando`. La respuesta sale de `comando.resultado`, así que
un reenvío idempotente devuelve exactamente lo mismo (INV-06).

Las rutas de LECTURA del estado de cuenta no viven acá sino con su entidad
(`clientes/api.py`, `proveedores/api.py`, `02` §11): comprueban la entidad y el
permiso propios (D2) y llaman a `cuentas_corrientes.service.estado_de_cuenta`.

`organizacion_id` sale siempre del token (INV-21). Una entidad ajena o inexistente
responde 404: lo garantiza la FK compuesta de D6, que el repositorio traduce a
`RecursoNoEncontradoError` (D7)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import construir_sobre_online
from app.core.autenticacion import EntradaComandoOnline, requiere_comando_online
from app.core.clock import SystemClock
from app.modules.cuentas_corrientes import commands as cuentas_corrientes_commands
from app.modules.cuentas_corrientes.domain.errores import ImporteInvalidoError
from app.modules.cuentas_corrientes.schemas import (
    SaldoInicialRegistrarRequest,
    SaldoInicialResponse,
)
from app.modules.sync import service as sync_service

PERMISO_SALDO_INICIAL = "IMPORTAR_DATOS"

router = APIRouter(prefix="/cuentas-corrientes", tags=["cuentas-corrientes"])


def _resultado_de(comando: sync_service.Comando) -> dict[str, object]:
    assert comando.resultado is not None
    return comando.resultado


@router.post("/saldos-iniciales", response_model=SaldoInicialResponse, status_code=201)
def registrar_saldo_inicial(
    datos: SaldoInicialRegistrarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_SALDO_INICIAL))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> SaldoInicialResponse:
    if isinstance(datos.importe, float):
        # La huella canónica del comando no admite `float` (INV-03): un número
        # con decimales en el JSON se rechaza acá, con el mismo código de dominio
        # que el resto de los importes mal formados, en vez de un error interno.
        raise ImporteInvalidoError('El importe debe enviarse como texto, por ejemplo "150000.00".')
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "cuenta_tipo": datos.cuenta_tipo,
        "entidad_id": str(datos.entidad_id),
        "importe": datos.importe,
        "sentido": datos.sentido,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="SALDO_INICIAL_REGISTRAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return cuentas_corrientes_commands.manejar_saldo_inicial_registrar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    return SaldoInicialResponse(
        movimiento_id=UUID(str(resultado["movimiento_id"])), saldo=str(resultado["saldo"])
    )
