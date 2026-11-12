"""INV-21 (`docs/01-dominio.md` §20; `design.md` D1 del change 02): ratchet
de rutas.

Recorre dinámicamente las rutas registradas de FastAPI (`app.openapi()["paths"]`,
que refleja el path completo con prefijo, a diferencia de `app.routes` cuyas
rutas anidadas no exponen el path resuelto en esta versión de FastAPI) y
falla nombrando ruta y método si aparece una ruta de negocio que no está en
`COBERTURA_DE_AISLAMIENTO`.

Tarea 12.1 (change 03) cierra lo que el change 02 dejó parcial (`design.md`
D1 de ese change: "hoy la prueba de rutas pasa sin ejercitar nada de
negocio... el change 03 no puede agregar su primer endpoint sin que la
suite se ponga roja hasta cubrirlo"): las rutas de negocio del grupo 10.7
(usuarios, roles, PIN, dispositivos, desbloqueo) ya están declaradas en
`COBERTURA_DE_AISLAMIENTO`, cada una con su prueba real en
`test_identidad_api_usuarios.py` / `test_inv21_aislamiento_endpoints_identidad.py`
(HTTP, con `login` real de un usuario de otra organización, nunca un JWT
fabricado a mano con `emitir_access_token`). Las rutas de `/auth` quedan
exentas en `RUTAS_DE_AUTENTICACION`, separadas de `RUTAS_DE_SISTEMA`,
porque operan sin organización en contexto (spec `aislamiento-multiorganizacion`,
escenario "Las rutas de autenticación quedan exentas por operar sin
organización en contexto").

CÓMO DECLARAR UNA RUTA NUEVA (tarea 9.2/12.1, para los changes siguientes):
cuando un módulo agrega una ruta de negocio, agregar la entrada
`(metodo, "/api/v1/<ruta>"): ("archivo.py::[Clase::]nombre_de_la_prueba",)` a
`COBERTURA_DE_AISLAMIENTO` en este archivo (change 28, D11: la ruta apunta a la prueba, que
tiene que existir y citar INV-21 en su nombre, su docstring o su archivo), junto con la prueba de
integración que demuestra su aislamiento real:
- dos organizaciones, cada una con su propio usuario autenticado por
  `POST /api/v1/auth/login` (login real, NUNCA un access token fabricado a
  mano con `emitir_access_token`, porque eso no prueba que el flujo de
  autenticación real produzca un contexto correcto);
- el usuario de la organización B ejerce la ruta sobre un recurso de la
  organización A (o, para una ruta de alta, con una referencia -- p. ej.
  `rol_id` -- que pertenece a la organización A);
- la respuesta indica "no encontrado", nunca un error de infraestructura ni
  un 200/201/204 que hubiera modificado o expuesto el recurso ajeno.
Sin esa prueba, no agregar la tupla: agregarla sin probar el aislamiento
real es exactamente la falsa sensación de cobertura que este ratchet existe
para evitar.
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Mapping
from pathlib import Path

from app.core.config import Settings
from app.main import crear_app

# Listas enumerables y explícitas (`design.md` D1 del change 02): nunca un
# patrón de nombre. Separadas porque representan dos motivos de exención
# distintos: sistema (sin negocio en absoluto) vs. autenticación (negocio de
# identidad, pero sin organización todavía en contexto -- tarea 12.1).
RUTAS_DE_SISTEMA = frozenset(
    {
        ("get", "/api/v1/salud"),
        ("get", "/api/v1/version"),
    }
)

RUTAS_DE_AUTENTICACION = frozenset(
    {
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/auth/refresh"),
        ("post", "/api/v1/auth/logout"),
    }
)

# Ver "CÓMO DECLARAR UNA RUTA NUEVA" arriba. Change 28, tarea 5.1 (D11): cada ruta de negocio
# apunta a la(s) prueba(s) que demuestran su aislamiento, como `archivo::nombre` (o
# `archivo::Clase::nombre`) relativo a `backend/tests/integration/`. El ratchet comprueba, sin
# correrlas, que cada una existe y cita INV-21, y que la ruta declarada sigue registrada.
COBERTURA_DE_AISLAMIENTO: dict[tuple[str, str], tuple[str, ...]] = {
    # Identidad
    ("get", "/api/v1/identidad/dispositivos"): (
        "test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeDispositivos::test_listar_dispositivos_no_incluye_los_de_otra_organizacion",
    ),
    ("delete", "/api/v1/identidad/dispositivos/{dispositivo_id}"): (
        "test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeDispositivos::test_revocar_un_dispositivo_de_otra_organizacion_no_lo_encuentra",
    ),
    ("get", "/api/v1/identidad/usuarios"): (
        "test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeUsuarios::test_listar_usuarios_no_incluye_los_de_otra_organizacion",
    ),
    ("post", "/api/v1/identidad/usuarios"): (
        "test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeUsuarios::test_dar_de_alta_un_usuario_con_un_rol_de_otra_organizacion_no_lo_encuentra",
    ),
    ("get", "/api/v1/yo"): (
        "test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeLaSesion::test_yo_del_usuario_de_b_no_trae_nada_de_la_organizacion_a",
        "test_inv21_aislamiento_endpoints_identidad.py::TestAislamientoDeLaSesion::test_yo_ignora_la_organizacion_y_el_usuario_de_a_informados",
    ),
    ("put", "/api/v1/identidad/roles/{rol_id}/permisos"): (
        "test_identidad_api_usuarios.py::TestComposicionDeRol::test_cambiar_composicion_de_rol_de_otra_organizacion_no_lo_encuentra",
    ),
    ("post", "/api/v1/identidad/usuarios/{usuario_id}/pin"): (
        "test_identidad_api_usuarios.py::TestRotacionDePin::test_rotar_el_pin_de_un_usuario_de_otra_organizacion_no_lo_encuentra",
    ),
    ("post", "/api/v1/identidad/usuarios/{usuario_id}/desbloqueo"): (
        "test_identidad_api_usuarios.py::TestDesbloqueoManualDeLogin::test_desbloquear_un_usuario_de_otra_organizacion_no_lo_encuentra",
    ),
    ("put", "/api/v1/identidad/roles/{rol_id}/tope-descuento"): (
        "test_identidad_tope_de_rol.py::test_inv21_put_sobre_un_rol_de_otra_organizacion_responde_404_sin_efectos",
        "test_identidad_tope_de_rol.py::test_inv21_un_cuerpo_con_organizacion_id_se_rechaza",
    ),
    ("get", "/api/v1/identidad/roles"): (
        "test_identidad_tope_de_rol.py::test_inv21_get_roles_no_mezcla_los_permisos_de_otra_organizacion",
    ),
    ("get", "/api/v1/identidad/permisos"): (
        "test_identidad_permisos_catalogo.py::test_get_roles_no_cuenta_los_usuarios_de_otra_organizacion",
    ),
    ("post", "/api/v1/identidad/usuarios/{usuario_id}/baja"): (
        "test_usuario_baja.py::test_un_usuario_de_otra_organizacion_responde_404_y_no_se_toca",
    ),
    ("post", "/api/v1/identidad/usuarios/{usuario_id}/reactivacion"): (
        "test_usuario_reactivar.py::test_un_usuario_de_otra_organizacion_responde_404",
    ),
    ("put", "/api/v1/identidad/usuarios/{usuario_id}"): (
        "test_usuario_modificar.py::test_un_usuario_de_otra_organizacion_responde_404",
    ),
    ("put", "/api/v1/identidad/usuarios/{usuario_id}/rol"): (
        "test_usuario_rol_cambiar.py::test_un_usuario_de_otra_organizacion_responde_404",
        "test_usuario_rol_cambiar.py::test_un_rol_de_otra_organizacion_responde_404",
    ),
    ("post", "/api/v1/identidad/usuarios/{usuario_id}/contrasena"): (
        "test_usuario_contrasena_restablecer.py::test_un_usuario_de_otra_organizacion_responde_404",
    ),
    ("put", "/api/v1/identidad/usuarios/{usuario_id}/tope-descuento"): (
        "test_usuario_tope_descuento_definir.py::test_un_usuario_de_otra_organizacion_responde_404",
    ),
    ("post", "/api/v1/yo/contrasena"): (
        "test_contrasena_propia_cambiar.py::test_inv21_cambiar_la_propia_no_toca_a_los_usuarios_de_otra_organizacion",
    ),
    ("post", "/api/v1/identidad/roles"): (
        "test_rol_crear_y_renombrar.py::test_el_mismo_nombre_en_otra_organizacion_se_acepta",
    ),
    ("put", "/api/v1/identidad/roles/{rol_id}/nombre"): (
        "test_rol_crear_y_renombrar.py::test_renombrar_un_rol_de_otra_organizacion_responde_404",
    ),
    ("post", "/api/v1/identidad/roles/{rol_id}/baja"): (
        "test_rol_baja_y_reactivacion.py::test_baja_y_reactivacion_de_un_rol_de_otra_organizacion_responden_404",
    ),
    ("post", "/api/v1/identidad/roles/{rol_id}/reactivacion"): (
        "test_rol_baja_y_reactivacion.py::test_baja_y_reactivacion_de_un_rol_de_otra_organizacion_responden_404",
    ),
    ("get", "/api/v1/identidad/usuarios/{usuario_id}"): (
        "test_identidad_lecturas_usuarios_roles.py::test_el_detalle_de_un_usuario_de_otra_organizacion_o_inexistente_responde_404",
    ),
    # Sync
    ("post", "/api/v1/sync/comandos"): (
        "test_bus_lote_sincronizacion.py::TestAislamientoEntreOrganizacionesHttp::test_una_organizacion_no_puede_sincronizar_declarando_usuario_de_otra",
        "test_bus_lote_sincronizacion.py::TestAislamientoEntreOrganizacionesHttp::test_una_organizacion_no_puede_sincronizar_declarando_dispositivo_de_otra",
        "test_cuarentena_comandos.py::TestAislamientoYNoBorrado::test_la_cuarentena_de_otra_organizacion_no_es_alcanzable",
    ),
    ("get", "/api/v1/sync/bootstrap"): (
        "test_sync_bootstrap.py::test_inv21_nada_de_otra_organizacion_en_el_bootstrap",
        "test_sync_bootstrap.py::test_inv21_ratchet_el_bootstrap_es_de_lectura_y_de_otra_organizacion_no_se_ve",
    ),
    # Catalogo
    ("post", "/api/v1/catalogo/categorias"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeCategorias::test_crear_categoria_es_independiente_por_organizacion",
    ),
    ("get", "/api/v1/catalogo/categorias"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeCategorias::test_listar_categorias_no_incluye_las_de_otra_organizacion",
    ),
    ("put", "/api/v1/catalogo/categorias/{categoria_id}"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeCategorias::test_modificar_una_categoria_de_otra_organizacion_no_la_encuentra",
    ),
    ("post", "/api/v1/catalogo/marcas"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeMarcas::test_crear_marca_es_independiente_por_organizacion",
    ),
    ("get", "/api/v1/catalogo/marcas"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeMarcas::test_listar_marcas_no_incluye_las_de_otra_organizacion",
    ),
    ("put", "/api/v1/catalogo/marcas/{marca_id}"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeMarcas::test_modificar_una_marca_de_otra_organizacion_no_la_encuentra",
    ),
    ("post", "/api/v1/catalogo/productos"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_crear_producto_con_categoria_de_otra_organizacion_no_la_encuentra",
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_crear_producto_con_marca_de_otra_organizacion_no_la_encuentra",
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_crear_producto_con_alicuota_de_otra_organizacion_no_la_encuentra",
        "test_inv21_aislamiento_endpoints_proveedores.py::TestReferenciaProveedorAjenaEnProductoV2::test_crear_producto_con_proveedor_de_otra_organizacion_no_lo_encuentra",
    ),
    ("get", "/api/v1/catalogo/productos"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_listar_productos_no_incluye_los_de_otra_organizacion",
    ),
    ("put", "/api/v1/catalogo/productos/{producto_id}"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_modificar_un_producto_de_otra_organizacion_no_lo_encuentra",
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_modificar_un_producto_propio_con_categoria_de_otra_organizacion_no_la_encuentra",
        "test_inv21_aislamiento_endpoints_proveedores.py::TestReferenciaProveedorAjenaEnProductoV2::test_modificar_producto_con_proveedor_de_otra_organizacion_no_lo_encuentra",
    ),
    ("get", "/api/v1/catalogo/productos/{producto_id}"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_obtener_un_producto_de_otra_organizacion_no_lo_encuentra",
    ),
    ("post", "/api/v1/catalogo/productos/{producto_id}/presentaciones"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDePresentaciones::test_agregar_presentacion_a_un_producto_de_otra_organizacion_no_lo_encuentra",
    ),
    ("put", "/api/v1/catalogo/presentaciones/{presentacion_id}"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDePresentaciones::test_modificar_una_presentacion_de_otra_organizacion_no_la_encuentra",
    ),
    ("put", "/api/v1/catalogo/productos/{producto_id}/referencia"): (
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDePresentaciones::test_cambiar_la_referencia_de_un_producto_de_otra_organizacion_no_lo_encuentra",
        "test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDePresentaciones::test_cambiar_la_referencia_con_una_presentacion_de_otra_organizacion_no_la_encuentra",
    ),
    ("get", "/api/v1/configuracion/alicuotas"): (
        "test_configuracion_api.py::TestAislamientoInv21::test_cada_organizacion_lista_solo_sus_propias_alicuotas",
    ),
    # Proveedores y costos
    ("post", "/api/v1/proveedores"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_crear_proveedor_no_lo_expone_a_otra_organizacion",
    ),
    ("get", "/api/v1/proveedores"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_listar_proveedores_no_incluye_los_de_otra_organizacion",
    ),
    ("get", "/api/v1/proveedores/opciones"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_opciones_de_proveedores_no_incluye_los_de_otra_organizacion",
    ),
    ("get", "/api/v1/proveedores/{proveedor_id}"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_obtener_un_proveedor_de_otra_organizacion_no_lo_encuentra",
    ),
    ("put", "/api/v1/proveedores/{proveedor_id}"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_modificar_un_proveedor_de_otra_organizacion_no_lo_encuentra",
    ),
    ("post", "/api/v1/costos"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_informar_costos_con_proveedor_de_otra_organizacion_no_lo_encuentra",
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_informar_costos_con_producto_de_otra_organizacion_no_lo_encuentra",
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_informar_costos_con_presentacion_de_otra_organizacion_no_la_encuentra",
    ),
    ("get", "/api/v1/costos/productos/{producto_id}/vigente"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_costo_vigente_de_un_producto_de_otra_organizacion_no_lo_encuentra",
    ),
    ("get", "/api/v1/costos/productos/{producto_id}/historial"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_historial_de_costos_de_un_producto_de_otra_organizacion_no_lo_encuentra",
    ),
    # Clientes
    ("get", "/api/v1/clientes"): (
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_el_listado_no_expone_clientes_de_otra_organizacion",
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_el_listado_ajeno_no_se_encuentra_tampoco_por_texto_ni_por_documento",
    ),
    ("post", "/api/v1/clientes"): (
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_el_alta_de_b_queda_en_b_y_a_no_la_ve",
    ),
    ("get", "/api/v1/clientes/consumidor-final"): (
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_la_lectura_del_consumidor_final_no_devuelve_el_de_otra_organizacion",
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_cada_organizacion_ve_su_propio_consumidor_final",
    ),
    ("post", "/api/v1/clientes/consumidor-final"): (
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_la_habilitacion_del_consumidor_final_de_a_no_toca_la_configuracion_de_b",
    ),
    ("get", "/api/v1/clientes/{cliente_id}"): (
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_la_ficha_de_un_cliente_ajeno_responde_404",
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_un_cliente_ajeno_es_indistinguible_de_uno_inexistente",
    ),
    ("put", "/api/v1/clientes/{cliente_id}"): (
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_modificar_un_cliente_de_otra_organizacion_responde_404_y_no_lo_cambia",
    ),
    ("put", "/api/v1/clientes/{cliente_id}/credito"): (
        "test_inv21_aislamiento_endpoints_clientes.py::TestAislamientoDeLasRutasDeClientes::test_el_credito_de_un_cliente_ajeno_no_se_modifica",
    ),
    # Cuentas corrientes
    ("post", "/api/v1/cuentas-corrientes/saldos-iniciales"): (
        "test_inv21_aislamiento_endpoints_cuentas_corrientes.py::test_inv21_escribir_el_saldo_inicial_de_un_cliente_ajeno_es_404_sin_rastro",
        "test_inv21_aislamiento_endpoints_cuentas_corrientes.py::test_inv21_escribir_el_saldo_inicial_de_un_proveedor_ajeno_es_404_sin_rastro",
        "test_inv21_aislamiento_endpoints_cuentas_corrientes.py::test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_la_cuenta",
    ),
    ("get", "/api/v1/clientes/{cliente_id}/cuenta-corriente"): (
        "test_inv21_aislamiento_endpoints_cuentas_corrientes.py::test_inv21_leer_la_cuenta_de_un_cliente_ajeno_es_404_y_no_revela_el_saldo",
        "test_inv21_aislamiento_endpoints_cuentas_corrientes.py::test_inv21_cada_organizacion_ve_solo_sus_movimientos",
    ),
    ("get", "/api/v1/proveedores/{proveedor_id}/cuenta-corriente"): (
        "test_inv21_aislamiento_endpoints_cuentas_corrientes.py::test_inv21_leer_la_cuenta_de_un_proveedor_ajeno_es_404_y_no_revela_el_saldo",
    ),
    # Stock
    ("post", "/api/v1/stock/ubicaciones"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_una_ubicacion_creada_queda_en_la_organizacion_del_token",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_la_ubicacion",
    ),
    ("get", "/api/v1/stock/ubicaciones"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_una_ubicacion_creada_queda_en_la_organizacion_del_token",
    ),
    ("put", "/api/v1/stock/ubicaciones/{ubicacion_id}"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_modificar_una_ubicacion_ajena_es_404_y_no_la_toca",
    ),
    ("get", "/api/v1/stock/ubicaciones/{ubicacion_id}/saldos"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_leer_el_stock_de_una_ubicacion_ajena_es_404_y_no_revela_nada",
    ),
    ("post", "/api/v1/stock/iniciales"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_registrar_stock_inicial_en_una_ubicacion_ajena_es_404_sin_rastro",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_registrar_stock_inicial_de_un_producto_ajeno_es_404_sin_rastro",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_el_stock_inicial",
    ),
    ("post", "/api/v1/stock/transferencias"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_transferir_desde_o_hacia_una_ubicacion_ajena_es_404_sin_rastro",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_transferir_un_producto_ajeno_es_404_sin_rastro",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_la_transferencia",
    ),
    ("get", "/api/v1/stock/transferencias"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_leer_transferencias_y_ajustes_ajenos_es_404_y_el_listado_no_los_muestra",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_filtrar_por_una_ubicacion_o_un_motivo_ajeno_no_revela_nada",
    ),
    ("get", "/api/v1/stock/transferencias/{transferencia_id}"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_leer_transferencias_y_ajustes_ajenos_es_404_y_el_listado_no_los_muestra",
    ),
    ("post", "/api/v1/stock/transferencias/{transferencia_id}/anulacion"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_anular_una_transferencia_o_un_ajuste_ajeno_es_404_y_los_deja_confirmados",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_el_motivo_de_otra_organizacion_no_anula_una_operacion_propia",
    ),
    ("post", "/api/v1/stock/ajustes"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_ajustar_con_una_ubicacion_motivo_o_producto_ajeno_es_404_sin_rastro",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_el_id_de_organizacion_del_cuerpo_no_reasigna_el_ajuste",
    ),
    ("get", "/api/v1/stock/ajustes"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_leer_transferencias_y_ajustes_ajenos_es_404_y_el_listado_no_los_muestra",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_filtrar_por_una_ubicacion_o_un_motivo_ajeno_no_revela_nada",
    ),
    ("get", "/api/v1/stock/ajustes/{ajuste_id}"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_leer_transferencias_y_ajustes_ajenos_es_404_y_el_listado_no_los_muestra",
    ),
    ("post", "/api/v1/stock/ajustes/{ajuste_id}/anulacion"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_anular_una_transferencia_o_un_ajuste_ajeno_es_404_y_los_deja_confirmados",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_el_motivo_de_otra_organizacion_no_anula_una_operacion_propia",
    ),
    ("post", "/api/v1/stock/jornadas"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_abrir_una_jornada_sobre_una_ubicacion_ajena_es_404_sin_rastro",
    ),
    ("post", "/api/v1/stock/jornadas/{jornada_id}/rendicion"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_rendir_cerrar_o_liberar_una_jornada_ajena_es_404_y_no_la_toca",
    ),
    ("post", "/api/v1/stock/jornadas/{jornada_id}/cierre"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_rendir_cerrar_o_liberar_una_jornada_ajena_es_404_y_no_la_toca",
    ),
    ("post", "/api/v1/stock/jornadas/{jornada_id}/liberacion"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_rendir_cerrar_o_liberar_una_jornada_ajena_es_404_y_no_la_toca",
    ),
    ("get", "/api/v1/stock/jornadas"): (
        "test_jornadas_ubicaciones_api.py::test_inv21_la_jornada_de_otra_organizacion_no_aparece",
    ),
    ("get", "/api/v1/stock/jornadas/actual"): (
        "test_jornadas_ubicaciones_api.py::test_inv21_la_jornada_de_otra_organizacion_no_aparece",
    ),
    ("get", "/api/v1/stock/jornadas/{jornada_id}"): (
        "test_jornadas_consultas_api.py::test_inv21_el_detalle_de_una_jornada_ajena_o_inexistente_responde_404",
        "test_jornadas_api.py::test_inv21_una_jornada_ajena_o_inexistente_responde_404",
    ),
    ("get", "/api/v1/stock/jornadas/{jornada_id}/resumen"): (
        "test_jornadas_api.py::test_inv21_el_resumen_de_una_jornada_ajena_o_inexistente_responde_404",
    ),
    ("get", "/api/v1/stock/kardex"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_leer_el_kardex_con_una_ubicacion_o_un_producto_ajenos_es_404_y_no_revela_nada",
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_cada_organizacion_ve_solo_su_stock_su_kardex_y_su_costo",
    ),
    ("get", "/api/v1/catalogo/productos/{producto_id}/costo"): (
        "test_inv21_aislamiento_endpoints_stock.py::test_inv21_leer_el_costo_de_un_producto_ajeno_es_404_y_no_revela_el_promedio",
    ),
    # Importacion
    ("post", "/api/v1/importaciones/{tipo}"): (
        "test_inv21_aislamiento_endpoints_importacion.py::test_inv21_la_importacion_escribe_solo_en_la_organizacion_del_token",
        "test_inv21_aislamiento_endpoints_importacion.py::test_inv21_un_nombre_que_existe_en_otra_organizacion_no_es_duplicado_ni_se_revela",
        "test_inv21_aislamiento_endpoints_importacion.py::test_inv21_una_columna_de_organizacion_en_el_archivo_se_rechaza_y_no_cambia_el_destino",
    ),
    ("get", "/api/v1/importaciones"): (
        "test_inv21_aislamiento_endpoints_importacion.py::test_inv21_el_historial_no_muestra_nada_de_otra_organizacion",
        "test_inv21_aislamiento_endpoints_importacion.py::test_inv21_un_cursor_de_otra_organizacion_no_filtra_su_historial",
    ),
    ("get", "/api/v1/importaciones/plantillas/{tipo}"): (
        "test_inv21_aislamiento_endpoints_importacion.py::test_inv21_la_plantilla_es_la_misma_para_toda_organizacion_y_no_trae_datos_propios",
    ),
    # Compras
    ("post", "/api/v1/compras"): (
        "test_compras_api.py::test_inv21_un_proveedor_de_otra_organizacion_responde_404_sin_efectos",
        "test_compras_api.py::test_inv21_una_ubicacion_ajena_responde_404",
        "test_compras_api.py::test_inv21_un_producto_ajeno_responde_404",
    ),
    ("post", "/api/v1/compras/{compra_id}/anulacion"): (
        "test_compras_api.py::test_inv21_anular_la_compra_de_otra_organizacion_responde_404",
        "test_compras_anular.py::test_anular_una_compra_de_otra_organizacion_responde_404_inv_21",
    ),
    ("get", "/api/v1/compras"): (
        "test_compras_api.py::test_inv21_el_listado_no_devuelve_compras_de_otra_organizacion",
        "test_compras_api.py::test_inv21_filtrar_por_el_proveedor_de_otra_organizacion_devuelve_lista_vacia",
    ),
    ("get", "/api/v1/compras/{compra_id}"): (
        "test_compras_api.py::test_inv21_el_detalle_de_una_compra_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/configuracion/medios-pago"): (
        "test_compras_api.py::test_medios_de_pago_devuelve_solo_los_activos_de_la_organizacion",
    ),
    ("get", "/api/v1/configuracion/motivos"): (
        "test_compras_api.py::test_motivos_devuelve_solo_los_activos_del_ambito_pedido_de_la_organizacion",
    ),
    # Condicion IVA
    ("get", "/api/v1/configuracion/fiscal"): (
        "test_condicion_iva_api.py::test_inv21_cada_organizacion_lee_solo_su_propia_configuracion_fiscal",
    ),
    ("post", "/api/v1/configuracion/fiscal/condicion-iva"): (
        "test_condicion_iva_api.py::test_inv21_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("get", "/api/v1/costos/resumen-regla-iva"): (
        "test_condicion_iva_api.py::test_inv21_el_resumen_cuenta_solo_los_costos_de_la_organizacion_del_token",
    ),
    # Catalogos de configuracion
    ("post", "/api/v1/configuracion/medios-pago"): (
        "test_medio_pago_comandos.py::TestMedioPagoCrear::test_el_mismo_nombre_en_otra_organizacion_se_acepta",
    ),
    ("put", "/api/v1/configuracion/medios-pago/{medio_pago_id}"): (
        "test_medio_pago_comandos.py::TestMedioPagoModificar::test_un_medio_de_otra_organizacion_o_inexistente_responde_404",
    ),
    ("get", "/api/v1/configuracion/medios-pago/todos"): (
        "test_medios_pago_lectura.py::test_solo_lee_los_medios_de_la_organizacion_del_token",
    ),
    ("post", "/api/v1/configuracion/motivos"): (
        "test_motivo_comandos.py::TestMotivoCrear::test_inv02_el_mismo_nombre_en_otro_ambito_o_en_otra_organizacion_se_acepta",
    ),
    ("put", "/api/v1/configuracion/motivos/{motivo_id}"): (
        "test_motivo_comandos.py::TestMotivoModificar::test_un_motivo_ajeno_o_inexistente_es_404",
    ),
    ("get", "/api/v1/configuracion/motivos/todos"): (
        "test_motivos_lectura.py::TestLecturaCompleta::test_inv21_trae_solo_los_motivos_de_la_organizacion_del_token",
    ),
    ("post", "/api/v1/configuracion/alicuotas"): (
        "test_alicuota_comandos.py::TestAlicuotaCrear::test_inv21_otra_organizacion_acepta_el_mismo_nombre_y_valor",
    ),
    ("put", "/api/v1/configuracion/alicuotas/{alicuota_id}"): (
        "test_alicuota_comandos.py::TestAlicuotaModificar::test_inv21_una_alicuota_ajena_o_inexistente_es_404",
    ),
    ("get", "/api/v1/configuracion/redondeo-por-defecto"): (
        "test_redondeo_por_defecto.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("post", "/api/v1/configuracion/redondeo-por-defecto"): (
        "test_redondeo_por_defecto.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    # Pagos a proveedores
    ("post", "/api/v1/pagos-proveedores"): (
        "test_pagos_proveedor_api.py::test_un_proveedor_ajeno_responde_404",
        "test_pagos_proveedor_api.py::test_un_medio_ajeno_responde_404_con_el_medio",
    ),
    ("post", "/api/v1/pagos-proveedores/{pago_id}/anulacion"): (
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDePagosAProveedores::test_la_anulacion_propia_cambia_el_estado_y_la_de_un_pago_ajeno_responde_404",
        "test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDePagosAProveedores::test_la_anulacion_ignora_el_organizacion_id_del_cuerpo",
    ),
    ("get", "/api/v1/pagos-proveedores"): (
        "test_pagos_proveedor_api.py::test_inv21_el_listado_no_muestra_los_pagos_de_otra_organizacion",
    ),
    ("get", "/api/v1/pagos-proveedores/{pago_id}"): (
        "test_pagos_proveedor_api.py::test_inv21_el_detalle_de_un_pago_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/proveedores/{proveedor_id}/saldo"): (
        "test_pagos_proveedor_api.py::test_inv21_el_saldo_de_un_proveedor_de_otra_organizacion_responde_404",
    ),
    # Precios
    ("post", "/api/v1/precios/listas"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_el_alta_el_listado_y_las_opciones_solo_ven_lo_propio",
    ),
    ("get", "/api/v1/precios/listas"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_el_alta_el_listado_y_las_opciones_solo_ven_lo_propio",
    ),
    ("get", "/api/v1/precios/listas/opciones"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_el_alta_el_listado_y_las_opciones_solo_ven_lo_propio",
    ),
    ("get", "/api/v1/precios/listas/{lista_id}"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("put", "/api/v1/precios/listas/{lista_id}"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("get", "/api/v1/precios/listas/{lista_id}/reglas"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("post", "/api/v1/precios/listas/{lista_id}/reglas"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
        "test_precios_api.py::test_inv21_una_regla_con_una_entidad_de_otra_organizacion_responde_404",
    ),
    ("put", "/api/v1/precios/listas/{lista_id}/reglas/{regla_id}"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("put", "/api/v1/precios/listas/{lista_id}/redondeos-categoria/{categoria_id}"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("post", "/api/v1/precios/listas/{lista_id}/borrador"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("get", "/api/v1/precios/listas/{lista_id}/borrador"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("put", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/precios/{producto_id}"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_una_version_o_un_producto_de_a_con_la_lista_de_b_responde_404",
        "test_precios_api.py::test_inv21_fijar_sobre_la_lista_o_la_version_de_otra_organizacion_responde_404",
    ),
    ("post", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/publicar"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("post", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/anular"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
        "test_precios_api.py::test_inv21_anular_la_version_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/precios/listas/{lista_id}/versiones"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("get", "/api/v1/precios/listas/{lista_id}/versiones/{version_id}/precios"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_toda_ruta_con_un_recurso_de_otra_organizacion_responde_404_sin_efectos",
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_una_version_o_un_producto_de_a_con_la_lista_de_b_responde_404",
    ),
    ("get", "/api/v1/precios/listas/{lista_id}/vigente"): (
        "test_precios_api.py::test_inv21_la_version_vigente_de_una_lista_de_otra_organizacion_responde_404",
    ),
    ("put", "/api/v1/precios/lista-predeterminada"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_la_lista_asignada_a_un_cliente_de_otra_organizacion_responde_404",
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_la_lista_predeterminada_leida_es_la_de_la_propia_organizacion",
    ),
    ("get", "/api/v1/precios/lista-predeterminada"): (
        "test_inv21_aislamiento_endpoints_precios.py::test_inv21_la_lista_predeterminada_leida_es_la_de_la_propia_organizacion",
    ),
    # Descuentos
    ("get", "/api/v1/descuentos/reglas"): (
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_el_listado_de_b_no_trae_nada_de_a_y_el_de_a_trae_lo_suyo",
    ),
    ("get", "/api/v1/descuentos/reglas/{regla_id}"): (
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_el_detalle_de_una_regla_de_a_responde_404_a_un_usuario_de_b",
    ),
    ("post", "/api/v1/descuentos/reglas"): (
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_el_alta_con_una_entidad_de_a_en_el_alcance_responde_404_sin_efectos",
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_el_alta_de_b_crea_la_regla_en_b_y_a_no_la_ve",
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_un_organizacion_id_de_a_en_el_cuerpo_se_rechaza",
    ),
    ("put", "/api/v1/descuentos/reglas/{regla_id}"): (
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_toda_escritura_sobre_una_regla_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("post", "/api/v1/descuentos/reglas/{regla_id}/activacion"): (
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_toda_escritura_sobre_una_regla_de_otra_organizacion_responde_404_sin_efectos",
    ),
    ("post", "/api/v1/descuentos/reglas/{regla_id}/pausa"): (
        "test_inv21_aislamiento_endpoints_descuentos.py::test_inv21_toda_escritura_sobre_una_regla_de_otra_organizacion_responde_404_sin_efectos",
    ),
    # Cobranzas
    ("post", "/api/v1/cobranzas"): (
        "test_cobranzas_api.py::test_inv21_un_cliente_de_otra_organizacion_responde_404_sin_efectos",
        "test_cobranzas_api.py::test_inv21_un_medio_de_otra_organizacion_responde_404_con_el_medio",
    ),
    ("post", "/api/v1/cobranzas/{cobranza_id}/anulacion"): (
        "test_cobranzas_api.py::test_inv21_anular_una_cobranza_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/cobranzas"): (
        "test_cobranzas_consultas_api.py::test_inv21_el_detalle_y_el_listado_no_cruzan_organizaciones",
    ),
    ("get", "/api/v1/cobranzas/{cobranza_id}"): (
        "test_cobranzas_consultas_api.py::test_inv21_el_detalle_y_el_listado_no_cruzan_organizaciones",
    ),
    ("get", "/api/v1/clientes/opciones"): (
        "test_clientes_opciones_y_saldo_api.py::test_inv21_las_opciones_no_traen_clientes_de_otra_organizacion",
    ),
    ("get", "/api/v1/clientes/{cliente_id}/saldo"): (
        "test_clientes_opciones_y_saldo_api.py::test_inv21_el_saldo_de_un_cliente_ajeno_o_inexistente_responde_404",
    ),
    ("post", "/api/v1/clientes/vendedor"): (
        "test_cliente_vendedor_asignar.py::test_un_cliente_inexistente_o_ajeno_es_404_y_ninguno_cambia",
        "test_cliente_vendedor_asignar.py::test_un_vendedor_de_otra_organizacion_es_404",
    ),
    ("get", "/api/v1/clientes/vendedores"): (
        "test_clientes_vendedores_elegibles.py::test_no_lista_usuarios_de_otra_organizacion",
    ),
    # Ventas
    ("post", "/api/v1/ventas"): (
        "test_ventas_api.py::test_inv21_un_cliente_de_otra_organizacion_responde_404_sin_efectos",
        "test_ventas_confirmar.py::test_inv21_el_contenido_no_elige_la_organizacion",
    ),
    ("get", "/api/v1/ventas"): (
        "test_ventas_consultas_api.py::test_inv21_las_ventas_de_otra_organizacion_no_aparecen_y_su_detalle_es_404",
    ),
    ("get", "/api/v1/ventas/{venta_id}"): (
        "test_ventas_consultas_api.py::test_inv21_las_ventas_de_otra_organizacion_no_aparecen_y_su_detalle_es_404",
    ),
    ("get", "/api/v1/ventas/{venta_id}/nota"): (
        "test_ventas_nota.py::test_inv21_seg07_la_nota_de_una_venta_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/ventas/precios"): (
        "test_ventas_lecturas_de_apoyo_api.py::test_inv21_una_ubicacion_cliente_o_lista_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/ventas/numeracion"): (
        "test_ventas_lecturas_de_apoyo_api.py::test_inv21_la_numeracion_de_una_organizacion_no_cuenta_las_ventas_de_la_otra",
    ),
    ("get", "/api/v1/ventas/versiones"): (
        "test_ventas_lecturas_de_apoyo_api.py::test_inv21_las_versiones_de_una_lista_ajena_responden_404_y_lista_id_es_obligatorio",
        "test_ventas_lecturas_de_apoyo_api.py::test_inv21_los_precios_de_una_version_de_otra_organizacion_responden_404",
    ),
    ("post", "/api/v1/ventas/{venta_id}/anulacion"): (
        "test_ventas_anular_api.py::test_inv21_una_venta_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/configuracion/descuento-manual"): (
        "test_descuento_manual_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("post", "/api/v1/configuracion/descuento-manual"): (
        "test_descuento_manual_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("get", "/api/v1/configuracion/credito"): (
        "test_credito_organizacion_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("post", "/api/v1/configuracion/credito"): (
        "test_credito_organizacion_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("get", "/api/v1/configuracion/nota-de-venta"): (
        "test_nota_venta_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("post", "/api/v1/configuracion/nota-de-venta"): (
        "test_nota_venta_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("get", "/api/v1/configuracion/organizacion"): (
        "test_organizacion_cuit_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("post", "/api/v1/configuracion/organizacion"): (
        "test_organizacion_cuit_configurar.py::test_inv21_http_el_cambio_afecta_solo_a_la_organizacion_del_token",
    ),
    ("post", "/api/v1/yo/pin-autorizacion"): (
        "test_identidad_pin_propio_definir.py::test_inv21_definir_el_pin_propio_no_toca_a_los_usuarios_de_otra_organizacion",
    ),
    ("get", "/api/v1/yo/pin-autorizacion"): (
        "test_identidad_yo_pin.py::test_seg07_cada_usuario_ve_solo_lo_suyo_y_get_yo_no_cambia",
    ),
    ("get", "/api/v1/ventas/contexto"): (
        "test_ventas_contexto.py::test_syn11_no_son_autorizadores_los_que_no_cumplen_las_condiciones",
        "test_ventas_contexto.py::test_dsc06_los_motivos_son_solo_los_activos_del_ambito_de_descuento_manual_propio",
    ),
    ("get", "/api/v1/ventas/credito"): (
        "test_ventas_credito_lectura.py::test_seg07_el_credito_de_un_cliente_de_otra_organizacion_responde_404",
    ),
    ("get", "/api/v1/ventas/descuentos-aplicables"): (
        "test_ventas_descuentos_aplicables.py::test_inv21_las_reglas_de_otra_organizacion_no_figuran",
    ),
    # Observaciones y rechazos
    ("post", "/api/v1/observaciones/resolucion"): (
        "test_observacion_resolver.py::test_una_observacion_de_otra_organizacion_responde_404_y_no_se_resuelve_ninguna",
    ),
    ("get", "/api/v1/observaciones"): (
        "test_bandeja_de_observaciones.py::test_otra_organizacion_no_aparece",
    ),
    ("get", "/api/v1/observaciones/resumen"): (
        "test_resumen_de_pendientes.py::test_solo_cuenta_la_organizacion_del_token",
    ),
    ("get", "/api/v1/observaciones/rechazos"): (
        "test_lista_de_rechazos.py::test_inv21_otra_organizacion_no_ve_los_rechazos_y_su_pedido_responde_404",
    ),
    ("get", "/api/v1/observaciones/rechazos/{rechazo_id}"): (
        "test_lista_de_rechazos.py::test_inv21_otra_organizacion_no_ve_los_rechazos_y_su_pedido_responde_404",
    ),
    ("post", "/api/v1/observaciones/rechazos/{rechazo_id}/resolucion"): (
        "test_rechazo_resolver.py::test_inv21_un_rechazo_de_otra_organizacion_o_inexistente_responde_404",
    ),
    # Reportes
    ("get", "/api/v1/reportes/ventas"): (
        "reportes/test_reporte_ventas.py::test_inv21_el_reporte_no_incluye_ventas_de_otra_organizacion",
        "reportes/test_reporte_ventas.py::test_inv21_filtrar_por_un_vendedor_de_otra_organizacion_devuelve_el_reporte_vacio",
        "reportes/test_reporte_ventas.py::test_inv21_la_organizacion_no_se_toma_de_la_consulta",
    ),
    ("get", "/api/v1/reportes/rendiciones"): (
        "reportes/test_reporte_rendiciones.py::test_inv21_la_lista_no_incluye_jornadas_de_otra_organizacion",
        "reportes/test_reporte_rendiciones.py::test_inv21_filtrar_por_un_vendedor_ajeno_devuelve_vacio",
    ),
    ("get", "/api/v1/reportes/rendiciones/{jornada_id}"): (
        "reportes/test_reporte_rendiciones.py::test_inv21_el_detalle_de_una_jornada_ajena_o_inexistente_es_404",
    ),
    ("get", "/api/v1/reportes/observaciones"): (
        "reportes/test_reporte_observaciones.py::test_inv21_no_cuenta_observaciones_ni_rechazos_de_otra_organizacion",
    ),
    ("get", "/api/v1/reportes/ajustes"): (
        "reportes/test_reporte_ajustes.py::test_inv21_no_cuenta_ajustes_ni_diferencias_de_otra_organizacion",
    ),
    ("get", "/api/v1/reportes/saldos/clientes"): (
        "reportes/test_reporte_saldos.py::test_inv21_no_ve_saldos_de_clientes_de_otra_organizacion",
    ),
    ("get", "/api/v1/reportes/saldos/proveedores"): (
        "reportes/test_reporte_saldos.py::test_inv21_no_ve_saldos_de_proveedores_de_otra_organizacion",
    ),
    # Sistema
    ("get", "/api/v1/sistema/consistencia"): (
        "test_consistencia_api.py::test_inv21_el_resultado_de_otra_organizacion_no_se_ve",
        "test_consistencia_api.py::test_inv21_un_identificador_ajeno_en_el_detalle_no_revela_el_nombre",
    ),
}


RAIZ_DE_PRUEBAS = Path(__file__).resolve().parent
"""Carpeta a la que son relativos los `archivo::nombre` de `COBERTURA_DE_AISLAMIENTO`."""

_CITA_INV21 = re.compile(r"INV[-_ ]?21", re.IGNORECASE)

Cobertura = Mapping[tuple[str, str], tuple[str, ...]]
Ruta = tuple[str, str]


def rutas_de_negocio_sin_cobertura(
    rutas_del_esquema: dict[str, dict[str, object]],
    *,
    rutas_exentas: frozenset[tuple[str, str]],
    cobertura: Cobertura,
) -> list[tuple[str, str]]:
    """Devuelve las rutas `(metodo, path)` que son de negocio (no están en
    `rutas_exentas`) y no están cubiertas por `cobertura`."""
    todas = [(metodo, path) for path, metodos in rutas_del_esquema.items() for metodo in metodos]
    de_negocio = [ruta for ruta in todas if ruta not in rutas_exentas]
    return [ruta for ruta in de_negocio if ruta not in cobertura]


def rutas_declaradas_que_no_existen(
    rutas_del_esquema: dict[str, dict[str, object]], cobertura: Cobertura
) -> list[Ruta]:
    """Rutas de `cobertura` que ya no están registradas en el esquema (D11)."""
    presentes = {
        (metodo, path) for path, metodos in rutas_del_esquema.items() for metodo in metodos
    }
    return [ruta for ruta in cobertura if ruta not in presentes]


def rutas_declaradas_sin_pruebas(cobertura: Cobertura) -> list[Ruta]:
    return [ruta for ruta, pruebas in cobertura.items() if not pruebas]


def _buscar_prueba(raiz: Path, referencia: str) -> tuple[ast.Module, str, ast.AST] | None:
    """Devuelve `(módulo, texto del archivo, nodo de la prueba)` o `None` si el archivo o la
    prueba no están. Lee el archivo, no lo importa ni lo corre."""
    archivo, separador, camino = referencia.partition("::")
    if not separador or not camino:
        return None
    ruta = raiz / archivo
    if not ruta.is_file():
        return None
    texto = ruta.read_text(encoding="utf-8")
    modulo = ast.parse(texto)
    cuerpo: list[ast.stmt] = modulo.body
    nodo: ast.AST | None = None
    for nombre in camino.split("::"):
        nodo = next(
            (
                n
                for n in cuerpo
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                and n.name == nombre
            ),
            None,
        )
        if nodo is None:
            return None
        cuerpo = getattr(nodo, "body", [])
    assert nodo is not None
    return modulo, texto, nodo


def pruebas_declaradas_inexistentes(cobertura: Cobertura, raiz: Path) -> list[tuple[Ruta, str]]:
    """`(ruta, referencia)` de cada prueba declarada que no está en su archivo (D11)."""
    return [
        (ruta, referencia)
        for ruta, referencias in cobertura.items()
        for referencia in referencias
        if _buscar_prueba(raiz, referencia) is None
    ]


def pruebas_declaradas_que_no_citan_inv21(
    cobertura: Cobertura, raiz: Path
) -> list[tuple[Ruta, str]]:
    """Las pruebas que existen pero no citan INV-21: ni en su nombre ni en su texto (docstring,
    comentarios, código) ni en el texto de su archivo (D11). Las inexistentes las informa
    `pruebas_declaradas_inexistentes`."""
    sin_cita: list[tuple[Ruta, str]] = []
    for ruta, referencias in cobertura.items():
        for referencia in referencias:
            hallada = _buscar_prueba(raiz, referencia)
            if hallada is None:
                continue
            _, texto_del_archivo, nodo = hallada
            texto_de_la_prueba = ast.get_source_segment(texto_del_archivo, nodo) or ""
            if not (
                _CITA_INV21.search(referencia.rpartition("::")[2])
                or _CITA_INV21.search(texto_de_la_prueba)
                or _CITA_INV21.search(texto_del_archivo)
            ):
                sin_cita.append((ruta, referencia))
    return sin_cita


def _rutas_reales_del_esquema() -> dict[str, dict[str, object]]:
    app = crear_app(Settings())  # type: ignore[call-arg]
    schema = app.openapi()
    paths: dict[str, dict[str, object]] = schema["paths"]
    return paths


def test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento(
    database_url: str,
) -> None:
    """Escenario 'Una ruta de negocio sin cobertura de aislamiento hace
    fallar la verificación'."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()
    rutas_exentas = RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        rutas, rutas_exentas=rutas_exentas, cobertura=COBERTURA_DE_AISLAMIENTO
    )

    total_de_negocio = len(
        [
            (metodo, path)
            for path, metodos in rutas.items()
            for metodo in metodos
            if (metodo, path) not in rutas_exentas
        ]
    )
    mensaje = (
        f"INV-21: {len(sin_cobertura)} ruta(s) de negocio sin cobertura de "
        f"aislamiento: {sin_cobertura}. Rutas de negocio cubiertas hoy: "
        f"{total_de_negocio - len(sin_cobertura)} de {total_de_negocio}."
    )
    assert sin_cobertura == [], mensaje


