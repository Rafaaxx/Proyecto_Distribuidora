import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 23, tarea 16.1: trazabilidad de las specs delta. Cada escenario de las seis specs
 * (`ruta/area-de-ruta`, `sistema/ayuda-contextual`, `sync/base-local`, `sync/cola-local`,
 * `sync/lote-de-comandos`, `sync/motor-de-sincronizacion`) se asocia con la prueba que lo ejercita
 * (archivo y fragmento de su título); los del servidor apuntan a su archivo de `backend/tests`.
 * Varios nombres se repiten entre specs («Doble sincronización», «Cobranza rechazada»...), por eso
 * la clave lleva la capacidad. Si una prueba se renombra o se borra, esta falla y obliga a revisar
 * la cobertura. Además comprueba que cada escenario de las specs tiene su entrada acá (y ninguna
 * sobra) y que INV-01, INV-05, INV-06, INV-08, INV-17 e INV-21 los cita alguna prueba por su ID
 * (`04` §2.1 puntos 2 y 3).
 *
 * Las specs se leen de la carpeta del change mientras está activo y, una vez archivado, de la del
 * archivo (el nombre lleva la fecha del archivo).
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RAIZ = resolve(UNIT, '..', '..', '..')
const BACKEND = resolve(RAIZ, 'backend', 'tests')
const CAMBIOS = resolve(RAIZ, 'openspec', 'changes')

function carpetaDeSpecs(): string {
  const activa = resolve(CAMBIOS, '23-cobranza-offline', 'specs')
  if (existsSync(activa)) return activa
  const archivados = resolve(CAMBIOS, 'archive')
  const nombre = readdirSync(archivados).find((n) => n.endsWith('-23-cobranza-offline'))
  if (nombre === undefined) throw new Error('No se encontró el change 23 ni activo ni archivado')
  return resolve(archivados, nombre, 'specs')
}

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const COBRAR = 'areas/ruta/CobrarScreen.test.tsx'
const CORTE = 'areas/ruta/CobrarSeCorta.test.tsx'
const GUARDADA = 'areas/ruta/cobranzas/CobranzaGuardadaYDeHoy.test.tsx'
const PANTALLA = 'areas/ruta/SincronizacionScreen.test.tsx'
const CIERRE = 'areas/ruta/sesion/CierreConPendientes.test.tsx'
const AYUDA = 'ayuda/textosRuta.test.ts'
const DB = 'lib/dispositivo/db.test.ts'
const BOOTSTRAP = 'sync/aplicarBootstrap.test.ts'
const COLA = 'sync/registrarCobranzaLocal.test.ts'
const DISPONIBLES = 'domain/ruta/disponiblesLocales.test.ts'
const APLICAR = 'sync/aplicarResultados.test.ts'

const LOTE = 'integration/test_cobranza_offline_desde_telefono.py'
const CODIGOS = 'unit/test_fixture_codigos_de_sincronizacion.py'

