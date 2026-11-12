import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock, guardarArchivoMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn(), guardarArchivoMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))
vi.mock('../../../../../src/lib/descarga', () => ({ guardarArchivo: guardarArchivoMock }))

import { ImportacionScreen } from '../../../../../src/areas/admin/importacion/ImportacionScreen'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const ZONA = 'America/Argentina/Mendoza'

function item(id: string, sobrescribir: Record<string, unknown> = {}) {
  return {
    id,
    tipo: 'PROVEEDORES',
    archivo_nombre: 'proveedores.csv',
    estado: 'CONFIRMADA',
    filas_total: 2,
    filas_ok: 2,
    filas_error: 0,
    usuario_id: 'u1',
    usuario_nombre: 'Ana Admin',
    registered_at: '2026-10-01T15:30:00Z',
    ...sobrescribir,
  }
}

function paginaDeHistorial(items: unknown[], cursor: string | null = null) {
  return { items, cursor_siguiente: cursor, zona_horaria: ZONA }
}

const ACEPTADO = { importacion_id: 'i1', filas_total: 2, filas_ok: 2 }

function reglasBase(extra: ReglaDeApi[] = []): ReglaDeApi[] {
  return [
    ...extra,
    { metodo: 'GET', ruta: '/importaciones', responder: () => ({ status: 200, cuerpo: paginaDeHistorial([]) }) },
    { metodo: 'POST', ruta: /^\/importaciones\/[A-Z_]+$/, responder: () => ({ status: 201, cuerpo: ACEPTADO }) },
  ]
}

/** Las plantillas se descargan como binario: el auxiliar `enrutar` solo responde JSON. */
function conPlantillas(): void {
  const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
  apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
    if (ruta.startsWith('/importaciones/plantillas/')) {
      return Promise.resolve({ ok: true, status: 200, blob: async () => new Blob(['nombre;codigo'], { type: 'text/csv' }) })
    }
    return base(ruta, init)
  })
}

