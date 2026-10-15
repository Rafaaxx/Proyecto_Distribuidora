import { useState } from 'react'
import type { UseFormRegisterReturn } from 'react-hook-form'

import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { agregarAlcance, quitarAlcance } from '../../../domain/descuentos/formulario'
import { etiquetaDeTipoDeAlcance } from '../../../domain/descuentos/presentacion'
import type { AlcanceDeFormulario } from '../../../domain/descuentos/reglaSchema'
import { TIPOS_ALCANCE } from '../../../domain/descuentos/tipos'
import { SelectorDeEntidad } from '../precios/SelectorDeEntidad'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface SelectorDeAlcancesProps {
  alcances: readonly AlcanceDeFormulario[]
  /** Nombre de cada entidad elegida, por `tipo:id`, para mostrarla en la lista. */
  nombres: Readonly<Record<string, string>>
  onCambiar: (alcances: AlcanceDeFormulario[], nombres: Record<string, string>) => void
  error?: string
}

function claveDe(alcance: AlcanceDeFormulario): string {
  return `${alcance.tipo}:${alcance.entidad_id}`
}

/**
 * Alcances de una regla de alcance (DSC-02): se elige el tipo (producto, categoría o marca), la
 * entidad y se la agrega a la lista. Reutiliza el selector de entidades del área de precios; las
 * lecturas del catálogo las abre `GESTIONAR_DESCUENTOS` solo en lectura (D18). La lista y los
 * repetidos los resuelve `domain/descuentos/formulario.ts`.
 */
export function SelectorDeAlcances({ alcances, nombres, onCambiar, error }: SelectorDeAlcancesProps) {
  const [tipo, setTipo] = useState<string>('PRODUCTO')
  const [entidad, setEntidad] = useState<{ id: string; nombre: string }>({ id: '', nombre: '' })
  // Remonta el selector de entidades para dejarlo en blanco tras agregar o al cambiar de tipo.
  const [vuelta, setVuelta] = useState(0)

  const registro: UseFormRegisterReturn = {
    name: 'alcance-entidad',
    onBlur: async () => undefined,
    ref: () => undefined,
    onChange: async (evento) => {
      const control = evento.target as HTMLSelectElement
      setEntidad({ id: control.value, nombre: control.selectedOptions[0]?.text ?? '' })
      return undefined
    },
  }

  const agregar = () => {
    const nuevo = { tipo, entidad_id: entidad.id }
    const lista = agregarAlcance(alcances, nuevo)
    if (lista.length === alcances.length) return
    onCambiar(lista, { ...nombres, [claveDe(nuevo)]: entidad.nombre })
    setEntidad({ id: '', nombre: '' })
    setVuelta((v) => v + 1)
  }

  return (
    <fieldset className="flex flex-col gap-3 rounded-md border border-border p-3">
      <legend className="px-1 text-sm font-medium text-primary">Alcances</legend>
      <div className="flex flex-wrap items-end gap-3">
        <Campo id="alcance-tipo" etiqueta="Tipo de alcance">
          <select
            id="alcance-tipo"
            className={CLASE_CONTROL}
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value)
              setEntidad({ id: '', nombre: '' })
              setVuelta((v) => v + 1)
            }}
          >
            {TIPOS_ALCANCE.map((valor) => (
              <option key={valor} value={valor}>
                {etiquetaDeTipoDeAlcance(valor)}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id="alcance-entidad" etiqueta="Entidad">
          <SelectorDeEntidad key={`${tipo}-${vuelta}`} alcance={tipo} id="alcance-entidad" registro={registro} />
        </Campo>
        <Boton variante="secundario" onClick={agregar}>
          Agregar alcance
        </Boton>
      </div>
      {alcances.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {alcances.map((alcance) => {
            const texto = `${etiquetaDeTipoDeAlcance(alcance.tipo)} ${nombres[claveDe(alcance)] ?? alcance.entidad_id}`
            return (
              <li key={claveDe(alcance)} className="flex items-center gap-2">
                <span>{texto}</span>
                <button
                  type="button"
                  aria-label={`Quitar ${texto}`}
                  className="text-primary/70 hover:text-primary hover:underline"
                  onClick={() => onCambiar(quitarAlcance(alcances, alcance), nombres as Record<string, string>)}
                >
                  Quitar
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </fieldset>
  )
}