def test_inv21_las_rutas_de_sistema_no_requieren_organizacion(database_url: str) -> None:
    """Escenario 'Las rutas de sistema no requieren organización': las
    rutas de sistema están explícitamente exentas, no por patrón de nombre."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    rutas_presentes = {(metodo, path) for path, metodos in rutas.items() for metodo in metodos}
    for ruta_sistema in RUTAS_DE_SISTEMA:
        assert ruta_sistema in rutas_presentes, (
            f"Ruta de sistema {ruta_sistema} esperada pero no está registrada."
        )


def test_inv21_las_rutas_de_autenticacion_quedan_exentas_por_operar_sin_organizacion(
    database_url: str,
) -> None:
    """Escenario 'Las rutas de autenticación quedan exentas por operar sin
    organización en contexto' (tarea 12.1, spec `aislamiento-multiorganizacion`):
    `/auth/login`, `/auth/refresh` y `/auth/logout` están registradas, y
    quedan fuera de la exigencia de `COBERTURA_DE_AISLAMIENTO` por estar
    declaradas explícitamente en `RUTAS_DE_AUTENTICACION` -- una lista
    separada de `RUTAS_DE_SISTEMA`, porque el motivo de la exención es
    distinto (sin organización en contexto todavía, no "sin negocio")."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    rutas_presentes = {(metodo, path) for path, metodos in rutas.items() for metodo in metodos}
    for ruta_auth in RUTAS_DE_AUTENTICACION:
        assert ruta_auth in rutas_presentes, (
            f"Ruta de autenticación {ruta_auth} esperada pero no está registrada."
        )

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        rutas,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )
    for ruta_auth in RUTAS_DE_AUTENTICACION:
        assert ruta_auth not in sin_cobertura, (
            f"{ruta_auth} no debería exigir cobertura de aislamiento: opera "
            "sin organización en contexto (tarea 12.1)."
        )


