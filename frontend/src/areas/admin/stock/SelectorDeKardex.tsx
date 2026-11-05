import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import type { CodigoPermiso } from '../../../domain/identidad/permisos'
import { useProductos } from '../../../features/catalogo/useListados'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { CLASE_CONTROL } from './piezasDeOperacion'

/** Los permisos con que el servidor deja leer la lista de productos (`catalogo/api.py`). */
const PERMISOS_DE_LECTURA_DE_PRODUCTOS: readonly CodigoPermiso[] = [
  'GESTIONAR_CATALOGO',
  'REGISTRAR_COMPRA',
  'GESTIONAR_LISTAS',
  'GESTIONAR_DESCUENTOS',
  'RENDIR_JORNADA',
]

/**
 * Acceso al kardex de cualquier producto en una ubicación, tenga o no saldo
 * (change 24, decisión 2026-11-05). Ofrece activos e inactivos: un producto dado de baja
 * puede tener historia. Se monta solo con un permiso que habilite leer la lista de
 * productos; sin él no se pide nada.
 */
export function SelectorDeKardex({ ubicacionId }: { ubicacionId: string }) {
  return (
    <SiTienePermiso permiso={PERMISOS_DE_LECTURA_DE_PRODUCTOS}>
      <SelectorDeProducto ubicacionId={ubicacionId} />
    </SiTienePermiso>
  )
}

function SelectorDeProducto({ ubicacionId }: { ubicacionId: string }) {
  const navegar = useNavigate()
  const [texto, setTexto] = useState('')
  const productos = useProductos({ texto: texto.trim() || undefined })
  const opciones = productos.data?.pages.flatMap((pagina) => pagina.items) ?? []

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-sm text-primary">
        Buscar producto
        <input
          type="search"
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          placeholder="Nombre o código"
          className={CLASE_CONTROL}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-primary">
        Ver kardex de…
        <select
          className={CLASE_CONTROL}
          value=""
          onChange={(evento) => {
            if (evento.target.value) navegar(`/admin/stock/ubicaciones/${ubicacionId}/kardex/${evento.target.value}`)
          }}
        >
          <option value="">Elegí un producto</option>
          {opciones.map((opcion) => (
            <option key={opcion.id} value={opcion.id}>
              {opcion.codigo} · {opcion.nombre}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
