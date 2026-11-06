import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 25, tarea 23.1: trazabilidad de las specs delta. Cada escenario de las nueve specs
 * (`ruta/area-de-ruta`, `sistema/ayuda-contextual`, `stock/rendicion-de-jornada`, `sync/bootstrap`,
 * `sync/cola-local`, `sync/cuarentena-de-comandos`, `sync/observaciones`,
 * `sync/rechazos-sin-conexion`, `sync/revision-de-observaciones`) se asocia con la prueba que lo
 * ejercita (archivo y fragmento de su nombre o título); los del servidor apuntan a su archivo de
 * `backend/tests`. Varios nombres se repiten entre specs («Sin permiso», «Doble envío de la
 * resolución»...), por eso la clave lleva la capacidad. Si una prueba se renombra o se borra, esta
 * falla y obliga a revisar la cobertura. Además comprueba que cada escenario de las specs tiene su
 * entrada acá (y ninguna sobra) y que SYN-08, INV-01, INV-02, INV-05, INV-06, INV-17 e INV-21 los
 * cita alguna prueba por su ID (`04` §2.1 puntos 2 y 3).
 *
 * Las specs se leen de la carpeta del change mientras está activo y, una vez archivado, de la del
 * archivo (el nombre lleva la fecha del archivo).
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RAIZ = resolve(UNIT, '..', '..', '..')
const BACKEND = resolve(RAIZ, 'backend', 'tests')
const CAMBIOS = resolve(RAIZ, 'openspec', 'changes')

function carpetaDeSpecs(): string {
  const activa = resolve(CAMBIOS, '25-observaciones-y-revision', 'specs')
  if (existsSync(activa)) return activa
  const archivados = resolve(CAMBIOS, 'archive')
  const nombre = readdirSync(archivados).find((n) => n.endsWith('-25-observaciones-y-revision'))
  if (nombre === undefined) throw new Error('No se encontró el change 25 ni activo ni archivado')
  return resolve(archivados, nombre, 'specs')
}

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const RESOLVER_OBS = 'integration/test_observacion_resolver.py'
const RESOLVER_RECHAZO = 'integration/test_rechazo_resolver.py'
const REGISTRO = 'integration/test_registro_de_rechazos.py'
const BANDEJA = 'integration/test_bandeja_de_observaciones.py'
const NOMBRES = 'integration/test_bandeja_nombres.py'
const LISTA = 'integration/test_lista_de_rechazos.py'
const BOOTSTRAP = 'integration/test_bootstrap_rechazos_resueltos.py'
const RENDICION = 'integration/test_rendicion_rechazos_pendientes.py'
const DESACTIVADO = 'integration/test_venta_offline_producto_desactivado.py'
const MIGRACION = 'integration/test_revision_migracion.py'
const CONCURRENCIA = 'concurrency/test_revision_concurrente.py'
const PROPIEDADES = 'properties/test_revision_propiedades.py'

const INICIO = 'areas/admin/AdminInicio.test.tsx'
const AYUDA_REVISION = 'areas/admin/revision/AyudaDeRevision.test.tsx'
const CONTEO = 'areas/admin/stock/RendicionScreen.test.tsx'
const RESUELTO_EN_RUTA = 'areas/ruta/RechazoResuelto.test.tsx'
const BOOTSTRAP_LOCAL = 'sync/rechazosResueltos.test.ts'
const TEXTOS = 'ayuda/textosRevision.test.ts'

