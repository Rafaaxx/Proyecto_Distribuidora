"""Tarea 4.3 (change 10): endpoints HTTP de `importacion`.

`POST /api/v1/importaciones/{tipo}` (multipart, con `Operation-Id`),
`GET /api/v1/importaciones` (historial paginado por cursor) y
`GET /api/v1/importaciones/plantillas/{tipo}` (CSV con solo el encabezado).

Mismo arnés HTTP que `test_stock_api.py`: PostgreSQL real, motor propio de la
aplicación y `login` real (nunca un access token fabricado).

Reglas citadas: CAT-01, INV-01, INV-06, INV-21, SEG-06, SYN-01, SYN-02, TR-07, TR-10 y
`design.md` D1, D2, D9, D11, D14. Escenarios de `specs/importacion/planillas` (formatos,
encabezados, límites, plantillas) y `registro-de-importaciones` (comando, informe,
idempotencia, historial).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from xml.sax.saxutils import escape

import pytest
from cuentas_corrientes_utiles import crear_organizacion
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository
from app.modules.importacion import repository as importacion_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-importacion-api"
URL = "/api/v1/importaciones"

ADMIN = frozenset({"IMPORTAR_DATOS"})
SIN_PERMISO = frozenset({"GESTIONAR_PROVEEDORES", "ADMIN_CONFIGURACION"})

ENCABEZADO = "nombre,cuit,contacto,telefono,email"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


class Entorno:
    """Una organización con su usuario y su dispositivo de siembra."""

    def __init__(
        self,
        sesion: Session,
        *,
        permisos: frozenset[str] = ADMIN,
        nombre_usuario: str = "admin1",
        nombre_para_mostrar: str = "Persona de prueba",
    ) -> None:
        self.sesion = sesion
        organizacion = crear_organizacion(sesion)
        self.org = organizacion.id
        self.slug = organizacion.slug
        self.nombre_usuario = nombre_usuario
        rol = identidad_repository.crear_rol(
            self.org,
            sesion,
            rol_id=nuevo_id(),
            nombre="Rol de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in permisos:
            identidad_repository.asignar_permiso_a_rol(
                self.org, sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        self.usuario_id = identidad_repository.crear_usuario(
            self.org,
            sesion,
            usuario_id=nuevo_id(),
            usuario=nombre_usuario,
            nombre=nombre_para_mostrar,
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        ).id
        self.dispositivo_id = identidad_repository.crear_dispositivo(
            self.org,
            sesion,
            dispositivo_id=nuevo_id(),
            nombre="Dispositivo de siembra",
            prefijo="S01",
            ultimo_correlativo=0,
            estado="ACTIVO",
            momento=MOMENTO,
        ).id

    def confirmar_y_entrar(self, cliente_http: TestClient) -> dict[str, str]:
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": self.nombre_usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def sembrar_importacion(
        self, *, registered_at: datetime, archivo: str = "semilla.csv", tipo: str = "PROVEEDORES"
    ) -> UUID:
        importacion = importacion_repository.crear_importacion(
            self.org,
            self.sesion,
            importacion_id=nuevo_id(),
            tipo=tipo,
            archivo_nombre=archivo,
            filas_total=3,
            filas_ok=3,
            operation_id=uuid4(),
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=registered_at,
            registered_at=registered_at,
        )
        return importacion.id


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _csv(*filas: str, encabezado: str = ENCABEZADO, separador: str = ",") -> bytes:
    lineas = [encabezado, *filas]
    return "\n".join(lineas).replace(",", separador).encode("utf-8")


def _archivo(
    contenido: bytes, nombre: str = "proveedores.csv"
) -> dict[str, tuple[str, bytes, str]]:
    return {"archivo": (nombre, contenido, "application/octet-stream")}


def _xlsx(filas: list[list[str]]) -> bytes:
    """Libro mínimo con cadenas en línea (las celdas numéricas y las fechas las cubre
    `test_importacion_lector_xlsx.py`)."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    xml_filas = ""
    for numero, celdas in enumerate(filas, start=1):
        xml_celdas = "".join(
            f'<c r="{chr(65 + i)}{numero}" t="inlineStr"><is><t>{escape(valor)}</t></is></c>'
            for i, valor in enumerate(celdas)
        )
        xml_filas += f'<row r="{numero}">{xml_celdas}</row>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{ns_rel}"><sheets>'
            '<sheet name="Datos" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetData>{xml_filas}</sheetData></worksheet>',
        )
    return buffer.getvalue()


