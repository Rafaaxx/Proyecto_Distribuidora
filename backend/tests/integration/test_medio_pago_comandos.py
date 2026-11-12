"""Tareas 4.1 a 4.3 (change 17b; `design.md` D1, D2, D3, D4, D11): `MEDIO_PAGO_CREAR` y
`MEDIO_PAGO_MODIFICAR` por `POST` y `PUT /api/v1/configuracion/medios-pago`.

Mismo arnés que `test_cobranzas_api.py`: PostgreSQL real, motor propio de la aplicación y
`login` real. Reglas citadas: TR-09, TR-06, TR-08, CAT-05, COB-02, PAG-01, INV-02, INV-06,
INV-21, SEG-06 y ADR-053.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import medios_pago_utiles as utiles
import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from medios_pago_utiles import (
    URL_COBRANZAS,
    URL_MEDIOS,
    URL_PAGOS,
    Entorno,
    con_op,
)
from sqlalchemy.orm import Session

from app.core.clock import FixedClock
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

# Las fixtures viven en `medios_pago_utiles.py`; se enlazan por asignación (no por `import`) para
# que pytest las encuentre sin que `ruff` las vea como redefiniciones.
_limpiar_datos_confirmados = utiles._limpiar_datos_confirmados
cliente_http = utiles.cliente_http
sesion = utiles.sesion


def _cuerpo(**cambios: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {"nombre": "Mercado Pago", "requiere_referencia": True}
    cuerpo.update(cambios)
    return cuerpo


def _modificar(entorno: Entorno, actual: str, **cambios: object) -> tuple[str, dict[str, object]]:
    """URL y cuerpo completo del `PUT` de un medio sembrado: parte de su estado actual."""
    fila = next(f for f in entorno.filas_de_medio() if f["nombre"] == actual)
    cuerpo: dict[str, object] = {
        "nombre": fila["nombre"],
        "requiere_referencia": fila["requiere_referencia"],
        "activo": fila["activo"],
    }
    cuerpo.update(cambios)
    return f"{URL_MEDIOS}/{fila['id']}", cuerpo


# ======================= MEDIO_PAGO_CREAR (4.1) ======================================


class TestMedioPagoCrear:
    def test_crea_un_medio_activo_con_el_nombre_recortado_y_lo_devuelve(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MEDIOS, json=_cuerpo(nombre="  Mercado Pago "), headers=con_op(headers)
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        UUID(cuerpo["id"])
        assert cuerpo["nombre"] == "Mercado Pago"
        assert (cuerpo["requiere_referencia"], cuerpo["activo"]) == (True, True)
        assert cuerpo["actualizado_en"]
        assert "organizacion_id" not in cuerpo
        assert [f["nombre"] for f in entorno.filas_de_medio()].count("Mercado Pago") == 1

    def test_un_medio_sin_referencia_se_guarda_sin_referencia(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MEDIOS,
            json=_cuerpo(nombre="Vale", requiere_referencia=False),
            headers=con_op(headers),
        )

        assert respuesta.status_code == 201
        assert respuesta.json()["requiere_referencia"] is False

    @pytest.mark.parametrize("nombre", ["", "   ", "\t"])
    def test_un_nombre_vacio_es_nombre_invalido_422(
        self, cliente_http: TestClient, sesion: Session, nombre: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MEDIOS, json=_cuerpo(nombre=nombre), headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "NOMBRE_INVALIDO"
        assert len(entorno.filas_de_medio()) == 5

    @pytest.mark.parametrize("repetido", ["Billetera", "billetera", " BILLETERA "])
    def test_un_nombre_repetido_es_409_sin_distinguir_mayusculas(
        self, cliente_http: TestClient, sesion: Session, repetido: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MEDIOS, json=_cuerpo(nombre=repetido), headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"
        assert len(entorno.filas_de_medio()) == 5

    def test_un_nombre_repetido_tambien_contra_un_medio_de_baja(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        entorno.dar_de_baja_en_sql("Billetera")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MEDIOS, json=_cuerpo(nombre="billetera"), headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"

    def test_el_mismo_nombre_en_otra_organizacion_se_acepta(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        una = Entorno(sesion)
        otra = Entorno(sesion)
        headers_una = una.entrar(cliente_http)
        headers_otra = otra.entrar(cliente_http)

        de_una = cliente_http.post(
            URL_MEDIOS, json=_cuerpo(nombre="Mercado Pago"), headers=con_op(headers_una)
        )
        de_otra = cliente_http.post(
            URL_MEDIOS, json=_cuerpo(nombre="Mercado Pago"), headers=con_op(headers_otra)
        )

        assert de_una.status_code == de_otra.status_code == 201
        assert de_una.json()["id"] != de_otra.json()["id"]

    def test_sin_admin_configuracion_responde_403_sin_efectos_ni_reserva(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http, "cobrador1")
        operation_id = uuid4()

        respuesta = cliente_http.post(
            URL_MEDIOS, json=_cuerpo(), headers=con_op(headers, operation_id)
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert len(entorno.filas_de_medio()) == 5
        assert entorno.contar_comandos("MEDIO_PAGO_CREAR") == 0

    def test_sin_operation_id_se_rechaza_con_400(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(URL_MEDIOS, json=_cuerpo(), headers=headers)

        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"

    def test_reenviar_el_mismo_operation_id_no_duplica(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # INV-06: el doble envío devuelve el mismo resultado y deja una sola fila.
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))

        primera = cliente_http.post(URL_MEDIOS, json=_cuerpo(), headers=headers)
        segunda = cliente_http.post(URL_MEDIOS, json=_cuerpo(), headers=headers)

        assert primera.status_code == segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]
        assert [f["nombre"] for f in entorno.filas_de_medio()].count("Mercado Pago") == 1
        assert len(entorno.auditoria_de("MEDIO_PAGO_CREAR")) == 1

    def test_el_mismo_operation_id_con_otro_contenido_es_comando_inconsistente(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))
        cliente_http.post(URL_MEDIOS, json=_cuerpo(), headers=headers)

        segunda = cliente_http.post(URL_MEDIOS, json=_cuerpo(nombre="Otro"), headers=headers)

        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "COMANDO_INCONSISTENTE"

    @pytest.mark.parametrize(
        "cambios",
        [{"organizacion_id": str(uuid4())}, {"activo": False}, {"nombre": 7}],
    )
    def test_un_cuerpo_malformado_se_rechaza_con_422(
        self, cliente_http: TestClient, sesion: Session, cambios: dict[str, object]
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(URL_MEDIOS, json=_cuerpo(**cambios), headers=con_op(headers))

        assert respuesta.status_code == 422
        assert len(entorno.filas_de_medio()) == 5

    def test_deja_una_fila_de_auditoria_con_el_estado_despues(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # D11, AUD-01: "cambios de configuración" con `despues`.
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))

        creado = cliente_http.post(URL_MEDIOS, json=_cuerpo(), headers=headers).json()

        filas = entorno.auditoria_de("MEDIO_PAGO_CREAR")
        assert len(filas) == 1
        fila = filas[0]
        assert fila["entidad"] == "medio_pago"
        assert str(fila["entidad_id"]) == creado["id"]
        assert fila["antes"] is None
        assert fila["despues"] == {
            "nombre": "Mercado Pago",
            "requiere_referencia": True,
            "activo": True,
        }
        assert fila["usuario_id"] == entorno.usuarios["admin1"]
        assert str(fila["operation_id"]) == headers["Operation-Id"]
        assert fila["origen"] == "COMANDO"


# ======================= MEDIO_PAGO_MODIFICAR (4.2) ==================================


class TestMedioPagoModificar:
    def test_renombra_un_medio_y_devuelve_el_estado_nuevo(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)
        url, cuerpo = _modificar(entorno, "Billetera", nombre="  Mercado Pago ")

        respuesta = cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["nombre"] == "Mercado Pago"
        nombres = [f["nombre"] for f in entorno.filas_de_medio()]
        assert "Mercado Pago" in nombres
        assert "Billetera" not in nombres

    def test_renombrar_a_un_nombre_ajeno_es_nombre_duplicado_409(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)
        url, cuerpo = _modificar(entorno, "Billetera", nombre="CHEQUE")

        respuesta = cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"
        assert "Billetera" in [f["nombre"] for f in entorno.filas_de_medio()]

    def test_cambiar_solo_las_mayusculas_del_propio_nombre_se_acepta(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)
        url, cuerpo = _modificar(entorno, "Billetera", nombre="BILLETERA")

        respuesta = cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert respuesta.status_code == 200
        assert respuesta.json()["nombre"] == "BILLETERA"

    def test_nombre_vacio_es_nombre_invalido_422(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)
        url, cuerpo = _modificar(entorno, "Billetera", nombre="  ")

        respuesta = cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "NOMBRE_INVALIDO"

    def test_marcar_referencia_hace_que_una_cobranza_con_conexion_sin_referencia_se_rechace(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # COB-02: Billetera nace sin referencia; al marcarla, cobrar sin número se rechaza.
        entorno = Entorno(sesion)
        admin = entorno.entrar(cliente_http)
        cobrador = entorno.entrar(cliente_http, "cobrador1")
        antes = cliente_http.post(
            URL_COBRANZAS, json=entorno.cuerpo_cobranza("Billetera"), headers=con_op(cobrador)
        )
        assert antes.status_code == 201
        url, cuerpo = _modificar(entorno, "Billetera", requiere_referencia=True)
        assert cliente_http.put(url, json=cuerpo, headers=con_op(admin)).status_code == 200

        sin_numero = cliente_http.post(
            URL_COBRANZAS, json=entorno.cuerpo_cobranza("Billetera"), headers=con_op(cobrador)
        )
        con_numero = cliente_http.post(
            URL_COBRANZAS,
            json=entorno.cuerpo_cobranza("Billetera", referencia="MP-0042"),
            headers=con_op(cobrador),
        )

        assert sin_numero.status_code == 422
        assert sin_numero.json()["codigo"] == "REFERENCIA_OBLIGATORIA"
        assert con_numero.status_code == 201

    def test_cobranza_por_transferencia_sin_referencia_se_rechaza_y_con_referencia_se_acepta(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # Escenario "Cobranza con transferencia después de la migración" (COB-02, D5-A): la
        # Transferencia, que pide referencia de origen, se comporta como cualquier medio marcado.
        entorno = Entorno(sesion)
        cobrador = entorno.entrar(cliente_http, "cobrador1")

        sin_numero = cliente_http.post(
            URL_COBRANZAS, json=entorno.cuerpo_cobranza("Transferencia"), headers=con_op(cobrador)
        )
        con_numero = cliente_http.post(
            URL_COBRANZAS,
            json=entorno.cuerpo_cobranza("Transferencia", referencia="0042"),
            headers=con_op(cobrador),
        )

        assert sin_numero.status_code == 422
        assert sin_numero.json()["codigo"] == "REFERENCIA_OBLIGATORIA"
        assert con_numero.status_code == 201

    def test_marcar_referencia_hace_que_un_pago_con_conexion_sin_referencia_se_rechace(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # PAG-01: la misma regla en el pago a proveedor.
        entorno = Entorno(sesion)
        admin = entorno.entrar(cliente_http)
        cobrador = entorno.entrar(cliente_http, "cobrador1")
        url, cuerpo = _modificar(entorno, "Efectivo", requiere_referencia=True)
        assert cliente_http.put(url, json=cuerpo, headers=con_op(admin)).status_code == 200

        respuesta = cliente_http.post(
            URL_PAGOS, json=entorno.cuerpo_pago("Efectivo"), headers=con_op(cobrador)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "REFERENCIA_OBLIGATORIA"

    def test_la_baja_saca_el_medio_del_listado_pero_sigue_legible_en_la_cobranza_que_lo_uso(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # CAT-05, TR-06: no se borra; lo viejo lo sigue mostrando.
        entorno = Entorno(sesion)
        admin = entorno.entrar(cliente_http)
        cobrador = entorno.entrar(cliente_http, "cobrador1")
        cuerpo_cobranza = entorno.cuerpo_cobranza("Billetera")
        creada = cliente_http.post(URL_COBRANZAS, json=cuerpo_cobranza, headers=con_op(cobrador))
        assert creada.status_code == 201
        cobranza_id = cuerpo_cobranza["cobranza_id"]
        url, cuerpo = _modificar(entorno, "Billetera", activo=False)

        baja = cliente_http.put(url, json=cuerpo, headers=con_op(admin))

        assert baja.status_code == 200
        assert baja.json()["activo"] is False
        activos = cliente_http.get(URL_MEDIOS, headers=admin).json()["items"]
        assert "Billetera" not in [m["nombre"] for m in activos]
        detalle = cliente_http.get(f"{URL_COBRANZAS}/{cobranza_id}", headers=cobrador)
        assert detalle.status_code == 200
        assert [m["medio_nombre"] for m in detalle.json()["medios"]] == ["Billetera"]
        assert "Billetera" in [f["nombre"] for f in entorno.filas_de_medio()]

    def test_la_baja_deja_legible_el_medio_en_el_detalle_del_pago_a_proveedor_que_lo_uso(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # CAT-05, TR-06, PAG-01: lo mismo que la cobranza, ahora en el pago.
        entorno = Entorno(sesion)
        admin = entorno.entrar(cliente_http)
        cobrador = entorno.entrar(cliente_http, "cobrador1")
        creado = cliente_http.post(
            URL_PAGOS, json=entorno.cuerpo_pago("Billetera"), headers=con_op(cobrador)
        )
        assert creado.status_code == 201
        pago_id = creado.json()["pago_id"]
        url, cuerpo = _modificar(entorno, "Billetera", activo=False)

        baja = cliente_http.put(url, json=cuerpo, headers=con_op(admin))

        assert baja.status_code == 200
        detalle = cliente_http.get(f"{URL_PAGOS}/{pago_id}", headers=cobrador)
        assert detalle.status_code == 200
        assert [m["medio_nombre"] for m in detalle.json()["medios"]] == ["Billetera"]

    def test_renombrar_y_dar_de_baja_a_la_vez_se_ve_con_el_nombre_nuevo_en_el_detalle_del_pago(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # Triangula: el pago guarda el id, así que un renombre se ve en el detalle (D2).
        entorno = Entorno(sesion)
        admin = entorno.entrar(cliente_http)
        cobrador = entorno.entrar(cliente_http, "cobrador1")
        creado = cliente_http.post(
            URL_PAGOS, json=entorno.cuerpo_pago("Efectivo"), headers=con_op(cobrador)
        )
        assert creado.status_code == 201
        url, cuerpo = _modificar(entorno, "Efectivo", nombre="Caja chica", activo=False)

        assert cliente_http.put(url, json=cuerpo, headers=con_op(admin)).status_code == 200

        detalle = cliente_http.get(f"{URL_PAGOS}/{creado.json()['pago_id']}", headers=cobrador)
        assert [m["medio_nombre"] for m in detalle.json()["medios"]] == ["Caja chica"]

    def test_una_cobranza_nueva_con_conexion_con_un_medio_de_baja_responde_medio_pago_inactivo(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        admin = entorno.entrar(cliente_http)
        cobrador = entorno.entrar(cliente_http, "cobrador1")
        url, cuerpo = _modificar(entorno, "Billetera", activo=False)
        assert cliente_http.put(url, json=cuerpo, headers=con_op(admin)).status_code == 200

        respuesta = cliente_http.post(
            URL_COBRANZAS, json=entorno.cuerpo_cobranza("Billetera"), headers=con_op(cobrador)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "MEDIO_PAGO_INACTIVO"

    def test_un_pago_nuevo_con_conexion_con_un_medio_de_baja_responde_medio_pago_inactivo(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        admin = entorno.entrar(cliente_http)
        cobrador = entorno.entrar(cliente_http, "cobrador1")
        url, cuerpo = _modificar(entorno, "Billetera", activo=False)
        assert cliente_http.put(url, json=cuerpo, headers=con_op(admin)).status_code == 200

        respuesta = cliente_http.post(
            URL_PAGOS, json=entorno.cuerpo_pago("Billetera"), headers=con_op(cobrador)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "MEDIO_PAGO_INACTIVO"

    def test_reactivar_un_medio_lo_vuelve_a_ofrecer(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        entorno.dar_de_baja_en_sql("Billetera")
        headers = entorno.entrar(cliente_http)
        url, cuerpo = _modificar(entorno, "Billetera", activo=True)

        respuesta = cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert respuesta.status_code == 200
        assert respuesta.json()["activo"] is True
        activos = cliente_http.get(URL_MEDIOS, headers=headers).json()["items"]
        assert "Billetera" in [m["nombre"] for m in activos]

    def test_no_se_puede_dar_de_baja_el_ultimo_medio_activo(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # D4: ULTIMO_MEDIO_ACTIVO (409); el medio queda como estaba.
        entorno = Entorno(sesion)
        entorno.dar_de_baja_en_sql("Transferencia", "Cheque", "Billetera", "Tarjeta")
        headers = entorno.entrar(cliente_http)
        url, cuerpo = _modificar(entorno, "Efectivo", activo=False)

        respuesta = cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "ULTIMO_MEDIO_ACTIVO"
        efectivo = next(f for f in entorno.filas_de_medio() if f["nombre"] == "Efectivo")
        assert efectivo["activo"] is True

    def test_con_dos_activos_se_puede_dar_de_baja_uno_y_el_siguiente_es_el_ultimo(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        entorno.dar_de_baja_en_sql("Cheque", "Billetera", "Tarjeta")
        headers = entorno.entrar(cliente_http)
        url_tr, cuerpo_tr = _modificar(entorno, "Transferencia", activo=False)
        url_ef, cuerpo_ef = _modificar(entorno, "Efectivo", activo=False)

        primera = cliente_http.put(url_tr, json=cuerpo_tr, headers=con_op(headers))
        segunda = cliente_http.put(url_ef, json=cuerpo_ef, headers=con_op(headers))

        assert primera.status_code == 200
        assert segunda.status_code == 409
        assert segunda.json()["codigo"] == "ULTIMO_MEDIO_ACTIVO"

    def test_un_medio_de_otra_organizacion_o_inexistente_responde_404(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # INV-21: un recurso ajeno responde 404, no 403.
        propia = Entorno(sesion)
        ajena = Entorno(sesion)
        headers = propia.entrar(cliente_http)
        url_ajena, cuerpo = _modificar(ajena, "Billetera", nombre="Hackeado")

        de_otra = cliente_http.put(url_ajena, json=cuerpo, headers=con_op(headers))
        inexistente = cliente_http.put(
            f"{URL_MEDIOS}/{uuid4()}", json=cuerpo, headers=con_op(headers)
        )

        assert de_otra.status_code == 404
        assert inexistente.status_code == 404
        assert "Billetera" in [f["nombre"] for f in ajena.filas_de_medio()]

    def test_sin_admin_configuracion_responde_403(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http, "nadie1")
        url, cuerpo = _modificar(entorno, "Billetera", nombre="Otro")

        respuesta = cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert "Billetera" in [f["nombre"] for f in entorno.filas_de_medio()]

    def test_reenviar_el_mismo_operation_id_responde_igual_y_audita_una_sola_vez(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))
        url, cuerpo = _modificar(entorno, "Billetera", nombre="Mercado Pago")

        primera = cliente_http.put(url, json=cuerpo, headers=headers)
        segunda = cliente_http.put(url, json=cuerpo, headers=headers)

        assert primera.status_code == segunda.status_code == 200
        assert primera.json() == segunda.json()
        assert len(entorno.auditoria_de("MEDIO_PAGO_MODIFICAR")) == 1

    def test_deja_una_fila_de_auditoria_con_antes_y_despues(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # D11, AUD-01.
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))
        url, cuerpo = _modificar(
            entorno, "Billetera", nombre="Mercado Pago", requiere_referencia=True, activo=False
        )

        respuesta = cliente_http.put(url, json=cuerpo, headers=headers)

        assert respuesta.status_code == 200
        filas = entorno.auditoria_de("MEDIO_PAGO_MODIFICAR")
        assert len(filas) == 1
        assert filas[0]["entidad"] == "medio_pago"
        assert filas[0]["antes"] == {
            "nombre": "Billetera",
            "requiere_referencia": False,
            "activo": True,
        }
        assert filas[0]["despues"] == {
            "nombre": "Mercado Pago",
            "requiere_referencia": True,
            "activo": False,
        }

    def test_un_rechazo_por_ultimo_medio_activo_no_cambia_nada(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        entorno.dar_de_baja_en_sql("Transferencia", "Cheque", "Billetera", "Tarjeta")
        headers = entorno.entrar(cliente_http)
        url, cuerpo = _modificar(entorno, "Efectivo", activo=False, nombre="Otro")

        cliente_http.put(url, json=cuerpo, headers=con_op(headers))

        assert entorno.auditoria_de("MEDIO_PAGO_MODIFICAR") == []
        assert "Efectivo" in [f["nombre"] for f in entorno.filas_de_medio()]

    def test_un_cuerpo_incompleto_se_rechaza_con_422(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # D2: reemplazo completo, sin `PATCH` parcial.
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)
        url, _ = _modificar(entorno, "Billetera")

        respuesta = cliente_http.put(url, json={"nombre": "Otro"}, headers=con_op(headers))

        assert respuesta.status_code == 422


# ======================= nadie borra medios (4.3) ===================================


def test_no_existe_ninguna_ruta_que_borre_medios(cliente_http: TestClient, sesion: Session) -> None:
    # TR-06, CAT-05: ni `DELETE` ni `PATCH` sobre un medio.
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)
    url, _ = _modificar(entorno, "Billetera")

    assert cliente_http.delete(url, headers=con_op(headers)).status_code == 405
    assert cliente_http.delete(URL_MEDIOS, headers=con_op(headers)).status_code == 405
    assert len(entorno.filas_de_medio()) == 5


# ======================= catálogo y lote del bus (4.3) ===============================


@pytest.mark.parametrize("tipo", ["MEDIO_PAGO_CREAR", "MEDIO_PAGO_MODIFICAR"])
def test_los_dos_tipos_estan_declarados_solo_online(tipo: str) -> None:
    # `02` §6.5: un maestro de configuración no se escribe sin conexión.
    import app.main  # noqa: F401  (puebla el catálogo real)
    from app.commands.catalogo import tipo_declarado

    declarado = tipo_declarado(tipo)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)


def _item_de_lote(
    entorno: Entorno, tipo: str, modo: str, contenido: dict[str, object]
) -> tuple[ItemLote, UUID, UUID]:

    usuario_id, dispositivo_id = _usuario_con_dispositivo(entorno)
    return (
        ItemLote(
            operation_id=uuid4(),
            tipo=tipo,
            version=1,
            modo=modo,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=MOMENTO_LOTE,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,  # type: ignore[arg-type]
        ),
        usuario_id,
        dispositivo_id,
    )


def _usuario_con_dispositivo(entorno: Entorno) -> tuple[UUID, UUID]:
    resultado = crear_usuario_y_dispositivo(
        entorno.sesion, entorno.org, permisos=frozenset({"ADMIN_CONFIGURACION"})
    )
    entorno.sesion.commit()
    return resultado


MOMENTO_LOTE = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("tipo", ["MEDIO_PAGO_CREAR", "MEDIO_PAGO_MODIFICAR"])
def test_el_lote_rechaza_los_comandos_de_medios_enviados_sin_conexion(
    sesion: Session, tipo: str
) -> None:
    entorno = Entorno(sesion)
    contenido: dict[str, object] = {"nombre": "Mercado Pago", "requiere_referencia": True}
    item, usuario_id, dispositivo_id = _item_de_lote(entorno, tipo, "OFFLINE", contenido)

    (resultado,) = sync_service.procesar_lote(
        sesion,
        FixedClock(MOMENTO_LOTE),
        organizacion_id=entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert len(entorno.filas_de_medio()) == 5


def test_por_el_lote_en_modo_online_se_comporta_igual_que_por_rest(sesion: Session) -> None:
    entorno = Entorno(sesion)
    contenido: dict[str, object] = {"nombre": "Mercado Pago", "requiere_referencia": True}
    item, usuario_id, dispositivo_id = _item_de_lote(
        entorno, "MEDIO_PAGO_CREAR", "ONLINE", contenido
    )

    (resultado,) = sync_service.procesar_lote(
        sesion,
        FixedClock(MOMENTO_LOTE),
        organizacion_id=entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "ACEPTADO", resultado
    filas = {f["nombre"]: f for f in entorno.filas_de_medio()}
    assert filas["Mercado Pago"]["requiere_referencia"] is True
    assert filas["Mercado Pago"]["activo"] is True
    assert len(entorno.auditoria_de("MEDIO_PAGO_CREAR")) == 1
