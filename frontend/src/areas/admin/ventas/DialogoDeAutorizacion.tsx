import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import {
  armarCredenciales,
  autorizadoresPara,
  faltaAlgunPin,
  personasQueDebenPonerPin,
  type AutorizadorDeContexto,
  type CredencialDePin,
  type SeleccionDeAutorizadores,
  type TipoDeAutorizacion,
} from '../../../domain/ventas/autorizacionDeVenta'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

const ETIQUETA_DE_AUTORIZACION: Record<TipoDeAutorizacion, string> = {
  DESCUENTO: 'Quién autoriza el descuento',
  CREDITO: 'Quién autoriza el exceso de crédito',
}

export interface DialogoDeAutorizacionProps {
  abierto: boolean
  necesarias: readonly TipoDeAutorizacion[]
  autorizadores: readonly AutorizadorDeContexto[]
  seleccion: SeleccionDeAutorizadores
  alCambiarSeleccion: (seleccion: SeleccionDeAutorizadores) => void
  /** Rechazo del servidor (PIN incorrecto, PIN bloqueado, autorizador sin permiso, ...). */
  error: string | null
  enviando: boolean
  /** Las credenciales viajan solo hacia quien envía; este diálogo no las guarda. */
  alConfirmar: (credenciales: CredencialDePin[]) => void
  alCancelar: () => void
}

/**
 * Autorización con PIN de supervisor (change 18b, D2, D4, D20; DSC-06, CRE-05, SEG-05). Una sola
 * credencial por persona aunque autorice las dos cosas. El PIN se escribe enmascarado, vive solo en
 * el estado del formulario de este diálogo (que se desmonta al cerrarse) y se borra al enviar y al
 * cancelar: nunca se guarda en el navegador (ni almacenamiento local, ni de sesión, ni IndexedDB, ni
 * caché de consultas).
 */
export function DialogoDeAutorizacion(props: DialogoDeAutorizacionProps) {
  return (
    <Dialogo abierto={props.abierto} titulo="Autorización" onCerrar={props.alCancelar}>
      <FormularioDeAutorizacion {...props} />
    </Dialogo>
  )
}

function FormularioDeAutorizacion({
  necesarias,
  autorizadores,
  seleccion,
  alCambiarSeleccion,
  error,
  enviando,
  alConfirmar,
  alCancelar,
}: DialogoDeAutorizacionProps) {
  const [pins, setPins] = useState<Record<string, string>>({})

  const personas = personasQueDebenPonerPin(necesarias, seleccion)
  const nombreDe = (id: string): string => autorizadores.find((a) => a.id === id)?.nombre ?? id
  const sinNadie = necesarias.some((tipo) => autorizadoresPara(tipo, autorizadores).length === 0)
  const completo = necesarias.every((tipo) => (seleccion[tipo] ?? '') !== '') && !faltaAlgunPin(personas, pins)

  const cancelar = () => {
    setPins({})
    alCancelar()
  }
  const confirmar = (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    if (!completo || enviando) return
    const credenciales = armarCredenciales(personas, pins)
    setPins({}) // el PIN sale de este formulario apenas se entrega
    alConfirmar(credenciales)
  }

  return (
    <form onSubmit={confirmar} className="flex flex-col gap-3" autoComplete="off">
      <p className="flex items-center gap-1 text-sm text-primary">
        Esta venta necesita que alguien con permiso la autorice.
        <Ayuda clave="ventas.autorizacion" />
      </p>
      {error && <Alert>{error}</Alert>}
      {sinNadie && (
        <Alert>
          No hay ningún supervisor con PIN que pueda dar esta autorización. Pedile a un administrador que defina el PIN.
        </Alert>
      )}
      {necesarias.map((tipo) => (
        <div key={tipo} className="flex flex-col gap-1">
          <label htmlFor={`autorizador-${tipo}`} className="text-sm font-medium text-primary">
            {ETIQUETA_DE_AUTORIZACION[tipo]}
          </label>
          <select
            id={`autorizador-${tipo}`}
            className={CLASE_CONTROL}
            value={seleccion[tipo] ?? ''}
            onChange={(evento) => alCambiarSeleccion({ ...seleccion, [tipo]: evento.target.value })}
          >
            <option value="">Elegí a la persona</option>
            {autorizadoresPara(tipo, autorizadores).map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        </div>
      ))}
      {personas.map((id) => (
        <div key={id} className="flex flex-col gap-1">
          <label htmlFor={`pin-${id}`} className="text-sm font-medium text-primary">
            {`PIN de ${nombreDe(id)}`}
          </label>
          <input
            id={`pin-${id}`}
            type="password"
            inputMode="numeric"
            autoComplete="off"
            className={`${CLASE_CONTROL} w-40`}
            value={pins[id] ?? ''}
            onChange={(evento) => setPins({ ...pins, [id]: evento.target.value })}
          />
        </div>
      ))}
      <div className="flex gap-2">
        <Boton type="submit" disabled={!completo || enviando || sinNadie}>
          Autorizar y registrar
        </Boton>
        <Boton variante="secundario" onClick={cancelar}>
          Cancelar
        </Boton>
      </div>
    </form>
  )
}
