"""Tarea 7.2 (change 10): importación de saldos iniciales por `IMPORTACION_REGISTRAR`,
contra PostgreSQL real (`specs/importacion/puesta-en-marcha`, `design.md` D4, D7, D12).

Cada fila es un `cuentas_corrientes.service.registrar_saldo_inicial` (las mismas reglas que
`SALDO_INICIAL_REGISTRAR`, CC-08, ADR-034): varios saldos por cuenta mientras no tenga
movimientos de otro tipo, cualquier estado de la entidad salvo el consumidor final. Los
rótulos de sentido son los de ADR-034 punto 8. El momento es el `occurred_at` del sobre.

Reglas citadas: CC-01, CC-08, CLI-03, INV-01, INV-06, INV-13, INV-21, TR-01.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from importacion_utiles import (
    MOMENTO,
    EntornoDeImportacion,
    contenido,
    errores_de,
    fila_de,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.cuentas_corrientes.models import CuentaMovimiento
from app.modules.importacion.domain.errores import ImportacionConErroresError
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

TIPO = "SALDOS_INICIALES"


def fila(
    numero: int, cuenta_tipo: str, entidad: str, importe: str, sentido: str
) -> dict[str, object]:
    return fila_de(
        numero,
        {"cuenta_tipo": cuenta_tipo, "entidad": entidad, "importe": importe, "sentido": sentido},
    )


@pytest.fixture
def entorno(db_session: Session) -> EntornoDeImportacion:
    return EntornoDeImportacion(db_session)


def importar(
    entorno: EntornoDeImportacion, *filas: dict[str, object], operation_id: UUID | None = None
) -> Comando:
    return entorno.enviar(contenido(TIPO, list(filas), "saldos.csv"), operation_id=operation_id)


def fallar(
    entorno: EntornoDeImportacion, *filas: dict[str, object]
) -> list[tuple[int, str | None, str]]:
    with pytest.raises(ImportacionConErroresError) as excinfo:
        importar(entorno, *filas)
    return errores_de(excinfo.value)


# --- clientes ------------------------------------------------------------------------------


def test_saldo_inicial_de_cliente_nos_debe(entorno: EntornoDeImportacion) -> None:
    """CC-08, INV-13."""
    cliente_id = entorno.cliente("C001")
    operation_id = uuid4()

    comando = importar(
        entorno, fila(2, "CLIENTE", "C001", "150000", "Nos debe"), operation_id=operation_id
    )

    assert comando.resultado is not None
    assert (comando.resultado["filas_total"], comando.resultado["filas_ok"]) == (1, 1)
    [movimiento] = entorno.movimientos_de_cuenta("CLIENTE", cliente_id)
    assert (movimiento.tipo, movimiento.sentido, str(movimiento.importe)) == (
        "SALDO_INICIAL",
        "AUMENTA",
        "150000.00",
    )
    assert movimiento.origen_id == operation_id
    assert movimiento.occurred_at == MOMENTO
    assert str(entorno.saldo_de_cuenta("CLIENTE", cliente_id)) == "150000.00"
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1


def test_saldo_a_favor_del_cliente_es_un_saldo_negativo(entorno: EntornoDeImportacion) -> None:
    """Triangula el sentido: "Saldo a favor" reduce."""
    cliente_id = entorno.cliente("C001")

    importar(entorno, fila(2, "CLIENTE", "C001", "2500,50", "Saldo a favor"))

    assert str(entorno.saldo_de_cuenta("CLIENTE", cliente_id)) == "-2500.50"


def test_correccion_en_el_mismo_archivo_deja_130000(entorno: EntornoDeImportacion) -> None:
    """CC-08, ADR-034 punto 1."""
    cliente_id = entorno.cliente("C001")

    importar(
        entorno,
        fila(2, "CLIENTE", "C001", "150000", "AUMENTA"),
        fila(3, "CLIENTE", "C001", "20000", "REDUCE"),
    )

    movimientos = entorno.movimientos_de_cuenta("CLIENTE", cliente_id)
    assert [(m.tipo, m.sentido) for m in movimientos] == [
        ("SALDO_INICIAL", "AUMENTA"),
        ("SALDO_INICIAL", "REDUCE"),
    ]
    assert str(entorno.saldo_de_cuenta("CLIENTE", cliente_id)) == "130000.00"


def test_el_cliente_se_busca_por_codigo_y_si_no_por_documento(
    entorno: EntornoDeImportacion,
) -> None:
    """D4."""
    por_codigo = entorno.cliente("C001")
    por_cuit = entorno.cliente("C002", documento=("CUIT", "20-12345678-9"))

    importar(
        entorno,
        fila(2, "CLIENTE", " c001 ", "100", "Nos debe"),
        fila(3, "CLIENTE", "20-12345678-9", "200", "Nos debe"),
        fila(4, "CLIENTE", "20123456789", "50", "Nos debe"),
    )

    assert str(entorno.saldo_de_cuenta("CLIENTE", por_codigo)) == "100.00"
    assert str(entorno.saldo_de_cuenta("CLIENTE", por_cuit)) == "250.00"


def test_cliente_inexistente_es_referencia_no_encontrada_en_entidad(
    entorno: EntornoDeImportacion,
) -> None:
    """INV-21, D4."""
    entorno.cliente("C001")

    errores = fallar(
        entorno,
        fila(2, "CLIENTE", "C999", "100", "Nos debe"),
        fila(3, "CLIENTE", "30-99999999-9", "100", "Nos debe"),
    )

    assert errores == [
        (2, "entidad", "REFERENCIA_NO_ENCONTRADA"),
        (3, "entidad", "REFERENCIA_NO_ENCONTRADA"),
    ]


def test_cliente_de_otra_organizacion_es_no_encontrado(entorno: EntornoDeImportacion) -> None:
    """INV-21."""
    otra = EntornoDeImportacion(entorno.sesion)
    otra.cliente("C001")

    assert fallar(entorno, fila(2, "CLIENTE", "C001", "100", "Nos debe")) == [
        (2, "entidad", "REFERENCIA_NO_ENCONTRADA")
    ]


def test_cliente_inactivo_admite_saldo_inicial(entorno: EntornoDeImportacion) -> None:
    """ADR-034 punto 6: cualquier estado salvo el consumidor final."""
    cliente_id = entorno.cliente("C001")
    entorno.sesion.execute(
        text("UPDATE cliente SET estado = 'INACTIVO' WHERE id = :id"), {"id": cliente_id}
    )
    entorno.sesion.commit()

    importar(entorno, fila(2, "CLIENTE", "C001", "100", "Nos debe"))

    assert str(entorno.saldo_de_cuenta("CLIENTE", cliente_id)) == "100.00"


def test_consumidor_final_da_consumidor_final_sin_cuenta(entorno: EntornoDeImportacion) -> None:
    """CC-08, CLI-03."""
    consumidor_id = entorno.cliente("CF")
    entorno.sesion.execute(
        text(
            "UPDATE configuracion_organizacion SET cliente_consumidor_final_id = :id "
            "WHERE organizacion_id = :org"
        ),
        {"id": consumidor_id, "org": entorno.org},
    )
    entorno.sesion.commit()

    errores = fallar(entorno, fila(2, "CLIENTE", "CF", "100", "Nos debe"))

    assert errores == [(2, "entidad", "CONSUMIDOR_FINAL_SIN_CUENTA")]


def test_cuenta_con_movimientos_de_otro_tipo_da_cuenta_con_operaciones(
    entorno: EntornoDeImportacion,
) -> None:
    """CC-08: un movimiento que no es `SALDO_INICIAL` (insertado por SQL, no hay
    todavía cobranzas ni ventas)."""
    cliente_id = entorno.cliente("C001")
    otro = entorno.cliente("C002")
    entorno.sesion.execute(
        text(
            "INSERT INTO cuenta_movimiento (id, organizacion_id, cuenta_tipo, entidad_id, tipo, "
            "sentido, importe, origen_tipo, origen_id, occurred_at, registered_at, usuario_id, "
            "dispositivo_id, operation_id) VALUES (:id, :org, 'CLIENTE', :ent, 'COBRANZA', "
            "'REDUCE', 10, 'COBRANZA', :op, :m, :m, :u, :d, :op)"
        ),
        {
            "id": uuid4(),
            "org": entorno.org,
            "ent": cliente_id,
            "op": uuid4(),
            "m": MOMENTO,
            "u": entorno.usuario_id,
            "d": entorno.dispositivo_id,
        },
    )
    entorno.sesion.commit()

    errores = fallar(
        entorno,
        fila(2, "CLIENTE", "C001", "100", "Nos debe"),
        fila(3, "CLIENTE", "C002", "100", "Nos debe"),
    )

    assert errores == [(2, "entidad", "CUENTA_CON_OPERACIONES")]
    assert entorno.movimientos_de_cuenta("CLIENTE", otro) == []


# --- proveedores ---------------------------------------------------------------------------


def test_saldo_inicial_de_proveedor_le_debemos(entorno: EntornoDeImportacion) -> None:
    """CC-08, CC-01."""
    proveedor_id = entorno.proveedor("Bodega Sur")

    importar(entorno, fila(2, "PROVEEDOR", "bodega SUR", "80000", "Le debemos"))

    assert str(entorno.saldo_de_cuenta("PROVEEDOR", proveedor_id)) == "80000.00"


def test_saldo_a_nuestro_favor_del_proveedor_reduce(entorno: EntornoDeImportacion) -> None:
    proveedor_id = entorno.proveedor("Bodega Sur")

    importar(
        entorno,
        fila(2, "PROVEEDOR", "Bodega Sur", "80000", "Le debemos"),
        fila(3, "PROVEEDOR", "Bodega Sur", "30000", "Saldo a nuestro favor"),
    )

    assert str(entorno.saldo_de_cuenta("PROVEEDOR", proveedor_id)) == "50000.00"


def test_proveedor_inexistente_o_de_otra_organizacion_es_no_encontrado(
    entorno: EntornoDeImportacion,
) -> None:
    otra = EntornoDeImportacion(entorno.sesion)
    otra.proveedor("Bodega Ajena")

    errores = fallar(
        entorno,
        fila(2, "PROVEEDOR", "Bodega Ajena", "100", "Le debemos"),
        fila(3, "PROVEEDOR", "No Existe SA", "100", "Le debemos"),
    )

    assert errores == [
        (2, "entidad", "REFERENCIA_NO_ENCONTRADA"),
        (3, "entidad", "REFERENCIA_NO_ENCONTRADA"),
    ]


# --- importe, sentido y tipo de cuenta -----------------------------------------------------------


@pytest.mark.parametrize("importe", ["100,005", "0", "-5"])
def test_importe_fuera_de_regla_da_importe_invalido_sin_redondear(
    entorno: EntornoDeImportacion, importe: str
) -> None:
    """TR-01: tres decimales, cero y negativo."""
    entorno.cliente("C001")

    assert fallar(entorno, fila(2, "CLIENTE", "C001", importe, "Nos debe")) == [
        (2, "importe", "IMPORTE_INVALIDO")
    ]


def test_importe_mal_escrito_da_numero_invalido(entorno: EntornoDeImportacion) -> None:
    """D12: el punto se rechaza."""
    entorno.cliente("C001")

    assert fallar(entorno, fila(2, "CLIENTE", "C001", "1.500", "Nos debe")) == [
        (2, "importe", "NUMERO_INVALIDO")
    ]


@pytest.mark.parametrize(
    ("cuenta_tipo", "entidad", "sentido"),
    [
        ("CLIENTE", "C001", "debe"),
        ("CLIENTE", "C001", "Le debemos"),
        ("PROVEEDOR", "Bodega Sur", "Nos debe"),
    ],
)
def test_sentido_desconocido_o_de_la_otra_cuenta_da_sentido_invalido(
    entorno: EntornoDeImportacion, cuenta_tipo: str, entidad: str, sentido: str
) -> None:
    """CC-01, ADR-034 punto 8."""
    entorno.cliente("C001")
    entorno.proveedor("Bodega Sur")

    assert fallar(entorno, fila(2, cuenta_tipo, entidad, "100", sentido)) == [
        (2, "sentido", "SENTIDO_INVALIDO")
    ]


def test_tipo_de_cuenta_desconocido_da_cuenta_tipo_invalido(
    entorno: EntornoDeImportacion,
) -> None:
    assert fallar(entorno, fila(2, "EMPLEADO", "Juan", "100", "Nos debe")) == [
        (2, "cuenta_tipo", "CUENTA_TIPO_INVALIDO")
    ]


# --- todo o nada, orden e idempotencia ---------------------------------------------


def test_una_fila_mala_impide_importar_las_buenas_y_se_informan_todas(
    entorno: EntornoDeImportacion,
) -> None:
    """INV-01."""
    cliente_id = entorno.cliente("C001")
    entorno.proveedor("Bodega Sur")

    errores = fallar(
        entorno,
        fila(2, "CLIENTE", "C001", "100", "Nos debe"),
        fila(3, "CLIENTE", "C999", "100", "Nos debe"),
        fila(4, "PROVEEDOR", "Bodega Sur", "100,005", "Le debemos"),
    )

    assert errores == [
        (3, "entidad", "REFERENCIA_NO_ENCONTRADA"),
        (4, "importe", "IMPORTE_INVALIDO"),
    ]
    assert entorno.movimientos_de_cuenta("CLIENTE", cliente_id) == []
    assert entorno.importaciones() == []


def test_las_cuentas_se_escriben_por_tipo_y_entidad_ascendentes_conservando_el_orden_del_archivo(
    entorno: EntornoDeImportacion,
) -> None:
    """`02` §7.3: orden de bloqueo por (`cuenta_tipo`, entidad)."""
    primero, segundo = sorted([entorno.cliente("C001"), entorno.cliente("C002")])
    codigo = {c: f"C00{i}" for i, c in enumerate(sorted([primero, segundo]), start=1)}
    proveedor_id = entorno.proveedor("Bodega Sur")

    importar(
        entorno,
        fila(2, "PROVEEDOR", "Bodega Sur", "10", "Le debemos"),
        fila(3, "CLIENTE", codigo[segundo], "20", "Nos debe"),
        fila(4, "CLIENTE", codigo[primero], "30", "Nos debe"),
        fila(5, "CLIENTE", codigo[primero], "5", "Saldo a favor"),
    )

    entorno.sesion.expire_all()
    movimientos = entorno.sesion.scalars(
        select(CuentaMovimiento)
        .where(CuentaMovimiento.organizacion_id == entorno.org)
        .order_by(CuentaMovimiento.registered_at, CuentaMovimiento.id)
    ).all()
    escritos = [(m.cuenta_tipo, m.entidad_id, m.sentido) for m in movimientos]
    assert escritos == [
        ("CLIENTE", primero, "AUMENTA"),
        ("CLIENTE", primero, "REDUCE"),
        ("CLIENTE", segundo, "AUMENTA"),
        ("PROVEEDOR", proveedor_id, "AUMENTA"),
    ]
    assert str(entorno.saldo_de_cuenta("CLIENTE", primero)) == "25.00"


def test_doble_envio_con_el_mismo_operation_id_no_duplica_el_saldo(
    entorno: EntornoDeImportacion,
) -> None:
    """INV-06."""
    cliente_id = entorno.cliente("C001")
    operation_id = uuid4()
    filas = (fila(2, "CLIENTE", "C001", "150000", "Nos debe"),)

    primero = importar(entorno, *filas, operation_id=operation_id)
    segundo = importar(entorno, *filas, operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.movimientos_de_cuenta("CLIENTE", cliente_id)) == 1
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1
