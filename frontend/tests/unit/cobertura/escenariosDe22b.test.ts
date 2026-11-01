import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 22b, tarea 16.1: trazabilidad de las specs delta. Cada escenario de las siete specs
 * (`identidad/pin-de-autorizacion`, `identidad/sesion-local`, `ruta/area-de-ruta`,
 * `sistema/aplicacion-instalable`, `sistema/ayuda-contextual`, `sync/cola-local`,
 * `sync/motor-de-sincronizacion`) se asocia con la prueba que lo ejercita (archivo y fragmento de
 * su título). Si una prueba se renombra o se borra, esta falla y obliga a revisar la cobertura.
 * Además comprueba que cada escenario de las specs tiene su entrada acá (y ninguna sobra). Cita
 * INV-01 (aplicación de resultados en una sola transacción) e INV-06 (doble envío: cliente y
 * servidor), `04` §2.1 puntos 2 y 3.
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RAIZ = resolve(UNIT, '..', '..', '..')
const BACKEND = resolve(RAIZ, 'backend', 'tests')
const SPECS = resolve(RAIZ, 'openspec', 'changes', '22b-motor-sincronizacion', 'specs')

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const PIN = 'lib/sesionLocal/pinSupervisor.test.ts'
const PIN_PESTANAS = 'lib/sesionLocal/pinSupervisorPestanas.test.ts'
const RENOVACION = 'lib/api/renovacionPestanas.test.ts'
const SELECCION = 'sync/seleccionDeCola.test.ts'
const CICLO = 'sync/sincronizar.test.ts'
const DOBLE = 'sync/dobleSincronizacion.test.ts'
const APLICAR = 'sync/aplicarResultados.test.ts'
const DISPARADORES = 'sync/disparadores.test.ts'
const MINIMA = 'sync/versionMinima.test.ts'
const ESTADO = 'areas/ruta/EstadoDeSincronizacion.test.tsx'
const PANTALLA = 'areas/ruta/SincronizacionScreen.test.tsx'
const INICIO = 'areas/ruta/InicioScreen.test.tsx'
const HOY = 'areas/ruta/ventas/VentasDeHoyScreen.test.tsx'
const VERSION_MINIMA = 'areas/ruta/ventas/VenderVersionMinima.test.tsx'
const AVISO = 'areas/ruta/pwa/AvisoDeVersion.test.tsx'
const GUARDA = 'areas/ruta/ventas/GuardaDelCarrito.test.tsx'
const VENDER = 'areas/ruta/ventas/VenderScreen.test.tsx'
const DISPONIBLES = 'domain/ruta/disponiblesLocales.test.ts'
const AYUDA = 'ayuda/textosRuta.test.ts'
const SERVIDOR_INV06 = 'concurrency/test_inv06_doble_sincronizacion_venta.py'