const MAPA: Record<string, Destino> = {
  // ruta/area-de-ruta
  'ruta/area-de-ruta: Rechazo resuelto': unit(RESUELTO_EN_RUTA, '«Cobranzas de hoy»: la cobranza rechazada resuelta lo dice y la otra no'),
  'ruta/area-de-ruta: Sin señal después de actualizar': unit(RESUELTO_EN_RUTA, 'tras recargar la aplicación sin señal (se vuelve a montar) la marca sigue ahí (ADR-062)'),
  'ruta/area-de-ruta: Sigue sin reenviarse': unit(RESUELTO_EN_RUTA, 'no se reenvía: la cola a enviar no incluye ninguna rechazada, resuelta o no (SYN-09, INV-06)'),
  // sistema/ayuda-contextual
  'sistema/ayuda-contextual: Ayuda de la bandeja': unit(AYUDA_REVISION, 'al abrir la ayuda de la bandeja se lee que resolver no cambia la operación'),
  'sistema/ayuda-contextual: Ayuda de las rechazadas': unit(AYUDA_REVISION, '«Rechazadas»: el diálogo de resolución tiene «Resolver» y «Vincular con» con su ayuda'),
  'sistema/ayuda-contextual: Ayuda de las rechazadas de la jornada': unit(AYUDA_REVISION, 'lleva la ayuda «Rechazadas de la jornada», con y sin permiso de revisión'),
  'sistema/ayuda-contextual: Textos revisados': unit(TEXTOS, 'cobranzas-observaciones suma «Llegó después de la rendición» y ya no dice que la bandeja llega más adelante'),
  'sistema/ayuda-contextual: Clave o ID inexistente': unit('ayuda/trazabilidad.test.ts', 'cada clave de <Ayuda clave> y de ayuda= existe en AYUDAS'),
  // stock/rendicion-de-jornada
  'stock/rendicion-de-jornada: Rendición con una venta rechazada sin resolver': servidor(RENDICION, 'test_rut05_la_rendicion_con_un_rechazo_pendiente_se_rechaza_sin_escribir_nada'),
  'stock/rendicion-de-jornada: Rendición permitida cuando todo está resuelto': servidor(RENDICION, 'test_syn08_resuelto_con_vinculo_a_la_venta_cargada_la_rendicion_se_acepta'),
  'stock/rendicion-de-jornada: Resuelto sin vínculo': servidor(RENDICION, 'test_syn08_resuelto_sin_vinculo_la_rendicion_se_acepta'),
  'stock/rendicion-de-jornada: La entrega del día no se bloquea': servidor(RENDICION, 'test_rut05_la_entrega_del_dia_no_se_bloquea_con_rechazos_pendientes'),
  'stock/rendicion-de-jornada: Rechazos de otra jornada o en cuarentena': servidor(RENDICION, 'test_inv21_rechazos_de_otra_jornada_sin_jornada_otra_organizacion_y_cuarentenas_no_bloquean'),
  'stock/rendicion-de-jornada: Pantalla de conteo con rechazos pendientes': unit(CONTEO, 'con rechazos pendientes avisa cuántos, deshabilita «Registrar rendición» y ofrece «Ver rechazadas» filtrada por la jornada'),
  'stock/rendicion-de-jornada: Sin permiso de revisión': unit(CONTEO, 'sin REVISAR_OBSERVACIONES dice quién las resuelve, no ofrece el acceso y no pide la lista (SEG-06)'),
  'stock/rendicion-de-jornada: Sin rechazos pendientes': unit(CONTEO, 'sin rechazos pendientes no hay aviso y «Registrar rendición» está habilitado'),
  'stock/rendicion-de-jornada: Doble envío de una rendición rechazada': servidor(RENDICION, 'test_inv06_el_mismo_operation_id_se_procesa_de_nuevo_despues_de_resolver'),
  'stock/rendicion-de-jornada: Resolución y rendición a la vez': servidor(CONCURRENCIA, 'class TestResolucionContraRendicion'),
  // sync/bootstrap
  'sync/bootstrap: Venta rechazada resuelta': servidor(BOOTSTRAP, 'test_syn11_trae_el_operation_id_de_la_venta_rechazada_resuelta'),
  'sync/bootstrap: Pendiente o de otra jornada': servidor(BOOTSTRAP, 'test_syn11_un_rechazo_pendiente_no_va'),
  'sync/bootstrap: Doble pedido': servidor(BOOTSTRAP, 'test_syn11_el_doble_pedido_devuelve_la_misma_lista'),
  // sync/cola-local
  'sync/cola-local: Corrección cargada en la oficina': unit(BOOTSTRAP_LOCAL, 'resuelta: ni el stock, ni el debito, ni el cobro en el momento cuentan'),
  'sync/cola-local: Rechazo todavía pendiente': unit(BOOTSTRAP_LOCAL, 'pendiente (no resuelta): la sigue contando completa'),
  'sync/cola-local: Falla al aplicar el bootstrap': unit(BOOTSTRAP_LOCAL, 'una falla a mitad deja la lista anterior y los datos anteriores (INV-01)'),
  'sync/cola-local: Doble actualización': unit(BOOTSTRAP_LOCAL, 'doble actualizacion con el mismo rechazo: deja de contar una sola vez (INV-06)'),
  // sync/cuarentena-de-comandos
  'sync/cuarentena-de-comandos: Revisar la venta de un teléfono dado de baja': servidor(RESOLVER_RECHAZO, 'test_syn06_una_cuarentena_se_resuelve_con_comentario_y_vinculo_sin_crear_nada'),
  'sync/cuarentena-de-comandos: El teléfono dado de baja reenvía': servidor(RESOLVER_RECHAZO, 'test_syn06_el_telefono_dado_de_baja_reenvia_y_sigue_en_dispositivo_revocado'),
  'sync/cuarentena-de-comandos: Ya revisada': servidor(RESOLVER_RECHAZO, 'test_syn06_una_cuarentena_ya_revisada_es_rechazo_ya_resuelto'),
  'sync/cuarentena-de-comandos: Cuarentena de otra organización': servidor(RESOLVER_RECHAZO, 'test_inv21_una_cuarentena_de_otra_organizacion_responde_404'),
  'sync/cuarentena-de-comandos: Solo cambian las columnas de la revisión': servidor(RESOLVER_RECHAZO, 'test_inv05_la_base_impide_cambiar_el_contenido_de_una_cuarentena'),
  // sync/observaciones
  'sync/observaciones: La aplicación no cambia el detalle': servidor(MIGRACION, 'test_inv05_app_runtime_solo_actualiza_la_resolucion_de_la_observacion'),
  'sync/observaciones: Resuelta sin comentario': servidor(MIGRACION, 'test_syn08_una_resolucion_incoherente_se_rechaza_en_la_base'),
  'sync/observaciones: Las de antes del change siguen pendientes': servidor(MIGRACION, 'test_el_ciclo_upgrade_downgrade_upgrade_con_datos'),
  'sync/observaciones: Producto desactivado después del bootstrap': servidor(DESACTIVADO, 'test_syn07_producto_desactivado_se_acepta_con_una_observacion_por_linea'),
  'sync/observaciones: Presentación desactivada': servidor(DESACTIVADO, 'test_syn07_presentacion_desactivada_indica_la_presentacion'),
  'sync/observaciones: Doble envío': servidor(DESACTIVADO, 'test_syn02_inv06_el_doble_envio_no_duplica_la_observacion'),
  // sync/rechazos-sin-conexion
  'sync/rechazos-sin-conexion: Venta con totales incoherentes': servidor(REGISTRO, 'test_syn06_una_venta_con_totales_incoherentes_queda_registrada_con_su_contenido'),
  'sync/rechazos-sin-conexion: Rechazo con fila de comando': servidor(REGISTRO, 'test_syn06_una_anulacion_de_una_venta_inexistente_queda_registrada'),
  'sync/rechazos-sin-conexion: Cobranza con medios que no suman': servidor(REGISTRO, 'test_inv08_una_cobranza_con_medios_que_no_suman_queda_registrada'),
  'sync/rechazos-sin-conexion: Anulación rechazada sin vínculo': servidor(RESOLVER_RECHAZO, 'test_syn08_una_anulacion_rechazada_se_resuelve_solo_con_comentario'),
  'sync/rechazos-sin-conexion: Jornada inexistente': servidor(REGISTRO, 'test_inv21_una_jornada_inexistente_se_registra_sin_jornada'),
  'sync/rechazos-sin-conexion: El rechazo no corta el lote': servidor(REGISTRO, 'test_syn03_el_rechazo_no_corta_el_lote'),
  'sync/rechazos-sin-conexion: Dispositivo revocado y credenciales': servidor(REGISTRO, 'test_syn06_un_dispositivo_revocado_va_solo_a_la_cuarentena'),
  'sync/rechazos-sin-conexion: Doble envío del rechazado': servidor(REGISTRO, 'test_syn02_el_doble_envio_del_rechazado_no_duplica_el_registro'),
  'sync/rechazos-sin-conexion: Otra organización': servidor(RESOLVER_RECHAZO, 'test_inv21_un_rechazo_de_otra_organizacion_o_inexistente_responde_404'),
  'sync/rechazos-sin-conexion: Error transitorio al guardar': servidor(REGISTRO, 'test_syn09_una_falla_transitoria_al_guardar_es_error_transitorio_y_corta_el_lote'),
  'sync/rechazos-sin-conexion: Resumen del contenido': servidor(LISTA, 'test_syn06_la_lista_muestra_cliente_numero_total_y_lineas_de_lo_que_envio_el_telefono'),
  'sync/rechazos-sin-conexion: Contenido con un cliente que no existe': servidor(LISTA, 'test_syn06_un_cliente_que_no_existe_o_es_de_otra_organizacion_se_indica_sin_fallar'),
  'sync/rechazos-sin-conexion: La aplicación no puede borrar un rechazo': servidor(LISTA, 'test_inv05_la_aplicacion_no_puede_borrar_un_rechazo'),
  'sync/rechazos-sin-conexion: Venta rechazada corregida con conexión': servidor(RESOLVER_RECHAZO, 'test_syn08_una_venta_rechazada_se_resuelve_vinculandola_sin_crear_ni_cambiar_nada'),
  'sync/rechazos-sin-conexion: La venta no ocurrió': servidor(RESOLVER_RECHAZO, 'test_syn08_una_venta_que_no_ocurrio_se_resuelve_sin_vinculo'),
  'sync/rechazos-sin-conexion: Vínculo de otro tipo': servidor(RESOLVER_RECHAZO, 'test_syn08_un_vinculo_que_no_corresponde_es_vinculo_invalido_y_nada_cambia'),
  'sync/rechazos-sin-conexion: Vínculo inexistente o ajeno': servidor(RESOLVER_RECHAZO, 'test_inv21_un_vinculo_inexistente_o_de_otra_organizacion_responde_404'),
  'sync/rechazos-sin-conexion: Ya resuelto': servidor(RESOLVER_RECHAZO, 'test_01_18_un_rechazo_ya_resuelto_no_se_resuelve_otra_vez'),
  'sync/rechazos-sin-conexion: Sin permiso': servidor(RESOLVER_RECHAZO, 'test_seg06_sin_el_permiso_responde_403_y_nada_cambia'),
  'sync/rechazos-sin-conexion: Doble envío de la resolución': servidor(RESOLVER_RECHAZO, 'test_inv06_el_doble_envio_devuelve_el_resultado_original_y_audita_una_vez'),
  'sync/rechazos-sin-conexion: Dos resoluciones a la vez': servidor(CONCURRENCIA, 'class TestDosPersonasResuelvenElMismoRechazo'),
  'sync/rechazos-sin-conexion: Resolver el último rechazo de la jornada habilita la rendición': servidor(RENDICION, 'test_syn08_resuelto_sin_vinculo_la_rendicion_se_acepta'),
  'sync/rechazos-sin-conexion: Cantidad pendiente por jornada': servidor(RENDICION, 'test_syn06_el_puerto_cuenta_solo_los_pendientes_de_la_jornada_y_la_organizacion'),
  // sync/revision-de-observaciones
  'sync/revision-de-observaciones: Resolver los avisos de una venta': servidor(RESOLVER_OBS, 'test_resolver_los_avisos_de_una_venta_deja_quien_cuando_y_por_que_sin_tocar_la_operacion'),
  'sync/revision-de-observaciones: Resolución en bloque de varias operaciones': servidor(RESOLVER_OBS, 'test_una_resolucion_en_bloque_resuelve_los_avisos_de_operaciones_distintas'),
  'sync/revision-de-observaciones: Una ya resuelta impide toda la resolución': servidor(RESOLVER_OBS, 'test_una_ya_resuelta_impide_toda_la_resolucion_y_se_nombra'),
  'sync/revision-de-observaciones: Comentario vacío o demasiado largo': servidor(RESOLVER_OBS, 'test_un_comentario_vacio_o_demasiado_largo_se_rechaza_y_nada_cambia'),
  'sync/revision-de-observaciones: Lista vacía, repetida o de más de 100': servidor(RESOLVER_OBS, 'test_una_lista_vacia_repetida_o_de_mas_de_cien_se_rechaza_y_nada_cambia'),
  'sync/revision-de-observaciones: Observación de otra organización': servidor(RESOLVER_OBS, 'test_una_observacion_de_otra_organizacion_responde_404_y_no_se_resuelve_ninguna'),
  'sync/revision-de-observaciones: Sin permiso': servidor(RESOLVER_OBS, 'test_sin_el_permiso_responde_403_y_nada_cambia'),
  'sync/revision-de-observaciones: Doble envío de la resolución': servidor(RESOLVER_OBS, 'test_el_doble_envio_devuelve_el_resultado_original_y_audita_una_sola_vez'),
  'sync/revision-de-observaciones: Dos personas resuelven a la vez': servidor(CONCURRENCIA, 'class TestDosPersonasResuelvenLaMismaObservacion'),
  'sync/revision-de-observaciones: Propiedad de no alteración': servidor(PROPIEDADES, 'test_syn08_resolver_observaciones_de_ventas_no_altera_la_operacion_ni_los_libros'),
  'sync/revision-de-observaciones: Una venta con varios avisos es una sola entrada': servidor(BANDEJA, 'test_una_venta_con_varios_avisos_es_una_sola_entrada'),
  'sync/revision-de-observaciones: El detalle de los descuentos y del crédito': servidor(BANDEJA, 'test_el_detalle_de_los_descuentos_y_del_credito_llega_completo'),
  'sync/revision-de-observaciones: Los nombres de lo que el detalle nombra por id': servidor(NOMBRES, 'test_el_producto_y_el_numero_de_la_linea_llegan_en_los_codigos_que_traen_la_linea'),
  'sync/revision-de-observaciones: Códigos de cobranza, de jornada y de consumidor final': servidor(BANDEJA, 'test_cobranza_jornada_y_consumidor_final_se_filtran_por_su_codigo'),
  'sync/revision-de-observaciones: Filtro por jornada y por vendedor': servidor(BANDEJA, 'test_filtro_por_jornada_por_vendedor_por_tipo_y_por_fechas'),
  'sync/revision-de-observaciones: Otra organización no aparece': servidor(BANDEJA, 'test_otra_organizacion_no_aparece'),
  'sync/revision-de-observaciones: Sin permiso no se lee la bandeja': servidor(BANDEJA, 'test_sin_el_permiso_no_se_lee_la_bandeja'),
  'sync/revision-de-observaciones: Exceso detectado al sincronizar': unit(INICIO, 'los excesos de crédito detectados al sincronizar van aparte, con la bandeja filtrada por ese código (CRE-09)'),
  'sync/revision-de-observaciones: Sin pendientes': unit(INICIO, 'sin nada pendiente dice «Sin avisos pendientes.» y el menú no muestra contador'),
  'sync/revision-de-observaciones: Sin permiso no hay aviso': unit(INICIO, 'sin REVISAR_OBSERVACIONES no hay tarjeta, no se pide el resumen y el inicio sigue llevando a la primera sección'),
}

