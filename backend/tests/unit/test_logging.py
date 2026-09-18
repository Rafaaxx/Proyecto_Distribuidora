import json
import logging


def test_json_formatter_produce_una_linea_json_con_campos_esperados():
    from app.core.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="mensaje de prueba",
        args=None,
        exc_info=None,
    )

    linea = formatter.format(record)
    datos = json.loads(linea)

    assert datos["level"] == "INFO"
    assert datos["message"] == "mensaje de prueba"
    assert "timestamp" in datos
    assert datos["operation_id"] is None
    assert datos["organizacion_id"] is None
    assert datos["usuario_id"] is None
    assert datos["dispositivo_id"] is None


def test_json_formatter_incluye_campos_de_contexto_extra():
    from app.core.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=2,
        msg="otro mensaje",
        args=None,
        exc_info=None,
    )
    record.request_id = "abc-123"

    linea = formatter.format(record)
    datos = json.loads(linea)

    assert datos["level"] == "WARNING"
    assert datos["request_id"] == "abc-123"


def test_request_id_filter_toma_el_valor_del_contexto_si_no_esta_en_el_record():
    from app.core.logging import RequestIdFilter, request_id_var

    token = request_id_var.set("del-contexto")
    try:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=3,
            msg="msg",
            args=None,
            exc_info=None,
        )
        RequestIdFilter().filter(record)
        assert record.request_id == "del-contexto"
    finally:
        request_id_var.reset(token)


def test_request_id_filter_no_pisa_un_request_id_ya_puesto_en_el_record():
    from app.core.logging import RequestIdFilter, request_id_var

    token = request_id_var.set("del-contexto")
    try:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=4,
            msg="msg",
            args=None,
            exc_info=None,
        )
        record.request_id = "explicito"
        RequestIdFilter().filter(record)
        assert record.request_id == "explicito"
    finally:
        request_id_var.reset(token)