const MAPA: Record<string, Destino> = {
  // identidad/pin-de-autorizacion
  'PIN correcto sin señal': unit(PIN, 'el PIN correcto verifica contra la derivación'),
  'PIN incorrecto': unit(PIN, 'un PIN incorrecto suma un fallo'),
  'Bloqueo por intentos': unit(PIN, 'con intentos_pin_max fallos el PIN queda bloqueado'),
  'El reloj no levanta el bloqueo': unit(PIN, 'adelantar el reloj del teléfono no levanta el bloqueo'),
  'El bootstrap levanta el bloqueo': unit(PIN, 'cualquier bootstrap nuevo levanta el bloqueo'),
  'Cualquier bootstrap reinicia la cuenta': unit(PIN, 'un bootstrap con otra derivación también reinicia la cuenta'),
  'Supervisor sin el permiso': unit(PIN, 'un autorizador sin el permiso requerido no se verifica'),
  'Intentos simultáneos desde dos pestañas': unit(PIN_PESTANAS, 'tres fallos simultáneos por pestaña con máximo 5'),
  'El bloqueo llega mientras otra pestaña verifica': unit(PIN_PESTANAS, 'toda derivación de más responde «bloqueado»'),
  'Dos supervisores a la vez': unit(PIN_PESTANAS, 'dos supervisores distintos no se esperan entre sí'),
  // identidad/sesion-local
  'Dos pestañas con el access token vencido': unit(RENOVACION, 'dos pestañas con el access vencido piden a la vez'),
  'Reuso real de un refresh token': unit(RENOVACION, 'un reuso real de un refresh ya rotado sigue revocando la familia'),
  // ruta/area-de-ruta
  'Con ventas sin enviar': unit(INICIO, 'con dos ventas confirmadas dice "2 ventas sin enviar"'),
  'Sin datos del día': unit(INICIO, 'sin datos del día "Vender" no está disponible'),
  'Sincronizar a pedido': unit(PANTALLA, 'el botón «Sincronizar» dispara a pedido'),
  'Sincronizar sin señal': unit(ESTADO, 'sin señal informa que requiere conexión'),
  'Lista sin señal': unit(HOY, 'sin señal lista las ventas'),
  'Ventas de otra jornada': unit(HOY, 'las ventas de otra jornada no aparecen'),
  'Estados después de sincronizar': unit(HOY, 'después de sincronizar muestra «Enviada»'),
  'Cabecera con pendientes': unit(ESTADO, 'en cualquier pantalla muestra la conexión y «N sin enviar»'),
  'Cabecera con una rechazada': unit(ESTADO, 'con una rechazada muestra el aviso'),
  'Lista de ventas con problemas': unit(PANTALLA, 'lista las «Con observaciones» y las «Rechazadas»'),
  'Sesión vencida': unit(PANTALLA, 'una sesión vencida pide iniciar sesión con señal'),
  'Sin problemas': unit(PANTALLA, 'con todo enviado dice «Todo enviado»'),
  'Inicio desactualizado': unit(VERSION_MINIMA, 'el inicio deshabilita «Vender»'),
  'Ficha del cliente desactualizada': unit(VERSION_MINIMA, 'la ficha del cliente deshabilita «Vender»'),
  // sistema/aplicacion-instalable
  'Versión nueva con carrito abierto': unit(AVISO, 'con un carrito abierto dice que se instala al terminar la venta'),
  'Después de confirmar': unit(AVISO, 'al confirmar o descartar el carrito vuelve'),
  'Salir con un pedido a medias': unit(GUARDA, 'el menú inferior con líneas pregunta'),
  'Botón atrás con un pedido a medias': unit(GUARDA, 'el botón atrás con líneas pregunta'),
  'Enlace del cuerpo con un pedido a medias': unit(GUARDA, 'un enlace del cuerpo ("Ver más" de una ayuda) con líneas pregunta'),
  'Recargar con un pedido a medias': unit(GUARDA, 'recargar o cerrar la pestaña con líneas pide el aviso del navegador'),
  'Confirmar no pregunta': unit(VENDER, 'se guarda sin llamar a POST /ventas'),
  // sistema/ayuda-contextual
  'Sincronizar': unit(AYUDA, 'ruta.sincronizar: qué envía'),
  'Con observaciones': unit(AYUDA, 'ruta.ventaConObservaciones'),
  'Rechazada': unit(AYUDA, 'ruta.ventaRechazada'),
  'Versión desactualizada': unit(AYUDA, 'ruta.versionMinima'),
  'Trazabilidad': unit('ayuda/trazabilidad.test.ts', 'cada ID de AYUDAS y de TEMAS existe'),
  // sync/cola-local
  'Segunda venta al mismo cliente': unit(DISPONIBLES, 'suma débitos y resta cobranzas'),
  'Stock después de vender': unit(DISPONIBLES, '63 botellas del bootstrap menos una venta de 15 = 48'),
  'Venta ya enviada': unit(APLICAR, '«Venta ya enviada»'),
  'Bootstrap con ventas sin enviar': unit('sync/aplicarBootstrap.test.ts', 'aplicar un bootstrap deja idénticas ventas'),
  'Bloqueo del PIN de desbloqueo': unit('sync/confirmarVentaLocal.test.ts', 'el bloqueo del PIN de desbloqueo no toca las tablas de operaciones'),
  'Resultado recibido': unit(APLICAR, 'nada se borra: venta, cobranza, movimientos y comando siguen'),
  'Venta rechazada visible': unit(HOY, 'después de sincronizar muestra «Enviada», «Con observaciones» y «Rechazada»'),
  // sync/motor-de-sincronizacion
  'Orden de envío': unit(SELECCION, 'elige solo los PENDIENTE del usuario y del dispositivo, de cualquier jornada, por secuencia'),
  'Más de 50 pendientes': unit(SELECCION, 'parte en lotes de 50'),
  'Cola de otro usuario': unit(SELECCION, 'elige solo los PENDIENTE del usuario y del dispositivo'),
  'Venta de una jornada anterior': unit(SELECCION, 'de cualquier jornada'),
  'Un rechazado no se reenvía solo': unit(SELECCION, 'un RECHAZADO no se elige'),
  'Dos pestañas a la vez': unit(DOBLE, '(a) dos «pestañas» disparan a la vez y sale un solo lote'),
  'Venta confirmada durante el envío': unit(CICLO, 'un disparador durante el envío produce UNA vuelta más'),
  'Venta aceptada': unit(APLICAR, 'por operation_id (no por posición)'),
  'Venta con observaciones': unit(APLICAR, 'por operation_id (no por posición)'),
  'Venta rechazada': unit(APLICAR, 'por operation_id (no por posición)'),
  'Corte a mitad del lote': unit(CICLO, 'un ítem ERROR_TRANSITORIO en la respuesta aplica lo demás, corta'),
  'Falla al escribir los resultados': unit(APLICAR, 'es una sola transacción: con una falla después del primer resultado ninguno cambia'),
  'Respuesta perdida': unit(DOBLE, '(b) el servidor procesa y la respuesta se pierde'),
  'Dos lotes simultáneos con la misma venta': servidor(SERVIDOR_INV06, 'dos_lotes_simultaneos_con_la_misma_venta'),
  'Sincronizar dos veces deliberadamente': unit(DOBLE, '(c) «Sincronizar» otra vez con todo aceptado no envía lote'),
  'Sin señal': unit(CICLO, 'corta ante un transitorio dejando el resto pendiente'),
  'Vuelve la señal': unit(DISPARADORES, '«online» la salta'),
  'Error del pedido': unit(CICLO, 'sesión vencida y error del pedido guardan el error'),
  'Sincronización exitosa': unit(CICLO, 'un éxito posterior borra el último error'),
  'Después de una venta': unit(DISPARADORES, 'después de confirmar una venta sincroniza solo si hay conexión'),
  'Cada 2 minutos': unit(DISPARADORES, 'sincroniza cada 2 minutos mientras está abierta'),
  'Sesión bloqueada': unit(DISPARADORES, 'con la sesión bloqueada (disparadores detenidos) no envía'),
  'Vuelta a primer plano': unit(DISPARADORES, 'volver a primer plano la pone en cero y envía en el momento'),
  'Vuelta a primer plano con la sesión bloqueada': unit(DISPARADORES, 'con la sesión bloqueada o sin usuario local «visible» no dispara'),
  'Aplicación oculta': unit(DISPARADORES, '«visible» con la sesión desbloqueada dispara; «hidden» no'),
  'Disparadores durante un envío': unit(DISPARADORES, 'durante un envío propio, varios disparadores'),
  'Aplicación desactualizada con ventas pendientes': unit(MINIMA, 'aunque la app esté por debajo, la cola se envía'),
  'Sin señal después de conocer la mínima': unit(MINIMA, 'sin señal o con error vale la última conocida'),
  'Aviso con el carrito abierto': unit(VERSION_MINIMA, 'con el carrito abierto, si llega el aviso'),
  'Versión sin formato': unit(MINIMA, 'estar por debajo de la mínima solo vale con las dos versiones en formato X.Y.Z'),
}