def _nombres_de_proveedores(sesion: Session, organizacion_id: UUID) -> list[str]:
    sesion.rollback()
    return list(
        sesion.scalars(
            text("select nombre from proveedor where organizacion_id = :o order by nombre"),
            {"o": organizacion_id},
        )
    )


def _contar(sesion: Session, tabla: str, organizacion_id: UUID) -> int:
    sesion.rollback()
    return int(
        sesion.scalar(
            text(f"select count(*) from {tabla} where organizacion_id = :o"),  # noqa: S608
            {"o": organizacion_id},
        )
        or 0
    )


# ======================= POST /importaciones/{tipo} ==============================


class TestImportar:
    def test_dos_proveedores_en_csv_responde_201_y_crea_todo(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenarios "CSV en UTF-8 aceptado" e "Importación aceptada"."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)
        datos = _csv("Bodega Sur,30-71234567-8,Ana,,", "Cervecería Norte,,,,")

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(datos), headers=_con_op(headers)
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        assert set(cuerpo) == {"importacion_id", "filas_total", "filas_ok"}
        assert (cuerpo["filas_total"], cuerpo["filas_ok"]) == (2, 2)
        assert _nombres_de_proveedores(sesion, entorno.org) == ["Bodega Sur", "Cervecería Norte"]
        assert _contar(sesion, "importacion", entorno.org) == 1
        cuit = sesion.scalar(
            text("select cuit from proveedor where nombre = 'Bodega Sur' and organizacion_id = :o"),
            {"o": entorno.org},
        )
        assert cuit == "30712345678"

    def test_un_csv_de_excel_en_espanol_windows_1252_con_punto_y_coma_se_lee_bien(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "CSV guardado por Excel en español"."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)
        datos = "nombre;cuit\r\nCervecería Ñandú;\r\n".encode("cp1252")

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(datos), headers=_con_op(headers)
        )

        assert respuesta.status_code == 201, respuesta.text
        assert _nombres_de_proveedores(sesion, entorno.org) == ["Cervecería Ñandú"]

    def test_un_xlsx_se_lee_de_la_primera_hoja(self, cliente: TestClient, sesion: Session) -> None:
        """Escenario "Excel aceptado"."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)
        libro = _xlsx([["nombre", "cuit"], ["Bodega Sur", "30712345678"], ["Norte", ""]])

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(libro, "proveedores.xlsx"),
            headers=_con_op(headers),
        )

        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["filas_total"] == 2
        assert _nombres_de_proveedores(sesion, entorno.org) == ["Bodega Sur", "Norte"]

    def test_sin_operation_id_se_rechaza_sin_escribir_nada(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Sin Operation-Id" (SYN-01, TR-07). Es el rechazo común de toda
        escritura del bus (400 `OPERATION_ID_REQUERIDO`)."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(_csv("Bodega Sur,,,,")), headers=headers
        )

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
        assert _nombres_de_proveedores(sesion, entorno.org) == []

    def test_sin_importar_datos_responde_403_sin_efectos_ni_reserva(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Sin permiso": `GESTIONAR_PROVEEDORES` no alcanza."""
        entorno = Entorno(sesion, permisos=SIN_PERMISO)
        headers = entorno.confirmar_y_entrar(cliente)
        operation_id = uuid4()

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(_csv("Bodega Sur,,,,")),
            headers=_con_op(headers, operation_id),
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _nombres_de_proveedores(sesion, entorno.org) == []
        assert (
            sesion.scalar(
                text("select count(*) from comando where operation_id = :o"), {"o": operation_id}
            )
            == 0
        )

    def test_sin_sesion_responde_401(self, cliente: TestClient) -> None:
        respuesta = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(_csv("Bodega Sur,,,,")),
            headers={"Operation-Id": str(uuid4())},
        )

        assert respuesta.status_code == 401

    def test_sin_archivo_es_un_error_de_validacion_422(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.post(f"{URL}/PROVEEDORES", headers=_con_op(headers))

        assert respuesta.status_code == 422

    @pytest.mark.parametrize("tipo", ["PRECIOS", "VENTAS", "proveedores"])
    def test_un_tipo_sin_importador_responde_422_tipo_importacion_invalido(
        self, cliente: TestClient, sesion: Session, tipo: str
    ) -> None:
        """D9: `PRECIOS` y los tipos desconocidos (y los que todavía no tienen
        importador) se rechazan con 422 sin leer el archivo."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            f"{URL}/{tipo}", files=_archivo(_csv("Bodega Sur,,,,")), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "TIPO_IMPORTACION_INVALIDO"
        assert _contar(sesion, "importacion", entorno.org) == 0

    def test_el_informe_de_errores_trae_todos_los_errores_por_fila_y_no_crea_nada(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenarios "Una fila mala impide toda la importación" y "Error en la
        tercera fila de datos": 422 con Problem Details y `errores`."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)
        datos = _csv("Bodega Sur,,,,", "Norte,,,,", "Este,20-1234,,,", "bodega sur,,,,")

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(datos), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.headers["content-type"].startswith("application/problem+json")
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "IMPORTACION_CON_ERRORES"
        assert cuerpo["status"] == 422
        assert [(e["fila"], e["columna"], e["codigo"]) for e in cuerpo["errores"]] == [
            (4, "cuit", "CUIT_INVALIDO"),
            (5, "nombre", "FILA_DUPLICADA"),
        ]
        assert all(e["mensaje"] for e in cuerpo["errores"])
        assert _nombres_de_proveedores(sesion, entorno.org) == []
        assert _contar(sesion, "importacion", entorno.org) == 0

    def test_una_columna_obligatoria_faltante_se_rechaza_con_su_nombre(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Falta una columna obligatoria"."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(_csv("30712345678,", encabezado="cuit,contacto")),
            headers=_con_op(headers),
        )

        assert respuesta.status_code == 422
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "COLUMNAS_INVALIDAS"
        assert cuerpo["columnas_faltantes"] == ["nombre"]
        assert "nombre" in cuerpo["title"]

    def test_una_columna_de_organizacion_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Una columna de organización no se admite" (INV-21, TR-08)."""
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(_csv(f"A,{uuid4()}", encabezado="nombre,organizacion_id")),
            headers=_con_op(headers),
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "COLUMNAS_INVALIDAS"
        assert respuesta.json()["columnas_desconocidas"] == ["organizacion_id"]

    @pytest.mark.parametrize(
        ("nombre", "datos"),
        [
            ("informe.pdf", b"%PDF-1.7\n1 0 obj\n"),
            ("viejo.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 libro viejo"),
            ("vacio.csv", b""),
            ("roto.xlsx", b"PK\x03\x04 no es un zip"),
            ("sin_extension", b"nombre\nA\n"),
        ],
    )
    def test_un_formato_no_admitido_o_ilegible_es_archivo_invalido(
        self, cliente: TestClient, sesion: Session, nombre: str, datos: bytes
    ) -> None:
        """Escenario "Formato no admitido" (INV-01)."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(datos, nombre), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "ARCHIVO_INVALIDO"
        assert _contar(sesion, "importacion", entorno.org) == 0

    def test_un_archivo_con_solo_el_encabezado_es_archivo_sin_filas(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(_csv()), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "ARCHIVO_SIN_FILAS"

    def test_el_limite_de_filas_se_acepta_y_una_mas_se_rechaza(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Archivo con demasiadas filas" (D11: 2.000 filas) y `design.md`
        D11 / tarea 10.3 (el tiempo de 2.000 filas lo mide el grupo 10)."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)
        filas = [f"Proveedor {n},,,," for n in range(2001)]

        demasiadas = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(_csv(*filas)), headers=_con_op(headers)
        )
        assert demasiadas.status_code == 422
        assert demasiadas.json()["codigo"] == "ARCHIVO_DEMASIADO_GRANDE"
        assert _nombres_de_proveedores(sesion, entorno.org) == []

        en_el_limite = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(_csv(*filas[:2000])), headers=_con_op(headers)
        )
        assert en_el_limite.status_code == 201, en_el_limite.text
        assert en_el_limite.json()["filas_total"] == 2000

    def test_un_archivo_de_mas_de_5_mb_se_rechaza_sin_leerlo_entero(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)
        enorme = b"nombre\n" + b"A" * (5 * 1024 * 1024 + 1)

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(enorme), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "ARCHIVO_DEMASIADO_GRANDE"

    def test_el_doble_envio_con_el_mismo_operation_id_devuelve_lo_mismo_sin_duplicar(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenarios "Doble envío" y "Mismo Operation-Id con otro archivo" (INV-06,
        SYN-02)."""
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)
        operation_id = uuid4()
        datos = _csv("Bodega Sur,,,,", "Norte,,,,")

        primero = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(datos), headers=_con_op(headers, operation_id)
        )
        segundo = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(datos), headers=_con_op(headers, operation_id)
        )
        otro_archivo = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(_csv("Otra,,,,")),
            headers=_con_op(headers, operation_id),
        )

        assert primero.status_code == 201 and segundo.status_code == 201
        assert primero.json() == segundo.json()
        assert otro_archivo.status_code == 409
        assert otro_archivo.json()["codigo"] == "COMANDO_INCONSISTENTE"
        assert _nombres_de_proveedores(sesion, entorno.org) == ["Bodega Sur", "Norte"]
        assert _contar(sesion, "importacion", entorno.org) == 1

    def test_la_misma_planilla_con_otro_nombre_de_archivo_con_el_mismo_operation_id_es_distinta(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """El nombre de archivo es parte del contenido del comando (huella)."""
        headers = Entorno(sesion).confirmar_y_entrar(cliente)
        operation_id = uuid4()
        datos = _csv("Bodega Sur,,,,")
        cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(datos, "a.csv"),
            headers=_con_op(headers, operation_id),
        )

        otra = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(datos, "b.csv"),
            headers=_con_op(headers, operation_id),
        )

        assert otra.status_code == 409

    def test_el_nombre_del_archivo_se_guarda_sin_la_ruta(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)

        cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(_csv("Bodega Sur,,,,"), "C:\\fakepath\\mis proveedores.csv"),
            headers=_con_op(headers),
        )

        assert (
            sesion.scalar(
                text("select archivo_nombre from importacion where organizacion_id = :o"),
                {"o": entorno.org},
            )
            == "mis proveedores.csv"
        )


