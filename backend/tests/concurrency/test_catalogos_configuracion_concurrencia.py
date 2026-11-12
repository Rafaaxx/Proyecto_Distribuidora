"""Change 20c, tarea 6.1: concurrencia real de los motivos y las alícuotas administrables, contra
PostgreSQL real (Testcontainers, `READ COMMITTED`, `docs/02-arquitectura.md` §7.1). Mismo arnés que
`test_medios_y_roles_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma su
propia transacción por el bus (`sync_service.procesar_comando`) y arranca junto a los otros en una
`threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4).

Escenarios (`design.md` D3, D4, D8, D9):

- dos bajas simultáneas de los dos últimos motivos activos de un ámbito: una sola se acepta
  (`ULTIMO_MOTIVO_ACTIVO`, INV-01);
- baja de una alícuota y alta de un producto con ella al mismo tiempo: o el producto se crea y la
  baja responde `ALICUOTA_EN_USO`, o la baja se acepta y el producto responde `ALICUOTA_INACTIVA`;
  nunca un producto activo con una alícuota inactiva (CAT-01, CAT-05);
- dos bajas simultáneas de las dos últimas alícuotas activas: una sola se acepta
  (`ULTIMA_ALICUOTA_ACTIVA`, INV-01);
- dos altas simultáneas de "Robo" en el mismo ámbito: una `NOMBRE_DUPLICADO` (INV-02);
- doble envío simultáneo del mismo comando con el mismo `operation_id`: una sola fila (INV-06).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
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
from app.modules.catalogo import commands as _catalogo_commands  # noqa: F401
from app.modules.configuracion import commands as _configuracion_commands  # noqa: F401
from app.modules.sync import service as sync_service
from tests.concurrency.test_compras_concurrencia import (
    MOMENTO,
    RELOJ,
    _en_paralelo,
    _sesion_independiente,
)
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)

RONDAS = 5
AMBITO = "AJUSTE_STOCK"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


class _Escenario:
    """Una organización confirmada con un administrador (`ADMIN_CONFIGURACION`), un gestor de
    catálogo (`GESTIONAR_CATALOGO`), una categoría y un proveedor."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            self.admin = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"ADMIN_CONFIGURACION"})
            )
            self.gestor = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"GESTIONAR_CATALOGO"})
            )
            self.proveedor_id = crear_proveedor(sesion, self.org)
            self.categoria_id = uuid4()
            sesion.execute(
                text(
                    "INSERT INTO categoria (id, organizacion_id, nombre, activo, creado_en, "
                    "actualizado_en) VALUES (:id, :o, 'Bebidas', true, :m, :m)"
                ),
                {"id": self.categoria_id, "o": self.org, "m": MOMENTO},
            )
            sesion.commit()
        finally:
            sesion.close()

    # --- armado de datos (cada pieza confirma) ----------------------------------------

    def crear_motivo(self, nombre: str, *, ambito: str = AMBITO) -> UUID:
        motivo_id = uuid4()
        self._ejecutar(
            "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :o, :a, :n, true, :m, :m)",
            id=motivo_id,
            a=ambito,
            n=nombre,
        )
        return motivo_id

    def crear_alicuota(self, nombre: str, valor: str) -> UUID:
        alicuota_id = uuid4()
        self._ejecutar(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, creado_en, "
            "actualizado_en) VALUES (:id, :o, :n, :v, true, :m, :m)",
            id=alicuota_id,
            n=nombre,
            v=Decimal(valor),
        )
        return alicuota_id

    def _ejecutar(self, consulta: str, **parametros: object) -> None:
        sesion = _sesion_independiente(self.database_url)
        try:
            sesion.execute(text(consulta), {"o": self.org, "m": MOMENTO, **parametros})
            sesion.commit()
        finally:
            sesion.close()

    # --- comandos por el bus ----------------------------------------------------------

    def enviar(
        self,
        sesion: Session,
        tipo: str,
        contenido: dict[str, Any],
        *,
        version: int = 1,
        operation_id: UUID | None = None,
        actor: tuple[UUID, UUID] | None = None,
    ) -> Any:
        usuario_id, dispositivo_id = actor or self.admin
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=version,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> Any:
            return registrado.funcion(
                sobre,
                validado,
                sesion=sesion_protegida,  # type: ignore[arg-type]
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def baja_de_motivo(self, sesion: Session, motivo_id: UUID, nombre: str) -> Any:
        return self.enviar(
            sesion,
            "MOTIVO_MODIFICAR",
            {"motivo_id": str(motivo_id), "nombre": nombre, "activo": False},
        )

    def alta_de_motivo(self, sesion: Session, nombre: str, operation_id: UUID | None = None) -> Any:
        return self.enviar(
            sesion,
            "MOTIVO_CREAR",
            {"ambito": AMBITO, "nombre": nombre},
            operation_id=operation_id,
        )

    def baja_de_alicuota(self, sesion: Session, alicuota_id: UUID, nombre: str, valor: str) -> Any:
        return self.enviar(
            sesion,
            "ALICUOTA_MODIFICAR",
            {"alicuota_id": str(alicuota_id), "nombre": nombre, "valor": valor, "activo": False},
        )

    def alta_de_alicuota(
        self, sesion: Session, nombre: str, valor: str, operation_id: UUID | None = None
    ) -> Any:
        return self.enviar(
            sesion,
            "ALICUOTA_CREAR",
            {"nombre": nombre, "valor": valor},
            operation_id=operation_id,
        )

    def alta_de_producto(self, sesion: Session, alicuota_id: UUID) -> Any:
        return self.enviar(
            sesion,
            "PRODUCTO_CREAR",
            {
                "codigo": f"P-{uuid4().hex[:8]}",
                "nombre": "Producto nuevo",
                "categoria_id": str(self.categoria_id),
                "proveedor_id": str(self.proveedor_id),
                "unidad_base": "unidad",
                "alicuota_id": str(alicuota_id),
                "presentaciones": [
                    {
                        "nombre": "Unidad",
                        "unidades_base": 1,
                        "usar_en_venta": True,
                        "usar_en_compra": True,
                        "es_referencia": True,
                    }
                ],
            },
            version=2,
            actor=self.gestor,
        )

    # --- lecturas confirmadas ---------------------------------------------------------

    def contar(self, consulta: str, **parametros: object) -> int:
        sesion = _sesion_independiente(self.database_url)
        try:
            valor = sesion.execute(text(consulta), {"o": self.org, **parametros}).scalar_one()
            return int(valor)
        finally:
            sesion.close()

    def motivos_activos(self) -> int:
        return self.contar(
            "SELECT count(*) FROM motivo WHERE organizacion_id = :o AND ambito = :a AND activo",
            a=AMBITO,
        )

    def motivos_con_nombre(self, nombre: str) -> int:
        return self.contar(
            "SELECT count(*) FROM motivo WHERE organizacion_id = :o AND ambito = :a "
            "AND lower(nombre) = lower(:n)",
            a=AMBITO,
            n=nombre,
        )

    def alicuotas_activas(self) -> int:
        return self.contar(
            "SELECT count(*) FROM alicuota_iva WHERE organizacion_id = :o AND activo"
        )

    def alicuotas_con_valor(self, valor: str) -> int:
        return self.contar(
            "SELECT count(*) FROM alicuota_iva WHERE organizacion_id = :o AND valor = :v",
            v=Decimal(valor),
        )

    def productos_activos_con_alicuota_inactiva(self) -> int:
        return self.contar(
            "SELECT count(*) FROM producto p JOIN alicuota_iva a "
            "ON a.organizacion_id = p.organizacion_id AND a.id = p.alicuota_id "
            "WHERE p.organizacion_id = :o AND p.activo AND NOT a.activo"
        )

    def productos(self) -> int:
        return self.contar("SELECT count(*) FROM producto WHERE organizacion_id = :o")

    def auditorias(self, accion: str, entidad: str) -> int:
        return self.contar(
            "SELECT count(*) FROM auditoria WHERE organizacion_id = :o "
            "AND accion = :a AND entidad = :e",
            a=accion,
            e=entidad,
        )


def _codigos(errores: dict[int, BaseException]) -> list[str]:
    assert all(isinstance(error, DomainError) for error in errores.values()), errores
    return sorted(error.codigo for error in errores.values() if isinstance(error, DomainError))


class TestDosBajasDeLosDosUltimosMotivosActivos:
    """INV-01, D4: `MOTIVO_MODIFICAR` bloquea los motivos del ámbito (`FOR UPDATE`) antes de
    contar los activos: dos bajas simultáneas no dejan cero."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_una_sola_se_acepta_y_queda_un_motivo_activo(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        rotura = escenario.crear_motivo("Rotura")
        merma = escenario.crear_motivo("Merma")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_motivo(sesion, rotura, "Rotura"),
            lambda sesion: escenario.baja_de_motivo(sesion, merma, "Merma"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert next(iter(resultados.values())).estado == "ACEPTADO"
        assert _codigos(errores) == ["ULTIMO_MOTIVO_ACTIVO"]
        assert escenario.motivos_activos() == 1
        assert escenario.auditorias("MOTIVO_MODIFICAR", "motivo") == 1

    def test_con_tres_activos_las_dos_bajas_se_aceptan(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el bloqueo no rechaza de más cuando sobran motivos."""
        escenario = _Escenario(database_url)
        rotura = escenario.crear_motivo("Rotura")
        merma = escenario.crear_motivo("Merma")
        escenario.crear_motivo("Vencido")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_motivo(sesion, rotura, "Rotura"),
            lambda sesion: escenario.baja_de_motivo(sesion, merma, "Merma"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2
        assert escenario.motivos_activos() == 1

    def test_las_bajas_de_dos_ambitos_distintos_no_se_bloquean_entre_si(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el último motivo se cuenta por ámbito; cada ámbito conserva el suyo."""
        escenario = _Escenario(database_url)
        rotura = escenario.crear_motivo("Rotura")
        escenario.crear_motivo("Merma")
        error_de_carga = escenario.crear_motivo("Error de carga", ambito="ANULACION_VENTA")
        escenario.crear_motivo("Otro", ambito="ANULACION_VENTA")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_motivo(sesion, rotura, "Rotura"),
            lambda sesion: escenario.baja_de_motivo(sesion, error_de_carga, "Error de carga"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2


class TestBajaDeUnaAlicuotaYAltaDeUnProductoConEllaAlMismoTiempo:
    """CAT-01, CAT-05, D8, D9: la baja bloquea las alícuotas `FOR UPDATE` y cuenta los productos
    activos; el alta del producto la lee `FOR SHARE`. Se serializan y nunca queda un producto
    activo con una alícuota inactiva."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_o_el_producto_se_crea_y_la_baja_es_en_uso_o_la_baja_se_acepta_y_el_producto_no(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        escenario.crear_alicuota("21%", "0.210000")
        reducida = escenario.crear_alicuota("10,5%", "0.105000")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_alicuota(sesion, reducida, "10,5%", "0.105000"),
            lambda sesion: escenario.alta_de_producto(sesion, reducida),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1 and len(errores) == 1, f"{resultados}, errores={errores}"
        codigos = _codigos(errores)
        if 0 in resultados:  # la baja confirmó primero: el producto no se crea
            assert codigos == ["ALICUOTA_INACTIVA"]
            assert escenario.productos() == 0
        else:  # el producto confirmó primero: la baja ve el producto y se rechaza
            assert codigos == ["ALICUOTA_EN_USO"]
            assert escenario.productos() == 1
        assert escenario.productos_activos_con_alicuota_inactiva() == 0

    def test_con_otra_alicuota_la_baja_y_el_alta_no_se_estorban(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el producto usa 21 % y se da de baja 10,5 %: se aceptan los dos."""
        escenario = _Escenario(database_url)
        general = escenario.crear_alicuota("21%", "0.210000")
        reducida = escenario.crear_alicuota("10,5%", "0.105000")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_alicuota(sesion, reducida, "10,5%", "0.105000"),
            lambda sesion: escenario.alta_de_producto(sesion, general),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2
        assert escenario.productos_activos_con_alicuota_inactiva() == 0


class TestDosBajasDeLasDosUltimasAlicuotasActivas:
    """INV-01, D8: la baja bloquea las alícuotas de la organización antes de contar las activas."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_una_sola_se_acepta_y_queda_una_alicuota_activa(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        general = escenario.crear_alicuota("21%", "0.210000")
        reducida = escenario.crear_alicuota("10,5%", "0.105000")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_alicuota(sesion, general, "21%", "0.210000"),
            lambda sesion: escenario.baja_de_alicuota(sesion, reducida, "10,5%", "0.105000"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert next(iter(resultados.values())).estado == "ACEPTADO"
        assert _codigos(errores) == ["ULTIMA_ALICUOTA_ACTIVA"]
        assert escenario.alicuotas_activas() == 1
        assert escenario.auditorias("ALICUOTA_MODIFICAR", "alicuota_iva") == 1

    def test_con_tres_activas_las_dos_bajas_se_aceptan(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el bloqueo no rechaza de más cuando sobran alícuotas."""
        escenario = _Escenario(database_url)
        general = escenario.crear_alicuota("21%", "0.210000")
        reducida = escenario.crear_alicuota("10,5%", "0.105000")
        escenario.crear_alicuota("0%", "0.000000")
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.baja_de_alicuota(sesion, general, "21%", "0.210000"),
            lambda sesion: escenario.baja_de_alicuota(sesion, reducida, "10,5%", "0.105000"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2
        assert escenario.alicuotas_activas() == 1


class TestDosAltasSimultaneasDelMismoNombre:
    """INV-02, D3, D7: los índices únicos deciden; el perdedor espera al ganador y responde
    `NOMBRE_DUPLICADO` (o `VALOR_DUPLICADO` para el mismo porcentaje)."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_dos_motivos_robo_una_se_acepta_y_la_otra_es_duplicada(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_motivo(sesion, "Robo"),
            lambda sesion: escenario.alta_de_motivo(sesion, "robo"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _codigos(errores) == ["NOMBRE_DUPLICADO"]
        assert escenario.motivos_con_nombre("Robo") == 1
        assert escenario.auditorias("MOTIVO_CREAR", "motivo") == 1

    def test_nombres_distintos_se_aceptan_los_dos(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        """Triangula: el índice no rechaza nombres distintos."""
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_motivo(sesion, "Robo"),
            lambda sesion: escenario.alta_de_motivo(sesion, "Merma"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert len(resultados) == 2

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_dos_alicuotas_del_mismo_porcentaje_una_es_valor_duplicado(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_alicuota(sesion, "27%", "0.270000"),
            lambda sesion: escenario.alta_de_alicuota(sesion, "IVA 27", "0.270000"),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert len(resultados) == 1, f"{resultados}, errores={errores}"
        assert _codigos(errores) == ["VALOR_DUPLICADO"]
        assert escenario.alicuotas_con_valor("0.270000") == 1


class TestDobleEnvioSimultaneoDelMismoComando:
    """INV-06: dos envíos del mismo `operation_id` a la vez producen un solo efecto."""

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_el_alta_de_un_motivo_queda_una_sola_vez(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_motivo(sesion, "Robo", operation_id),
            lambda sesion: escenario.alta_de_motivo(sesion, "Robo", operation_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert {c.estado for c in resultados.values()} == {"ACEPTADO"}
        assert escenario.motivos_con_nombre("Robo") == 1
        assert escenario.auditorias("MOTIVO_CREAR", "motivo") == 1

    @pytest.mark.parametrize("repeticion", range(RONDAS))
    def test_el_alta_de_una_alicuota_queda_una_sola_vez(
        self, database_url: str, _engine_de_sesion, repeticion: int
    ) -> None:
        escenario = _Escenario(database_url)
        operation_id = uuid4()
        trabajos: list[Callable[[Session], Any]] = [
            lambda sesion: escenario.alta_de_alicuota(sesion, "27%", "0.270000", operation_id),
            lambda sesion: escenario.alta_de_alicuota(sesion, "27%", "0.270000", operation_id),
        ]

        resultados, errores = _en_paralelo(database_url, trabajos)

        assert not errores, errores
        assert {c.estado for c in resultados.values()} == {"ACEPTADO"}
        assert escenario.alicuotas_con_valor("0.270000") == 1
        assert escenario.auditorias("ALICUOTA_CREAR", "alicuota_iva") == 1
