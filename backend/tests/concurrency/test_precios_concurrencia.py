"""Change 13, tarea 14.1: concurrencia real de `precios` contra PostgreSQL real (Testcontainers,
`READ COMMITTED`, `docs/02-arquitectura.md` §7.1), con el mismo arnés que
`test_compras_concurrencia.py`: cada hilo tiene su propia conexión/sesión, confirma su propia
transacción (el bus lo hace en `procesar_comando`) y arranca junto a los otros en una
`threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4); los datos confirmados se
limpian al final.

`design.md` D14: la fila de `lista_precio` es el candado de la lista. Todo comando que escribe
versiones o precios de una lista la toma primero (`SELECT ... FOR UPDATE`) y revalida el estado
antes de escribir; la desactivación de una lista toma el mismo candado y la asignación a un
cliente un candado compartido, así que no se cruzan.

Escenarios (specs `precios/*` y `clientes/fichas-de-cliente`):

- dos `LISTA_GENERAR_BORRADOR` simultáneos dejan un solo borrador con un precio por producto
  (PRC-02, D5);
- `LISTA_PUBLICAR` en paralelo con `LISTA_BORRADOR_PRECIO_FIJAR`: o se publica con el precio
  manual o este se rechaza, y ningún precio cambia después de publicado (INV-11, PRC-04);
- dos `LISTA_PUBLICAR` del mismo borrador dejan una sola publicación;
- dos `LISTA_ANULAR_VERSION` dejan una anulación y una `VERSION_NO_PUBLICADA` (PRC-05);
- dos `REGLA_MARGEN_CREAR` del mismo alcance dejan una regla y una `REGLA_DUPLICADA` (D8);
- desactivar una lista mientras se la asigna a un cliente nunca deja un cliente activo con una
  lista inactiva (PRC-20, D11);
- el mismo `Operation-Id` en paralelo tiene un solo efecto (INV-06, SYN-02).
"""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import crear_engine, crear_session_factory
from tests.integration.cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from tests.integration.precios_utiles import LISTA_CREAR, MOMENTO, Entorno

ESPERA_MAXIMA = 60
REPETICIONES = 6


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _sesion_independiente(database_url: str) -> Session:
    """Conexión/sesión propia que confirma sus propias transacciones: simula un worker de
    FastAPI distinto (`02` §16.2)."""
    return crear_session_factory(crear_engine(database_url))()