def test_inv21_una_ruta_de_autenticacion_no_declarada_no_queda_exenta_por_prefijo(
    database_url: str,
) -> None:
    """Verificación en negativo (tarea 12.1, mismo criterio que la de
    sistema/tarea 9.3): la exención de `/auth` es una lista enumerable, no
    un patrón de prefijo -- una ruta de negocio nueva bajo `/auth` que no
    esté declarada en `RUTAS_DE_AUTENTICACION` sigue exigiendo cobertura."""
    esquema_con_ruta_ficticia = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/auth/login": {"post": {}},
        "/api/v1/auth/impersonar": {"post": {}},  # ruta de negocio ficticia bajo /auth
    }

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema_con_ruta_ficticia,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )

    assert sin_cobertura == [("post", "/api/v1/auth/impersonar")]


def test_inv21_detecta_una_ruta_de_negocio_ficticia_sin_cobertura() -> None:
    """Verificación en negativo (tarea 9.3, extendida en 12.6): una ruta de
    negocio no registrada en `COBERTURA_DE_AISLAMIENTO` debe ser detectada y
    nombrada -- el ratchet falla si se agrega a propósito una ruta de
    negocio sin declarar su cobertura de aislamiento."""
    esquema_con_ruta_ficticia = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/version": {"get": {}},
        "/api/v1/venta": {"post": {}},  # ruta de negocio ficticia, sin cobertura
    }

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema_con_ruta_ficticia,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=COBERTURA_DE_AISLAMIENTO,
    )

    assert sin_cobertura == [("post", "/api/v1/venta")]


