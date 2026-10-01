"""Tarea 6.1 (change 10): importación de clientes por `IMPORTACION_REGISTRAR`, contra
PostgreSQL real (`specs/importacion/importacion-de-maestros`, `design.md` D6).

El cliente nace como por `CLIENTE_CREAR` (TR-10): `ACTIVO`, sin datos de crédito propios
(heredan los de la organización) y sin lista de precios, con el documento normalizado a
dígitos (CLI-05). `codigo` es obligatorio en la planilla (D6, restricción de negocio
aprobada). Solo altas: una clave existente da el error de duplicado de la entidad y una
repetida dentro del archivo, `FILA_DUPLICADA`.

Reglas citadas: CLI-01, CLI-05, INV-01, INV-06, INV-21, TR-10.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from importacion_utiles import EntornoDeImportacion, contenido, errores_de, fila_de
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.clientes.models import Cliente
from app.modules.importacion.domain.errores import ImportacionConErroresError
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

TIPO = "CLIENTES"


def fila(numero: int, **cambios: str) -> dict[str, object]:
    valores = {
        "nombre": "Almacén Don Pepe",
        "codigo": "C001",
        "razon_social": "",
        "documento_tipo": "",
        "documento_numero": "",
        "direccion": "San Martín 123",
        "contacto": "Pepe",
        "telefono": "",
        "email": "",
        "estado_facturacion_default": "",
    }
    valores.update(cambios)
    return fila_de(numero, valores)


@pytest.fixture
def entorno(db_session: Session) -> EntornoDeImportacion:
    return EntornoDeImportacion(db_session)


def clientes(entorno: EntornoDeImportacion, org: object | None = None) -> list[Cliente]:
    return list(
        entorno.sesion.scalars(
            select(Cliente)
            .where(Cliente.organizacion_id == (org or entorno.org))
            .order_by(Cliente.codigo)
        ).all()
    )


def importar(entorno: EntornoDeImportacion, *filas: dict[str, object]) -> Comando:
    return entorno.enviar(contenido(TIPO, list(filas), "clientes.csv"))


def fallar(
    entorno: EntornoDeImportacion, *filas: dict[str, object]
) -> list[tuple[int, str | None, str]]:
    with pytest.raises(ImportacionConErroresError) as excinfo:
        importar(entorno, *filas)
    return errores_de(excinfo.value)


# --- escenario "Cliente con CUIT" --------------------------------------------------


def test_cliente_con_cuit_nace_activo_con_documento_normalizado_y_sin_credito_propio(
    entorno: EntornoDeImportacion,
) -> None:
    """CLI-01, CLI-05."""
    comando = importar(
        entorno,
        fila(2, documento_tipo="CUIT", documento_numero="20-12345678-9"),
    )

    assert comando.resultado is not None
    assert (comando.resultado["filas_total"], comando.resultado["filas_ok"]) == (1, 1)
    [cliente] = clientes(entorno)
    assert (cliente.codigo, cliente.nombre, cliente.estado) == (
        "C001",
        "Almacén Don Pepe",
        "ACTIVO",
    )
    assert (cliente.documento_tipo, cliente.documento_numero) == ("CUIT", "20123456789")
    assert (cliente.direccion, cliente.contacto) == ("San Martín 123", "Pepe")
    assert cliente.limite_credito is None
    assert cliente.politica_credito is None
    assert cliente.lista_precio_id is None
    assert cliente.es_consumidor_final is False


def test_varios_clientes_con_y_sin_documento_y_con_los_campos_opcionales(
    entorno: EntornoDeImportacion,
) -> None:
    importar(
        entorno,
        fila(2, documento_tipo="DNI", documento_numero="30-111-222"),
        fila(
            3,
            nombre="Kiosco Sol",
            codigo="C002",
            razon_social="Sol SA",
            telefono="261 555",
            email="sol@ejemplo.com",
            estado_facturacion_default="pendiente",
        ),
    )

    uno, dos = clientes(entorno)
    assert (uno.codigo, uno.documento_tipo, uno.documento_numero) == ("C001", "DNI", "30111222")
    assert (dos.codigo, dos.documento_tipo, dos.documento_numero) == ("C002", None, None)
    assert (dos.razon_social, dos.telefono, dos.email) == ("Sol SA", "261 555", "sol@ejemplo.com")
    assert dos.estado_facturacion_default == "PENDIENTE"
    assert uno.estado_facturacion_default is None
    [importacion] = entorno.importaciones()
    assert (importacion.tipo, importacion.filas_total, importacion.filas_ok) == (TIPO, 2, 2)


# --- errores de la ficha y del documento --------------------------------------------


def test_dni_de_longitud_invalida_da_documento_invalido(entorno: EntornoDeImportacion) -> None:
    """Escenario "DNI de longitud inválida" (CLI-05)."""
    errores = fallar(entorno, fila(2, documento_tipo="DNI", documento_numero="123456"))

    assert errores == [(2, "documento_numero", "DOCUMENTO_INVALIDO")]
    assert clientes(entorno) == []


def test_cuit_de_longitud_invalida_y_tipo_fuera_del_catalogo_tambien(
    entorno: EntornoDeImportacion,
) -> None:
    errores = fallar(
        entorno,
        fila(2, documento_tipo="CUIT", documento_numero="20-1234"),
        fila(3, codigo="C002", documento_tipo="PASAPORTE", documento_numero="123456789"),
    )

    assert errores == [
        (2, "documento_numero", "DOCUMENTO_INVALIDO"),
        (3, "documento_numero", "DOCUMENTO_INVALIDO"),
    ]


def test_ficha_incompleta_sin_direccion_se_informa_en_direccion(
    entorno: EntornoDeImportacion,
) -> None:
    """Escenario "Ficha incompleta" (CLI-01)."""
    errores = fallar(entorno, fila(2, direccion=""))

    assert errores == [(2, "direccion", "FICHA_INCOMPLETA")]


def test_ficha_incompleta_sin_contacto_se_informa_en_contacto(
    entorno: EntornoDeImportacion,
) -> None:
    assert fallar(entorno, fila(2, contacto="")) == [(2, "contacto", "FICHA_INCOMPLETA")]


def test_el_codigo_es_obligatorio_en_la_planilla(entorno: EntornoDeImportacion) -> None:
    """D6: CLI-01 lo deja opcional en la pantalla; en la planilla se exige."""
    errores = fallar(entorno, fila(2, codigo=""), fila(3, codigo="  ", nombre="Otro"))

    assert errores == [(2, "codigo", "VALOR_OBLIGATORIO"), (3, "codigo", "VALOR_OBLIGATORIO")]
    assert clientes(entorno) == []


def test_documento_con_tipo_sin_numero_da_documento_incompleto(
    entorno: EntornoDeImportacion,
) -> None:
    """CLI-01: el documento se informa en pareja."""
    errores = fallar(entorno, fila(2, documento_tipo="CUIT"))

    assert errores == [(2, "documento_numero", "DOCUMENTO_INCOMPLETO")]


def test_un_estado_de_facturacion_desconocido_es_un_error_de_fila_y_no_un_fallo_interno(
    entorno: EntornoDeImportacion,
) -> None:
    errores = fallar(entorno, fila(2, estado_facturacion_default="FACTURADO"))

    assert errores == [(2, "estado_facturacion_default", "ESTADO_FACTURACION_INVALIDO")]
    assert clientes(entorno) == []


def test_un_nombre_vacio_da_nombre_invalido(entorno: EntornoDeImportacion) -> None:
    assert fallar(entorno, fila(2, nombre="")) == [(2, "nombre", "NOMBRE_INVALIDO")]


# --- solo altas y duplicados (D6) ----------------------------------------------------


def test_codigo_ya_existente_da_codigo_duplicado_y_el_cliente_no_cambia(
    entorno: EntornoDeImportacion,
) -> None:
    importar(entorno, fila(2))
    [existente] = clientes(entorno)

    errores = fallar(entorno, fila(2, nombre="Otro nombre"))

    assert errores == [(2, "codigo", "CODIGO_DUPLICADO")]
    [igual] = clientes(entorno)
    assert (igual.id, igual.nombre) == (existente.id, "Almacén Don Pepe")


def test_documento_ya_existente_da_documento_duplicado(entorno: EntornoDeImportacion) -> None:
    importar(entorno, fila(2, documento_tipo="CUIT", documento_numero="20123456789"))

    errores = fallar(
        entorno, fila(2, codigo="C002", documento_tipo="CUIT", documento_numero="20-12345678-9")
    )

    assert errores == [(2, "documento_numero", "DOCUMENTO_DUPLICADO")]


def test_codigo_repetido_dentro_del_archivo_da_fila_duplicada_en_la_segunda(
    entorno: EntornoDeImportacion,
) -> None:
    errores = fallar(entorno, fila(2), fila(3, nombre="Kiosco Sol"), fila(4, codigo="C002"))

    assert errores == [(3, "codigo", "FILA_DUPLICADA")]
    assert clientes(entorno) == []


def test_documento_repetido_dentro_del_archivo_da_fila_duplicada_en_la_segunda(
    entorno: EntornoDeImportacion,
) -> None:
    errores = fallar(
        entorno,
        fila(2, documento_tipo="CUIT", documento_numero="20-12345678-9"),
        fila(3, codigo="C002", documento_tipo="CUIT", documento_numero="20123456789"),
    )

    assert errores == [(3, "documento_numero", "FILA_DUPLICADA")]


def test_el_mismo_codigo_en_otra_organizacion_no_es_duplicado(
    entorno: EntornoDeImportacion, db_session: Session
) -> None:
    """INV-21."""
    ajena = EntornoDeImportacion(db_session)
    importar(ajena, fila(2))

    importar(entorno, fila(2))

    assert [c.codigo for c in clientes(entorno)] == ["C001"]
    assert [c.codigo for c in clientes(ajena)] == ["C001"]


# --- todo o nada --------------------------------------------------------------------


def test_dos_filas_malas_se_informan_juntas_y_no_se_crea_ni_el_cliente_valido(
    entorno: EntornoDeImportacion,
) -> None:
    """INV-01: el informe completo, un solo rechazo."""
    errores = fallar(
        entorno,
        fila(2, documento_tipo="DNI", documento_numero="123456"),
        fila(3, codigo="C002", nombre="Kiosco Sol"),
        fila(4, codigo="C003", direccion=""),
    )

    assert errores == [
        (2, "documento_numero", "DOCUMENTO_INVALIDO"),
        (4, "direccion", "FICHA_INCOMPLETA"),
    ]
    assert clientes(entorno) == []
    assert entorno.importaciones() == []


def test_doble_envio_con_el_mismo_operation_id_no_duplica_clientes(
    entorno: EntornoDeImportacion,
) -> None:
    """INV-06."""
    operation_id = uuid4()
    cuerpo = contenido(TIPO, [fila(2), fila(3, codigo="C002", nombre="Kiosco Sol")], "clientes.csv")

    primero = entorno.enviar(cuerpo, operation_id=operation_id)
    segundo = entorno.enviar(cuerpo, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(clientes(entorno)) == 2
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1