# ======================= GET /importaciones (historial) ===========================


class TestHistorial:
    def test_lista_de_la_mas_reciente_a_la_mas_antigua_con_usuario_y_filas(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Ver el historial" (D14, `02` §11)."""
        entorno = Entorno(sesion, nombre_para_mostrar="Ana Admin")
        viejo = entorno.sembrar_importacion(registered_at=MOMENTO, archivo="viejo.csv")
        nuevo = entorno.sembrar_importacion(
            registered_at=MOMENTO + timedelta(days=1), archivo="nuevo.csv", tipo="CLIENTES"
        )
        headers = entorno.confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL, headers=headers)

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert [i["id"] for i in cuerpo["items"]] == [str(nuevo), str(viejo)]
        assert cuerpo["cursor_siguiente"] is None
        primero = cuerpo["items"][0]
        assert primero["tipo"] == "CLIENTES"
        assert primero["archivo_nombre"] == "nuevo.csv"
        assert primero["estado"] == "CONFIRMADA"
        assert (primero["filas_total"], primero["filas_ok"], primero["filas_error"]) == (3, 3, 0)
        assert primero["usuario_id"] == str(entorno.usuario_id)
        assert primero["usuario_nombre"] == "Ana Admin"
        assert datetime.fromisoformat(primero["registered_at"]) == MOMENTO + timedelta(days=1)
        # TR-04: la pantalla muestra la fecha en la zona de la organización.
        assert cuerpo["zona_horaria"] == "America/Argentina/Mendoza"

    def test_pagina_por_cursor_sin_repetir_ni_saltear(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        ids = [
            entorno.sembrar_importacion(registered_at=MOMENTO + timedelta(hours=n))
            for n in range(5)
        ]
        headers = entorno.confirmar_y_entrar(cliente)

        vistos: list[str] = []
        cursor: str | None = None
        paginas = 0
        while True:
            parametros: dict[str, str | int] = {"limite": 2}
            if cursor is not None:
                parametros["cursor"] = cursor
            cuerpo = cliente.get(URL, params=parametros, headers=headers).json()
            vistos.extend(i["id"] for i in cuerpo["items"])
            paginas += 1
            cursor = cuerpo["cursor_siguiente"]
            if cursor is None:
                break

        assert vistos == [str(i) for i in reversed(ids)]
        assert paginas == 3

    def test_con_el_mismo_momento_el_id_desempata_y_el_cursor_no_pierde_filas(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        ids = [entorno.sembrar_importacion(registered_at=MOMENTO) for _ in range(3)]
        headers = entorno.confirmar_y_entrar(cliente)

        primera = cliente.get(URL, params={"limite": 2}, headers=headers).json()
        segunda = cliente.get(
            URL, params={"limite": 2, "cursor": primera["cursor_siguiente"]}, headers=headers
        ).json()

        vistos = [i["id"] for i in primera["items"] + segunda["items"]]
        assert vistos == [str(i) for i in sorted(ids, reverse=True)]
        assert segunda["cursor_siguiente"] is None

    @pytest.mark.parametrize("limite", [0, 201, -1])
    def test_un_limite_fuera_de_1_a_200_es_error_de_validacion(
        self, cliente: TestClient, sesion: Session, limite: int
    ) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL, params={"limite": limite}, headers=headers)

        assert respuesta.status_code == 422

    def test_el_limite_maximo_se_acepta(self, cliente: TestClient, sesion: Session) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        assert cliente.get(URL, params={"limite": 200}, headers=headers).status_code == 200

    def test_un_cursor_ilegible_es_422_cursor_invalido(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL, params={"cursor": "basura"}, headers=headers)

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "CURSOR_INVALIDO"

    def test_inv21_no_muestra_las_importaciones_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Ver el historial": dos en la organización, una en otra."""
        entorno = Entorno(sesion)
        propias = {
            entorno.sembrar_importacion(registered_at=MOMENTO),
            entorno.sembrar_importacion(registered_at=MOMENTO + timedelta(days=1)),
        }
        otra = Entorno(sesion, nombre_usuario="otro1")
        ajena = otra.sembrar_importacion(registered_at=MOMENTO + timedelta(days=2))
        headers = entorno.confirmar_y_entrar(cliente)

        ids = {i["id"] for i in cliente.get(URL, headers=headers).json()["items"]}

        assert ids == {str(i) for i in propias}
        assert str(ajena) not in ids

    def test_sin_importar_datos_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        """Escenario "Historial sin permiso"."""
        headers = Entorno(sesion, permisos=SIN_PERMISO).confirmar_y_entrar(cliente)

        respuesta = cliente.get(URL, headers=headers)

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"

    def test_la_importacion_hecha_por_http_aparece_en_el_historial(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.confirmar_y_entrar(cliente)
        creada = cliente.post(
            f"{URL}/PROVEEDORES",
            files=_archivo(_csv("Bodega Sur,,,,"), "proveedores.csv"),
            headers=_con_op(headers),
        ).json()

        (item,) = cliente.get(URL, headers=headers).json()["items"]

        assert item["id"] == creada["importacion_id"]
        assert item["archivo_nombre"] == "proveedores.csv"


# ======================= GET /importaciones/plantillas/{tipo} =====================


class TestPlantillas:
    def test_la_plantilla_de_proveedores_es_un_csv_con_solo_el_encabezado(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario "Descargar la plantilla de productos", con proveedores."""
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.get(f"{URL}/plantillas/PROVEEDORES", headers=headers)

        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("text/csv")
        assert "plantilla-proveedores.csv" in respuesta.headers["content-disposition"]
        # UTF-8 con BOM y `;`: así la abre Excel en español sin romper las columnas.
        assert respuesta.content.decode("utf-8-sig") == "nombre;cuit;contacto;telefono;email\r\n"

    def test_la_plantilla_de_productos_trae_las_columnas_de_d5(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.get(f"{URL}/plantillas/PRODUCTOS", headers=headers)

        assert respuesta.status_code == 200
        assert respuesta.content.decode("utf-8-sig").strip().split(";") == [
            "codigo",
            "nombre",
            "categoria",
            "marca",
            "proveedor",
            "unidad_base",
            "alicuota",
            "presentacion",
            "unidades_base",
            "usar_en_venta",
            "usar_en_compra",
            "es_referencia",
        ]

    def test_la_plantilla_descargada_se_importa_sin_errores_de_columnas(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """ "La plantilla DEBE poder importarse sin errores de columnas": solo falla
        por no tener filas de datos."""
        headers = Entorno(sesion).confirmar_y_entrar(cliente)
        plantilla = cliente.get(f"{URL}/plantillas/PROVEEDORES", headers=headers).content

        respuesta = cliente.post(
            f"{URL}/PROVEEDORES", files=_archivo(plantilla), headers=_con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "ARCHIVO_SIN_FILAS"

    @pytest.mark.parametrize("tipo", ["PRECIOS", "VENTAS", "proveedores"])
    def test_un_tipo_sin_plantilla_es_422(
        self, cliente: TestClient, sesion: Session, tipo: str
    ) -> None:
        headers = Entorno(sesion).confirmar_y_entrar(cliente)

        respuesta = cliente.get(f"{URL}/plantillas/{tipo}", headers=headers)

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "TIPO_IMPORTACION_INVALIDO"

    def test_sin_importar_datos_responde_403(self, cliente: TestClient, sesion: Session) -> None:
        """Escenario "Plantilla sin permiso"."""
        headers = Entorno(sesion, permisos=SIN_PERMISO).confirmar_y_entrar(cliente)

        respuesta = cliente.get(f"{URL}/plantillas/PROVEEDORES", headers=headers)

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