def test_inv21_no_marca_una_ruta_de_negocio_que_si_tiene_cobertura_declarada() -> None:
    """Verificación complementaria: si una ruta de negocio SÍ está en
    `cobertura`, no se marca como infractora."""
    esquema = {
        "/api/v1/salud": {"get": {}},
        "/api/v1/venta": {"post": {}},
    }
    cobertura_de_prueba = frozenset({("post", "/api/v1/venta")})

    sin_cobertura = rutas_de_negocio_sin_cobertura(
        esquema,
        rutas_exentas=RUTAS_DE_SISTEMA | RUTAS_DE_AUTENTICACION,
        cobertura=cobertura_de_prueba,
    )

    assert sin_cobertura == []


# --- Change 28, tarea 5.1 (D11): cada ruta declarada apunta a pruebas que existen -------------


def _tabla_de_pruebas(raiz: Path, archivo: str, contenido: str) -> None:
    destino = raiz / archivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")


def test_inv21_cada_prueba_declarada_existe() -> None:
    """Escenario 'Una prueba declarada que no existe hace fallar la verificación': cada
    `archivo::nombre` de `COBERTURA_DE_AISLAMIENTO` se encuentra en el archivo, sin correrla."""
    inexistentes = pruebas_declaradas_inexistentes(COBERTURA_DE_AISLAMIENTO, RAIZ_DE_PRUEBAS)

    assert inexistentes == [], f"INV-21: pruebas declaradas que no existen: {inexistentes}"