// Escenarios que se repiten con el mismo nombre en dos specs: el nombre vale para ambas y cada una
// tiene su propia prueba en el mapa. `Sesión vencida` (ruta y motor) y `Ventas de otra jornada`
// (ruta y cola local) se cubren con la prueba de cada pantalla o del ciclo.
const EXTRAS: Record<string, Destino> = {
  'Sesión vencida (motor)': unit(CICLO, 'sesión vencida y error del pedido guardan el error'),
  'Ventas de otra jornada (cola local)': unit(DISPONIBLES, 'no cuenta las operaciones de otra jornada'),
}

function escenariosDeLasSpecs(): string[] {
  const nombres = new Set<string>()
  const recorrer = (dir: string): void => {
    for (const entrada of readdirSync(dir)) {
      const ruta = resolve(dir, entrada)
      if (entrada.endsWith('.md')) {
        for (const linea of readFileSync(ruta, 'utf-8').split(/\r?\n/)) {
          const m = /^#### Scenario: (.+)$/.exec(linea)
          if (m?.[1] !== undefined) nombres.add(m[1].trim())
        }
      } else if (!entrada.includes('.')) recorrer(ruta)
    }
  }
  recorrer(SPECS)
  return [...nombres].sort()
}

describe('trazabilidad de las specs delta del 22b (tarea 16.1; INV-01, INV-06)', () => {
  it.each(Object.entries({ ...MAPA, ...EXTRAS }))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('cada escenario de las siete specs está en el mapa y el mapa no tiene escenarios inexistentes', () => {
    const reales = escenariosDeLasSpecs()
    expect(reales.length).toBeGreaterThan(60)
    expect(reales.filter((nombre) => !(nombre in MAPA))).toEqual([])
    expect(Object.keys(MAPA).filter((nombre) => !reales.includes(nombre))).toEqual([])
  })

  it('la aplicación de resultados cita INV-01 y el doble envío cita INV-06 en el cliente y en el servidor', () => {
    const texto = (archivo: string): string => readFileSync(resolve(UNIT, archivo), 'utf-8')
    expect(texto(APLICAR)).toContain('INV-01')
    expect(texto(DOBLE)).toContain('INV-06')
    expect(texto('areas/ruta/FlujoSincronizacion.test.tsx')).toContain('INV-06')
    expect(readFileSync(resolve(BACKEND, SERVIDOR_INV06), 'utf-8')).toContain('INV-06')
  })
})
