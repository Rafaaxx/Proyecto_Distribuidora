import { useQuery } from '@tanstack/react-query'

import { usePermisos } from '../identidad/usePermisos'
import { listarVendedoresElegibles, type VendedorElegible } from './api'
import { clavesClientes } from './claves'

export type EstadoDeVendedores = 'cargando' | 'listo' | 'sin-acceso'

export interface VendedoresElegibles {
  vendedores: VendedorElegible[]
  estado: EstadoDeVendedores
}

/**
 * Los usuarios que se pueden elegir como vendedor de un cliente (change 20b, D15): activos, con rol
 * activo y con `VENDER` o `REGISTRAR_COBRANZA`. Salen de `GET /clientes/vendedores`, que pide
 * `GESTIONAR_CLIENTES` (el permiso de quien asigna) y no `ADMIN_USUARIOS`; sin ese permiso la
 * pantalla lo dice (`sin-acceso`). El servidor valida igual (`VENDEDOR_INVALIDO`, 409).
 */
export function useVendedoresElegibles(): VendedoresElegibles {
  const { tiene } = usePermisos()
  const puedeLeer = tiene('GESTIONAR_CLIENTES')
  const consulta = useQuery({
    queryKey: clavesClientes.vendedores(),
    queryFn: listarVendedoresElegibles,
    enabled: puedeLeer,
    retry: false,
  })

  if (consulta.isError) return { vendedores: [], estado: 'sin-acceso' }
  if (consulta.isSuccess) return { vendedores: consulta.data, estado: 'listo' }
  return { vendedores: [], estado: puedeLeer ? 'cargando' : 'sin-acceso' }
}
