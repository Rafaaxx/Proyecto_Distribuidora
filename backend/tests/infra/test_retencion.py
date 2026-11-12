"""Retencion de 14 diarios y 8 semanales (change 27b, Lote 1; D1).

Spec `sistema/respaldos`, requisito «Retencion de 14 backups diarios y 8 semanales». Cita
`docs/02-arquitectura.md` §16.2. La regla es una funcion de shell pura (`retencion.sh`, cargada
con `RETENCION_SOLO_FUNCIONES=1` como `programar.sh`): recibe nombres por la entrada estandar y
devuelve los que se conservan (`retencion_conservar`) o los que sobran (`retencion_sobrantes`).
Se corre dentro de la imagen real de backup (GNU date de postgres:17).
"""

from datetime import date, datetime, timedelta

NOMBRE = "distribuidora-{:%Y%m%d}-{}.dump"


def nombre(dia: date, hora: str = "030000") -> str:
    return NOMBRE.format(dia, hora)


def _funcion(corredor, funcion: str, nombres: list[str], diarios: int = 14, semanales: int = 8):
    entrada = "\n".join(nombres)
    codigo, salida = corredor.correr(
        "RETENCION_SOLO_FUNCIONES=1 . /opt/backup/retencion.sh; "
        f"{funcion} {diarios} {semanales} <<'FIN'\n{entrada}\nFIN\n"
        "echo RC=$?; exit 0",
        red=False,
    )
    cuerpo, _, rc = salida.rpartition("RC=")
    assert rc.strip() == "0", salida
    return [x for x in cuerpo.split("\n") if x.strip()]


def _conservar(corredor, nombres, diarios=14, semanales=8):
    return _funcion(corredor, "retencion_conservar", nombres, diarios, semanales)


def _dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


def test_dos_meses_de_backups_diarios_dejan_19(corredor):
    # Escenario «Dos meses de backups diarios».
    todos = [nombre(d) for d in _dias(date(2026, 11, 1), date(2026, 12, 31))]
    assert len(todos) == 61
    esperados = [nombre(d) for d in _dias(date(2026, 12, 18), date(2026, 12, 31))]
    esperados += [
        nombre(date(2026, m, d)) for m, d in ((12, 13), (12, 6), (11, 29), (11, 22), (11, 15))
    ]
    assert _conservar(corredor, todos) == sorted(esperados)
    assert len(esperados) == 19


def test_varios_backups_el_mismo_dia_queda_el_mas_reciente(corredor):
    # Escenario «Varios backups el mismo dia».
    dias = _dias(date(2026, 12, 18), date(2026, 12, 30))
    nombres = [nombre(d) for d in dias]  # los 13 dias anteriores
    nombres += [nombre(date(2026, 12, 31), "030000"), nombre(date(2026, 12, 31), "152000")]
    conservados = _conservar(corredor, nombres)
    assert nombre(date(2026, 12, 31), "152000") in conservados
    assert nombre(date(2026, 12, 31), "030000") not in conservados


def test_si_los_backups_se_detienen_no_se_borran_los_ultimos(corredor):
    # Escenario «Si los backups se detienen, no se borran los ultimos».
    nombres = [nombre(d) for d in _dias(date(2026, 9, 1), date(2026, 9, 14))]
    nombres.append(nombre(date(2026, 12, 1)))
    conservados = _conservar(corredor, nombres)
    assert nombre(date(2026, 9, 1)) not in conservados
    assert len(conservados) == 14
    assert nombre(date(2026, 12, 1)) in conservados
    assert nombre(date(2026, 9, 2)) in conservados


def test_poco_material_no_borra_nada(corredor):
    nombres = [nombre(d) for d in _dias(date(2026, 12, 1), date(2026, 12, 5))]
    assert _conservar(corredor, nombres) == sorted(nombres)
    assert _funcion(corredor, "retencion_sobrantes", nombres) == []


def test_la_semana_va_de_lunes_a_domingo(corredor):
    # 2026-12-20 es domingo, 2026-12-21 es lunes: son semanas distintas. Con 1 diario y 2
    # semanales se conservan el ultimo del dia mas reciente (lunes 21... 27) y el domingo 20.
    nombres = [nombre(date(2026, 12, 20)), nombre(date(2026, 12, 21)), nombre(date(2026, 12, 14))]
    assert _conservar(corredor, nombres, diarios=1, semanales=2) == sorted(
        [nombre(date(2026, 12, 21)), nombre(date(2026, 12, 20))]
    )
    # El lunes 14 y el domingo 20 son la misma semana: queda solo el domingo (el mas reciente).
    nombres = [nombre(date(2026, 12, 14)), nombre(date(2026, 12, 20))]
    assert _conservar(corredor, nombres, diarios=1, semanales=1) == [nombre(date(2026, 12, 20))]


def test_un_nombre_que_es_diario_y_semanal_se_cuenta_una_vez(corredor):
    nombres = [nombre(d) for d in _dias(date(2026, 12, 25), date(2026, 12, 31))]
    conservados = _conservar(corredor, nombres, diarios=3, semanales=1)
    assert conservados == sorted(nombre(d) for d in _dias(date(2026, 12, 29), date(2026, 12, 31)))


def test_cantidades_configurables(corredor):
    nombres = [nombre(d) for d in _dias(date(2026, 12, 1), date(2026, 12, 31))]
    assert len(_conservar(corredor, nombres, diarios=5, semanales=1)) == 5
    assert (
        len(_conservar(corredor, nombres, diarios=2, semanales=3)) == 4
    )  # 2 diarios + 2 semanales extra


def test_nombres_sin_formato_se_ignoran(corredor):
    validos = [nombre(d) for d in _dias(date(2026, 12, 1), date(2026, 12, 3))]
    ajenos = [
        "restauracion-de-prueba.sql",
        "distribuidora-20260101-030000.dump.fallido",
        "distribuidora-20260101-030000.dump.tmp",
        "distribuidora-2026-01-01.dump",
        "notas.txt",
    ]
    assert _conservar(corredor, validos + ajenos, diarios=1, semanales=1) == [validos[-1]]


def test_sobrantes_son_los_validos_que_no_se_conservan(corredor):
    validos = [nombre(d) for d in _dias(date(2026, 12, 1), date(2026, 12, 3))]
    sobrantes = _funcion(corredor, "retencion_sobrantes", validos + ["notas.txt"], 1, 1)
    assert sobrantes == validos[:-1]
    assert datetime.strptime(sobrantes[0][14:22], "%Y%m%d")
