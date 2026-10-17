/**
 * Change 17b, tarea 11.1: los "(?)" de "Medios de pago" y de "Roles y permisos" (spec
 * `sistema/ayuda-contextual`, requisito "Las pantallas de medios de pago y de roles explican sus
 * reglas"; `design.md` D12; ADR-051). Los textos son los aprobados por el usuario el 2026-10-17
 * (los corregidos a mano: el 3 sin nombre de persona, el 4 sin ejemplo).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../src/areas/admin/configuracion/ConfiguracionArea'
import RolesArea from '../../../../src/areas/admin/roles/RolesArea'
import { AYUDAS } from '../../../../src/ayuda/textos'
import { enrutar } from '../../utils/enrutarApi'
import { queryClientConYo } from '../../utils/permisosDePrueba'

const ROL = '22222222-2222-4222-8222-222222222222'

function servidor() {
  enrutar(apiFetchMock, [
    {
      metodo: 'GET',
      ruta: '/configuracion/medios-pago/todos',
      responder: () => ({
        status: 200,
        cuerpo: {
          items: [
            { id: '11111111-1111-4111-8111-111111111111', nombre: 'Efectivo', requiere_referencia: false, activo: true, actualizado_en: '2026-10-17T12:00:00Z' },
          ],
        },
      }),
    },
    {
      metodo: 'GET',
      ruta: '/identidad/roles',
      responder: () => ({
        status: 200,
        cuerpo: [
          { id: ROL, nombre: 'Supervisor comercial', activo: true, tope_descuento: '0.000000', permisos: ['AUTORIZAR_DESCUENTO', 'ANULAR_COBRANZA'], usuarios_activos: 2 },
        ],
      }),
    },
    {
      metodo: 'GET',
      ruta: '/identidad/permisos',
      responder: () => ({
        status: 200,
        cuerpo: [
          { codigo: 'ADMIN_USUARIOS', descripcion: 'Usuarios, roles y permisos', modulo: 'identidad' },
          { codigo: 'ANULAR_COBRANZA', descripcion: 'Anular cobranzas', modulo: 'cobranzas' },
          { codigo: 'AUTORIZAR_DESCUENTO', descripcion: 'Superar tope de descuento', modulo: 'ventas' },
        ],
      }),
    },
  ])
}

function montar(ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('ADM')}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
          <Route path="/admin/roles/*" element={<RolesArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Abre el "(?)" `Ayuda: <titulo>` y devuelve el panel que se despliega. */
async function abrirAyuda(titulo: string): Promise<HTMLElement> {
  const usuario = userEvent.setup()
  await usuario.click(screen.getAllByRole('button', { name: `Ayuda: ${titulo}` })[0] as HTMLElement)
  const boton = screen.getAllByRole('button', { name: `Ayuda: ${titulo}` })[0] as HTMLElement
  return document.getElementById(boton.getAttribute('aria-controls') as string) as HTMLElement
}

