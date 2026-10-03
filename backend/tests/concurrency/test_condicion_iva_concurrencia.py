"""Change 11b, tarea 8.1: concurrencia real de `ORGANIZACION_CONDICION_IVA_CAMBIAR` contra
PostgreSQL real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md` §7.1), con el
mismo arnés que `test_compras_concurrencia.py`: cada hilo tiene su propia conexión/sesión,
confirma su propia transacción y arranca junto a los otros en una `threading.Barrier`. Nunca
hay rollback externo (`CLAUDE.md` §4).

Escenarios (`design.md` D3, D7; specs `parametros-de-organizacion` y `compras`):

- una `COMPRA_CONFIRMAR` simultánea con un cambio de condición: todas las líneas de la compra
  llevan la misma regla (`computa_credito_fiscal` idéntico, la que rigió al leer la condición,
  CST-06, TR-06) y no hay interbloqueo;
- dos cambios simultáneos al mismo valor: uno `ACEPTADO` y el otro `CONDICION_IVA_SIN_CAMBIO`
  (TR-10), con una sola auditoría.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.db import crear_engine
from app.core.errors import DomainError
from app.modules.identidad import commands as identidad_commands
from app.modules.sync import service as sync_service
from tests.concurrency.test_compras_concurrencia import (
    MOMENTO,
    RELOJ,
    _en_paralelo,
    _Escenario,
    _sesion_independiente,
)
from tests.integration.cuentas_corrientes_utiles import crear_usuario_y_dispositivo

CAMBIAR = "ORGANIZACION_CONDICION_IVA_CAMBIAR"
RONDAS = 6


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _EscenarioFiscal(_Escenario):
    """El escenario de compras más un administrador (`ADMIN_CONFIGURACION`) y una organización
    sin modalidad de IVA, que es lo que la base exige para poder pasar a no inscripta (D2)."""

    def __init__(self, database_url: str) -> None:
        super().__init__(database_url)
        sesion = _sesion_independiente(database_url)
        try:
            self.admin_id, self.admin_dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"ADMIN_CONFIGURACION"})
            )
            sesion.execute(
                text(
                    "UPDATE configuracion_organizacion SET modo_impositivo = 'A', "
                    "modalidad_iva_default = NULL WHERE organizacion_id = :o"
                ),
                {"o": self.org},
            )
            sesion.commit()
        finally:
            sesion.close()

    def cambiar_condicion(self, sesion: Session, condicion: str) -> Any:
        sobre = SobreComando(
            operation_id=uuid4(),
            tipo=CAMBIAR,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.admin_id,
            dispositivo_id=self.admin_dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido={"condicion_iva": condicion},
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> Any:
            return identidad_commands.manejar_organizacion_condicion_iva_cambiar(
                sobre,
                validado,  # type: ignore[arg-type]
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def condicion(self) -> str:
        ((condicion,),) = self.leer(
            "SELECT condicion_iva FROM configuracion_organizacion WHERE organizacion_id = :o"
        )
        assert isinstance(condicion, str)
        return condicion

    def reglas_de_las_lineas(self, compra_id: UUID) -> list[bool]:
        filas = self.leer(
            "SELECT computa_credito_fiscal FROM compra_linea "
            "WHERE organizacion_id = :o AND compra_id = :c ORDER BY orden",
            c=compra_id,
        )
        return [bool(fila[0]) for fila in filas]

    def auditorias_del_cambio(self) -> int:
        """La auditoría de la ESCRITURA (entidad `configuracion_organizacion`), no la fila
        genérica que el bus deja por cada comando (entidad `comando`)."""
        return self.cantidad_de(
            "auditoria",
            "accion = 'ORGANIZACION_CONDICION_IVA_CAMBIAR' "
            "AND entidad = 'configuracion_organizacion'",
        )


class TestCompraYCambioDeCondicionSimultaneos:
    """CST-06, TR-06, `02` §7.3: `COMPRA_CONFIRMAR` lee la condición `FOR SHARE` y el cambio
    la toma `FOR UPDATE`: se serializan. La compra queda entera con la regla anterior o entera
    con la nueva, nunca mezclada, y sin interbloqueo."""

    def test_todas_las_lineas_de_la_compra_llevan_la_misma_regla_en_cada_ronda(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _EscenarioFiscal(database_url)
        a, b = escenario.productos

        for ronda in range(RONDAS):
            antes = escenario.condicion()
            despues = "MONOTRIBUTO" if antes == "RESPONSABLE_INSCRIPTO" else "RESPONSABLE_INSCRIPTO"
            contenido = escenario.contenido_de_compra([(a, 10, "100.00"), (b, 10, "200.00")])
            trabajos: list[Callable[[Session], Any]] = [
                lambda sesion, contenido=contenido: escenario.enviar(sesion, contenido, uuid4()),
                lambda sesion, despues=despues: escenario.cambiar_condicion(sesion, despues),
            ]

            resultados, errores = _en_paralelo(database_url, trabajos)

            assert not errores, f"ronda {ronda}: {resultados}, errores={errores}"
            assert escenario.condicion() == despues
            compra_id = UUID(str(resultados[0].resultado["compra_id"]))
            reglas = escenario.reglas_de_las_lineas(compra_id)
            assert len(reglas) == 2
            assert len(set(reglas)) == 1, f"ronda {ronda}: líneas con reglas distintas {reglas}"

        assert escenario.cantidad_de("compra") == RONDAS
        assert escenario.auditorias_del_cambio() == RONDAS
        assert escenario.diferencias() == []


class TestDosCambiosSimultaneosAlMismoValor:
    """TR-10: el segundo cambio, que espera al bloqueo del primero, ve la condición ya
    cambiada y se rechaza con `CONDICION_IVA_SIN_CAMBIO` sin auditar nada."""

    @pytest.mark.parametrize("repeticion", range(3))
    def test_uno_se_acepta_y_el_otro_no_tiene_cambio(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _EscenarioFiscal(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.cambiar_condicion(sesion, "MONOTRIBUTO"),
            lambda sesion: escenario.cambiar_condicion(sesion, "MONOTRIBUTO"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        (aceptado,) = resultados.values()
        assert aceptado.estado == "ACEPTADO"
        (error,) = errores.values()
        assert isinstance(error, DomainError)
        assert error.codigo == "CONDICION_IVA_SIN_CAMBIO"
        assert escenario.condicion() == "MONOTRIBUTO"
        assert escenario.auditorias_del_cambio() == 1
