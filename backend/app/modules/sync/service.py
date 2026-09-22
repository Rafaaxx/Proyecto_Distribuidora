"""Interfaz pública de `sync` (`CLAUDE.md` §4): la reserva de idempotencia
de un comando (change 04, grupo 5, INV-06, `design.md` D3) y la transacción
completa del bus con reintentos transitorios (change 04, grupo 6, `02` §6.3).

`procesar_idempotente` es el mecanismo mínimo de idempotencia -- reserva,
compara huella, ejecuta el handler solo si la reserva es nueva, persiste el
resultado. A propósito, NO abre ni confirma ninguna transacción por su
cuenta (`sesion.flush()`, nunca `commit()`): la transacción la gestiona
quien llama (`procesar_comando`, más abajo, o la prueba misma en los casos
de concurrencia del grupo 5), igual que el resto del sistema (`02` §5.2).

`procesar_comando` envuelve `procesar_idempotente` con los pasos 4 a 7 del
pipeline (permisos, handler, resultado, commit) y con el reintento de la
transacción COMPLETA -- incluida la reserva -- ante un error transitorio de
PostgreSQL (serialización `40001`, interbloqueo `40P01`, `design.md` D5).
Vive acá y no en `app/commands/` porque `app/commands/` no importa ningún
`app/modules/*` (`design.md` D3, contrato `commands-no-modulos`) y esta
función necesita orquestar la persistencia de `comando`, que es de `sync`
-- la misma razón por la que `procesar_idempotente` ya vive acá y no allá.

Dos caminos de rechazo distintos y deliberados (decisión de diseño tomada
dentro del alcance del grupo 6, reportada para confirmación humana -- ver
resumen de la sesión; `design.md` fija el resultado observable de sus dos
escenarios pero no el mecanismo exacto, y esta es la única forma de
satisfacer ambos sin que se contradigan):

- El handler (o `verificar_permiso`) LANZA una excepción: es "el handler
  falla" (`02` §6.3). `procesar_comando` revierte TODA la transacción,
  incluida la reserva -- no queda ninguna fila de `comando` para ese
  `operation_id`, así que el mismo `operation_id` puede reintentarse como
  comando nuevo con el contenido corregido (escenario "Un identificador de
  operación rechazado por regla de negocio puede reintentarse corregido").
  La excepción se re-lanza tal cual para que la capa de API la traduzca.
- El handler DEVUELVE `("RECHAZADO", resultado, error_codigo)` sin lanzar
  (mecanismo del grupo 5, sin cambios): es una decisión de negocio que sí
  debe quedar registrada y visible ante un reenvío idéntico (SYN-09) -- se
  persiste como cualquier otro estado final, dentro de la misma transacción
  que confirma `procesar_comando`.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.commands import catalogo, registro
from app.commands.errores import (
    CodigoDeObservacionInvalidoError,
    ComandoInconsistenteError,
    ModoNoAdmitidoParaTipoError,
)
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import DomainError
from app.core.ids import nuevo_id
from app.core.logging import comando_contexto_var
from app.modules.identidad import service as identidad_service
from app.modules.sync import repository
from app.modules.sync.models import CODIGOS_OBSERVACION, Comando, ComandoCuarentena, Observacion

# Change 04, grupo 12 (tarea 12.2/12.3, `02` §17): logger dedicado al bus de
# comandos. Nunca recibe el CONTENIDO de un comando como argumento -- solo
# metadata (operation_id vía `ComandoContextoFilter`, duración, resultado,
# reintentos, tamaño de lote) -- para no filtrar datos de negocio en nivel
# INFO (`02` §18).
logger = logging.getLogger("app.sync")

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""`(estado, resultado, error_codigo)`, tal como lo devuelve un handler."""


@dataclass(frozen=True)
class ObservacionProducida:
    """Una observación que un handler produce como parte de su resultado
    (`design.md`, Goals: "un handler ... devuelve resultado y
    observaciones"; change 04, grupo 9, SYN-04, SYN-07, SYN-08).

    `operacion_tipo`/`operacion_id` identifican la operación de negocio
    sobre la que recae la observación -- no necesariamente el comando
    mismo (`comando_id` la asocia por separado): un handler de venta puede
    observar la venta que él mismo crea."""

    codigo: str
    operacion_tipo: str
    operacion_id: UUID
    detalle: dict[str, object] | None = None


