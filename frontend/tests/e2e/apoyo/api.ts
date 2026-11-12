/**
 * Lecturas de apoyo por la API REST (change 28, D14): la suite comprueba lo que la pantalla
 * muestra Y lo que el servidor guardó (stock, saldos, costos), sin depender de cómo se dibuja.
 * Inicia sesión con un usuario de la siembra; cada sesión registra su propio dispositivo.
 */
import { randomUUID } from 'node:crypto'

import type { APIRequestContext, Browser } from '@playwright/test'

import { CONTRASENA, ORGANIZACION, type NombreDeUsuario } from '../datos/escenario'

export class ApiDeAceptacion {
  private readonly peticiones: APIRequestContext
  private readonly token: string

  private constructor(peticiones: APIRequestContext, token: string) {
    this.peticiones = peticiones
    this.token = token
  }

  static async iniciarSesion(
    browser: Browser,
    baseURL: string,
    usuario: NombreDeUsuario,
    organizacion: string = ORGANIZACION,
  ): Promise<ApiDeAceptacion> {
    const contexto = await browser.newContext({ ignoreHTTPSErrors: true, baseURL })
    const respuesta = await contexto.request.post('/api/v1/auth/login', {
      data: {
        organizacion_slug: organizacion,
        usuario,
        contrasena: CONTRASENA,
        dispositivo_id: randomUUID(),
        nombre_dispositivo: `Aceptación ${usuario}`,
      },
    })
    if (!respuesta.ok()) {
      throw new Error(`No se pudo iniciar sesión por la API como ${usuario}: ${String(respuesta.status())}`)
    }
    const { access_token: token } = (await respuesta.json()) as { access_token: string }
    return new ApiDeAceptacion(contexto.request, token)
  }

  async leer<T>(ruta: string): Promise<T> {
    const respuesta = await this.peticiones.get(ruta, { headers: { Authorization: `Bearer ${this.token}` } })
    if (!respuesta.ok()) {
      throw new Error(`GET ${ruta} respondió ${String(respuesta.status())}`)
    }
    return (await respuesta.json()) as T
  }

  /** Para comprobar un rechazo (403, 404): devuelve el código sin lanzar. */
  async estado(ruta: string, metodo: 'GET' | 'POST' = 'GET', datos?: unknown): Promise<number> {
    const respuesta = await this.peticiones.fetch(ruta, {
      method: metodo,
      data: datos,
      headers: { Authorization: `Bearer ${this.token}`, 'Operation-Id': randomUUID() },
    })
    return respuesta.status()
  }
}

interface Pagina<T> {
  items: T[]
  cursor_siguiente: string | null
}

export interface VentaDelListado {
  venta_id: string
  numero: string
  cliente_nombre: string | null
  total: string
  estado: string
}

export interface VentaDetallada extends VentaDelListado {
  cobranza: { importe: string } | null
  lineas: { producto_nombre: string | null; cantidad_base: number; costo_total: string | null; importe_neto: string }[]
}

/** Lecturas con los nombres de negocio que usa la suite. */
export class Consultas {
  private readonly api: ApiDeAceptacion

  constructor(api: ApiDeAceptacion) {
    this.api = api
  }

  private async todos<T>(ruta: string): Promise<T[]> {
    const items: T[] = []
    let cursor: string | null = null
    do {
      const separador = ruta.includes('?') ? '&' : '?'
      const pagina: Pagina<T> = await this.api.leer<Pagina<T>>(
        `${ruta}${separador}limite=100${cursor === null ? '' : `&cursor=${cursor}`}`,
      )
      items.push(...pagina.items)
      cursor = pagina.cursor_siguiente
    } while (cursor !== null)
    return items
  }

  async idDeProducto(codigo: string): Promise<string> {
    const productos = await this.todos<{ id: string; codigo: string }>('/api/v1/catalogo/productos')
    const producto = productos.find((p) => p.codigo === codigo)
    if (producto === undefined) throw new Error(`No existe el producto ${codigo}`)
    return producto.id
  }

  async idDeUbicacion(nombre: string): Promise<string> {
    const ubicaciones = await this.todos<{ id: string; nombre: string }>('/api/v1/stock/ubicaciones')
    const ubicacion = ubicaciones.find((u) => u.nombre === nombre)
    if (ubicacion === undefined) throw new Error(`No existe la ubicación ${nombre}`)
    return ubicacion.id
  }

  async idDeProveedor(nombre: string): Promise<string> {
    const proveedores = await this.todos<{ id: string; nombre: string }>('/api/v1/proveedores')
    const proveedor = proveedores.find((p) => p.nombre === nombre)
    if (proveedor === undefined) throw new Error(`No existe el proveedor ${nombre}`)
    return proveedor.id
  }

  async idDeCliente(codigo: string): Promise<string> {
    const clientes = await this.todos<{ id: string; codigo: string | null }>('/api/v1/clientes')
    const cliente = clientes.find((c) => c.codigo === codigo)
    if (cliente === undefined) throw new Error(`No existe el cliente ${codigo}`)
    return cliente.id
  }

  /** Cantidad base de un producto en una ubicación (0 si no tiene fila). */
  async stockBase(ubicacion: string, codigoDeProducto: string): Promise<number> {
    const ubicacionId = await this.idDeUbicacion(ubicacion)
    const productoId = await this.idDeProducto(codigoDeProducto)
    const lineas = await this.todos<{ producto_id: string; cantidad_base: number }>(
      `/api/v1/stock/ubicaciones/${ubicacionId}/saldos`,
    )
    return lineas.find((l) => l.producto_id === productoId)?.cantidad_base ?? 0
  }

  async costoPromedio(codigoDeProducto: string): Promise<{ costo: string | null; stockTotal: number }> {
    const productoId = await this.idDeProducto(codigoDeProducto)
    const r = await this.api.leer<{ costo_promedio: string | null; stock_total: number }>(
      `/api/v1/catalogo/productos/${productoId}/costo`,
    )
    return { costo: r.costo_promedio, stockTotal: r.stock_total }
  }

  async saldoDeProveedor(nombre: string): Promise<string> {
    const id = await this.idDeProveedor(nombre)
    return (await this.api.leer<{ saldo: string }>(`/api/v1/proveedores/${id}/saldo`)).saldo
  }

  async saldoDeCliente(codigo: string): Promise<string> {
    const id = await this.idDeCliente(codigo)
    return (await this.api.leer<{ saldo: string }>(`/api/v1/clientes/${id}/saldo`)).saldo
  }

  /** Ventas de la organización (todas las páginas), de la más reciente a la más vieja. */
  async ventas(): Promise<VentaDelListado[]> {
    return this.todos<VentaDelListado>('/api/v1/ventas')
  }

  async detalleDeVenta(ventaId: string): Promise<VentaDetallada> {
    return this.api.leer<VentaDetallada>(`/api/v1/ventas/${ventaId}`)
  }
}