class _Escenario:
    """Una organización confirmada (usuario, producto `Vino A`, categoría, proveedor) sobre la
    que cada hilo trabaja con su propia sesión."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.base = Entorno(sesion, permisos=frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"}))
            self.org = self.base.org
            self.usuario_clientes = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=frozenset({"GESTIONAR_CLIENTES"})
            )
            sesion.commit()
        finally:
            sesion.close()
        self._contador = 0

    def nombre_nuevo(self) -> str:
        self._contador += 1
        return f"Lista {self._contador}"

    def entorno(self, sesion: Session, *, para_clientes: bool = False) -> Entorno:
        """El entorno de la organización atado a la sesión de un hilo."""
        entorno = copy.copy(self.base)
        entorno.sesion = sesion
        if para_clientes:
            entorno.usuario_id, entorno.dispositivo_id = self.usuario_clientes
        return entorno

    def preparar(self, trabajo: Callable[[Entorno], object]) -> object:
        """Corre `trabajo` en su propia sesión, confirmando lo que haya dejado el bus, y devuelve
        su resultado."""
        sesion = _sesion_independiente(self.database_url)
        try:
            resultado = trabajo(self.entorno(sesion))
            sesion.commit()
            return resultado
        finally:
            sesion.close()

    def borrador(self) -> tuple[UUID, UUID]:
        """Una lista nueva con su borrador generado (Vino A a `8600.00`), todo confirmado."""
        nombre = self.nombre_nuevo()
        resultado = self.preparar(lambda entorno: entorno.borrador_de_general(nombre))
        assert isinstance(resultado, tuple)
        return resultado

    def leer(self, consulta: str, **parametros: object) -> list[tuple[object, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def precio_de(self, version_id: UUID, producto_id: UUID) -> tuple[Decimal, bool] | None:
        filas = self.leer(
            "SELECT precio_final, manual FROM precio_item "
            "WHERE organizacion_id = :o AND version_id = :v AND producto_id = :p",
            v=version_id,
            p=producto_id,
        )
        if not filas:
            return None
        precio, manual = filas[0]
        assert isinstance(precio, Decimal)
        assert isinstance(manual, bool)
        return precio, manual

    def estado_de(self, version_id: UUID) -> str:
        ((estado,),) = self.leer(
            "SELECT estado FROM lista_version WHERE organizacion_id = :o AND id = :v", v=version_id
        )
        assert isinstance(estado, str)
        return estado


def _en_paralelo(
    escenario: _Escenario,
    trabajos: list[Callable[[Entorno], object]],
    *,
    como_usuario_de_clientes: frozenset[int] = frozenset(),
) -> tuple[list[str], list[object]]:
    """Corre cada trabajo en su hilo y su sesión, todos arrancando juntos. Devuelve, por trabajo,
    `"OK"` o el código del error de dominio (o el nombre de la excepción), y su resultado."""
    barrera = threading.Barrier(len(trabajos))
    veredictos: list[str] = ["NO_CORRIO"] * len(trabajos)
    resultados: list[object] = [None] * len(trabajos)

    def _hilo(indice: int) -> None:
        sesion = _sesion_independiente(escenario.database_url)
        try:
            entorno = escenario.entorno(sesion, para_clientes=indice in como_usuario_de_clientes)
            barrera.wait(timeout=10)
            resultados[indice] = trabajos[indice](entorno)
            veredictos[indice] = "OK"
        except BaseException as error:  # noqa: BLE001 -- se reporta en el hilo principal
            sesion.rollback()
            veredictos[indice] = str(getattr(error, "codigo", type(error).__name__))
        finally:
            sesion.close()

    hilos = [threading.Thread(target=_hilo, args=(i,)) for i in range(len(trabajos))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=ESPERA_MAXIMA)
    assert not any(hilo.is_alive() for hilo in hilos), (
        "Un hilo quedó colgado (posible interbloqueo)."
    )
    return veredictos, resultados


def _carrera_publicar_contra_fijar(escenario: _Escenario) -> None:
    """Una carrera: borrador nuevo; publicarlo mientras se le fija un precio manual."""
    lista_id, version_id = escenario.borrador()
    vino_id = escenario.base.vino_id

    veredictos, _ = _en_paralelo(
        escenario,
        [
            lambda entorno: entorno.publicar(lista_id, version_id),
            lambda entorno: entorno.fijar_precio(lista_id, version_id, vino_id, "9000.00"),
        ],
    )

    assert veredictos[0] == "OK", veredictos
    assert escenario.estado_de(version_id) == "PUBLICADA"
    publicado = escenario.precio_de(version_id, vino_id)
    if veredictos[1] == "OK":
        assert publicado == (Decimal("9000.00"), True)
    else:
        assert veredictos[1] == "VERSION_NO_ES_BORRADOR", veredictos
        assert publicado == (Decimal("8600.00"), False)
    # INV-11: nada cambia después de publicado.
    time.sleep(0.2)
    assert escenario.precio_de(version_id, vino_id) == publicado


def _carrera_desactivar_contra_asignar(escenario: _Escenario) -> None:
    """Una carrera: lista nueva; desactivarla mientras se crea un cliente con esa lista."""
    nombre = escenario.nombre_nuevo()
    lista_id = escenario.preparar(lambda entorno: entorno.crear_lista(nombre, "100.00", "ARRIBA"))
    assert isinstance(lista_id, UUID)

    veredictos, _ = _en_paralelo(
        escenario,
        [
            lambda entorno: entorno.desactivar_lista(lista_id, nombre),
            lambda entorno: entorno.crear_cliente(f"Cliente de {nombre}", lista_precio_id=lista_id),
        ],
        como_usuario_de_clientes=frozenset({1}),
    )

    assert sorted(veredictos) in (["LISTA_EN_USO", "OK"], ["LISTA_INACTIVA", "OK"]), veredictos
    ((incoherentes,),) = escenario.leer(
        "SELECT count(*) FROM cliente c JOIN lista_precio l "
        "ON l.organizacion_id = c.organizacion_id AND l.id = c.lista_precio_id "
        "WHERE c.organizacion_id = :o AND c.estado <> 'INACTIVO' AND NOT l.activo"
    )
    assert incoherentes == 0, f"Cliente activo con lista inactiva ({veredictos})"


class TestGenerarBorradorSimultaneo:
    """PRC-02, `design.md` D5 y D14: dos generaciones simultáneas de la misma lista se serializan
    con el candado de la lista; una crea el borrador y la otra lo regenera."""

    def test_dos_generaciones_dejan_un_solo_borrador_con_un_precio_por_producto(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        def _lista_con_cinco_productos(entorno: Entorno) -> UUID:
            lista_id = entorno.crear_lista(escenario.nombre_nuevo(), "100.00", "ARRIBA")
            entorno.crear_regla(lista_id, tipo="MARGEN_BRUTO", valor="0.300000")
            entorno.informar_costo(entorno.vino_id, "1000")
            for numero in range(4):
                producto = entorno.crear_producto(f"Producto {numero}")
                entorno.informar_costo(producto, "500")
            return lista_id

        lista_id = escenario.preparar(_lista_con_cinco_productos)
        assert isinstance(lista_id, UUID)

        veredictos, resultados = _en_paralelo(
            escenario,
            [lambda entorno: entorno.generar_borrador(lista_id) for _ in range(2)],
        )

        assert veredictos == ["OK", "OK"], veredictos
        versiones = escenario.leer(
            "SELECT id, estado, numero FROM lista_version "
            "WHERE organizacion_id = :o AND lista_id = :l",
            l=lista_id,
        )
        assert [(estado, numero) for _id, estado, numero in versiones] == [("BORRADOR", 1)]
        ((total, distintos),) = escenario.leer(
            "SELECT count(*), count(DISTINCT producto_id) FROM precio_item "
            "WHERE organizacion_id = :o AND version_id = :v",
            v=versiones[0][0],
        )
        assert (total, distintos) == (5, 5)
        regenerado = sorted(bool(comando.resultado["regenerado"]) for comando in resultados)  # type: ignore[union-attr,attr-defined]
        assert regenerado == [False, True]


class TestPublicarContraFijarPrecio:
    """INV-11, PRC-04, `design.md` D14: publicar y fijar un precio manual en paralelo. Hay dos
    órdenes posibles y los dos son correctos: el precio manual entra antes y se publica, o llega
    después y se rechaza con `VERSION_NO_ES_BORRADOR`. Lo que no puede pasar es que el precio de
    una versión ya publicada cambie. Se repite para ejercer las dos entradas de la carrera."""

    def test_el_precio_manual_se_publica_o_se_rechaza_y_ningun_precio_cambia_despues(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        for _ in range(REPETICIONES):
            _carrera_publicar_contra_fijar(escenario)

    def test_fijar_un_precio_sobre_una_version_ya_publicada_se_rechaza_y_no_cambia_nada(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)
        lista_id, version_id = escenario.borrador()
        vino_id = escenario.base.vino_id
        escenario.preparar(lambda entorno: entorno.publicar(lista_id, version_id))

        veredictos, _ = _en_paralelo(
            escenario,
            [lambda entorno: entorno.fijar_precio(lista_id, version_id, vino_id, "9000.00")],
        )

        assert veredictos == ["VERSION_NO_ES_BORRADOR"]
        assert escenario.precio_de(version_id, vino_id) == (Decimal("8600.00"), False)


class TestDosPublicacionesDelMismoBorrador:
    """PRC-04, `design.md` D14: dos publicaciones simultáneas del mismo borrador dejan una sola
    publicación; la otra encuentra la versión ya publicada."""

    def test_una_sola_publicacion(self, database_url: str, _engine_de_sesion) -> None:
        escenario = _Escenario(database_url)
        lista_id, version_id = escenario.borrador()

        veredictos, _ = _en_paralelo(
            escenario,
            [lambda entorno: entorno.publicar(lista_id, version_id) for _ in range(2)],
        )

        assert sorted(veredictos) == ["OK", "VERSION_NO_ES_BORRADOR"], veredictos
        assert escenario.estado_de(version_id) == "PUBLICADA"
        ((publicadas,),) = escenario.leer(
            "SELECT count(*) FROM lista_version "
            "WHERE organizacion_id = :o AND lista_id = :l AND estado = 'PUBLICADA'",
            l=lista_id,
        )
        assert publicadas == 1


class TestDosAnulacionesDeLaMismaVersion:
    """PRC-05, `design.md` D14: dos anulaciones simultáneas de una versión programada dejan una
    anulación y una `VERSION_NO_PUBLICADA`."""

    def test_una_sola_anulacion(self, database_url: str, _engine_de_sesion) -> None:
        escenario = _Escenario(database_url)
        lista_id, version_id = escenario.borrador()
        escenario.preparar(
            lambda entorno: entorno.publicar(
                lista_id, version_id, desde=MOMENTO + timedelta(days=1)
            )
        )

        veredictos, _ = _en_paralelo(
            escenario,
            [lambda entorno: entorno.anular_version(lista_id, version_id) for _ in range(2)],
        )

        assert sorted(veredictos) == ["OK", "VERSION_NO_PUBLICADA"], veredictos
        assert escenario.estado_de(version_id) == "ANULADA"
        ((anulaciones,),) = escenario.leer(
            "SELECT count(*) FROM auditoria WHERE organizacion_id = :o "
            "AND accion = 'LISTA_ANULAR_VERSION'"
        )
        assert anulaciones == 1


class TestDosReglasDelMismoAlcance:
    """PRC-13, `design.md` D8 y D14: dos `REGLA_MARGEN_CREAR` simultáneas del mismo alcance dejan
    una regla activa y una `REGLA_DUPLICADA`."""

    def test_una_sola_regla_activa_por_alcance(self, database_url: str, _engine_de_sesion) -> None:
        escenario = _Escenario(database_url)
        lista_id = escenario.preparar(
            lambda entorno: entorno.crear_lista(escenario.nombre_nuevo(), "100.00", "ARRIBA")
        )
        assert isinstance(lista_id, UUID)
        categoria_id = escenario.base.categoria_id

        veredictos, _ = _en_paralelo(
            escenario,
            [
                lambda entorno: entorno.crear_regla(
                    lista_id,
                    tipo="MARKUP",
                    valor="0.300000",
                    alcance_tipo="CATEGORIA",
                    alcance_id=categoria_id,
                ),
                lambda entorno: entorno.crear_regla(
                    lista_id,
                    tipo="MARKUP",
                    valor="0.400000",
                    alcance_tipo="CATEGORIA",
                    alcance_id=categoria_id,
                ),
            ],
        )

        assert sorted(veredictos) == ["OK", "REGLA_DUPLICADA"], veredictos
        ((activas,),) = escenario.leer(
            "SELECT count(*) FROM regla_margen WHERE organizacion_id = :o AND lista_id = :l "
            "AND activo AND alcance_tipo = 'CATEGORIA'",
            l=lista_id,
        )
        assert activas == 1


class TestDesactivarListaContraAsignarlaACliente:
    """PRC-20, `design.md` D11 y D14: desactivar una lista y asignarla a un cliente en paralelo.
    Hay dos órdenes y los dos son correctos: el cliente se crea y la desactivación se rechaza con
    `LISTA_EN_USO`, o la lista se desactiva y la asignación se rechaza con `LISTA_INACTIVA`.
    Nunca queda un cliente activo con una lista inactiva."""

    def test_nunca_queda_un_cliente_activo_con_una_lista_inactiva(
        self, database_url: str, _engine_de_sesion
    ) -> None:
        escenario = _Escenario(database_url)

        for _ in range(REPETICIONES):
            _carrera_desactivar_contra_asignar(escenario)


class TestMismoOperationIdEnParalelo:
    """INV-06, SYN-02: dos envíos simultáneos del MISMO comando con el mismo `Operation-Id` tienen
    un solo efecto; los dos informan el mismo resultado."""

    def test_un_solo_efecto(self, database_url: str, _engine_de_sesion) -> None:
        escenario = _Escenario(database_url)
        operation_id = uuid4()
        contenido = {
            "nombre": "General",
            "redondeo_multiplo": "100.00",
            "redondeo_direccion": "ARRIBA",
        }

        veredictos, resultados = _en_paralelo(
            escenario,
            [
                lambda entorno: entorno.enviar(LISTA_CREAR, contenido, operation_id=operation_id)
                for _ in range(2)
            ],
        )

        assert veredictos == ["OK", "OK"], veredictos
        listas_informadas = {str(comando.resultado["lista_id"]) for comando in resultados}  # type: ignore[attr-defined,union-attr]
        assert len(listas_informadas) == 1
        ((listas,),) = escenario.leer(
            "SELECT count(*) FROM lista_precio WHERE organizacion_id = :o"
        )
        assert listas == 1
        ((comandos,),) = escenario.leer(
            "SELECT count(*) FROM comando WHERE organizacion_id = :o AND operation_id = :op",
            op=operation_id,
        )
        assert comandos == 1
        ((auditorias,),) = escenario.leer(
            "SELECT count(*) FROM auditoria "
            "WHERE organizacion_id = :o AND accion = 'LISTA_PRECIO_CREAR'"
        )
        assert auditorias == 1
