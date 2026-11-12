"""Unitarias de `clientes/domain/` (tareas 1.3 y 6.1).

Una prueba por comportamiento con la regla citada, y al menos dos casos por
comportamiento (la forma mala y la buena, o dos valores que rompen la regla de
distinta forma) para que una prueba que pasa por el motivo equivocado no deje
hueco. Ninguna toca la base: son funciones puras (`CLAUDE.md` §4).

Reglas citadas: CLI-01, CLI-02, CLI-03, CLI-05, CLI-06, TR-08, TR-10, INV-03,
CRE-01, CRE-03, CRE-06, y `design.md` D1, D6, D7, D8.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import product

import pytest

from app.core.errors import DomainError
from app.modules.clientes.domain.credito import (
    POLITICAS_CREDITO,
    TIPOS_TOLERANCIA,
    limite_de_consumidor_final,
    validar_credito_de_consumidor_final,
    validar_limite_credito,
    validar_politica_credito,
    validar_tolerancia_offline,
)
from app.modules.clientes.domain.estado import (
    ESTADOS,
    puede_inactivar,
    validar_estado,
    validar_transicion,
)
from app.modules.clientes.domain.ficha import (
    normalizar_codigo,
    normalizar_contacto,
    normalizar_direccion,
    normalizar_documento,
    normalizar_nombre,
)

# --------------------------------------------------------------------------
# ficha.py -- nombre, código y documento
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Kiosco La Esquina", "Kiosco La Esquina"),
        ("  Kiosco La Esquina  ", "Kiosco La Esquina"),
        ("\tKiosco\n", "Kiosco"),
    ],
)
def test_el_nombre_se_recorta_sin_tocar_el_resto(nombre: str, esperado: str) -> None:
    """TR-10, CLI-01, D1: el nombre se recorta en los bordes y nada más (los
    espacios de adentro son parte del nombre)."""
    assert normalizar_nombre(nombre) == esperado


@pytest.mark.parametrize("nombre", ["", "   ", "\t\n  "])
def test_un_nombre_vacio_o_de_espacios_se_rechaza(nombre: str) -> None:
    """TR-10: `NOMBRE_INVALIDO` y ninguna fila (spec "Nombre vacío")."""
    with pytest.raises(DomainError) as error:
        normalizar_nombre(nombre)

    assert error.value.codigo == "NOMBRE_INVALIDO"


def test_un_nombre_invalido_responde_422() -> None:
    """El código de la ficha es un error de contenido, no de conflicto."""
    with pytest.raises(DomainError) as error:
        normalizar_nombre(" ")

    assert error.value.status_http == 422


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        (None, None),
        ("K-001", "K-001"),
        ("  K-001  ", "K-001"),
        # D1: el código es opcional, así que vacío y ausente son lo mismo. Si
        # se guardara "" dos clientes sin código chocarían en el índice único.
        ("", None),
        ("   ", None),
    ],
)
def test_el_codigo_se_recorta_y_vacio_se_normaliza_a_nulo(
    codigo: str | None, esperado: str | None
) -> None:
    """D1: `codigo` único por organización con índice PARCIAL
    `WHERE codigo IS NOT NULL`; la fila sin código tiene que quedar en `NULL`
    para que el índice no la considere duplicada de la otra."""
    assert normalizar_codigo(codigo) == esperado


@pytest.mark.parametrize(
    "documento",
    [
        (None, None),
        ("", ""),
        ("  ", "  "),
    ],
)
def test_sin_documento_no_hay_documento(
    documento: tuple[str | None, str | None],
) -> None:
    """CLI-01: el documento es opcional COMO PAREJA. Sin los dos, el cliente se
    identifica por su `id` y no se rechaza (spec "Cliente sin código ni
    documento")."""
    assert normalizar_documento(*documento) is None


@pytest.mark.parametrize(
    ("tipo", "numero", "esperado"),
    [
        ("DNI", "30111222", "DNI 30111222"),
        # Separadores que se descartan: el usuario los teclea, la comparación y
        # el índice los ven como dígitos (CLI-05, D1).
        ("DNI", "30-111 222", "DNI 30111222"),
        ("DNI", "  30111222  ", "DNI 30111222"),
        # El tipo se compara y se guarda en mayúsculas para que coincida con el
        # catálogo y con el índice único.
        ("dni", "30111222", "DNI 30111222"),
        ("cuit", "30111222224", "CUIT 30111222224"),
        # CLI-05: 11 dígitos para CUIT, 7 u 8 para DNI.
        ("CUIT", "20111111112", "CUIT 20111111112"),
        ("DNI", "1234567", "DNI 1234567"),
    ],
)
def test_el_documento_se_normaliza_a_digitos(tipo: str, numero: str, esperado: str) -> None:
    """CLI-05: "el número se normaliza a dígitos antes de comparar y de guardar"
    (D1). `30-111 222` y `30111222` tienen que terminar en la misma fila para que
    `DOCUMENTO_DUPLICADO` funcione."""
    documento = normalizar_documento(tipo, numero)

    assert documento is not None
    assert str(documento) == esperado


@pytest.mark.parametrize(
    ("tipo", "numero"),
    [
        ("DNI", None),
        (None, "30111222"),
        ("DNI", ""),
        ("", "30111222"),
    ],
)
def test_un_documento_a_medias_se_rechaza_como_incompleto(
    tipo: str | None, numero: str | None
) -> None:
    """CLI-01, D1: un tipo sin número (o al revés) se rechaza con
    `DOCUMENTO_INCOMPLETO`, que es un código distinto del de longitud inválida
    (spec "Documento a medias o con letras")."""
    with pytest.raises(DomainError) as error:
        normalizar_documento(tipo, numero)

    assert error.value.codigo == "DOCUMENTO_INCOMPLETO"


@pytest.mark.parametrize(
    "numero",
    [
        "3011AB222",  # letras
        "30.111.222",  # puntos: no son separadores aceptados
        "30111/222",
        "+5430111222",  # prefijo internacional
    ],
)
def test_un_numero_con_basura_se_rechaza_como_incompleto(numero: str) -> None:
    """D1: un número con letras se rechaza con `DOCUMENTO_INCOMPLETO` (spec
    "Documento a medias o con letras"). No se "limpia": `30.111.222` y
    `30111222` se normalizan distinto y dejar pasar el primero haría que el
    índice único comparara dos textos distintos."""
    with pytest.raises(DomainError) as error:
        normalizar_documento("DNI", numero)

    assert error.value.codigo == "DOCUMENTO_INCOMPLETO"


@pytest.mark.parametrize(
    ("tipo", "numero"),
    [
        ("PASAPORTE", "30111222"),  # tipo fuera del catálogo
        ("OTRO", "1234567"),
        # Longitud que no corresponde al tipo (CLI-05).
        ("CUIT", "30111222"),  # 8 en vez de 11
        ("CUIT", "301112222241"),  # 12 en vez de 11
        ("DNI", "123456"),  # 6, el mínimo es 7
        ("DNI", "123456789"),  # 9, el máximo es 8
    ],
)
def test_un_tipo_o_una_longitud_invalida_se_rechaza_como_invalido(tipo: str, numero: str) -> None:
    """CLI-05, D1: catálogo cerrado y longitud por tipo. Un `CUIT` de 8 dígitos
    y un `DNI` de 6 levantan `DOCUMENTO_INVALIDO`, que NO es el mismo error que
    un documento a medias (spec "Longitud inválida según el tipo")."""
    with pytest.raises(DomainError) as error:
        normalizar_documento(tipo, numero)

    assert error.value.codigo == "DOCUMENTO_INVALIDO"


def test_un_documento_valido_no_es_un_error_de_contenido() -> None:
    """Triangulación: los casos válidos no levantan nada. Una función que
    rechazara todo también passaría los casos de arriba."""
    documento = normalizar_documento("DNI", "30111222")

    assert documento is not None
    assert documento.tipo == "DNI"
    assert documento.numero == "30111222"


@pytest.mark.parametrize("campo", ["direccion", "contacto"])
def test_la_ficha_sin_direccion_o_contacto_se_rechaza(campo: str) -> None:
    """CLI-01: `direccion` y `contacto` son los dos campos que CLI-01 NO marca
    como opcionales, así que faltan se rechazan (spec "Ficha sin un campo
    obligatorio")."""
    valor: str | None = None

    with pytest.raises(DomainError) as error:
        if campo == "direccion":
            normalizar_direccion(valor)
        else:
            normalizar_contacto(valor)

    assert error.value.codigo == "FICHA_INCOMPLETA"


@pytest.mark.parametrize("blanco", ["", "   ", "\t\n"])
def test_la_direccion_y_el_contacto_de_espacios_no_cumplen(blanco: str) -> None:
    """El mismo `FICHA_INCOMPLETA` para vacío y para solo espacios: la columna
    es `NOT NULL` y un espacio es tan poco dato como una cadena vacía."""
    with pytest.raises(DomainError) as error:
        normalizar_direccion(blanco)
    assert error.value.codigo == "FICHA_INCOMPLETA"

    with pytest.raises(DomainError) as error:
        normalizar_contacto(blanco)
    assert error.value.codigo == "FICHA_INCOMPLETA"


def test_la_direccion_y_el_contacto_se_recortan() -> None:
    """Cuando vienen, se guardan recortados; la dirección es obligatoria, así
    que un vacío es error y no un valor neutro."""
    assert normalizar_direccion("  Av. San Martín 1420  ") == "Av. San Martín 1420"
    assert normalizar_contacto("  Rocío  ") == "Rocío"


# --------------------------------------------------------------------------
# estado.py -- la máquina de estados de `01` §18
# --------------------------------------------------------------------------

# Las cinco transiciones de `01` §18, escritas acá para que la prueba de la
# matriz sea una especificación legible y no una copia del código.
_TRANSICIONES_PERMITIDAS = frozenset(
    {
        ("ACTIVO", "SUSPENDIDO"),
        ("SUSPENDIDO", "ACTIVO"),
        ("ACTIVO", "INACTIVO"),
        ("SUSPENDIDO", "INACTIVO"),
        ("INACTIVO", "ACTIVO"),
    }
)


def test_el_catalogo_de_estados_es_el_de_la_dominio() -> None:
    """`03` §10 y `01` §18: exactamente estos tres, y ninguno más. La prueba
    falla si alguien agrega un estado sin que la spec lo pida."""
    assert {"ACTIVO", "SUSPENDIDO", "INACTIVO"} == ESTADOS


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSPENDIDO", "INACTIVO"])
def test_los_tres_estados_del_catalogo_pasan(estado: str) -> None:
    """Triangulación: el validador no rechaza lo que tiene que aceptar."""
    assert validar_estado(estado) == estado


@pytest.mark.parametrize("estado", ["activo", "ACTIVO_OLD", "", "BORRADO", "ACTIVO "])
def test_un_estado_fuera_del_catalogo_se_rechaza(estado: str) -> None:
    """Spec "Estado fuera del catálogo": `ESTADO_INVALIDO`. Se compara el valor
    tal cual, sin normalizar: es un catálogo cerrado, y "arreglarlo" en
    mayúsculas escondería un cliente que no habría pasado el `CHECK` de la
    base."""
    with pytest.raises(DomainError) as error:
        validar_estado(estado)

    assert error.value.codigo == "ESTADO_INVALIDO"


@pytest.mark.parametrize(
    ("actual", "nuevo"),
    [
        ("ACTIVO", "SUSPENDIDO"),
        ("SUSPENDIDO", "ACTIVO"),
        ("ACTIVO", "INACTIVO"),
        ("SUSPENDIDO", "INACTIVO"),
        ("INACTIVO", "ACTIVO"),
    ],
)
def test_las_transiciones_permitidas_pasan(actual: str, nuevo: str) -> None:
    """`01` §18: `ACTIVO <-> SUSPENDIDO`, `-> INACTIVO` desde los dos activos, y
    la única salida de `INACTIVO` (CLI-06)."""
    assert validar_transicion(actual, nuevo) == nuevo


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSPENDIDO", "INACTIVO"])
def test_quedarse_en_el_mismo_estado_no_es_un_error(estado: str) -> None:
    """`CLIENTE_MODIFICAR` manda la ficha entera, así que reenviar la misma
    ficha deja el estado como estaba. Si esto fuera un error, guardar la ficha
    sin tocar el estado fallaría siempre."""
    assert validar_transicion(estado, estado) == estado


def test_inactivo_a_activo_sin_operaciones_pasa() -> None:
    """CLI-06, ADR-030, D7: en este change ningún cliente tiene operaciones
    (ventas, cobranzas y compras son de los changes 08, 10, 17 y 18a), así que
    reactivar está disponible (spec "Reactivar un cliente sin operaciones")."""
    assert validar_transicion("INACTIVO", "ACTIVO", tiene_operaciones=False) == "ACTIVO"


def test_inactivo_a_activo_con_operaciones_se_rechaza() -> None:
    """CLI-06, ADR-030: con operaciones `INACTIVO` es terminal y sale
    `CLIENTE_CON_OPERACIONES`, NO el genérico de transición. La spec exige ese
    código propio para que el frontend pueda explicar la diferencia."""
    with pytest.raises(DomainError) as error:
        validar_transicion("INACTIVO", "ACTIVO", tiene_operaciones=True)

    assert error.value.codigo == "CLIENTE_CON_OPERACIONES"


def test_una_transicion_no_permitida_se_rechaza() -> None:
    """D7, `01` §18: la única pareja del catálogo que no está permitida es
    `INACTIVO -> SUSPENDIDO` (de `INACTIVO` solo se sale hacia `ACTIVO`, CLI-06),
    y levanta `TRANSICION_ESTADO_INVALIDA` con 409, que es un conflicto de estado
    y no un contenido malformado.

    El resto de la máquina la cubre `test_la_matriz_completa_de_transiciones`,
    que enumera las nueve parejas."""
    with pytest.raises(DomainError) as error:
        validar_transicion("INACTIVO", "SUSPENDIDO")

    assert error.value.codigo == "TRANSICION_ESTADO_INVALIDA"
    assert error.value.status_http == 409


@pytest.mark.parametrize(("actual", "nuevo"), sorted(product(sorted(ESTADOS), repeat=2)))
def test_la_matriz_completa_de_transiciones(actual: str, nuevo: str) -> None:
    """Las nueve parejas de `01` §18, una por una.

    Enumerar la matriz entera es lo que hace que esta prueba sirva: si mañana
    alguien abre una transición en el código sin tocar la spec, esta prueba
    falla; si la cierra sin querer, también. Una prueba con dos o tres casos
    sueltos deja pasar todo lo demás.

    Las tres diagonales (quedarse en el mismo estado) son válidas porque
    `CLIENTE_MODIFICAR` manda la ficha entera."""
    permitida = actual == nuevo or (actual, nuevo) in _TRANSICIONES_PERMITIDAS

    if permitida:
        assert validar_transicion(actual, nuevo) == nuevo
    else:
        with pytest.raises(DomainError) as error:
            validar_transicion(actual, nuevo)
        assert error.value.codigo == "TRANSICION_ESTADO_INVALIDA"


def test_un_estado_nuevo_fuera_del_catalogo_se_rechaza_antes_de_la_transicion() -> None:
    """El estado pedido se valida contra el catálogo antes que la transición:
    `ACTIVO -> NO_EXISTE` es `ESTADO_INVALIDO` (la spec lo pide así), no un
    error de máquina de estados que además hablaría de un estado que no existe."""
    with pytest.raises(DomainError) as error:
        validar_transicion("ACTIVO", "NO_EXISTE")

    assert error.value.codigo == "ESTADO_INVALIDO"


def test_un_estado_actual_fuera_del_catalogo_tambien_se_rechaza() -> None:
    """Una fila con un estado que ya no está en el catálogo es una
    inconsistencia que hay que ver, no asumir."""
    with pytest.raises(DomainError) as error:
        validar_transicion("LEGADO", "ACTIVO")

    assert error.value.codigo == "ESTADO_INVALIDO"


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSPENDIDO"])
def test_el_consumidor_final_se_suspende_y_regresa(estado: str) -> None:
    """CLI-03, spec "El consumidor final admite la misma máquina de estados":
    suspenderlo y reactivarlo es normal; lo único prohibido es inactivarlo."""
    otro = "SUSPENDIDO" if estado == "ACTIVO" else "ACTIVO"

    assert validar_transicion(estado, otro, es_consumidor_final=True) == otro


@pytest.mark.parametrize("estado", ["ACTIVO", "SUSPENDIDO"])
def test_el_consumidor_final_no_se_inactiva(estado: str) -> None:
    """CLI-03, ADR-029, D4: el consumidor final solo puede estar `ACTIVO` o
    `SUSPENDIDO`. Se rechaza con su propio código, no con el de la máquina, para
    que el mensaje diga por qué."""
    with pytest.raises(DomainError) as error:
        validar_transicion(estado, "INACTIVO", es_consumidor_final=True)

    assert error.value.codigo == "CONSUMIDOR_FINAL_NO_INACTIVABLE"


def test_el_consumidor_final_tampoco_se_inactiva_siendo_ya_inactivo() -> None:
    """Quedarse donde está no es un cambio: si la fila ya está `INACTIVO` (no
    debería pasar, porque el comando no lo dejó llegar ahí), el mismo estado no
    es una transición a `INACTIVO`."""
    assert validar_transicion("INACTIVO", "INACTIVO", es_consumidor_final=True) == "INACTIVO"


@pytest.mark.parametrize(
    ("estado", "es_consumidor_final", "esperado"),
    [
        ("ACTIVO", False, True),
        ("SUSPENDIDO", False, True),
        ("INACTIVO", False, False),  # ya está inactivo
        ("ACTIVO", True, False),  # el consumidor final no se inactiva
        ("SUSPENDIDO", True, False),
        ("NO_EXISTE", False, False),
    ],
)
def test_puede_inactivar_responde_lo_mismo_que_la_maquina(
    estado: str, es_consumidor_final: bool, esperado: bool
) -> None:
    """La pantalla de inactivación pide el nombre completo antes de enviar
    (D7, confirmación tipeada), y para saber si va a tener que pedirlo consulta
    esto. No puede discrepar de `validar_transicion`."""
    assert puede_inactivar(estado, es_consumidor_final=es_consumidor_final) is esperado


# --------------------------------------------------------------------------
# credito.py -- límite, política y tolerancia
# --------------------------------------------------------------------------


def test_el_catalogo_de_politicas_es_el_de_la_organizacion() -> None:
    """CRE-03, `03` §4: los mismos tres valores que
    `configuracion_organizacion.politica_credito_default`."""
    assert {"ADVERTIR", "AUTORIZAR", "BLOQUEAR"} == POLITICAS_CREDITO


def test_el_catalogo_de_tipos_de_tolerancia_es_el_de_la_organizacion() -> None:
    """CRE-06, D6, `03` §4: los mismos dos que la organización."""
    assert {"IMPORTE", "PORCENTAJE"} == TIPOS_TOLERANCIA


@pytest.mark.parametrize(
    "limite",
    [
        None,  # sin control de crédito (CRE-01)
        Decimal("0.00"),  # cero NO es "sin control": es solo contado
        Decimal("150000.00"),
        Decimal("150000"),  # un entero es un Decimal exacto
        Decimal("0.01"),
    ],
)
def test_los_limites_validos_pasan(limite: Decimal | None) -> None:
    """Triangulación: `None` (sin control) y `0.00` son valores LEGÍTIMOS y
    distintos entre sí (CRE-01). Un validador que rechazara el cero o el nulo
    estaría rompiendo la herencia de la organización."""
    assert validar_limite_credito(limite) == limite


@pytest.mark.parametrize(
    ("limite", "motivo"),
    [
        (Decimal("-1.00"), "negativo"),
        (Decimal("-0.01"), "negativo"),
        # La spec pide `LIMITE_CREDITO_INVALIDO` para "100.005" y NO un importe
        # redondeado en silencio: redondear convertiría un error del usuario en
        # un dato distinto del que escribió (INV-03, `core/money.py`).
        (Decimal("100.005"), "más decimales que la columna"),
        (Decimal("0.001"), "más decimales que la columna"),
        (Decimal("-0.005"), "negativo y con más decimales"),
    ],
)
def test_un_limite_invalido_se_rechaza(limite: Decimal, motivo: str) -> None:
    """CRE-01, INV-03, D6: `numeric(14,2)` sin redondeo. El `motivo` está en el
    nombre del caso para que quede escrito por qué ese valor es inválido."""
    with pytest.raises(DomainError) as error:
        validar_limite_credito(limite)

    assert error.value.codigo == "LIMITE_CREDITO_INVALIDO", motivo
    assert error.value.status_http == 422


@pytest.mark.parametrize("limite", [100.5, 1.0, True])
def test_un_limite_que_no_sea_decimal_exacto_se_rechaza(limite: object) -> None:
    """INV-03: un `float` binario no es dinero y un `bool` no es un número a
    propósito. Sin esta guarda, un `float` colado por un camino secundario
    llegaría a la columna con la escala que le dé la suerte."""
    with pytest.raises(DomainError) as error:
        validar_limite_credito(limite)  # type: ignore[arg-type]

    assert error.value.codigo == "LIMITE_CREDITO_INVALIDO"


@pytest.mark.parametrize("politica", ["ADVERTIR", "AUTORIZAR", "BLOQUEAR"])
def test_las_politicas_validas_pasan(politica: str) -> None:
    """Triangulación: las tres del catálogo pasan sin cambios."""
    assert validar_politica_credito(politica) == politica


def test_sin_politica_hereda_y_no_se_reemplaza_por_el_default() -> None:
    """CRE-03: la fila guarda el nulo y la herencia se resuelve al evaluar. Si
    acá se copiara `ADVERTIR`, el cliente quedaría con un valor propio que no
    eligió y dejaría de seguir a la organización cuando ella lo cambie."""
    assert validar_politica_credito(None) is None


@pytest.mark.parametrize("politica", ["IGNORAR", "autorizar", "", "BLOQUEAR "])
def test_una_politica_fuera_del_catalogo_se_rechaza(politica: str) -> None:
    """CRE-03, `03` §4: `POLITICA_CREDITO_INVALIDA`. No se normaliza: es un
    catálogo cerrado, y `autorizar` en minúsculas no es la política."""
    with pytest.raises(DomainError) as error:
        validar_politica_credito(politica)

    assert error.value.codigo == "POLITICA_CREDITO_INVALIDA"


@pytest.mark.parametrize(
    ("tipo", "valor", "esperado"),
    [
        (None, None, (None, None)),
        ("IMPORTE", Decimal("25.00"), ("IMPORTE", Decimal("25.00"))),
        ("PORCENTAJE", Decimal("2.50"), ("PORCENTAJE", Decimal("2.50"))),
        # D6: con `numeric(14,2)` un porcentaje admite dos decimales, y eso
        # alcanza para una tolerancia.
        ("PORCENTAJE", Decimal("2.5"), ("PORCENTAJE", Decimal("2.5"))),
        ("IMPORTE", Decimal("0.00"), ("IMPORTE", Decimal("0.00"))),
    ],
)
def test_las_tolerancias_validas_pasan(
    tipo: str | None, valor: Decimal | None, esperado: tuple[str | None, Decimal | None]
) -> None:
    """Triangulación: la pareja válida pasa, y sin tolerancia vuelve a nulo
    (hereda la de la organización, CRE-06)."""
    assert validar_tolerancia_offline(tipo, valor) == esperado


@pytest.mark.parametrize(
    ("tipo", "valor"),
    [
        # A medias en las dos direcciones (CRE-06).
        ("IMPORTE", None),
        (None, Decimal("25.00")),
        # Tipo fuera del catálogo (`03` §4).
        ("CUALQUIERA", Decimal("25.00")),
        ("importe", Decimal("25.00")),
        # Valor inválido: una tolerancia negativa es una exigencia de
        # diferencia, no una tolerancia.
        ("IMPORTE", Decimal("-1.00")),
        # Más de dos decimales que la columna (D6): se rechaza, no se redondea.
        ("PORCENTAJE", Decimal("2.505")),
    ],
)
def test_una_tolerancia_invalida_se_rechaza(tipo: str | None, valor: Decimal | None) -> None:
    """CRE-06, D6: `TOLERANCIA_OFFLINE_INVALIDA` para todos los casos, porque
    la spec no los separa en códigos distintos (spec "Tolerancia a medias o con
    tipo desconocido")."""
    with pytest.raises(DomainError) as error:
        validar_tolerancia_offline(tipo, valor)

    assert error.value.codigo == "TOLERANCIA_OFFLINE_INVALIDA"


def test_la_tolerancia_no_acepta_un_punto_flotante() -> None:
    """INV-03, igual que el límite."""
    with pytest.raises(DomainError) as error:
        validar_tolerancia_offline("IMPORTE", 25.0)  # type: ignore[arg-type]

    assert error.value.codigo == "TOLERANCIA_OFFLINE_INVALIDA"


@pytest.mark.parametrize(
    ("limite", "politica", "tipo", "valor"),
    [
        (Decimal("50000.00"), None, None, None),
        (None, "AUTORIZAR", None, None),
        (None, None, "IMPORTE", Decimal("25.00")),
        (None, None, None, Decimal("25.00")),
    ],
)
def test_el_consumidor_final_no_admite_ningun_campo_de_credito(
    limite: Decimal | None,
    politica: str | None,
    tipo: str | None,
    valor: Decimal | None,
) -> None:
    """CLI-03, CRE-01, spec "No se puede cambiar el límite del consumidor
    final": `CONSUMIDOR_FINAL_SIN_CREDITO` y el límite sigue en cero. Se prueba
    cada campo por separado porque cualquiera de los cuatro alcanza para
    rechazar, y un chequeo que solo mirara el límite dejaría pasar la
    política."""
    with pytest.raises(DomainError) as error:
        validar_credito_de_consumidor_final(True, limite, politica, tipo, valor)

    assert error.value.codigo == "CONSUMIDOR_FINAL_SIN_CREDITO"


def test_el_consumidor_final_admite_una_escritura_vacia() -> None:
    """Triangulación: mandar los cuatro en nulo no cambia nada y no es un error.
    Si lo fuera, un reenvío del mismo crédito del consumidor final fallaría."""
    validar_credito_de_consumidor_final(True, None, None, None, None)


@pytest.mark.parametrize(
    ("limite", "politica", "tipo", "valor"),
    [
        (None, None, None, None),
        (Decimal("150000.00"), "AUTORIZAR", "IMPORTE", Decimal("25.00")),
    ],
)
def test_un_cliente_comun_admite_credito_propio(
    limite: Decimal | None,
    politica: str | None,
    tipo: str | None,
    valor: Decimal | None,
) -> None:
    """Triangulación: la restricción es del consumidor final, no de todos. Un
    chequeo sin la marca rechazaría a cualquier cliente y dejaría el comando
    inútil para el 99% de los casos."""
    validar_credito_de_consumidor_final(False, limite, politica, tipo, valor)


def test_el_limite_del_consumidor_final_es_cero_con_dos_decimales() -> None:
    """CLI-03, CRE-01: el límite es cero, y cero en `numeric(14,2)` es
    `0.00`. El test comprueba la escala, no solo el valor: `"0"` en la columna
    es el mismo número que `0.00` y la API devuelve lo que hay en la fila."""
    limite = limite_de_consumidor_final()

    assert limite == Decimal("0.00")
    assert limite.as_tuple().exponent == -2