describe('ayuda contextual de medios de pago y roles (tarea 11.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    servidor()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('textos aprobados el 2026-10-17', () => {
    it('Pide referencia: el dato que se anota, qué pasa con y sin conexión y el ejemplo de $20.000 por la transferencia n.º 0042', () => {
      const ayuda = AYUDAS['mediosPago.requiereReferencia']

      expect(ayuda.texto).toContain('como el número de la transferencia o del cheque')
      expect(ayuda.texto).toContain('Con conexión, sin ese dato no se guarda el cobro ni el pago')
      expect(ayuda.texto).toContain('si el vendedor está sin señal, entra igual y queda marcado para revisar')
      expect(ayuda.ejemplo).toContain('al cobrar $20.000 por transferencia hay que escribir el n.º 0042')
      expect(ayuda.reglas).toEqual(['COB-02', 'PAG-01', 'SYN-07'])
    })

    it('Dar de baja: deja de ofrecerse, no se borra, se reactiva y siempre queda uno activo', () => {
      const ayuda = AYUDAS['mediosPago.baja']

      expect(ayuda.texto).toContain('Deja de ofrecerse en cobros y pagos nuevos')
      expect(ayuda.texto).toContain('No se borra')
      expect(ayuda.texto).toContain('Siempre tiene que quedar al menos un medio activo')
      expect(ayuda.ejemplo).toContain('el pago de $10.000 de ayer sigue diciendo «Billetera»')
      expect(ayuda.reglas).toEqual(['CAT-05', 'TR-06', 'ADR-053'])
    })

    it('Permisos del rol: vale desde la próxima acción, sin nombre de persona (corrección del usuario)', () => {
      const ayuda = AYUDAS['roles.permisos']

      expect(ayuda.texto).toContain('el cambio vale para todos los usuarios del rol desde su próxima acción, sin cerrar la sesión')
      expect(ayuda.ejemplo).toBe('Ej.: le quitás «Anular cobranzas» al Supervisor comercial → ya no ven el botón «Anular» en las cobranzas.')
      expect(ayuda.reglas).toEqual(['ADR-017'])
    })

    it('Último administrador: sin ejemplo (corrección del usuario)', () => {
      const ayuda = AYUDAS['roles.ultimoAdministrador']

      expect(ayuda.texto).toBe(
        'Siempre tiene que quedar al menos una persona activa que pueda administrar usuarios y roles; si no, nadie podría arreglar los permisos después. Por eso no te deja quitar este permiso si es el último que lo tiene.',
      )
      expect('ejemplo' in ayuda).toBe(false)
      expect(ayuda.reglas).toEqual(['ADR-053'])
    })

    it('Permisos de autorización: el PIN se borra y el ejemplo de Ana', () => {
      const ayuda = AYUDAS['roles.autorizacion']

      expect(ayuda.texto).toContain('se borra el PIN de sus usuarios')
      expect(ayuda.ejemplo).toContain('el PIN de Ana deja de servir')
      expect(ayuda.reglas).toEqual(['ADR-011'])
    })

    it.each(['mediosPago.requiereReferencia', 'mediosPago.baja', 'roles.permisos', 'roles.ultimoAdministrador', 'roles.autorizacion'] as const)(
      '%s no lleva tema "Ver más"',
      (clave) => {
        expect('verMas' in AYUDAS[clave]).toBe(false)
      },
    )
  })

  describe('medios de pago', () => {
    it('el "(?)" de "Pide referencia" abre su texto', async () => {
      montar('/admin/configuracion/medios-pago')
      await screen.findByText('Efectivo')

      const panel = await abrirAyuda(AYUDAS['mediosPago.requiereReferencia'].titulo)

      expect(within(panel).getByText(/cada vez que se use este medio hay que anotar un dato/i)).toBeInTheDocument()
      expect(within(panel).getByText(/n\.º 0042/)).toBeInTheDocument()
    })

    it('el "(?)" de "Dar de baja" abre su texto', async () => {
      montar('/admin/configuracion/medios-pago')
      await screen.findByText('Efectivo')

      const panel = await abrirAyuda(AYUDAS['mediosPago.baja'].titulo)

      expect(within(panel).getByText(/deja de ofrecerse en cobros y pagos nuevos/i)).toBeInTheDocument()
    })

    it('el formulario de alta también explica "Pide referencia"', async () => {
      const usuario = userEvent.setup()
      montar('/admin/configuracion/medios-pago')
      await screen.findByText('Efectivo')

      await usuario.click(screen.getByRole('button', { name: 'Nuevo medio de pago' }))
      const dialogo = await screen.findByRole('dialog')

      expect(within(dialogo).getByRole('button', { name: `Ayuda: ${AYUDAS['mediosPago.requiereReferencia'].titulo}` })).toBeInTheDocument()
    })
  })

  describe('roles y permisos', () => {
    async function conRolElegido() {
      const usuario = userEvent.setup()
      montar('/admin/roles')
      await usuario.click(await screen.findByRole('button', { name: 'Editar permisos de Supervisor comercial' }))
      await screen.findByRole('region', { name: 'Permisos de Supervisor comercial' })
    }

    it('el "(?)" de los permisos del rol explica que el cambio vale desde la próxima acción', async () => {
      await conRolElegido()

      const panel = await abrirAyuda(AYUDAS['roles.permisos'].titulo)

      expect(within(panel).getByText(/vale para todos los usuarios del rol desde su próxima acción/i)).toBeInTheDocument()
    })

    it('el "(?)" del permiso "Usuarios, roles y permisos" explica que siempre queda una persona', async () => {
      await conRolElegido()

      const panel = await abrirAyuda(AYUDAS['roles.ultimoAdministrador'].titulo)

      expect(within(panel).getByText(/siempre tiene que quedar al menos una persona activa/i)).toBeInTheDocument()
    })

    it('el "(?)" de los permisos de autorización explica que se borra el PIN', async () => {
      await conRolElegido()

      const panel = await abrirAyuda(AYUDAS['roles.autorizacion'].titulo)

      expect(within(panel).getByText(/se borra el pin de sus usuarios/i)).toBeInTheDocument()
    })

    it('el "(?)" del permiso del último administrador está junto a ese permiso y no junto a los demás', async () => {
      await conRolElegido()
      const panel = screen.getByRole('region', { name: 'Permisos de Supervisor comercial' })

      const ayudas = within(panel).getAllByRole('button', { name: `Ayuda: ${AYUDAS['roles.ultimoAdministrador'].titulo}` })

      expect(ayudas).toHaveLength(1)
      expect(ayudas[0]?.closest('li')).toHaveTextContent('Usuarios, roles y permisos')
    })
  })
})