const MAPA: Record<string, Destino> = {
  // ruta/area-de-ruta
  'ruta/area-de-ruta: Cobrar sin señal': unit(COBRAR, 'cobra sin señal con dos medios (uno con referencia): guarda, encola, dispara el envío'),
  'ruta/area-de-ruta: Medios que no suman el importe': unit(COBRAR, 'los medios que no suman el importe no confirman y se indica la diferencia (INV-08, COB-02)'),
  'ruta/area-de-ruta: Referencia exigida': unit(COBRAR, 'un medio que exige referencia sin ella (%j) no confirma y se pide la referencia'),
  'ruta/area-de-ruta: Importe inválido': unit(COBRAR, 'el importe %j no confirma (COB-01, INV-03)'),
  'ruta/area-de-ruta: Saldo a favor': unit(COBRAR, 'si el saldo resultante queda a favor, avisa «El cliente queda con {importe} a favor.»'),
  'ruta/area-de-ruta: Consumidor final': unit(COBRAR, 'el consumidor final pedido por la dirección no se cobra (CLI-03)'),
  'ruta/area-de-ruta: Cliente suspendido o fuera de la cartera': unit(COBRAR, 'cobra a un cliente suspendido que no está en la cartera sin aviso'),
  'ruta/area-de-ruta: Sin permiso': unit(COBRAR, 'sin REGISTRAR_COBRANZA no se puede cobrar (SYN-10, SEG-06)'),
  'ruta/area-de-ruta: Salir con datos cargados': unit(COBRAR, 'con un importe cargado, salir pregunta «¿Descartar la cobranza?»'),
  'ruta/area-de-ruta: Cobranzas de hoy': unit(GUARDADA, 'lista las cobranzas de la jornada con cliente, importe, hora y estado, la más nueva primero'),
  'ruta/area-de-ruta: Cobranza con observaciones': unit(GUARDADA, 'una cobranza con observaciones (MEDIO_INACTIVO sobre «Billetera») dice «Con observaciones»'),
  'ruta/area-de-ruta: Cobranza rechazada en Sincronización': unit(PANTALLA, 'una cobranza rechazada se lista como «Cobranza a {cliente}» con su texto'),
  'ruta/area-de-ruta: Código desconocido': unit(GUARDADA, 'un código desconocido muestra el texto general de la cobranza y el código'),
  'ruta/area-de-ruta: Pendientes': unit(PANTALLA, 'dos ventas, una anulación y una cobranza sin enviar: «2 ventas, 1 anulación y 1 cobranza sin enviar»'),
  'ruta/area-de-ruta: Solo cobranzas pendientes': unit(CIERRE, 'tres cobranzas sin enviar y nada más: otro usuario que inicia sesión ve «Hay 3 cobranzas sin enviar de {vendedor}.»'),
  'ruta/area-de-ruta: Doble sincronización': unit(GUARDADA, 'actualizar los resultados dos veces con lo mismo no cambia la lista (INV-06)'),
  'ruta/area-de-ruta: Jornada liberada': unit(CORTE, 'con la jornada %s «Cobrar» queda deshabilitado y se lee'),
  'ruta/area-de-ruta: Formulario abierto cuando se corta': unit(CORTE, 'con el formulario abierto, si el teléfono se entera «Confirmar cobranza» no guarda'),
  'ruta/area-de-ruta: Versión por debajo de la mínima': unit(CORTE, 'por debajo de la versión mínima «Cobrar» está deshabilitado con el aviso de versión'),
  'ruta/area-de-ruta: Sin dato guardado': unit(CORTE, 'sin dato guardado y con la versión al día «Cobrar» funciona como siempre'),
  // sistema/ayuda-contextual
  'sistema/ayuda-contextual: Ayuda de la pantalla de cobro': unit(AYUDA, 'ruta.cobrar: registra un pago también sin señal'),
  'sistema/ayuda-contextual: Ayuda de una cobranza rechazada': unit(AYUDA, 'ruta.cobranzaRechazada: el motivo está en el detalle'),
  'sistema/ayuda-contextual: Textos revisados': unit(AYUDA, 'las cinco revisadas nombran también las cobranzas y citan ADR-067'),
  'sistema/ayuda-contextual: Clave o ID inexistente': unit('ayuda/trazabilidad.test.ts', 'cada clave de <Ayuda clave> y de ayuda= existe en AYUDAS'),
  // sync/base-local
  'sync/base-local: Actualización de la base': unit(DB, 'una base v4 con sesión, PIN, datos, dos ventas con cobro, una anulación y la cola abre en v5 sin perder nada'),
  'sync/base-local: Bootstrap con cobranzas pendientes': unit(BOOTSTRAP, 'un bootstrap con una cobranza sin enviar la deja con su movimiento y su comando'),
  'sync/base-local: Cerrar sesión con una cobranza pendiente': unit(BOOTSTRAP, 'cerrar la sesión local no borra una cobranza rechazada (SYN-09)'),
  // sync/cola-local
  'sync/cola-local: Cobranza local': unit(COLA, 'escribe la cobranza «Sin enviar», un crédito al cliente y el comando COBRANZA_REGISTRAR OFFLINE con la secuencia 8'),
  'sync/cola-local: Falla a mitad de la cobranza': unit(COLA, 'falla a mitad: no queda cobranza, movimiento ni comando y la secuencia no avanza (INV-01)'),
  'sync/cola-local: Doble toque': unit(COLA, 'reconfirmar la misma cobranza devuelve la existente sin escribir nada (INV-06, SYN-02)'),
  'sync/cola-local: Cobranza después de una venta sin enviar': unit(COLA, 'detrás de una venta «Sin enviar»: venta 1, cobranza 2 y se envían en ese orden (SYN-03)'),
  'sync/cola-local: Crédito después de cobrar': unit(DISPONIBLES, 'saldo 150.000 y una cobranza de 50.000 sin enviar: saldo 100.000 y disponible 100.000 con límite 200.000'),
  'sync/cola-local: Cobranza incluida en el bootstrap': unit(DISPONIBLES, 'incluida en el bootstrap (marca 8, saldo 100.000) no se cuenta dos veces: 100.000 y no 50.000'),
  'sync/cola-local: Cobranza pendiente después de actualizar los datos': unit(DISPONIBLES, 'pendiente después de actualizar los datos (marca 7, saldo 150.000, secuencia 8): 100.000'),
  'sync/cola-local: Cobranza rechazada': unit(DISPONIBLES, 'rechazada: no cuenta, con o sin marca que la cubra (CRE-08, SYN-06)'),
  'sync/cola-local: El cobro de una venta rechazada sigue con su venta': unit(DISPONIBLES, 'el cobro de una venta rechazada sigue contando completo con su venta (CRE-08, ADR-065)'),
  'sync/cola-local: Saldo a favor': unit(DISPONIBLES, 'saldo a favor: debe 150.000, cobra 160.000 y queda -10.000 (COB-01, CC-04)'),
  'sync/cola-local: Doble sincronización': unit(DISPONIBLES, 'doble sincronización: el mismo resultado dos veces no cambia el saldo (INV-06, SYN-02)'),
  // sync/lote-de-comandos
  'sync/lote-de-comandos: Sobre del teléfono aceptado': servidor(LOTE, 'test_cob01_el_sobre_del_fixture_se_acepta_con_la_jornada_del_sobre'),
  'sync/lote-de-comandos: Venta y cobranza en el mismo lote': servidor(LOTE, 'test_syn03_venta_y_cobranza_del_mismo_cliente_se_procesan_en_orden'),
  'sync/lote-de-comandos: Cliente inexistente': servidor(LOTE, 'test_inv21_un_cliente_inexistente_se_rechaza_sin_efectos_y_el_lote_sigue'),
  'sync/lote-de-comandos: Medios que no suman el importe': servidor(LOTE, 'test_inv08_medios_que_no_suman_el_importe_se_rechazan_sin_efectos'),
  'sync/lote-de-comandos: Doble envío': servidor(LOTE, 'test_inv06_el_doble_envio_devuelve_lo_mismo_y_el_saldo_baja_una_sola_vez'),
  'sync/lote-de-comandos: Lista cerrada de rechazos de la cobranza': servidor(CODIGOS, 'test_syn06_los_rechazos_de_la_cobranza_son_el_bus_mas_registrar_cobranza'),
  // sync/motor-de-sincronizacion
  'sync/motor-de-sincronizacion: Cobranza aceptada': unit(APLICAR, 'aceptada: la cobranza y su comando quedan «Enviada» y ninguna venta ni cobro de venta cambia'),
  'sync/motor-de-sincronizacion: Cobranza con observaciones': unit(APLICAR, 'con observaciones: queda «Con observaciones» y el comando guarda la observación con su detalle'),
  'sync/motor-de-sincronizacion: Cobranza rechazada': unit(APLICAR, 'rechazada: queda «Rechazada» con su código, sigue visible y no vuelve a la selección de envío'),
  'sync/motor-de-sincronizacion: Jornada liberada': unit(APLICAR, '«JORNADA_LIBERADA» sobre la cobranza marca la jornada como liberada (RUT-09, SYN-07)'),
  'sync/motor-de-sincronizacion: Falla al escribir el resultado': unit(APLICAR, 'falla a mitad de la respuesta: ni la cobranza ni la venta cambian'),
  'sync/motor-de-sincronizacion: Reenvío': unit(APLICAR, 'reenvío: el mismo resultado otra vez no cambia la cobranza, su comando ni sus observaciones (INV-06, SYN-02)'),
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

describe('trazabilidad de las specs delta del 23 (tarea 16.1; INV-01, INV-05, INV-06, INV-08, INV-17, INV-21)', () => {
  it.each(Object.entries(MAPA))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('cada escenario de las seis specs está en el mapa y el mapa no tiene escenarios inexistentes', () => {
    const reales = escenariosDeLasSpecs()
    expect(reales.length).toBeGreaterThan(45)
    expect(reales.filter((nombre) => !(nombre in MAPA))).toEqual([])
    expect(Object.keys(MAPA).filter((nombre) => !reales.includes(nombre))).toEqual([])
  })

  it('INV-01, INV-05, INV-06, INV-08, INV-17 e INV-21 los cita alguna prueba por su ID (04 §2.1 puntos 2 y 3)', () => {
    const texto = (ruta: string): string => readFileSync(ruta, 'utf-8')
    expect(texto(resolve(UNIT, COLA))).toContain('INV-01')
    expect(texto(resolve(UNIT, DB))).toContain('INV-05')
    expect(texto(resolve(UNIT, 'areas/ruta/FlujoCobranzaSinConexion.test.tsx'))).toContain('INV-06')
    expect(texto(resolve(UNIT, 'areas/ruta/FlujoCobranzaSinConexion.test.tsx'))).toContain('INV-08')
    expect(texto(resolve(BACKEND, LOTE))).toContain('INV-08')
    expect(texto(resolve(BACKEND, LOTE))).toContain('INV-17')
    expect(texto(resolve(BACKEND, LOTE))).toContain('INV-21')
  })
})