ResultadoHandlerConObservaciones = tuple[
    str, dict[str, object] | None, str | None, tuple[ObservacionProducida, ...]
]
"""Extensión opcional de `ResultadoHandler` con un cuarto elemento: las
observaciones que produjo el handler (change 04, grupo 9, tarea 9.5). Un
handler existente que sigue devolviendo un 3-tuple no se ve afectado --
`_procesar_item_de_lote` distingue ambas formas por longitud, igual que ya
distingue por tipo el resto del contrato de `HandlerFuncion` (que devuelve
`object` a propósito, `design.md` D3)."""


def registrar_observacion(
    sesion: Session,
    *,
    comando_id: UUID,
    organizacion_id: UUID,
    observacion: ObservacionProducida,
) -> Observacion:
    """Registra una observación `PENDIENTE` asociada a `comando_id`
    (tarea 9.5). Sin `commit`: la transacción la gestiona quien llama
    (`procesar_comando`, o la prueba misma cuando ejercita el mecanismo
    directamente, mismo criterio que el resto de este módulo).

    Valida `observacion.codigo` contra el catálogo de la etapa (SYN-07,
    tarea 9.4) ANTES de tocar la sesión: un código fuera de
    `CODIGOS_OBSERVACION` nunca llega a intentar un `INSERT` (que la base
    igualmente rechazaría por `ck_observacion__codigo`, migración
    `f6a7b8c9d0e1`) -- la validación de aplicación da un error de dominio
    con código estable en vez de dejar que la excepción de integridad de la
    base burbujee tal cual."""
    if observacion.codigo not in CODIGOS_OBSERVACION:
        raise CodigoDeObservacionInvalidoError(
            f"{observacion.codigo!r} no está en el catálogo de observaciones de la etapa (SYN-07)."
        )
    return repository.crear_observacion(
        sesion,
        observacion_id=nuevo_id(),
        organizacion_id=organizacion_id,
        comando_id=comando_id,
        operacion_tipo=observacion.operacion_tipo,
        operacion_id=observacion.operacion_id,
        codigo=observacion.codigo,
        detalle=observacion.detalle,
    )


def registrar_observaciones(
    sesion: Session,
    *,
    comando_id: UUID,
    organizacion_id: UUID,
    observaciones: tuple[ObservacionProducida, ...],
) -> list[Observacion]:
    """Registra varias observaciones del mismo comando, en el orden en que
    el handler las produjo (tarea 9.5)."""
    return [
        registrar_observacion(
            sesion,
            comando_id=comando_id,
            organizacion_id=organizacion_id,
            observacion=observacion,
        )
        for observacion in observaciones
    ]


# `02` §6.3: los únicos SQLSTATE que el pipeline reintenta.
CODIGOS_SQLSTATE_TRANSITORIOS = frozenset({"40001", "40P01"})


def procesar_idempotente(
    sesion: Session,
    reloj: Clock,
    *,
    sobre: SobreComando,
    huella: str,
    ejecutar_handler: Callable[[], ResultadoHandler],
) -> Comando:
    """Reserva `(organizacion_id, operation_id)` de `sobre` y ejecuta
    `ejecutar_handler` únicamente si la reserva es nueva.

    - Reserva nueva: ejecuta `ejecutar_handler`, persiste su resultado en
      `comando` y lo devuelve.
    - `operation_id` ya registrado con la MISMA huella: devuelve el
      `comando` existente tal cual (su resultado guardado, o su estado
      intermedio si todavía está en curso), sin ejecutar `ejecutar_handler`
      (SYN-02).
    - `operation_id` ya registrado con OTRA huella: `ComandoInconsistenteError`
      (`COMANDO_INCONSISTENTE`), sin alterar el registro original (SYN-02,
      SYN-06).
    """
    reserva = repository.reservar_comando(
        sesion,
        comando_id=nuevo_id(),
        organizacion_id=sobre.organizacion_id,
        operation_id=sobre.operation_id,
        tipo=sobre.tipo,
        version=sobre.version,
        modo=sobre.modo,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        jornada_id=sobre.jornada_id,
        secuencia=sobre.secuencia,
        huella=huella,
        app_version=sobre.app_version,
        occurred_at=sobre.occurred_at,
        registered_at=reloj.now(),
    )

    if not reserva.gano:
        if reserva.comando.huella != huella:
            raise ComandoInconsistenteError(
                f"El comando {sobre.operation_id} ya está registrado con una huella distinta."
            )
        return reserva.comando

    estado, resultado, error_codigo = ejecutar_handler()
    repository.finalizar_comando(
        sesion, reserva.comando, estado=estado, resultado=resultado, error_codigo=error_codigo
    )
    return reserva.comando


