import { useRef, useState, type KeyboardEvent } from 'react'

import { filtrarVendedores } from '../../../domain/clientes/cartera'
import type { VendedorElegible } from '../../../features/clientes/api'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

export interface OpcionFija {
  valor: string
  etiqueta: string
}

interface SelectorDeVendedorProps {
  id: string
  etiqueta: string
  valor: string
  vendedores: readonly VendedorElegible[]
  onCambio: (valor: string) => void
  /** Opciones fijas que siempre quedan alcanzables ("Sin vendedor", "Quitar vendedor"...). */
  fijas: readonly OpcionFija[]
}

/**
 * Selector de vendedor con buscador por nombre (change 20b): mientras se escribe, los vendedores que
 * coinciden quedan a la vista como una lista de opciones para tocar (sin abrir ningún desplegable);
 * no distingue mayúsculas ni acentos (`filtrarVendedores`). Lo comparten la ficha del cliente y el
 * diálogo "Asignar vendedor". La opción elegida y las fijas no se filtran.
 */
export function SelectorDeVendedor({ id, etiqueta, valor, vendedores, onCambio, fijas }: SelectorDeVendedorProps) {
  const [busqueda, setBusqueda] = useState('')
  const lista = useRef<HTMLUListElement>(null)
  const visibles = filtrarVendedores(vendedores, busqueda, valor)
  const sinCoincidencias = busqueda.trim() !== '' && !visibles.some((vendedor) => vendedor.id !== valor)
  const opciones: OpcionFija[] = [
    ...fijas,
    ...visibles.filter((vendedor) => !fijas.some((fija) => fija.valor === vendedor.id)).map((vendedor) => ({ valor: vendedor.id, etiqueta: vendedor.nombre })),
  ]

  const alTeclear = (evento: KeyboardEvent<HTMLLIElement>, opcion: string) => {
    if (evento.key === 'Enter' || evento.key === ' ') {
      evento.preventDefault()
      onCambio(opcion)
      return
    }
    if (evento.key !== 'ArrowDown' && evento.key !== 'ArrowUp') return
    evento.preventDefault()
    const items = Array.from(lista.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? [])
    const indice = items.indexOf(evento.currentTarget)
    items[indice + (evento.key === 'ArrowDown' ? 1 : -1)]?.focus()
  }

  return (
    <div className="flex flex-col gap-1">
      <span id={`${id}-etiqueta`} className="text-sm font-medium text-primary">
        {etiqueta}
      </span>
      <label htmlFor={`${id}-buscar`} className="text-sm font-medium text-primary">
        Buscar vendedor
      </label>
      <input
        id={`${id}-buscar`}
        type="search"
        className={CLASE_CONTROL}
        value={busqueda}
        onChange={(evento) => setBusqueda(evento.target.value)}
      />
      <ul
        ref={lista}
        id={id}
        role="listbox"
        aria-labelledby={`${id}-etiqueta`}
        className="flex max-h-48 flex-col overflow-y-auto rounded-md border border-border"
      >
        {opciones.map((opcion) => {
          const elegida = opcion.valor === valor
          return (
            <li
              key={opcion.valor}
              role="option"
              aria-selected={elegida}
              tabIndex={elegida ? 0 : -1}
              onClick={() => onCambio(opcion.valor)}
              onKeyDown={(evento) => alTeclear(evento, opcion.valor)}
              className={`flex cursor-pointer items-center justify-between px-2 py-1 text-sm hover:bg-primary/5 focus:bg-primary/5 focus:outline-none ${elegida ? 'bg-primary/10 font-medium' : ''}`}
            >
              {opcion.etiqueta}
              {elegida && <span aria-hidden="true">✓</span>}
            </li>
          )
        })}
      </ul>
      {sinCoincidencias && <p className="text-sm text-primary/70">Ningún vendedor coincide con la búsqueda.</p>}
    </div>
  )
}
