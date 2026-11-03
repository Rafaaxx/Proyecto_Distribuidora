import 'fake-indexeddb/auto'

import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { components } from '../../../../src/api/schema.gen'

const mocks = vi.hoisted(() => ({ dispararTrasVenta: vi.fn() }))
vi.mock('../../../../src/sync/disparadores', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../../src/sync/disparadores')>()
  return { ...real, dispararTrasVenta: mocks.dispararTrasVenta }
})

import { AnularVentaScreen } from '../../../../src/areas/ruta/ventas/AnularVentaScreen'
import { VentaGuardadaScreen } from '../../../../src/areas/ruta/ventas/VentaGuardadaScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'
import { marcarJornadaNoAbierta } from '../../../../src/sync/estadoDeJornada'
import { ID } from '../../utils/bootstrapDePrueba'
import { bootstrapParaVender } from '../../utils/datosParaVender'
import { montarEnRuta } from '../../utils/rutaDePrueba'
import { sembrarVenta } from '../../utils/sembrarVenta'

type Bootstrap = components['schemas']['BootstrapResponse']

/**
 * Change 22d, tarea 10.1 (spec `ruta/area-de-ruta`, «Una venta de la jornada se anula desde el
 * teléfono», sus ocho escenarios; `design.md` D5, D10; cita VTA-20, VTA-22, VTA-24, CLI-03,
 * SEG-06, INV-06, RUT-09): la pantalla `/ruta/ventas/:id/anular` y el botón «Anular venta» del
 * detalle.
 */
const ERROR_DE_CARGA = ID(70)
const OTRO_MOTIVO = ID(71)

function bootstrapConAnulacion(cambios: (b: Bootstrap) => void = () => undefined): Bootstrap {
  return bootstrapParaVender((b) => {
    b.sesion.permisos = ['VENDER', 'ANULAR_VENTA']
    b.catalogos.motivos = [
      ...b.catalogos.motivos,
      { id: ERROR_DE_CARGA, ambito: 'ANULACION_VENTA', nombre: 'Error de carga' },
      { id: OTRO_MOTIVO, ambito: 'ANULACION_VENTA', nombre: 'El cliente se arrepintió' },
    ]
    cambios(b)
  })
}

function montarAnular(ventaId: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/ventas/:id/anular" element={<AnularVentaScreen />} />
      <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
    </Routes>,
    { ruta: `/ruta/ventas/${ventaId}/anular` },
  )
}

function montarDetalle(ventaId: string) {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/ventas/:id/anular" element={<p>Pantalla de anulación</p>} />
      <Route path="/ruta/ventas/:id" element={<VentaGuardadaScreen />} />
    </Routes>,
    { ruta: `/ruta/ventas/${ventaId}` },
  )
}

describe('«Anular venta» en el detalle (tarea 10.1, D5)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('con ANULAR_VENTA y una venta de la jornada se ofrece y lleva a la pantalla de anulación (VTA-24)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')

    montarDetalle('venta-a')

    const enlace = await screen.findByRole('link', { name: 'Anular venta' })
    expect(enlace).toHaveAttribute('href', '/ruta/ventas/venta-a/anular')
    expect(screen.getByRole('button', { name: /ayuda: anular una venta/i })).toBeInTheDocument()
  })

  it('sin ANULAR_VENTA no se ofrece (SEG-06)', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a')

    montarDetalle('venta-a')

    await screen.findByRole('heading', { name: /Venta 0001-000008/ })
    expect(screen.queryByRole('link', { name: 'Anular venta' })).not.toBeInTheDocument()
  })

  it('una venta rechazada no se ofrece', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    await baseLocal.ventas.update('venta-a', { estado_envio: 'RECHAZADA' })

    montarDetalle('venta-a')

    await screen.findByRole('heading', { name: /Venta 0001-000008/ })
    expect(screen.queryByRole('link', { name: 'Anular venta' })).not.toBeInTheDocument()
  })

  it('una venta de una jornada anterior guardada en el teléfono no se ofrece', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    await baseLocal.ventas.update('venta-a', { jornada_id: 'jornada-anterior' })

    montarDetalle('venta-a')

    await screen.findByRole('heading', { name: /Venta 0001-000008/ })
    expect(screen.queryByRole('link', { name: 'Anular venta' })).not.toBeInTheDocument()
  })

  it('con la jornada guardada como liberada no se ofrece (RUT-09)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    await marcarJornadaNoAbierta(ID(2), 'LIBERADA', new Date('2026-11-03T12:00:00.000Z'))

    montarDetalle('venta-a')

    await screen.findByRole('heading', { name: /Venta 0001-000008/ })
    expect(screen.queryByRole('link', { name: 'Anular venta' })).not.toBeInTheDocument()
  })

  it('una venta que ya tiene su anulación no la ofrece de nuevo', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    const u = userEvent.setup()
    const { unmount } = montarAnular('venta-a')
    await u.selectOptions(await screen.findByLabelText('Motivo'), ERROR_DE_CARGA)
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    await u.click(await screen.findByRole('button', { name: 'Confirmar anulación' }))
    await screen.findByText('Anulada')
    unmount()

    montarDetalle('venta-a')

    await screen.findByText('Anulada')
    expect(screen.queryByRole('link', { name: 'Anular venta' })).not.toBeInTheDocument()
  })
})

