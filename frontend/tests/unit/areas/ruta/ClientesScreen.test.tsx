import 'fake-indexeddb/auto'

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { bootstrapDePrueba, clienteDePrueba, ID } from '../../utils/bootstrapDePrueba'
import { montarEnRuta } from '../../utils/rutaDePrueba'

import { ClienteFichaScreen } from '../../../../src/areas/ruta/clientes/ClienteFichaScreen'
import { ClientesScreen } from '../../../../src/areas/ruta/clientes/ClientesScreen'
import { baseLocal } from '../../../../src/lib/dispositivo/db'
import { formatearFechaHora } from '../../../../src/lib/fecha'
import { aplicarBootstrap } from '../../../../src/sync/aplicarBootstrap'

/**
 * Change 21, tarea 14.1 (spec `ruta/area-de-ruta`, "Clientes desde la base local con cartera
 * primero"; cita `01` §19, CRE-01, CLI-02, INV-17, INV-03): consumidor final, luego cartera, luego
 * el resto; la búsqueda recorre todos; marca de suspendido; ficha con saldo y disponible exactos.
 */
function cliente(n: number, nombre: string, cambios: Partial<ReturnType<typeof clienteDePrueba>> = {}) {
  return { ...clienteDePrueba(n, nombre), ...cambios }
}

async function sembrar(clientes = [
  cliente(1, 'Zapatería Zeta'),
  cliente(2, 'Almacén Alfa', { en_cartera: false, documento_numero: '20-12345678-9' }),
  cliente(3, 'Consumidor final', { es_consumidor_final: true, en_cartera: false }),
  cliente(4, 'Kiosco Beta', { estado: 'SUSPENDIDO', en_cartera: false }),
]) {
  const b = bootstrapDePrueba({ clientes })
  await aplicarBootstrap(b)
  return b
}

function montarLista() {
  return montarEnRuta(
    <Routes>
      <Route path="/ruta/clientes" element={<ClientesScreen />} />
      <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
    </Routes>,
    { ruta: '/ruta/clientes' },
  )
}

function nombresEnLista(): string[] {
  return within(screen.getByRole('list')).getAllByRole('listitem').map((li) => li.querySelector('a span')?.textContent ?? '')
}

describe('ClientesScreen (tarea 14.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('lista primero el consumidor final, luego la cartera y al final el resto, con su "(?)"', async () => {
    const b = await sembrar()
    montarLista()

    await screen.findByText('Zapatería Zeta')
    expect(nombresEnLista()).toEqual(['Consumidor final', 'Zapatería Zeta', 'Almacén Alfa', 'Kiosco Beta'])
    expect(screen.getByRole('button', { name: 'Ayuda: Tu cartera de clientes' })).toBeInTheDocument()
    expect(screen.getByText(`Datos de ${formatearFechaHora(b.generado_en)}`)).toBeInTheDocument()
  })

  it('la búsqueda recorre todos los clientes, también los que no son de la cartera', async () => {
    await sembrar()
    montarLista()
    const u = userEvent.setup()

    await u.type(await screen.findByLabelText('Buscar cliente'), 'alfa')
    await waitFor(() => expect(nombresEnLista()).toEqual(['Almacén Alfa']))

    await u.clear(screen.getByLabelText('Buscar cliente'))
    await u.type(screen.getByLabelText('Buscar cliente'), '20123456789')
    await waitFor(() => expect(nombresEnLista()).toEqual(['Almacén Alfa']))

    await u.clear(screen.getByLabelText('Buscar cliente'))
    await u.type(screen.getByLabelText('Buscar cliente'), 'inexistente')
    expect(await screen.findByText(/no hay clientes/i)).toBeInTheDocument()
  })

  it('el cliente suspendido lleva la marca', async () => {
    await sembrar()
    montarLista()

    const fila = (await screen.findByText('Kiosco Beta')).closest('li')
    expect(fila).not.toBeNull()
    expect(within(fila as HTMLElement).getByText('Suspendido')).toBeInTheDocument()
    const otra = screen.getByText('Almacén Alfa').closest('li') as HTMLElement
    expect(within(otra).queryByText('Suspendido')).not.toBeInTheDocument()
  })

  it('sin bootstrap avisa que no hay datos descargados', async () => {
    montarLista()
    expect(await screen.findByText(/todavía no hay datos descargados/i)).toBeInTheDocument()
  })
})

