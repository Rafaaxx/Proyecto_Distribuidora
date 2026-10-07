"""INV-11 y la unicidad de borrador y de vigente de `precios`, contra PostgreSQL real y con
Hypothesis (change 13, tarea 15.1).

INV-11 (`docs/01` §20, PRC-04): una versión de lista `PUBLICADA` o `ANULADA` no cambia sus
precios. Acá se prueba que secuencias arbitrarias y válidas de costos informados, cambios de
regla y de redondeo de la lista, generaciones del borrador, precios manuales, publicaciones y
anulaciones, ejecutadas por el bus, dejan TODA fila de `precio_item` de TODA versión publicada
o anulada idéntica a la del momento de su publicación (precio final, unidades de referencia,
marca de manual y todos los datos del cálculo), y mantienen:

- como máximo un borrador por lista (`design.md` D5);
- como máximo una versión vigente por lista y momento (PRC-03, `design.md` D6), leído por el
  camino real de las consultas (`queries.listar_versiones`) en varios momentos.

Las invariantes se comprueban con SQL y con las consultas de la aplicación después de CADA paso,
no solo al final. Cada ejemplo crea su propia organización dentro de la transacción de
`db_session`, que se revierte al terminar la prueba; no usa un `SAVEPOINT` por ejemplo porque el
bus confirma la transacción del comando. Es una prueba de las invariantes, no de concurrencia
(esa confirma transacciones reales, `tests/concurrency/test_precios_concurrencia.py`).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.modules.precios import queries
from tests.integration.precios_utiles import MOMENTO, REGLA_MODIFICAR, Entorno

PERMISOS = frozenset({"GESTIONAR_LISTAS", "PUBLICAR_LISTAS"})
CANTIDAD_DE_PRODUCTOS = 3
# Rechazos de dominio que una secuencia válida puede provocar a propósito y que no son un error
# (una publicación sin precios, un borrador que ya no está para fijarle un precio, etc.).
_RECHAZOS_ESPERADOS = frozenset({"VERSION_SIN_PRECIOS", "VERSION_NO_ES_BORRADOR"})

_COSTO = st.integers(min_value=100, max_value=5_000_000)  # centavos por unidad base
_PRODUCTO = st.integers(min_value=0, max_value=CANTIDAD_DE_PRODUCTOS - 1)
_PRECIO_MANUAL = st.integers(min_value=100, max_value=100_000_000)  # centavos
_PORCENTAJE = st.integers(min_value=0, max_value=95)
_CAMBIO = st.one_of(
    st.tuples(st.just("costo"), _PRODUCTO, _COSTO),
    st.tuples(st.just("regla"), st.sampled_from(["MARKUP", "MARGEN_BRUTO"]), _PORCENTAJE),
    st.tuples(
        st.just("redondeo"),
        st.sampled_from(["0.01", "1.00", "50.00", "100.00"]),
        st.sampled_from(["ARRIBA", "CERCANO", "ABAJO"]),
    ),
)
_MANUAL = st.one_of(
    st.tuples(st.just("manual"), _PRODUCTO, _PRECIO_MANUAL),
    st.tuples(st.just("quitar_manual"), _PRODUCTO),
)
# Un episodio: cambios de costo, regla o redondeo; se regenera el borrador; precios manuales; y
# se cierra publicando (casi siempre), anulando una versión programada o dejándolo abierto.
_EPISODIO = st.tuples(
    st.lists(_CAMBIO, max_size=3),
    st.lists(_MANUAL, max_size=2),
    st.sampled_from(["publicar", "publicar", "publicar", "anular", "nada"]),
    st.integers(min_value=0, max_value=50),
)
_EPISODIOS = st.lists(_EPISODIO, min_size=1, max_size=5)


def _operaciones(
    episodios: list[tuple[list[tuple[object, ...]], list[tuple[object, ...]], str, int]],
):
    """Aplana los episodios en la secuencia de operaciones que ejecuta el mundo."""
    operaciones: list[tuple[object, ...]] = []
    for cambios, manuales, cierre, indice in episodios:
        operaciones.extend(cambios)
        operaciones.append(("generar",))
        operaciones.extend(manuales)
        if cierre == "publicar":
            operaciones.append(("publicar",))
        elif cierre == "anular":
            operaciones.append(("anular", indice))
    return operaciones


_PROPIEDAD = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

type FilaDePrecio = tuple[object, ...]


def _centavos(centavos: int) -> str:
    return str(Decimal(centavos).scaleb(-2))


def _fraccion(porcentaje: int) -> str:
    return str((Decimal(porcentaje) / Decimal(100)).quantize(Decimal("0.000001")))


class _Mundo:
    """Una organización con una lista (margen sobre toda la lista y redondeo), tres productos y
    el seguimiento de lo que la secuencia fue publicando."""

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.entorno = Entorno(sesion, permisos=PERMISOS)
        self.productos = [self.entorno.vino_id] + [
            self.entorno.crear_producto(f"Producto {numero}", unidades_base=numero + 6)
            for numero in range(1, CANTIDAD_DE_PRODUCTOS)
        ]
        self.lista_id = self.entorno.crear_lista("General", "100.00", "ARRIBA")
        self.regla_id = self.entorno.crear_regla(self.lista_id, tipo="MARKUP", valor="0.300000")
        self.costos_informados = 0
        self.publicaciones = 0
        self.borrador_id: UUID | None = None
        self.programadas: list[UUID] = []
        # Los precios de cada versión publicada o anulada, tal como quedaron al publicarla.
        self.instantaneas: dict[UUID, list[FilaDePrecio]] = {}
        for producto_id in self.productos:
            self.informar_costo(producto_id, 100_000)

    def informar_costo(self, producto_id: UUID, centavos: int) -> None:
        self.costos_informados += 1
        self.entorno.informar_costo(
            producto_id,
            _centavos(centavos),
            creado_en=MOMENTO + timedelta(seconds=self.costos_informados),
        )

    def filas_de_precios(self, version_id: UUID) -> list[FilaDePrecio]:
        filas = self.sesion.execute(
            text(
                "SELECT producto_id, precio_final, unidades_referencia, manual, "
                "costo_informado_id, costo_referencia, regla_margen_id, tipo_margen, "
                "valor_margen, precio_calculado FROM precio_item "
                "WHERE organizacion_id = :o AND version_id = :v ORDER BY producto_id"
            ),
            {"o": self.entorno.org, "v": version_id},
        ).all()
        return [tuple(fila) for fila in filas]

    def aplicar(self, operacion: tuple[object, ...]) -> None:
        tipo = operacion[0]
        entorno, lista_id = self.entorno, self.lista_id
        if tipo == "costo":
            self.informar_costo(self.productos[int(operacion[1])], int(operacion[2]))  # type: ignore[call-overload]
        elif tipo == "regla":
            entorno.enviar(
                REGLA_MODIFICAR,
                {
                    "lista_id": str(lista_id),
                    "regla_id": str(self.regla_id),
                    "tipo": operacion[1],
                    "valor": _fraccion(int(operacion[2])),  # type: ignore[call-overload]
                    "activo": True,
                },
            )
        elif tipo == "redondeo":
            entorno.enviar(
                "LISTA_PRECIO_MODIFICAR",
                {
                    "lista_id": str(lista_id),
                    "nombre": "General",
                    "redondeo_multiplo": operacion[1],
                    "redondeo_direccion": operacion[2],
                    "activo": True,
                },
            )
        elif tipo == "generar":
            self._intentar(lambda: entorno.generar_borrador(lista_id))
            self.borrador_id = self._borrador_actual()
        elif tipo in {"manual", "quitar_manual"} and self.borrador_id is not None:
            producto_id = self.productos[int(operacion[1])]  # type: ignore[call-overload]
            precio = _centavos(int(operacion[2])) if tipo == "manual" else None  # type: ignore[call-overload]
            self._intentar(
                lambda: entorno.fijar_precio(lista_id, self.borrador_id, producto_id, precio)  # type: ignore[arg-type]
            )
        elif tipo == "publicar" and self.borrador_id is not None:
            self._publicar()
        elif tipo == "anular" and self.programadas:
            version_id = self.programadas.pop(int(operacion[1]) % len(self.programadas))  # type: ignore[call-overload]
            entorno.anular_version(lista_id, version_id)

    def _intentar(self, accion: object) -> None:
        """Ejecuta un comando que una secuencia válida puede ver rechazado de forma esperada."""
        try:
            accion()  # type: ignore[operator]
        except DomainError as error:
            if error.codigo not in _RECHAZOS_ESPERADOS:
                raise

    def _borrador_actual(self) -> UUID | None:
        versiones = self.entorno.versiones(self.lista_id)
        borradores = [v.id for v in versiones if v.estado == "BORRADOR"]
        return borradores[0] if borradores else None

    def _publicar(self) -> None:
        """Publica el borrador: la primera vez vigente desde ya y las siguientes programadas, cada
        una con una vigencia desde distinta (`VIGENCIA_DUPLICADA`)."""
        version_id = self.borrador_id
        assert version_id is not None
        desde = None if self.publicaciones == 0 else MOMENTO + timedelta(days=self.publicaciones)
        try:
            self.entorno.publicar(self.lista_id, version_id, desde=desde)
        except DomainError as error:
            if error.codigo not in _RECHAZOS_ESPERADOS:
                raise
            return
        self.publicaciones += 1
        self.instantaneas[version_id] = self.filas_de_precios(version_id)
        if desde is not None:
            self.programadas.append(version_id)
        self.borrador_id = None

    def verificar(self) -> None:
        """INV-11 y las unicidades, con SQL y con las consultas reales."""
        for version_id, esperadas in self.instantaneas.items():
            assert self.filas_de_precios(version_id) == esperadas, (
                f"INV-11: cambió el precio de la versión publicada {version_id}"
            )
        ((maximo_de_borradores,),) = self.sesion.execute(
            text(
                "SELECT COALESCE(MAX(c), 0) FROM (SELECT count(*) AS c FROM lista_version "
                "WHERE organizacion_id = :o AND estado = 'BORRADOR' GROUP BY lista_id) t"
            ),
            {"o": self.entorno.org},
        ).all()
        assert maximo_de_borradores <= 1
        for dias in range(self.publicaciones + 2):
            momento = MOMENTO + timedelta(days=dias, minutes=1)
            respuesta = queries.listar_versiones(
                self.entorno.org, self.lista_id, self.sesion, ahora=momento
            )
            vigentes = [v for v in respuesta.items if v.estado_derivado == "VIGENTE"]
            assert len(vigentes) <= 1, f"más de una versión vigente el {momento}"


@_PROPIEDAD
@given(episodios=_EPISODIOS)
def test_inv11_ninguna_version_publicada_cambia_y_hay_un_borrador_y_un_vigente_como_maximo(
    db_session: Session,
    episodios: list[tuple[list[tuple[object, ...]], list[tuple[object, ...]], str, int]],
) -> None:
    mundo = _Mundo(db_session)

    for operacion in _operaciones(episodios):
        mundo.aplicar(operacion)
        mundo.verificar()

    # Estadística de cobertura (`--hypothesis-show-statistics`): cuántas versiones se publicaron.
    event(f"versiones publicadas: {mundo.publicaciones}")
    event(f"versiones programadas sin anular: {len(mundo.programadas)}")