def test_inv21_cada_prueba_declarada_cita_inv21() -> None:
    """Escenario 'Una prueba que no cita INV-21 hace fallar la verificación'."""
    sin_cita = pruebas_declaradas_que_no_citan_inv21(COBERTURA_DE_AISLAMIENTO, RAIZ_DE_PRUEBAS)

    assert sin_cita == [], f"INV-21: pruebas declaradas que no citan INV-21: {sin_cita}"


def test_inv21_toda_ruta_declarada_tiene_al_menos_una_prueba() -> None:
    sin_pruebas = rutas_declaradas_sin_pruebas(COBERTURA_DE_AISLAMIENTO)

    assert sin_pruebas == [], f"INV-21: rutas declaradas sin ninguna prueba: {sin_pruebas}"


def test_inv21_no_hay_rutas_declaradas_que_ya_no_existen(database_url: str) -> None:
    """Escenario 'Una ruta declarada que ya no existe hace fallar la verificación'."""
    os.environ.setdefault("DATABASE_URL", database_url)
    rutas = _rutas_reales_del_esquema()

    sobrantes = rutas_declaradas_que_no_existen(rutas, COBERTURA_DE_AISLAMIENTO)

    assert sobrantes == [], f"INV-21: rutas declaradas que ya no existen: {sobrantes}"


