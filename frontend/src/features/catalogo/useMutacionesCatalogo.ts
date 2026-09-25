import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useRef } from 'react'

import { generarOperationId } from '../../lib/api/operationId'
import { debeReintentar } from '../../lib/api/reintentoDeRed'
import {
  agregarPresentacion,
  cambiarReferencia,
  crearCategoria,
  crearMarca,
  crearProducto,
  modificarCategoria,
  modificarMarca,
  modificarPresentacion,
  modificarProducto,
  type Categoria,
  type CategoriaCrearDatos,
  type CategoriaModificarDatos,
  type Marca,
  type MarcaCrearDatos,
  type MarcaModificarDatos,
  type Presentacion,
  type PresentacionAgregarDatos,
  type PresentacionModificarDatos,
  type Producto,
  type ProductoCrearDatos,
  type ProductoDetalle,
  type ProductoModificarDatos,
} from './api'
import { clavesCatalogo } from './claves'

/**
 * Mutaciones de escritura de catálogo (tarea 10.2).
 *
 * El `Operation-Id` de cada envío se genera una sola vez en `onMutate`
 * (que TanStack Query ejecuta una única vez por llamada a `.mutate(...)`,
 * antes de cualquier intento) y se guarda en un `ref`; `mutationFn` lo lee
 * de ahí en cada intento. El reintento automático de TanStack Query
 * (`retry`) vuelve a invocar `mutationFn` con las mismas variables pero
 * SIN volver a llamar `onMutate`, así que el reintento reenvía exactamente
 * el mismo `Operation-Id` (INV-06, `design.md` D10) -- generarlo dentro de
 * `mutationFn` en cambio produciría uno distinto en cada intento, porque
 * `mutationFn` sí se re-ejecuta en cada reintento. Quien llama puede fijar
 * su propio `operationId` en las variables (por ejemplo, para reintentar a
 * mano con los mismos datos tras cerrar y reabrir el formulario).
 *
 * `retry` usa `debeReintentar` (`lib/api/reintentoDeRed.ts`) en vez de un
 * número fijo: solo reintenta un error de RED (nunca llegó a haber una
 * respuesta HTTP), no un rechazo de dominio ya resuelto por el servidor
 * (409/422 con `codigo`) -- bug de la verificación manual 13.5, corregido
 * en la tarea 14.2.
 */

function useMutacionConOperationId<TVariables extends { operationId?: string }, TResultado>(opciones: {
  ejecutar: (variables: TVariables, operationId: string) => Promise<TResultado>
  onSuccess?: (resultado: TResultado, variables: TVariables) => void
}) {
  const operationIdRef = useRef<string | null>(null)
  return useMutation<TResultado, Error, TVariables>({
    retry: debeReintentar,
    retryDelay: 0,
    onMutate: (variables) => {
      operationIdRef.current = variables.operationId ?? generarOperationId()
    },
    mutationFn: (variables) => opciones.ejecutar(variables, operationIdRef.current ?? generarOperationId()),
    onSuccess: opciones.onSuccess,
  })
}

function useInvalidar(clavesAInvalidar: QueryKey[]) {
  const queryClient = useQueryClient()
  return () => {
    for (const clave of clavesAInvalidar) {
      void queryClient.invalidateQueries({ queryKey: clave })
    }
  }
}

// --- Categorías ---

interface VariablesCrearCategoria extends CategoriaCrearDatos {
  operationId?: string
}

export function useCrearCategoria() {
  const invalidar = useInvalidar([clavesCatalogo.categorias()])
  return useMutacionConOperationId<VariablesCrearCategoria, Categoria>({
    ejecutar: ({ nombre }, operationId) => crearCategoria({ nombre }, operationId),
    onSuccess: invalidar,
  })
}

interface VariablesModificarCategoria extends CategoriaModificarDatos {
  categoriaId: string
  operationId?: string
}

export function useModificarCategoria() {
  const invalidar = useInvalidar([clavesCatalogo.categorias()])
  return useMutacionConOperationId<VariablesModificarCategoria, Categoria>({
    ejecutar: ({ categoriaId, nombre, activo }, operationId) =>
      modificarCategoria(categoriaId, { nombre, activo }, operationId),
    onSuccess: invalidar,
  })
}

// --- Marcas ---