describe('pantalla de anulación (tarea 10.1, D5, D10)', () => {
  beforeEach(async () => {
    mocks.dispararTrasVenta.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('anular sin señal: motivo, confirmación «¿Anular la venta …?» y queda «Anulada» y «Sin enviar» (VTA-24)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    const u = userEvent.setup()
    montarAnular('venta-a')

    const motivo = await screen.findByLabelText('Motivo')
    // Solo los motivos del ámbito de la anulación (no «Promo», que es de descuento).
    expect(screen.queryByRole('option', { name: 'Promo' })).not.toBeInTheDocument()
    await u.selectOptions(motivo, ERROR_DE_CARGA)
    await u.type(screen.getByLabelText('Observación (opcional)'), 'Se cargó dos veces')
    await u.click(screen.getByRole('button', { name: 'Continuar' }))

    expect(await screen.findByRole('dialog', { name: '¿Anular la venta 0001-000008?' })).toBeInTheDocument()
    expect(await baseLocal.anulaciones.count()).toBe(0)
    await u.click(screen.getByRole('button', { name: 'Confirmar anulación' }))

    expect(await screen.findByRole('heading', { name: /Venta 0001-000008/ })).toBeInTheDocument()
    expect(await screen.findByText('Anulada')).toBeInTheDocument()
    expect(await baseLocal.anulaciones.get('venta-a')).toMatchObject({
      motivo_id: ERROR_DE_CARGA,
      motivo_nombre: 'Error de carga',
      observacion: 'Se cargó dos veces',
      devuelve_dinero: null,
      estado_envio: 'PENDIENTE',
    })
    expect(mocks.dispararTrasVenta).toHaveBeenCalledTimes(1)
  })

  it('cancelar la confirmación no escribe nada', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    const u = userEvent.setup()
    montarAnular('venta-a')

    await u.selectOptions(await screen.findByLabelText('Motivo'), OTRO_MOTIVO)
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    await u.click(await screen.findByRole('button', { name: 'Cancelar' }))

    expect(await baseLocal.anulaciones.count()).toBe(0)
    expect(await baseLocal.cola.count()).toBe(1)
    expect(mocks.dispararTrasVenta).not.toHaveBeenCalled()
  })

  it('sin motivo no se confirma y se indica qué falta (VTA-20)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    const u = userEvent.setup()
    montarAnular('venta-a')

    await u.click(await screen.findByRole('button', { name: 'Continuar' }))

    expect(screen.getByText('Elegí un motivo.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await baseLocal.anulaciones.count()).toBe(0)
  })

  it('una observación de 501 caracteres no se confirma; de 500 sí (VTA-20)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    const u = userEvent.setup()
    montarAnular('venta-a')

    await u.selectOptions(await screen.findByLabelText('Motivo'), ERROR_DE_CARGA)
    fireEvent.change(screen.getByLabelText('Observación (opcional)'), { target: { value: 'a'.repeat(501) } })
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(screen.getByText('La observación admite hasta 500 caracteres.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Observación (opcional)'), { target: { value: 'a'.repeat(500) } })
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('una venta con cobro en el acto exige elegir si se devuelve (VTA-22)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a', { cobro: '30000.00' })
    const u = userEvent.setup()
    montarAnular('venta-a')

    await u.selectOptions(await screen.findByLabelText('Motivo'), ERROR_DE_CARGA)
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(screen.getByText('Indicá si devolvés lo cobrado.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await u.click(screen.getByRole('radio', { name: /No, queda a favor del cliente/ }))
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    await u.click(await screen.findByRole('button', { name: 'Confirmar anulación' }))

    await screen.findByText('Anulada')
    expect(await baseLocal.anulaciones.get('venta-a')).toMatchObject({ devuelve_dinero: false })
  })

  it('devolver lo cobrado se guarda como sí (VTA-22)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a', { cobro: '30000.00' })
    const u = userEvent.setup()
    montarAnular('venta-a')

    await u.selectOptions(await screen.findByLabelText('Motivo'), ERROR_DE_CARGA)
    await u.click(screen.getByRole('radio', { name: /Sí, devuelvo el dinero/ }))
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    await u.click(await screen.findByRole('button', { name: 'Confirmar anulación' }))

    await screen.findByText('Anulada')
    expect(await baseLocal.anulaciones.get('venta-a')).toMatchObject({ devuelve_dinero: true })
  })

  it('al consumidor final la devolución figura elegida y no se puede cambiar (CLI-03, VTA-22)', async () => {
    await aplicarBootstrap(
      bootstrapConAnulacion((b) => {
        const cliente = b.clientes[0]
        if (cliente) cliente.es_consumidor_final = true
      }),
    )
    await sembrarVenta('a', { cobro: '120000.00' })
    const u = userEvent.setup()
    montarAnular('venta-a')

    await u.selectOptions(await screen.findByLabelText('Motivo'), ERROR_DE_CARGA)
    expect(screen.getByTestId('devolucion-fija')).toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    await u.click(await screen.findByRole('button', { name: 'Confirmar anulación' }))

    await screen.findByText('Anulada')
    expect(await baseLocal.anulaciones.get('venta-a')).toMatchObject({ devuelve_dinero: true })
  })

  it('una venta sin cobro no pregunta la devolución', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    montarAnular('venta-a')

    await screen.findByLabelText('Motivo')

    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByTestId('devolucion-fija')).not.toBeInTheDocument()
  })

  it('doble toque en «Confirmar anulación»: una sola anulación y un solo comando (INV-06)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    const u = userEvent.setup()
    montarAnular('venta-a')

    await u.selectOptions(await screen.findByLabelText('Motivo'), ERROR_DE_CARGA)
    await u.click(screen.getByRole('button', { name: 'Continuar' }))
    await u.dblClick(await screen.findByRole('button', { name: 'Confirmar anulación' }))

    await screen.findByText('Anulada')
    expect(await baseLocal.anulaciones.count()).toBe(1)
    const operacion = (await baseLocal.anulaciones.get('venta-a'))?.operation_id ?? ''
    expect(await baseLocal.cola.where('operation_id').equals(operacion).count()).toBe(1)
    expect(await baseLocal.cola.count()).toBe(2)
  })

  it('una venta que no se puede anular no muestra el formulario (sin permiso)', async () => {
    await aplicarBootstrap(bootstrapParaVender())
    await sembrarVenta('a')
    montarAnular('venta-a')

    expect(await screen.findByText('Esta venta no se puede anular desde el teléfono.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Motivo')).not.toBeInTheDocument()
  })

  it('con la jornada liberada tampoco muestra el formulario (RUT-09)', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a')
    await marcarJornadaNoAbierta(ID(2), 'LIBERADA', new Date('2026-11-03T12:00:00.000Z'))
    montarAnular('venta-a')

    expect(await screen.findByText('Esta venta no se puede anular desde el teléfono.')).toBeInTheDocument()
    expect(screen.getByText('Tu jornada fue liberada.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Motivo')).not.toBeInTheDocument()
  })

  it('una venta que no está en el teléfono avisa', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    montarAnular('no-existe')

    await waitFor(() => expect(screen.getByText('No encontramos esa venta en este teléfono.')).toBeInTheDocument())
  })

  it('lleva las ayudas del motivo y de la devolución', async () => {
    await aplicarBootstrap(bootstrapConAnulacion())
    await sembrarVenta('a', { cobro: '30000.00' })
    montarAnular('venta-a')

    await screen.findByLabelText('Motivo')

    expect(screen.getByRole('button', { name: /ayuda: motivo/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: ¿devolvés lo que cobraste/i })).toBeInTheDocument()
  })
})