function escenariosDeLasSpecs(): string[] {
  const nombres = new Set<string>()
  const recorrer = (dir: string, capacidad: string): void => {
    for (const entrada of readdirSync(dir, { withFileTypes: true })) {
      const ruta = resolve(dir, entrada.name)
      if (entrada.isDirectory()) {
        recorrer(ruta, capacidad === '' ? entrada.name : `${capacidad}/${entrada.name}`)
      } else if (entrada.name.endsWith('.md')) {
        for (const linea of readFileSync(ruta, 'utf-8').split(/\r?\n/)) {
          const m = /^#### Scenario: (.+)$/.exec(linea)
          if (m?.[1] !== undefined) nombres.add(`${capacidad}: ${m[1].trim()}`)
        }
      }
    }
  }
  recorrer(carpetaDeSpecs(), '')
  return [...nombres].sort()
}

describe('trazabilidad de las specs delta del 25 (tarea 23.1; SYN-08, INV-01, INV-02, INV-05, INV-06, INV-17, INV-21)', () => {
  it.each(Object.entries(MAPA))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('cada escenario de las nueve specs está en el mapa y el mapa no tiene escenarios inexistentes', () => {
    const reales = escenariosDeLasSpecs()
    expect(reales.length).toBeGreaterThan(70)
    expect(reales.filter((nombre) => !(nombre in MAPA))).toEqual([])
    expect(Object.keys(MAPA).filter((nombre) => !reales.includes(nombre))).toEqual([])
  })

  it('SYN-08, INV-01, INV-02, INV-05, INV-06, INV-17 e INV-21 los cita alguna prueba por su ID (04 §2.1 puntos 2 y 3)', () => {
    const texto = (ruta: string): string => readFileSync(ruta, 'utf-8')
    const citas: Record<string, readonly string[]> = {
      'SYN-08': [resolve(BACKEND, PROPIEDADES), resolve(BACKEND, RESOLVER_OBS), resolve(BACKEND, RESOLVER_RECHAZO), resolve(BACKEND, RENDICION)],
      'INV-01': [resolve(BACKEND, CONCURRENCIA), resolve(BACKEND, RESOLVER_OBS), resolve(BACKEND, RENDICION), resolve(UNIT, BOOTSTRAP_LOCAL)],
      'INV-02': [resolve(BACKEND, MIGRACION), resolve(BACKEND, RESOLVER_OBS), resolve(BACKEND, BANDEJA)],
      'INV-05': [resolve(BACKEND, MIGRACION), resolve(BACKEND, PROPIEDADES), resolve(BACKEND, RESOLVER_RECHAZO)],
      'INV-06': [resolve(BACKEND, CONCURRENCIA), resolve(BACKEND, RESOLVER_RECHAZO), resolve(BACKEND, RENDICION), resolve(UNIT, BOOTSTRAP_LOCAL)],
      'INV-17': [resolve(BACKEND, DESACTIVADO)],
      'INV-21': [resolve(BACKEND, BOOTSTRAP), resolve(BACKEND, RESOLVER_OBS), resolve(BACKEND, RESOLVER_RECHAZO), resolve(BACKEND, BANDEJA)],
    }
    for (const [id, archivos] of Object.entries(citas)) {
      for (const archivo of archivos) {
        expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
        expect(texto(archivo), `${archivo} no cita ${id}`).toContain(id)
      }
    }
  })
})
