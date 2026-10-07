import type { UseFormRegisterReturn } from 'react-hook-form'

import { useCategorias, useMarcas, useProductos } from '../../../features/catalogo/useListados'
import { useCargaCompleta } from '../../../features/precios/useCargaCompleta'
import { useOpcionesDeProveedores } from '../../../features/proveedores/useListados'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface OpcionDeEntidad {
  id: string
  nombre: string
}

function Opciones({
  id,
  registro,
  opciones,
}: {
  id: string
  registro: UseFormRegisterReturn
  opciones: readonly OpcionDeEntidad[]
}) {
  return (
    <select id={id} className={CLASE_CONTROL} {...registro}>
      <option value="">Elegí una opción</option>
      {opciones.map((opcion) => (
        <option key={opcion.id} value={opcion.id}>
          {opcion.nombre}
        </option>
      ))}
    </select>
  )
}

function SelectorDeCategorias(props: { id: string; registro: UseFormRegisterReturn }) {
  const consulta = useCategorias()
  useCargaCompleta(consulta)
  return <Opciones {...props} opciones={consulta.data?.pages.flatMap((p) => p.items) ?? []} />
}

function SelectorDeMarcas(props: { id: string; registro: UseFormRegisterReturn }) {
  const consulta = useMarcas()
  useCargaCompleta(consulta)
  return <Opciones {...props} opciones={consulta.data?.pages.flatMap((p) => p.items) ?? []} />
}

function SelectorDeProductos(props: { id: string; registro: UseFormRegisterReturn }) {
  const consulta = useProductos({ activo: true })
  useCargaCompleta(consulta)
  return <Opciones {...props} opciones={consulta.data?.pages.flatMap((p) => p.items) ?? []} />
}

function SelectorDeProveedores(props: { id: string; registro: UseFormRegisterReturn }) {
  const consulta = useOpcionesDeProveedores()
  useCargaCompleta(consulta)
  return <Opciones {...props} opciones={consulta.data?.pages.flatMap((p) => p.items) ?? []} />
}

/** Selector de la entidad de una regla según su alcance (PRC-13); solo lee, con `GESTIONAR_LISTAS` (D12). */
export function SelectorDeEntidad({
  alcance,
  id,
  registro,
}: {
  alcance: string
  id: string
  registro: UseFormRegisterReturn
}) {
  switch (alcance) {
    case 'CATEGORIA':
      return <SelectorDeCategorias id={id} registro={registro} />
    case 'MARCA':
      return <SelectorDeMarcas id={id} registro={registro} />
    case 'PRODUCTO':
      return <SelectorDeProductos id={id} registro={registro} />
    case 'PROVEEDOR':
      return <SelectorDeProveedores id={id} registro={registro} />
    default:
      return null
  }
}

/** Categorías para el selector del redondeo por categoría. */
export function SelectorDeCategoriaDeRedondeo({
  id,
  registro,
}: {
  id: string
  registro: UseFormRegisterReturn
}) {
  return <SelectorDeCategorias id={id} registro={registro} />
}