describe('ClienteFichaScreen (tarea 14.1)', () => {
  beforeEach(async () => {
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
  })

  it('muestra contacto, lista aplicable, saldo y disponible exactos, con la hora de los datos (CRE-01, INV-03)', async () => {
    const c = cliente(1, 'Almacén Uno', {
      razon_social: 'Almacén Uno SRL',
      documento_tipo: 'CUIT',
      documento_numero: '30-11111111-2',
      telefono: '11 5555-0000',
      lista_precio_id: ID(50),
      saldo: '125000.00',
      credito: { limite: '500000.00', politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null },
    })
    const b = await sembrar([c])
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${c.id}` },
    )

    expect(await screen.findByRole('heading', { name: 'Almacén Uno' })).toBeInTheDocument()
    expect(screen.getByText('Almacén Uno SRL')).toBeInTheDocument()
    expect(screen.getByText('CUIT 30-11111111-2')).toBeInTheDocument()
    expect(screen.getByText('Calle 1')).toBeInTheDocument()
    expect(screen.getByText('11 5555-0000')).toBeInTheDocument()
    expect(screen.getByText('General')).toBeInTheDocument()
    expect(screen.getByText('$ 125.000,00')).toBeInTheDocument()
    expect(screen.getByText('$ 375.000,00')).toBeInTheDocument()
    expect(screen.getByText(`Datos de ${formatearFechaHora(b.generado_en)}`)).toBeInTheDocument()
  })

  it('sin límite de crédito, el disponible es "Sin límite"; con deuda sobre el límite, queda negativo', async () => {
    const sinLimite = cliente(1, 'Sin Límite', {
      credito: { limite: null, politica: 'PERMITIR', tolerancia_tipo: null, tolerancia_valor: null },
    })
    const excedido = cliente(2, 'Excedido', {
      saldo: '650000.50',
      credito: { limite: '500000.00', politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null },
    })
    await sembrar([sinLimite, excedido])
    const { unmount } = montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${sinLimite.id}` },
    )
    expect(await screen.findAllByText('Sin límite')).toHaveLength(2) // límite y disponible
    unmount()

    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${excedido.id}` },
    )
    expect(await screen.findByText('$ -150.000,50')).toBeInTheDocument()
  })

  it('un cliente suspendido muestra la marca en la ficha', async () => {
    const c = cliente(1, 'Suspendido Uno', { estado: 'SUSPENDIDO' })
    await sembrar([c])
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${c.id}` },
    )
    expect(await screen.findByText('Suspendido')).toBeInTheDocument()
  })

  it('un cliente que no está en la base local avisa y vuelve a la lista', async () => {
    await sembrar([cliente(1, 'Almacén Uno')])
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${ID(999)}` },
    )
    expect(await screen.findByText(/no encontramos ese cliente/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Volver a Clientes' })).toHaveAttribute('href', '/ruta/clientes')
  })

  it('con VENDER y la jornada abierta la ficha ofrece "Vender" a ese cliente (change 22a, D14)', async () => {
    const c = cliente(1, 'Almacén Uno')
    await sembrar([c])
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${c.id}` },
    )

    expect(await screen.findByRole('link', { name: 'Vender' })).toHaveAttribute('href', `/ruta/vender?cliente=${c.id}`)
  })

  it('sin VENDER entre los permisos del bootstrap la ficha no ofrece "Vender"', async () => {
    const c = cliente(1, 'Almacén Uno')
    const b = bootstrapDePrueba({ clientes: [c] })
    b.sesion.permisos = ['CONSULTAR_STOCK']
    await aplicarBootstrap(b)
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${c.id}` },
    )

    expect(await screen.findByRole('heading', { name: 'Almacén Uno' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Vender' })).not.toBeInTheDocument()
  })

  it('con la jornada liberada la ficha no ofrece "Vender"', async () => {
    const c = cliente(1, 'Almacén Uno')
    await sembrar([c])
    montarEnRuta(
      <Routes>
        <Route path="/ruta/clientes/:id" element={<ClienteFichaScreen />} />
      </Routes>,
      { ruta: `/ruta/clientes/${c.id}`, sesion: { entrada: { tipo: 'sin_jornada' } } },
    )

    expect(await screen.findByRole('heading', { name: 'Almacén Uno' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Vender' })).not.toBeInTheDocument()
  })
})
