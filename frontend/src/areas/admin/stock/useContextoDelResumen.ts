import { referenciaDeRespuesta, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { useProductosParaRendicion, useSaldosCompletos } from '../../../features/stock/hooks'

export interface ContextoDelResumen {
  nombres: ReadonlyMap<string, string>
  referencias: ReadonlyMap<string, ReferenciaDePresentacion>
}

/**
 * Nombres de producto y presentaciones de referencia que necesita la tabla del resumen. Se pide al montar la
 * pantalla (junto con el resumen) para que ambos lleguen a la vez.
 */
export function useContextoDelResumen(ubicacionId: string): ContextoDelResumen {
  const catalogo = useProductosParaRendicion()
  const permisos = usePermisos()
  const saldos = useSaldosCompletos(permisos.tiene('TRANSFERIR_STOCK') ? ubicacionId : undefined)

  const nombres = new Map(catalogo.productos.map((p) => [p.id, p.nombre]))
  const referencias = new Map<string, ReferenciaDePresentacion>()
  for (const saldo of saldos.lineas) {
    const referencia = referenciaDeRespuesta(saldo.unidades_referencia, saldo.nombre_referencia)
    if (referencia !== null) referencias.set(saldo.producto_id, referencia)
  }
  return { nombres, referencias }
}
