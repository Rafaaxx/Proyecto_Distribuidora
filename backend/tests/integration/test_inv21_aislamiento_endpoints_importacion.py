"""Change 10, tarea 4.4: cobertura de aislamiento (INV-21, SEG-07) de las tres rutas de
`importacion`:

- `POST /importaciones/{tipo}`: escribe solo en la organización del token;
- `GET /importaciones`: lista solo las importaciones de la organización del token;
- `GET /importaciones/plantillas/{tipo}`: no depende de ningún dato de organización.

Mismo arnés HTTP que `test_importacion_api.py` (PostgreSQL real, `login` real de dos
organizaciones, nunca un token fabricado): se reutilizan su `Entorno` y sus fixtures.
La organización nunca se indica en el archivo ni en la petición (INV-21, TR-08): una
columna `organizacion_id` se rechaza, y un nombre que existe en otra organización no
cuenta como duplicado (ni revela que exista).
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_importacion_api import (  # noqa: F401  (fixtures reutilizadas)
    MOMENTO,
    URL,
    Entorno,
    _archivo,
    _con_op,
    _contar,
    _csv,
    _limpiar_datos_confirmados,
    _nombres_de_proveedores,
    cliente,
    sesion,
)


def _dos_organizaciones(sesion: Session) -> tuple[Entorno, Entorno]:
    return Entorno(sesion, nombre_usuario="a1"), Entorno(sesion, nombre_usuario="b1")


def test_inv21_la_importacion_escribe_solo_en_la_organizacion_del_token(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/PROVEEDORES",
        files=_archivo(_csv("Bodega Sur,,,,", "Norte,,,,")),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 201, respuesta.text
    assert _nombres_de_proveedores(sesion, entorno_b.org) == ["Bodega Sur", "Norte"]
    assert _nombres_de_proveedores(sesion, entorno_a.org) == []
    assert _contar(sesion, "importacion", entorno_b.org) == 1
    assert _contar(sesion, "importacion", entorno_a.org) == 0


def test_inv21_un_nombre_que_existe_en_otra_organizacion_no_es_duplicado_ni_se_revela(
    cliente: TestClient, sesion: Session
) -> None:
    """Un proveedor "Bodega Sur" de A no hace fallar a B: para B es como si no
    existiera (mismo criterio que `REFERENCIA_NO_ENCONTRADA`, TR-08)."""
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_a = entorno_a.confirmar_y_entrar(cliente)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    datos = _csv("Bodega Sur,30-71234567-8,,,")

    de_a = cliente.post(f"{URL}/PROVEEDORES", files=_archivo(datos), headers=_con_op(headers_a))
    de_b = cliente.post(f"{URL}/PROVEEDORES", files=_archivo(datos), headers=_con_op(headers_b))

    assert (de_a.status_code, de_b.status_code) == (201, 201)
    assert _nombres_de_proveedores(sesion, entorno_a.org) == ["Bodega Sur"]
    assert _nombres_de_proveedores(sesion, entorno_b.org) == ["Bodega Sur"]


def test_inv21_el_operation_id_de_otra_organizacion_no_choca_ni_devuelve_su_resultado(
    cliente: TestClient, sesion: Session
) -> None:
    """La reserva de idempotencia es por organización: B reusando el `Operation-Id`
    de A importa lo suyo y no recibe el resultado de A."""
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_a = entorno_a.confirmar_y_entrar(cliente)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    operation_id = uuid4()

    de_a = cliente.post(
        f"{URL}/PROVEEDORES",
        files=_archivo(_csv("Bodega Sur,,,,")),
        headers=_con_op(headers_a, operation_id),
    )
    de_b = cliente.post(
        f"{URL}/PROVEEDORES",
        files=_archivo(_csv("Otra Bodega,,,,")),
        headers=_con_op(headers_b, operation_id),
    )

    assert (de_a.status_code, de_b.status_code) == (201, 201)
    assert de_a.json()["importacion_id"] != de_b.json()["importacion_id"]
    assert _nombres_de_proveedores(sesion, entorno_b.org) == ["Otra Bodega"]


def test_inv21_una_columna_de_organizacion_en_el_archivo_se_rechaza_y_no_cambia_el_destino(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.post(
        f"{URL}/PROVEEDORES",
        files=_archivo(_csv(f"Bodega Sur,{entorno_a.org}", encabezado="nombre,organizacion_id")),
        headers=_con_op(headers_b),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "COLUMNAS_INVALIDAS"
    assert _nombres_de_proveedores(sesion, entorno_a.org) == []
    assert _nombres_de_proveedores(sesion, entorno_b.org) == []


def test_inv21_el_historial_no_muestra_nada_de_otra_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    ajena = entorno_a.sembrar_importacion(registered_at=MOMENTO, archivo="secreto-de-a.csv")
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    respuesta = cliente.get(URL, headers=headers_b)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["items"], cuerpo["cursor_siguiente"]) == ([], None)
    assert str(ajena) not in respuesta.text
    assert "secreto-de-a.csv" not in respuesta.text


def test_inv21_un_cursor_de_otra_organizacion_no_filtra_su_historial(
    cliente: TestClient, sesion: Session
) -> None:
    """Un cursor armado con datos de A, usado por B, solo ordena lo de B."""
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    for n in range(3):
        entorno_a.sembrar_importacion(registered_at=MOMENTO, archivo=f"a{n}.csv")
    propia = entorno_b.sembrar_importacion(registered_at=MOMENTO, archivo="b.csv")
    headers_a = entorno_a.confirmar_y_entrar(cliente)
    headers_b = entorno_b.confirmar_y_entrar(cliente)
    cursor_de_a = cliente.get(URL, params={"limite": 1}, headers=headers_a).json()[
        "cursor_siguiente"
    ]

    respuesta = cliente.get(URL, params={"cursor": cursor_de_a}, headers=headers_b)

    assert respuesta.status_code == 200
    assert {i["id"] for i in respuesta.json()["items"]} <= {str(propia)}
    assert "a0.csv" not in respuesta.text


def test_inv21_la_plantilla_es_la_misma_para_toda_organizacion_y_no_trae_datos_propios(
    cliente: TestClient, sesion: Session
) -> None:
    entorno_a, entorno_b = _dos_organizaciones(sesion)
    entorno_a.sembrar_importacion(registered_at=MOMENTO)
    headers_a = entorno_a.confirmar_y_entrar(cliente)
    headers_b = entorno_b.confirmar_y_entrar(cliente)

    de_a = cliente.get(f"{URL}/plantillas/PROVEEDORES", headers=headers_a)
    de_b = cliente.get(f"{URL}/plantillas/PROVEEDORES", headers=headers_b)

    assert de_a.status_code == de_b.status_code == 200
    assert de_a.content == de_b.content
    assert de_a.content.decode("utf-8-sig") == "nombre;cuit;contacto;telefono;email\r\n"
