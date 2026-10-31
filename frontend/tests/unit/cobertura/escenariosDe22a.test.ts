import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 22a, tarea 18.1: trazabilidad de las specs delta. Cada requisito y escenario de las siete
 * specs (`identidad/pin-de-autorizacion`, `ruta/area-de-ruta`, `sistema/aplicacion-instalable`,
 * `sync/base-local`, `sync/cola-local`, `ventas/nota-de-venta`, `ventas/venta-en-ruta`) se asocia
 * con la prueba que lo ejercita (archivo y fragmento de su título). Si una prueba se renombra o
 * se borra, esta falla y obliga a revisar la cobertura. Cita INV-01 (confirmación local y
 * bootstrap), INV-03 (importes exactos), INV-04 (cantidades enteras) e INV-06 (reconfirmación y
 * doble envío del sobre).
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const BACKEND = resolve(UNIT, '..', '..', '..', 'backend', 'tests')

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const VENDER = 'areas/ruta/ventas/VenderScreen.test.tsx'
const CONFIRMAR = 'sync/confirmarVentaLocal.test.ts'
const PIN = 'lib/sesionLocal/pinSupervisor.test.ts'
const ARMADO = 'domain/ruta/armadoDeVentaLocal.test.ts'
const REGLAS = 'domain/ruta/reglasDeVentaLocal.test.ts'
const NOTA = 'areas/ruta/ventas/NotaSinSenal.test.tsx'
const AVISO = 'areas/ruta/pwa/AvisoDeVersion.test.tsx'
const CIERRE = 'areas/ruta/sesion/CierreConPendientes.test.tsx'
const INTEGRACION = 'integration/test_contrato_sobre_venta_offline.py'