function renderPantalla(rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/importacion']}>
        <Routes>
          <Route path="/admin/importacion" element={<ImportacionScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function archivo(nombre = 'proveedores.csv', contenido = 'nombre\nBodega Sur\nCervecería Norte') {
  return new File([contenido], nombre, { type: 'text/csv' })
}

async function elegirTipo(usuario: ReturnType<typeof userEvent.setup>, tipo: string) {
  await usuario.selectOptions(await screen.findByLabelText('Tipo de importación'), tipo)
}

async function subir(usuario: ReturnType<typeof userEvent.setup>, f: File = archivo()) {
  await usuario.upload(await screen.findByLabelText('Archivo'), f)
}

function envios(tipo: string) {
  return llamadas(apiFetchMock, 'POST', `/importaciones/${tipo}`)
}

function operationId(tipo: string, indice: number): string | null {
  return new Headers(envios(tipo)[indice]?.init.headers).get('Operation-Id')
}

describe('ImportacionScreen (tareas 8.1 y 8.2; spec administracion-de-importaciones)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    guardarArchivoMock.mockReset()
    enrutar(apiFetchMock, reglasBase())
    conPlantillas()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('permiso IMPORTAR_DATOS (ADR-027)', () => {
    it('la sección está declarada con IMPORTAR_DATOS y la ve solo el Administrador', () => {
      const seccion = SECCIONES.find((s) => s.ruta === '/admin/importacion')
      expect(seccion).toEqual({ ruta: '/admin/importacion', etiqueta: 'Importación', permiso: 'IMPORTAR_DATOS' })

      const ve = (rol: RolDePrueba) =>
        seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).some((s) => s.etiqueta === 'Importación')
      expect((['ADM', 'GES', 'SUP', 'VEN', 'CON'] as RolDePrueba[]).map(ve)).toEqual([true, false, false, false, false])
    })

    it('un Vendedor que entra por la ruta directa ve que no tiene permiso y no se pide nada', async () => {
      renderPantalla('VEN')

      expect(await screen.findByText('No tenés permiso para importar datos.')).toBeInTheDocument()
      expect(screen.queryByLabelText('Tipo de importación')).not.toBeInTheDocument()
      expect(apiFetchMock).not.toHaveBeenCalled()
    })

    it('el Administrador ve el formulario', async () => {
      renderPantalla('ADM')

      expect(await screen.findByLabelText('Tipo de importación')).toBeInTheDocument()
    })
  })

  describe('elegir tipo y descargar la plantilla', () => {
    it('ofrece los seis tipos con importador y no ofrece las listas de precios (change 13)', async () => {
      renderPantalla()

      const selector = await screen.findByLabelText('Tipo de importación')
      const opciones = within(selector).getAllByRole('option').map((o) => o.textContent)

      expect(opciones).toEqual(['Proveedores', 'Productos', 'Clientes', 'Costos', 'Stock inicial', 'Saldos iniciales'])
    })

    it.each([
      ['Clientes', 'CLIENTES', 'plantilla-clientes.csv'],
      ['Saldos iniciales', 'SALDOS_INICIALES', 'plantilla-saldos_iniciales.csv'],
    ])('descarga la plantilla de %s', async (etiqueta, tipo, nombre) => {
      const usuario = userEvent.setup()
      renderPantalla()

      await elegirTipo(usuario, etiqueta)
      await usuario.click(screen.getByRole('button', { name: 'Descargar plantilla' }))

      await waitFor(() => expect(guardarArchivoMock).toHaveBeenCalledTimes(1))
      expect(llamadas(apiFetchMock, 'GET', `/importaciones/plantillas/${tipo}`)).toHaveLength(1)
      const [blob, nombreGuardado] = guardarArchivoMock.mock.calls[0] as [Blob, string]
      expect(blob).toBeInstanceOf(Blob)
      expect(nombreGuardado).toBe(nombre)
    })

    it('si la plantilla no se puede descargar lo avisa', async () => {
      const usuario = userEvent.setup()
      renderPantalla()
      const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
      apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) =>
        ruta.startsWith('/importaciones/plantillas/')
          ? Promise.resolve({ ok: false, status: 403, json: async () => ({ title: 'Falta el permiso IMPORTAR_DATOS.', codigo: 'PERMISO_REQUERIDO' }) })
          : base(ruta, init),
      )

      await usuario.click(await screen.findByRole('button', { name: 'Descargar plantilla' }))

      expect(await screen.findByRole('alert')).toHaveTextContent('No tenés permiso para importar datos.')
      expect(guardarArchivoMock).not.toHaveBeenCalled()
    })
  })

  describe('ayuda de la plantilla (change 11b, CST-06)', () => {
    it('Costos explica que el valor es el pagado y que incluye_iva es solo de un inscripto', async () => {
      const usuario = userEvent.setup()
      renderPantalla()

      await elegirTipo(usuario, 'COSTOS')

      const ayuda = await screen.findByRole('note')
      expect(ayuda).toHaveTextContent('valor pagado')
      expect(ayuda).toHaveTextContent('incluye_iva')
      expect(ayuda).toHaveTextContent('monotributista')
    })

    it('Stock inicial explica que el costo es por unidad base, tal como se pagó', async () => {
      const usuario = userEvent.setup()
      renderPantalla()

      await elegirTipo(usuario, 'STOCK_INICIAL')

      const ayuda = await screen.findByRole('note')
      expect(ayuda).toHaveTextContent('por unidad base')
      expect(ayuda).toHaveTextContent('tal como lo pagaste')
    })

    it('un tipo sin ayuda no muestra ninguna nota', async () => {
      const usuario = userEvent.setup()
      renderPantalla()

      await elegirTipo(usuario, 'PROVEEDORES')

      expect(screen.queryByRole('note')).not.toBeInTheDocument()
    })

    it('la ayuda cambia al cambiar de tipo', async () => {
      const usuario = userEvent.setup()
      renderPantalla()

      await elegirTipo(usuario, 'COSTOS')
      await elegirTipo(usuario, 'STOCK_INICIAL')

      expect(await screen.findByRole('note')).not.toHaveTextContent('incluye_iva')
    })
  })

  describe('importación exitosa', () => {
    it('sube el archivo por multipart con su Operation-Id y muestra "2 filas importadas"', async () => {
      const usuario = userEvent.setup()
      renderPantalla()

      await elegirTipo(usuario, 'Proveedores')
      await subir(usuario)
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))

      expect(await screen.findByText('2 filas importadas')).toBeInTheDocument()
      const [envio] = envios('PROVEEDORES')
      expect(envios('PROVEEDORES')).toHaveLength(1)
      const cuerpo = envio?.init.body
      expect(cuerpo).toBeInstanceOf(FormData)
      const enviado = (cuerpo as FormData).get('archivo') as File
      expect(enviado.name).toBe('proveedores.csv')
      const encabezados = new Headers(envio?.init.headers)
      expect(encabezados.get('Operation-Id')).toMatch(/^[0-9a-f-]{36}$/)
      // El navegador fija el `Content-Type` multipart con su `boundary`.
      expect(encabezados.has('Content-Type')).toBe(false)
    })

    it('con una sola fila dice "1 fila importada" y vuelve a pedir el historial', async () => {
      const usuario = userEvent.setup()
      enrutar(apiFetchMock, reglasBase([{ metodo: 'POST', ruta: '/importaciones/CLIENTES', responder: () => ({ status: 201, cuerpo: { importacion_id: 'i2', filas_total: 1, filas_ok: 1 } }) }]))
      conPlantillas()
      renderPantalla()
      await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/importaciones')).toHaveLength(1))

      await elegirTipo(usuario, 'Clientes')
      await subir(usuario, archivo('clientes.csv', 'nombre\nDon Pepe'))
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))

      expect(await screen.findByText('1 fila importada')).toBeInTheDocument()
      await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/importaciones').length).toBeGreaterThanOrEqual(2))
    })

    it('no deja importar sin elegir un archivo', async () => {
      renderPantalla()

      expect(await screen.findByRole('button', { name: 'Importar' })).toBeDisabled()
    })
  })

  describe('informe de errores', () => {
    const ERRORES = [
      { fila: 45, columna: 'documento_numero', codigo: 'DOCUMENTO_INVALIDO', mensaje: 'El DNI debe tener 7 u 8 dígitos.' },
      { fila: 210, columna: 'codigo', codigo: 'CODIGO_DUPLICADO', mensaje: 'Ya existe un cliente con ese código.' },
    ]

    it('muestra una tabla con fila, columna, código y mensaje y avisa que no se importó ninguna fila', async () => {
      const usuario = userEvent.setup()
      enrutar(
        apiFetchMock,
        reglasBase([
          {
            metodo: 'POST',
            ruta: '/importaciones/CLIENTES',
            responder: () => ({
              status: 422,
              cuerpo: { title: 'La importación tiene 2 error(es); no se importó ninguna fila.', codigo: 'IMPORTACION_CON_ERRORES', errores: ERRORES },
            }),
          },
        ]),
      )
      renderPantalla()

      await elegirTipo(usuario, 'Clientes')
      await subir(usuario, archivo('clientes.csv', 'x'))
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))

      expect(await screen.findByText('No se importó ninguna fila')).toBeInTheDocument()
      const tabla = screen.getByRole('table', { name: 'Errores de la importación' })
      const encabezados = within(tabla).getAllByRole('columnheader').map((h) => h.textContent)
      expect(encabezados).toEqual(['Fila', 'Columna', 'Código', 'Mensaje'])
      const filas = within(tabla).getAllByRole('row').slice(1)
      expect(filas.map((f) => within(f).getAllByRole('cell').map((c) => c.textContent))).toEqual([
        ['45', 'documento_numero', 'DOCUMENTO_INVALIDO', 'El DNI debe tener 7 u 8 dígitos.'],
        ['210', 'codigo', 'CODIGO_DUPLICADO', 'Ya existe un cliente con ese código.'],
      ])
      expect(screen.queryByText(/importadas?$/)).not.toBeInTheDocument()
    })

    it('un error sin columna (de toda la fila) se muestra con un guion', async () => {
      const usuario = userEvent.setup()
      enrutar(
        apiFetchMock,
        reglasBase([
          {
            metodo: 'POST',
            ruta: '/importaciones/PROVEEDORES',
            responder: () => ({
              status: 422,
              cuerpo: { title: 'x', codigo: 'IMPORTACION_CON_ERRORES', errores: [{ fila: 3, columna: null, codigo: 'ALGO', mensaje: 'Algo falló.' }] },
            }),
          },
        ]),
      )
      renderPantalla()

      await subir(usuario)
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))

      const tabla = await screen.findByRole('table', { name: 'Errores de la importación' })
      expect(within(within(tabla).getAllByRole('row')[1] as HTMLElement).getAllByRole('cell')[1]).toHaveTextContent('—')
    })

    it('un error de columnas se muestra como mensaje general nombrando la columna, sin tabla', async () => {
      const usuario = userEvent.setup()
      enrutar(
        apiFetchMock,
        reglasBase([
          {
            metodo: 'POST',
            ruta: '/importaciones/PRODUCTOS',
            responder: () => ({
              status: 422,
              cuerpo: { title: 'Faltan columnas obligatorias: codigo.', codigo: 'COLUMNAS_INVALIDAS', columnas_faltantes: ['codigo'] },
            }),
          },
        ]),
      )
      renderPantalla()

      await elegirTipo(usuario, 'Productos')
      await subir(usuario, archivo('productos.csv', 'nombre\nX'))
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))

      const alerta = await screen.findByRole('alert')
      expect(alerta).toHaveTextContent('Faltan columnas obligatorias: codigo.')
      expect(alerta).toHaveTextContent('No se importó ninguna fila')
      expect(screen.queryByRole('table', { name: 'Errores de la importación' })).not.toBeInTheDocument()
    })

    it('sin permiso del servidor (403) lo dice con el mensaje de permiso', async () => {
      const usuario = userEvent.setup()
      enrutar(
        apiFetchMock,
        reglasBase([{ metodo: 'POST', ruta: '/importaciones/PROVEEDORES', responder: () => ({ status: 403, cuerpo: { title: 'Falta el permiso IMPORTAR_DATOS.', codigo: 'PERMISO_REQUERIDO' } }) }]),
      )
      renderPantalla()

      await subir(usuario)
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))

      expect(await screen.findByRole('alert')).toHaveTextContent('No tenés permiso para importar datos.')
    })
  })

  describe('Operation-Id (SYN-02, INV-06)', () => {
    function redCaida(): ReglaDeApi {
      return {
        metodo: 'POST',
        ruta: '/importaciones/PROVEEDORES',
        responder: () => {
          throw new TypeError('Failed to fetch')
        },
      }
    }

    it('tras un error de red reintenta con el mismo Operation-Id, y uno nuevo al elegir otro archivo', async () => {
      const usuario = userEvent.setup()
      enrutar(apiFetchMock, reglasBase([redCaida()]))
      renderPantalla()

      await subir(usuario, archivo('a.csv'))
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))
      await screen.findByRole('button', { name: 'Reintentar' })
      expect(screen.getByRole('alert')).toHaveTextContent('Se necesita conexión')
      const primero = operationId('PROVEEDORES', 0)
      expect(primero).toBeTruthy()
      // Los reintentos automáticos de la mutación también reenvían el mismo valor.
      const intentos = envios('PROVEEDORES').length
      expect(intentos).toBeGreaterThan(1)
      for (let i = 0; i < intentos; i += 1) expect(operationId('PROVEEDORES', i)).toBe(primero)

      // El usuario reintenta sin cambiar el archivo: mismo Operation-Id.
      await usuario.click(screen.getByRole('button', { name: 'Reintentar' }))
      await waitFor(() => expect(envios('PROVEEDORES').length).toBeGreaterThan(intentos))
      expect(operationId('PROVEEDORES', intentos)).toBe(primero)

      // Otro archivo: Operation-Id nuevo.
      await subir(usuario, archivo('b.csv'))
      const antes = envios('PROVEEDORES').length
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))
      await waitFor(() => expect(envios('PROVEEDORES').length).toBeGreaterThan(antes))
      expect(operationId('PROVEEDORES', antes)).not.toBe(primero)
    })

    it('si el servidor responde con un error ya resuelto, el siguiente envío es una operación nueva', async () => {
      const usuario = userEvent.setup()
      let rechazar = true
      enrutar(
        apiFetchMock,
        reglasBase([
          {
            metodo: 'POST',
            ruta: '/importaciones/PROVEEDORES',
            responder: () =>
              rechazar
                ? { status: 422, cuerpo: { title: 'x', codigo: 'IMPORTACION_CON_ERRORES', errores: [{ fila: 2, columna: 'cuit', codigo: 'CUIT_INVALIDO', mensaje: 'm' }] } }
                : { status: 201, cuerpo: ACEPTADO },
          },
        ]),
      )
      renderPantalla()

      await subir(usuario)
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))
      await screen.findByText('No se importó ninguna fila')
      rechazar = false
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))

      await screen.findByText('2 filas importadas')
      expect(envios('PROVEEDORES')).toHaveLength(2)
      expect(operationId('PROVEEDORES', 1)).not.toBe(operationId('PROVEEDORES', 0))
    })

    it('el mismo archivo con otro tipo es otra operación, aunque el envío anterior se haya cortado', async () => {
      const usuario = userEvent.setup()
      enrutar(apiFetchMock, reglasBase([redCaida()]))
      renderPantalla()

      await subir(usuario)
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))
      await screen.findByRole('button', { name: 'Reintentar' })
      await elegirTipo(usuario, 'Clientes')
      await usuario.click(screen.getByRole('button', { name: 'Importar' }))
      await waitFor(() => expect(envios('CLIENTES')).toHaveLength(1))

      expect(operationId('CLIENTES', 0)).not.toBe(operationId('PROVEEDORES', 0))
    })
  })

  describe('historial (tarea 8.2; TR-04)', () => {
    it('lista tipo, archivo, filas importadas, usuario y fecha en la zona de la organización', async () => {
      enrutar(
        apiFetchMock,
        reglasBase([
          {
            metodo: 'GET',
            ruta: '/importaciones',
            responder: () => ({
              status: 200,
              cuerpo: paginaDeHistorial([
                item('i2', { tipo: 'CLIENTES', archivo_nombre: 'clientes.xlsx', filas_total: 300, filas_ok: 300, usuario_nombre: 'Ana Admin', registered_at: '2026-10-02T02:30:00Z' }),
                item('i1', { usuario_nombre: null }),
              ]),
            }),
          },
        ]),
      )
      renderPantalla()

      const tabla = await screen.findByRole('table', { name: 'Historial de importaciones' })
      const filas = within(tabla).getAllByRole('row').slice(1)
      expect(filas.map((f) => within(f).getAllByRole('cell').map((c) => c.textContent))).toEqual([
        // 02:30 UTC del 2 de octubre es 23:30 del 1 de octubre en Mendoza (UTC-3).
        ['01/10/2026 23:30', 'Clientes', 'clientes.xlsx', '300', 'Ana Admin'],
        ['01/10/2026 12:30', 'Proveedores', 'proveedores.csv', '2', '—'],
      ])
    })

    it('sin importaciones lo dice', async () => {
      renderPantalla()

      expect(await screen.findByText('Todavía no hay importaciones.')).toBeInTheDocument()
    })

    it('pagina por cursor con "Cargar más" sin repetir filas', async () => {
      const usuario = userEvent.setup()
      enrutar(
        apiFetchMock,
        reglasBase([
          {
            metodo: 'GET',
            ruta: '/importaciones',
            responder: (url) =>
              url.searchParams.get('cursor') === 'c1'
                ? { status: 200, cuerpo: paginaDeHistorial([item('i1', { archivo_nombre: 'viejo.csv' })]) }
                : { status: 200, cuerpo: paginaDeHistorial([item('i2', { archivo_nombre: 'nuevo.csv' })], 'c1') },
          },
        ]),
      )
      renderPantalla()

      expect(await screen.findByText('nuevo.csv')).toBeInTheDocument()
      expect(screen.queryByText('viejo.csv')).not.toBeInTheDocument()
      await usuario.click(screen.getByRole('button', { name: 'Cargar más' }))

      expect(await screen.findByText('viejo.csv')).toBeInTheDocument()
      expect(screen.getByText('nuevo.csv')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()
    })

    it('si no se pudo obtener el historial lo avisa sin ocultar el formulario', async () => {
      enrutar(
        apiFetchMock,
        reglasBase([{ metodo: 'GET', ruta: '/importaciones', responder: () => ({ status: 500, cuerpo: { title: 'Error', codigo: 'ERROR' } }) }]),
      )
      renderPantalla()

      expect(await screen.findByText('No se pudo obtener el historial de importaciones.')).toBeInTheDocument()
      expect(screen.getByLabelText('Tipo de importación')).toBeInTheDocument()
    })
  })
})