def test_inv21_detecta_una_prueba_inexistente(tmp_path: Path) -> None:
    """Negativo con datos de prueba: archivo ausente, función ausente, método de clase
    ausente. La existente (función suelta y método de clase) no se marca."""
    _tabla_de_pruebas(
        tmp_path,
        "test_a.py",
        "class TestA:\n    def test_metodo(self):\n        pass\n\ndef test_suelta():\n    pass\n",
    )
    cobertura = {
        ("get", "/x"): (
            "test_a.py::test_suelta",
            "test_a.py::TestA::test_metodo",
            "test_a.py::test_no_esta",
            "test_a.py::TestA::test_no_esta",
            "test_b.py::test_suelta",
        )
    }

    inexistentes = pruebas_declaradas_inexistentes(cobertura, tmp_path)

    assert inexistentes == [
        (("get", "/x"), "test_a.py::test_no_esta"),
        (("get", "/x"), "test_a.py::TestA::test_no_esta"),
        (("get", "/x"), "test_b.py::test_suelta"),
    ]


def test_inv21_una_referencia_mal_formada_cuenta_como_inexistente(tmp_path: Path) -> None:
    cobertura = {("get", "/x"): ("sin_separador",)}

    assert pruebas_declaradas_inexistentes(cobertura, tmp_path) == [
        (("get", "/x"), "sin_separador")
    ]