const MAPA: Record<string, Destino> = {
  // identidad/pin-de-autorizacion
  'El PIN de un supervisor se verifica en el teléfono con límite de intentos': unit(PIN, 'el PIN correcto verifica contra la derivación'),
  'PIN correcto sin señal': unit(PIN, 'el PIN correcto verifica contra la derivación'),
  'PIN incorrecto': unit(PIN, 'un PIN incorrecto suma un fallo'),
  'Bloqueo por intentos': unit(PIN, 'con intentos_pin_max fallos el PIN queda bloqueado'),
  'El reloj no levanta el bloqueo': unit(PIN, 'adelantar el reloj del teléfono no levanta el bloqueo'),
  'El bootstrap levanta el bloqueo': unit(PIN, 'cualquier bootstrap nuevo levanta el bloqueo'),
  'Cualquier bootstrap reinicia la cuenta': unit(PIN, 'un bootstrap con otra derivación también reinicia la cuenta'),
  'Supervisor sin el permiso': unit(PIN, 'un autorizador sin el permiso requerido no se verifica'),
  // ruta/area-de-ruta
  'Lista sin señal': unit('areas/ruta/ventas/VentasDeHoyScreen.test.tsx', 'sin señal lista las ventas'),
  'Cerrar sesión con ventas sin enviar avisa y no borra': unit(CIERRE, 'con una venta sin enviar avisa con el texto de la spec'),
  'Cerrar sesión con pendientes': unit(CIERRE, 'con una venta sin enviar avisa con el texto de la spec'),
  'Otro usuario en el teléfono': unit(CIERRE, 'el login de vendedor2 muestra'),
  // sistema/aplicacion-instalable
  'Una versión nueva no se aplica con un carrito abierto': unit(AVISO, 'con un carrito abierto dice que se instala al terminar la venta'),
  'Versión nueva con carrito abierto': unit(AVISO, 'con un carrito abierto dice que se instala al terminar la venta'),
  'Después de confirmar': unit(AVISO, 'al confirmar o descartar el carrito vuelve'),
  'Salir con un pedido a medias': unit(AVISO, '¿Descartar la venta?'),
  // sync/base-local
  'La base local guarda las operaciones del dispositivo': unit('lib/dispositivo/db.test.ts', 'las tablas de operaciones tienen sus índices'),
  'Actualización de la base': unit('lib/dispositivo/db.test.ts', 'una base v2 con sesión, PIN, dispositivo_id y maestros abre en v3'),
  'El bootstrap no toca las operaciones locales': unit('sync/aplicarBootstrap.test.ts', 'aplicar un bootstrap deja idénticas ventas'),
  'Bootstrap con operaciones pendientes': unit('sync/aplicarBootstrap.test.ts', 'aplicar un bootstrap deja idénticas ventas'),
  'Bootstrap que falla con operaciones pendientes': unit('sync/aplicarBootstrap.test.ts', 'un bootstrap que falla a mitad deja las operaciones'),
  // sync/cola-local
  'Confirmar una venta local es una sola transacción': unit(CONFIRMAR, 'escribe venta, cobranza, movimientos, comando y contadores'),
  'Confirmación completa': unit(CONFIRMAR, 'escribe venta, cobranza, movimientos, comando y contadores'),
  'Falla a mitad de la confirmación': unit(CONFIRMAR, 'una falla al escribir la cola no deja nada'),
  'Doble toque en confirmar': unit(CONFIRMAR, 'reconfirmar con el mismo operation_id no crea otra venta'),
  'Cantidades e importes exactos': unit(CONFIRMAR, 'importes con dos decimales y cantidades enteras'),
  'El número de la venta lo asigna el teléfono al confirmar': unit('domain/ruta/numeracionLocal.test.ts', 'el teléfono va adelante del servidor'),
  'Orden de la cola': unit(CONFIRMAR, 'dos ventas seguidas: número y secuencia crecen sin huecos'),
  'Sin credenciales en la cola': unit('sync/sobre.test.ts', 'nunca incluye PIN ni credenciales'),
  'Contrato con el servidor': servidor(INTEGRACION, 'test_syn05_el_lote_acepta_el_sobre_del_telefono'),
  'Doble envío del mismo sobre': servidor(INTEGRACION, 'el_reenvio_no_duplica'),
  'El saldo y el stock locales suman lo que hizo el teléfono': unit('domain/ruta/disponiblesLocales.test.ts', 'suma débitos y resta cobranzas'),
  'Stock después de vender': unit('domain/ruta/disponiblesLocales.test.ts', '63 botellas del bootstrap menos una venta de 15 = 48'),
  'Bootstrap con ventas sin enviar': unit('domain/ruta/disponiblesLocales.test.ts', 'no cuenta las operaciones con resultado del servidor'),
  // ventas/nota-de-venta
  'La nota de una venta del teléfono se arma con sus datos congelados y sin señal': unit('domain/ventas/notaDesdeLocal.test.ts', 'produce DatosDeNotaDeVenta'),
  'Compartir sin señal': unit(NOTA, 'sin red, "Compartir nota" abre el menú de compartir'),
  'Reimpresión tras un bootstrap': unit(NOTA, 'un bootstrap posterior que cambia la razón social no cambia la nota'),
  // ventas/venta-en-ruta
  'La venta de ruta se confirma siempre en el teléfono': unit(VENDER, 'se guarda sin llamar a POST /ventas'),
  'Sin el permiso de vender': unit(VENDER, 'sin VENDER no hay pantalla de venta'),
  'El pedido usa los precios, los descuentos y las presentaciones del bootstrap': unit(ARMADO, '2 cajas + 3 unidades de Gaseosa'),
  'Pedido en cajas y unidades': unit(ARMADO, '2 cajas + 3 unidades de Gaseosa'),
  'Descuento manual general': unit(ARMADO, '5 % general dentro del tope'),
  'Lista anterior sin permiso': unit(VENDER, 'con una lista distinta al cliente sin USAR_LISTA_ANTERIOR'),
  'Lista anterior sin motivo': unit(VENDER, 'elegir otra versión sin motivo no deja confirmar'),
  'El teléfono aplica las reglas del cliente antes de encolar': unit(REGLAS, 'cliente suspendido'),
  'Cliente suspendido sin permiso': unit(REGLAS, 'sin VENDER_CLIENTE_SUSPENDIDO bloquea'),
  'Consumidor final con cobro de más': unit(REGLAS, 'cobro parcial ($4.000 de $4.300) y cobro de más ($5.000) bloquean'),
  'El stock insuficiente bloquea salvo con PERMITIR_STOCK_NEGATIVO': unit('domain/ruta/stockDeVenta.test.ts', 'sin el permiso, 50 con 48 disponibles bloquea'),
  'Sin el permiso, la línea que supera el stock bloquea': unit(VENDER, 'stock sin PERMITIR_STOCK_NEGATIVO'),
  'Con el permiso, aviso y "Vender igual"': unit(VENDER, 'aviso y "Vender igual"'),
  'Con el permiso, cancela ante el aviso': unit(VENDER, 'con el permiso y sin aceptar "Vender igual" no se confirma nada'),
  'El crédito se evalúa sin conexión con el saldo local': unit(ARMADO, 'el saldo considerado suma las ventas locales de la jornada'),
  'Exceso fuera de la tolerancia': unit(VENDER, 'el supervisor elegido escribe su PIN correcto'),
  'Política advertir sin aceptar': unit(VENDER, 'política ADVERTIR: pide aceptar el exceso'),
  'La venta confirmada se muestra con su número y su estado': unit('areas/ruta/ventas/VentaGuardadaScreen.test.tsx', 'muestra el número asignado, el total'),
}

describe('trazabilidad de las specs delta del 22a (tarea 18.1; INV-01, INV-03, INV-04, INV-06)', () => {
  it.each(Object.entries(MAPA))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('los invariantes INV-01, INV-03, INV-04 e INV-06 se citan por ID', () => {
    const citados = new Set<string>()
    for (const [archivo] of Object.values(MAPA)) {
      const texto = readFileSync(archivo, 'utf-8')
      for (const inv of ['INV-01', 'INV-03', 'INV-04', 'INV-06']) if (texto.includes(inv)) citados.add(inv)
    }
    expect([...citados].sort()).toEqual(['INV-01', 'INV-03', 'INV-04', 'INV-06'])
  })
})