interface VariablesCrearMarca extends MarcaCrearDatos {
  operationId?: string
}

export function useCrearMarca() {
  const invalidar = useInvalidar([clavesCatalogo.marcas()])
  return useMutacionConOperationId<VariablesCrearMarca, Marca>({
    ejecutar: ({ nombre }, operationId) => crearMarca({ nombre }, operationId),
    onSuccess: invalidar,
  })
}

interface VariablesModificarMarca extends MarcaModificarDatos {
  marcaId: string
  operationId?: string
}

export function useModificarMarca() {
  const invalidar = useInvalidar([clavesCatalogo.marcas()])
  return useMutacionConOperationId<VariablesModificarMarca, Marca>({
    ejecutar: ({ marcaId, nombre, activo }, operationId) => modificarMarca(marcaId, { nombre, activo }, operationId),
    onSuccess: invalidar,
  })
}

// --- Productos ---

interface VariablesCrearProducto extends ProductoCrearDatos {
  operationId?: string
}

export function useCrearProducto() {
  const invalidar = useInvalidar([clavesCatalogo.productos()])
  return useMutacionConOperationId<VariablesCrearProducto, ProductoDetalle>({
    ejecutar: (variables, operationId) =>
      crearProducto(
        {
          codigo: variables.codigo,
          nombre: variables.nombre,
          categoria_id: variables.categoria_id,
          marca_id: variables.marca_id,
          proveedor_id: variables.proveedor_id,
          unidad_base: variables.unidad_base,
          alicuota_id: variables.alicuota_id,
          presentaciones: variables.presentaciones,
        },
        operationId,
      ),
    onSuccess: invalidar,
  })
}

interface VariablesModificarProducto extends ProductoModificarDatos {
  productoId: string
  operationId?: string
}

export function useModificarProducto() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesModificarProducto, Producto>({
    ejecutar: (variables, operationId) =>
      modificarProducto(
        variables.productoId,
        {
          codigo: variables.codigo,
          nombre: variables.nombre,
          categoria_id: variables.categoria_id,
          marca_id: variables.marca_id,
          proveedor_id: variables.proveedor_id,
          unidad_base: variables.unidad_base,
          alicuota_id: variables.alicuota_id,
          activo: variables.activo,
        },
        operationId,
      ),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({ queryKey: clavesCatalogo.productos() })
      void queryClient.invalidateQueries({ queryKey: clavesCatalogo.producto(variables.productoId) })
    },
  })
}

// --- Presentaciones ---

interface VariablesAgregarPresentacion extends PresentacionAgregarDatos {
  productoId: string
  operationId?: string
}

export function useAgregarPresentacion() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesAgregarPresentacion, Presentacion>({
    ejecutar: (variables, operationId) =>
      agregarPresentacion(
        variables.productoId,
        {
          nombre: variables.nombre,
          unidades_base: variables.unidades_base,
          usar_en_venta: variables.usar_en_venta,
          usar_en_compra: variables.usar_en_compra,
        },
        operationId,
      ),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({ queryKey: clavesCatalogo.producto(variables.productoId) })
    },
  })
}

interface VariablesModificarPresentacion extends PresentacionModificarDatos {
  presentacionId: string
  productoId: string
  operationId?: string
}

export function useModificarPresentacion() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesModificarPresentacion, Presentacion>({
    ejecutar: (variables, operationId) =>
      modificarPresentacion(
        variables.presentacionId,
        {
          nombre: variables.nombre,
          unidades_base: variables.unidades_base,
          usar_en_venta: variables.usar_en_venta,
          usar_en_compra: variables.usar_en_compra,
          activo: variables.activo,
        },
        operationId,
      ),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({ queryKey: clavesCatalogo.producto(variables.productoId) })
    },
  })
}

interface VariablesCambiarReferencia {
  productoId: string
  presentacionId: string
  operationId?: string
}

export function useCambiarReferencia() {
  const queryClient = useQueryClient()
  return useMutacionConOperationId<VariablesCambiarReferencia, Presentacion>({
    ejecutar: ({ productoId, presentacionId }, operationId) => cambiarReferencia(productoId, presentacionId, operationId),
    onSuccess: (_resultado, variables) => {
      void queryClient.invalidateQueries({ queryKey: clavesCatalogo.producto(variables.productoId) })
    },
  })
}