class HandlerNoPuedeConfirmarError(RuntimeError):
    """Un handler intentó `commit`/`rollback`/`close` sobre la sesión que le
    entregó `procesar_comando` (`CLAUDE.md` §4: "Los handlers no hacen
    commit. La transacción la gestiona el bus."). Error de programación:
    nunca debería alcanzar producción con un handler real."""


class SesionSinCommit:
    """Envoltorio de una `Session` real que `procesar_comando` entrega a
    `ejecutar_handler`: delega cualquier atributo salvo `commit`,
    `rollback` y `close`, que rechaza. Convierte la regla "un handler no
    confirma la transacción" en una propiedad verificable en tiempo de
    ejecución, no solo en una convención de código (tarea 6.3)."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    def __getattr__(self, nombre: str) -> object:
        return getattr(self._sesion, nombre)

    def commit(self) -> None:
        raise HandlerNoPuedeConfirmarError(
            "Un handler no puede confirmar la transacción: la gestiona el bus."
        )

    def rollback(self) -> None:
        raise HandlerNoPuedeConfirmarError(
            "Un handler no puede revertir la transacción: la gestiona el bus."
        )

    def close(self) -> None:
        raise HandlerNoPuedeConfirmarError(
            "Un handler no puede cerrar la sesión: la gestiona el bus."
        )


class ErrorTransitorioAgotadoError(Exception):
    """Se agotaron los reintentos ante fallos transitorios de PostgreSQL
    (`02` §6.3). Distinguible de un `RECHAZADO`: el cliente puede reintentar
    más tarde SIN cambiar el `operation_id`, porque el comando no queda con
    estado final (SYN-04, SYN-09)."""

    codigo = "ERROR_TRANSITORIO"

    def __init__(self, mensaje: str, *, intentos: int) -> None:
        super().__init__(mensaje)
        self.intentos = intentos


@dataclass(frozen=True)
class ConfiguracionReintentos:
    """Parámetros operativos del reintento (`design.md` D5): no son regla de
    negocio, se ajustan sin ADR. Espera exponencial con jitter completo
    (`random.uniform(0, techo)`): el jitter evita que dos transacciones que
    chocan por la misma fila reintenten en fase y vuelvan a chocar."""

    intentos_maximos: int = 3
    espera_base_segundos: float = 0.02
    espera_techo_segundos: float = 0.5


def es_error_transitorio(error: BaseException) -> bool:
    """`02` §6.3: serialización (`40001`) e interbloqueo (`40P01`), leídos
    de `.orig.sqlstate` (el driver psycopg expone `sqlstate` en la
    excepción original que SQLAlchemy envuelve en `DBAPIError`/subclases).
    Un error de dominio (`DomainError`, sin `.orig`) nunca es transitorio,
    ni ningún otro fallo que no traiga ese código."""
    sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
    return sqlstate in CODIGOS_SQLSTATE_TRANSITORIOS


def _espera_para_intento(intento: int, config: ConfiguracionReintentos) -> float:
    techo = min(config.espera_techo_segundos, config.espera_base_segundos * (2**intento))
    return random.uniform(0, techo)


def procesar_comando(
    sesion: Session,
    reloj: Clock,
    *,
    sobre: SobreComando,
    huella: str,
    ejecutar_handler: Callable[[object], ResultadoHandler],
    verificar_permiso: Callable[[], None] = lambda: None,
    config: ConfiguracionReintentos | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> Comando:
    """Ejecuta el pipeline del comando dentro de una transacción y la
    confirma (`02` §6.3, pasos 2 a 7: reserva -- delegada a
    `procesar_idempotente` --, permisos, handler, resultado, commit).
    Reintenta la transacción COMPLETA, incluida la reserva, hasta
    `config.intentos_maximos` veces ante un error transitorio de PostgreSQL.

    `ejecutar_handler` recibe una `SesionSinCommit` (tarea 6.3), nunca la
    `Session` real: así un handler no puede confirmar ni revertir la
    transacción por su cuenta. `verificar_permiso` corre antes que
    `ejecutar_handler`, dentro de la misma reserva ya tomada (SEG-06,
    `02` §6.3 paso 4): si lanza, revierte también la reserva, igual que un
    fallo del handler.

    Auditoría automática (change 04, grupo 10, tarea 10.5): TODO comando
    que efectivamente ejecuta su handler (reserva nueva, `procesar_
    idempotente` decide esto -- ver grupo 5) queda auditado con `origen=
    'COMANDO'` y el `operation_id` del sobre, escrito con la `Session`
    REAL (no `sesion_protegida`) para que la auditoría en sí no dependa
    de un handler que no puede tocar la sesión protegida, y confirmado en
    el mismo `sesion.commit()` que los efectos del comando (INV-01,
    TR-06). Un reenvío idempotente (SYN-02, la reserva ya existía con la
    misma huella) NO ejecuta el handler y por lo tanto no vuelve a
    auditar -- lo distingue el flag `se_ejecuto_el_handler`, puesto en
    `True` únicamente dentro de `_paso_permiso_y_handler`, la misma
    función que `procesar_idempotente` invoca solo cuando la reserva es
    nueva.
    """
    configuracion = config or ConfiguracionReintentos()
    sesion_protegida = SesionSinCommit(sesion)
    se_ejecuto_el_handler = False
    inicio = time.monotonic()

    def _paso_permiso_y_handler() -> ResultadoHandler:
        nonlocal se_ejecuto_el_handler
        verificar_permiso()
        se_ejecuto_el_handler = True
        return ejecutar_handler(sesion_protegida)

    # Change 04, grupo 12 (tarea 12.2): contexto de comando propagado a
    # cualquier registro emitido durante esta ejecución -- por CUALQUIER
    # logger, no solo el de acá arriba -- vía `ComandoContextoFilter`
    # (`core/logging.py`). Todos los valores viajan como `str` porque un
    # `LogRecord`/JSON no distingue `UUID` de texto, y `JsonFormatter` ya
    # hace `default=str` para lo que no serialice -- pero acá se hace
    # explícito, no implícito. Se libera (`reset`) al salir, éxito o error,
    # para que un registro posterior fuera de esta ejecución no herede este
    # contexto (tarea 12.1, escenario "campos aún sin origen").
    token = comando_contexto_var.set(
        {
            "operation_id": str(sobre.operation_id),
            "organizacion_id": str(sobre.organizacion_id),
            "usuario_id": str(sobre.usuario_id),
            "dispositivo_id": str(sobre.dispositivo_id),
        }
    )
    try:
        for intento in range(configuracion.intentos_maximos):
            se_ejecuto_el_handler = False
            try:
                comando = procesar_idempotente(
                    sesion,
                    reloj,
                    sobre=sobre,
                    huella=huella,
                    ejecutar_handler=_paso_permiso_y_handler,
                )
                if se_ejecuto_el_handler:
                    identidad_service.registrar_auditoria(
                        sobre.organizacion_id,
                        sesion,
                        reloj,
                        accion=sobre.tipo,
                        entidad="comando",
                        entidad_id=comando.id,
                        ocurrido_en=sobre.occurred_at,
                        usuario_id=sobre.usuario_id,
                        dispositivo_id=sobre.dispositivo_id,
                        origen="COMANDO",
                        operation_id=sobre.operation_id,
                    )
                sesion.commit()
                # Tarea 12.3 (`02` §17): duración, resultado y reintentos por
                # comando, SIN el contenido (nunca se pasa `sobre.contenido`
                # ni `comando.resultado` acá -- solo metadata).
                duracion_ms = (time.monotonic() - inicio) * 1000
                logger.info(
                    "Comando procesado",
                    extra={
                        "duration_ms": round(duracion_ms, 2),
                        "resultado": comando.estado,
                        "reintentos": intento,
                    },
                )
                return comando
            except Exception as error:
                sesion.rollback()
                if not es_error_transitorio(error):
                    raise
                if intento == configuracion.intentos_maximos - 1:
                    raise ErrorTransitorioAgotadoError(
                        f"Se agotaron los {configuracion.intentos_maximos} intentos por "
                        "errores transitorios de PostgreSQL.",
                        intentos=configuracion.intentos_maximos,
                    ) from error
                dormir(_espera_para_intento(intento, configuracion))

        raise AssertionError("inalcanzable: el bucle siempre retorna o lanza")  # pragma: no cover
    finally:
        comando_contexto_var.reset(token)


# --- Lote de sincronización y cuarentena (change 04, grupo 8) --------------
#
# `02` §6.3 paso 1 y `design.md` D6: si el dispositivo está revocado, el
# comando se guarda en cuarentena EN UNA TRANSACCIÓN APARTE (con su propio
# `commit`, distinto de `procesar_comando` de arriba, que nunca confirma por
# su cuenta) y se responde RECHAZADO sin llegar siquiera a la reserva de
# idempotencia de `comando` -- SYN-06 no exige que un comando de un
# dispositivo revocado deje NINGÚN rastro en `comando`, solo en
# `comando_cuarentena`.


class ColaAjenaError(DomainError):
    """La cola pertenece al usuario y al dispositivo que la generaron (`02`
    §6.4, SEG-02, change 04, tarea 8.5): un ítem del lote cuyo `usuario_id`
    o `dispositivo_id` declarado no coincide con el de la sesión que
    sincroniza se rechaza -- el LOTE COMPLETO, antes de procesar nada, para
    no ejecutar ni un solo comando ajeno.

    Decisión de diseño tomada dentro del alcance de este grupo (mismo
    criterio que las tareas 3.3/4.5/6.2/7.3: reportada para confirmación
    humana): `02` §6.2 dice que `usuario_id`/`dispositivo_id` salen SIEMPRE
    del token, nunca del contenido -- eso es literal para los endpoints REST
    directos (D4), donde no hay otra fuente. Pero la cola local (Dexie,
    `cola` de `02` §13.2) puede acumular comandos generados por una sesión
    distinta de la que finalmente sincroniza (mismo dispositivo, otro
    usuario que inició sesión después; o el mismo usuario en otro
    dispositivo). Para que el escenario "Otro usuario no puede sincronizar
    la cola ajena" sea un RECHAZO real y no una reatribución silenciosa
    (que sería peor: ejecutar la operación de A como si la hubiera hecho
    B), el ítem del lote SÍ declara `usuario_id`/`dispositivo_id` -- el
    valor con el que se generó localmente -- y el servidor los compara
    contra `ContextoAutenticado` (el token de la petición HTTP que envía el
    lote), rechazando ante cualquier discrepancia en vez de sobreescribir.
    El sobre de cada comando aceptado usa igualmente los valores del
    token (nunca el declarado) una vez pasada esta verificación de
    igualdad -- la propiedad "el contenido no elige quién es" (`sobre.py`)
    se preserva."""

    codigo = "COLA_AJENA"
    status_http = 403


@dataclass(frozen=True)
class ItemLote:
    """Un comando dentro del lote de sincronización (`02` §6.2, §6.4),
    antes de convertirse en `SobreComando`. `usuario_id`/`dispositivo_id`
    son los declarados por el dispositivo al generarlo (ver
    `ColaAjenaError`), no necesariamente los de la sesión HTTP actual --
    `procesar_lote` los verifica antes de construir el sobre real."""

    operation_id: UUID
    tipo: str
    version: int
    modo: str
    usuario_id: UUID
    dispositivo_id: UUID
    occurred_at: datetime
    secuencia: int
    app_version: str
    contenido: dict[str, ContenidoComando] = field(default_factory=dict)
    jornada_id: UUID | None = None


@dataclass(frozen=True)
class ResultadoItemLote:
    """Un resultado por comando del lote (SYN-04, SYN-09, `02` §6.4):
    identificado por su `operation_id`, nunca por su posición -- el cliente
    no debe asumir que el orden de la respuesta es el de la petición."""

    operation_id: UUID
    estado: str
    resultado: dict[str, object] | None
    error_codigo: str | None


def poner_en_cuarentena(
    sesion: Session,
    reloj: Clock,
    *,
    organizacion_id: UUID,
    dispositivo_id: UUID,
    usuario_id: UUID,
    operation_id: UUID,
    tipo: str,
    contenido: dict[str, ContenidoComando],
    motivo: str,
) -> ComandoCuarentena:
    """Guarda un comando en cuarentena y CONFIRMA de inmediato (`design.md`
    D6, `02` §6.3 paso 1: "transacción aparte"), a propósito distinto del
    resto de este módulo -- ni `procesar_idempotente` ni `procesar_comando`
    hacen `commit` por su cuenta, pero esta función SÍ, porque es el paso 1
    del pipeline, no un handler. El reenvío del mismo `operation_id` no
    duplica el registro (`repository.crear_cuarentena`, `ON CONFLICT DO
    NOTHING`, tarea 8.8)."""
    resultado = repository.crear_cuarentena(
        sesion,
        cuarentena_id=nuevo_id(),
        organizacion_id=organizacion_id,
        dispositivo_id=dispositivo_id,
        usuario_id=usuario_id,
        operation_id=operation_id,
        tipo=tipo,
        contenido=contenido,
        motivo=motivo,
        recibido_en=reloj.now(),
    )
    sesion.commit()
    return resultado.registro


def _procesar_item_de_lote(
    sesion: Session,
    reloj: Clock,
    *,
    sobre: SobreComando,
    config: ConfiguracionReintentos | None,
    dormir: Callable[[float], None],
) -> Comando:
    """Resuelve el handler de `(sobre.tipo, sobre.version)` (`app.commands.
    registro`), valida el modo contra el catálogo (tarea 8.10) y el
    contenido contra su esquema, y delega en `procesar_comando`. Cualquier
    excepción de acá (tipo desconocido, versión sin handler, modo no
    admitido, contenido inválido) ocurre ANTES de la reserva de
    idempotencia: no hay `commit` que revertir todavía, así que se propaga
    tal cual -- `procesar_lote` la traduce a un resultado RECHAZADO sin que
    quede ninguna fila de `comando` (reintentable con contenido corregido,
    mismo criterio que un handler que lanza, tarea 6.2)."""
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    declarado = catalogo.tipo_declarado(sobre.tipo)
    if declarado is not None:
        admite_el_modo = (
            declarado.admite_online if sobre.modo == "ONLINE" else declarado.admite_offline
        )
        if not admite_el_modo:
            raise ModoNoAdmitidoParaTipoError(
                f"El tipo {sobre.tipo!r} no admite el modo {sobre.modo!r} (`02` §6.5)."
            )
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)
    huella = calcular_huella(sobre.contenido)

    def _ejecutar_handler(_sesion_protegida: object) -> ResultadoHandler:
        resultado_bruto = handler_registrado.funcion(sobre, contenido_validado)
        assert isinstance(resultado_bruto, tuple) and len(resultado_bruto) in (3, 4), (
            "Un handler registrado (`app.commands.registro`) DEBE devolver "
            "una tupla (estado, resultado, error_codigo) o, si produce "
            "observaciones (tarea 9.5), (estado, resultado, error_codigo, "
            "observaciones): convención del bus (`design.md` D3), no "
            "impuesta por el tipo de `HandlerFuncion` porque `app.commands` "
            "no puede importar `ResultadoHandler` de `app.modules.sync` "
            "(contrato `commands-no-modulos`)."
        )
        if len(resultado_bruto) == 4:
            estado, resultado, error_codigo, observaciones = resultado_bruto
        else:
            estado, resultado, error_codigo = resultado_bruto
            observaciones = ()

        # Tarea 9.5: las observaciones se registran EN LA MISMA transacción
        # del comando, a través de `sync/service.py` -- `sesion` (la real,
        # no la envoltura `SesionSinCommit` que recibe el handler de
        # negocio) está disponible por clausura de `_procesar_item_de_lote`,
        # ya con la reserva de `comando` flusheada por `procesar_idempotente`
        # antes de invocar este callback, así que `comando_actual` siempre
        # existe. Un comando RECHAZADO no deja observaciones (SYN-04): si el
        # handler devolviera observaciones junto con un rechazo (no debería,
        # SYN-07 lo prohíbe implícitamente), se descartan en vez de
        # registrarse.
        if observaciones:
            if estado == "ACEPTADO":
                estado = "ACEPTADO_CON_OBSERVACIONES"
            if estado == "ACEPTADO_CON_OBSERVACIONES":
                comando_actual = repository.obtener_comando_por_operation_id(
                    sesion, sobre.organizacion_id, sobre.operation_id
                )
                assert comando_actual is not None  # ya reservado antes de llegar acá.
                registrar_observaciones(
                    sesion,
                    comando_id=comando_actual.id,
                    organizacion_id=sobre.organizacion_id,
                    observaciones=observaciones,
                )

        return estado, resultado, error_codigo

    return procesar_comando(
        sesion,
        reloj,
        sobre=sobre,
        huella=huella,
        ejecutar_handler=_ejecutar_handler,
        config=config,
        dormir=dormir,
    )


def procesar_lote(
    sesion: Session,
    reloj: Clock,
    *,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    items: list[ItemLote],
    config: ConfiguracionReintentos | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> list[ResultadoItemLote]:
    """Procesa el lote de sincronización (`02` §6.4, change 04, grupo 8).

    - Lote vacío: devuelve `[]` sin error (tarea 8.2).
    - Ordena por `secuencia` creciente, NO por la posición en la lista
      (SYN-03, tareas 8.1).
    - Si algún ítem declara un `usuario_id`/`dispositivo_id` distinto del de
      la sesión, rechaza TODO el lote con `ColaAjenaError` antes de procesar
      nada (tarea 8.5).
    - Si el dispositivo de la sesión está `REVOCADO`, cada ítem se guarda en
      cuarentena y se responde RECHAZADO, sin pasar por `comando` (tareas
      8.7, 8.8).
    - Un resultado ACEPTADO/ACEPTADO_CON_OBSERVACIONES/RECHAZADO no detiene
      el lote (tarea 8.3); un error transitorio agotado SÍ lo detiene, y los
      ítems posteriores no se procesan (tarea 8.4).
    """
    # Tarea 12.3 (`02` §17): tamaño del lote, ANTES de cualquier salida
    # temprana -- un lote vacío también informa su tamaño (0), no se omite
    # el registro por estar vacío. Nunca el contenido de sus ítems.
    logger.info("Procesando lote de sincronización", extra={"lote_tamano": len(items)})

    if not items:
        return []

    for item in items:
        if item.usuario_id != usuario_id or item.dispositivo_id != dispositivo_id:
            raise ColaAjenaError(
                "La cola pertenece al usuario y al dispositivo que generaron sus "
                "comandos: este lote incluye al menos un comando de otra sesión."
            )

    items_ordenados = sorted(items, key=lambda item: item.secuencia)

    dispositivo = identidad_service.obtener_dispositivo(organizacion_id, sesion, dispositivo_id)
    if dispositivo is not None and dispositivo.estado == "REVOCADO":
        resultados_cuarentena: list[ResultadoItemLote] = []
        for item in items_ordenados:
            poner_en_cuarentena(
                sesion,
                reloj,
                organizacion_id=organizacion_id,
                dispositivo_id=dispositivo_id,
                usuario_id=usuario_id,
                operation_id=item.operation_id,
                tipo=item.tipo,
                contenido=item.contenido,
                motivo="DISPOSITIVO_REVOCADO",
            )
            resultados_cuarentena.append(
                ResultadoItemLote(
                    operation_id=item.operation_id,
                    estado="RECHAZADO",
                    resultado=None,
                    error_codigo="DISPOSITIVO_REVOCADO",
                )
            )
        return resultados_cuarentena

    resultados: list[ResultadoItemLote] = []
    for item in items_ordenados:
        sobre = SobreComando(
            operation_id=item.operation_id,
            tipo=item.tipo,
            version=item.version,
            modo=item.modo,
            organizacion_id=organizacion_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=item.occurred_at,
            secuencia=item.secuencia,
            app_version=item.app_version,
            contenido=item.contenido,
            jornada_id=item.jornada_id,
        )
        try:
            comando = _procesar_item_de_lote(
                sesion, reloj, sobre=sobre, config=config, dormir=dormir
            )
        except ErrorTransitorioAgotadoError as error:
            resultados.append(
                ResultadoItemLote(
                    operation_id=item.operation_id,
                    estado="ERROR_TRANSITORIO",
                    resultado=None,
                    error_codigo=error.codigo,
                )
            )
            break  # tarea 8.4: un error transitorio corta el lote acá.
        except DomainError as error:
            resultados.append(
                ResultadoItemLote(
                    operation_id=item.operation_id,
                    estado="RECHAZADO",
                    resultado=None,
                    error_codigo=error.codigo,
                )
            )
            continue  # tarea 8.3: un rechazo no detiene el lote.
        else:
            resultados.append(
                ResultadoItemLote(
                    operation_id=comando.operation_id,
                    estado=comando.estado,
                    resultado=comando.resultado,
                    error_codigo=comando.error_codigo,
                )
            )
    return resultados