def test_inv21_detecta_una_prueba_que_no_cita_inv21(tmp_path: Path) -> None:
    """Negativo y triangulación: cita por el nombre, por la docstring de la prueba o por el
    texto del archivo -> pasa; sin cita en ninguno -> se nombra."""
    _tabla_de_pruebas(
        tmp_path,
        "test_con_cita.py",
        "def test_inv21_por_nombre():\n    pass\n\n"
        'def test_por_docstring():\n    """Cubre INV-21."""\n\n'
        "def test_ajena():\n    pass\n",
    )
    _tabla_de_pruebas(
        tmp_path,
        "test_cita_en_el_archivo.py",
        '"""Este archivo cubre el aislamiento (INV-21)."""\n\ndef test_x():\n    pass\n',
    )
    _tabla_de_pruebas(tmp_path, "test_sin_cita.py", "def test_y():\n    pass\n")
    cobertura = {
        ("get", "/x"): (
            "test_con_cita.py::test_inv21_por_nombre",
            "test_con_cita.py::test_por_docstring",
            "test_cita_en_el_archivo.py::test_x",
            "test_sin_cita.py::test_y",
        )
    }

    sin_cita = pruebas_declaradas_que_no_citan_inv21(cobertura, tmp_path)

    assert sin_cita == [(("get", "/x"), "test_sin_cita.py::test_y")]


def test_inv21_detecta_una_ruta_declarada_que_ya_no_existe() -> None:
    esquema = {"/api/v1/a": {"get": {}}, "/api/v1/b": {"post": {}, "get": {}}}
    cobertura = {
        ("get", "/api/v1/a"): ("t.py::t",),
        ("get", "/api/v1/borrada"): ("t.py::t",),
        ("delete", "/api/v1/b"): ("t.py::t",),
    }

    sobrantes = rutas_declaradas_que_no_existen(esquema, cobertura)

    assert sobrantes == [("get", "/api/v1/borrada"), ("delete", "/api/v1/b")]


def test_inv21_detecta_una_ruta_declarada_sin_pruebas() -> None:
    cobertura = {("get", "/x"): ("t.py::t",), ("post", "/y"): ()}

    assert rutas_declaradas_sin_pruebas(cobertura) == [("post", "/y")]
