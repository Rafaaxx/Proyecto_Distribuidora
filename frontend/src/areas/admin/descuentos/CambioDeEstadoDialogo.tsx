import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { useActivarReglaDescuento, usePausarReglaDescuento } from '../../../features/descuentos/hooks'
import { mensajeDeErrorDeDescuentos } from '../../../features/descuentos/mapaErrorACampo'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from './errores'

export type TipoDeCambio = 'ACTIVAR' | 'PAUSAR'

interface CambioDeEstadoDialogoProps {
  tipo: TipoDeCambio
  reglaId: string
  nombre: string
  onCerrar: () => void
  /** El servidor dijo `REGLA_ESTADO_INVALIDO`: la pantalla refresca el estado y muestra el mensaje. */
  onEstadoInvalido: (mensaje: string) => void
  onHecho: () => void
}

const TEXTOS: Record<TipoDeCambio, { titulo: string; confirmar: string }> = {
  ACTIVAR: { titulo: 'Activar regla', confirmar: 'Confirmar activación' },
  PAUSAR: { titulo: 'Pausar regla', confirmar: 'Confirmar pausa' },
}

/**
 * Confirmación de "Activar" y "Pausar" (change 16, tarea 15.3; `01` §18, D15). Avisa, al activar,
 * que la regla ya no se podrá editar. Todas las escrituras son `ONLINE`: sin conexión avisa y no
 * envía. El reintento del mismo cambio tras un error de red reenvía el mismo `Operation-Id`
 * (INV-06).
 */
export function CambioDeEstadoDialogo({
  tipo,
  reglaId,
  nombre,
  onCerrar,
  onEstadoInvalido,
  onHecho,
}: CambioDeEstadoDialogoProps) {
  const activar = useActivarReglaDescuento()
  const pausar = usePausarReglaDescuento()
  const operationId = useOperationIdDeEnvio({ tipo, reglaId })
  const [error, setError] = useState<string | null>(null)
  const enviando = activar.isPending || pausar.isPending

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      const variables = { reglaId, operationId: operationId.obtener() }
      if (tipo === 'ACTIVAR') await activar.mutateAsync(variables)
      else await pausar.mutateAsync(variables)
      operationId.completar()
      onHecho()
    } catch (falla) {
      const { codigo, mensaje } = describirError(falla)
      if (codigo === 'REGLA_ESTADO_INVALIDO') {
        operationId.completar()
        onEstadoInvalido(mensajeDeErrorDeDescuentos(codigo, mensaje))
        return
      }
      setError(mensajeDeErrorDeDescuentos(codigo, mensaje))
    }
  }

  return (
    <Dialogo abierto titulo={TEXTOS[tipo].titulo} onCerrar={onCerrar}>
      <div className="flex flex-col gap-4">
        {tipo === 'ACTIVAR' ? (
          <p className="text-sm text-primary">
            Vas a activar «{nombre}». Una vez activada, la regla ya no se podrá editar: para cambiarla hay que pausarla y
            crear otra. Solo se podrá fijar su vigencia hasta.
          </p>
        ) : (
          <p className="text-sm text-primary">
            Vas a pausar «{nombre}». Una regla pausada deja de aplicarse hasta que se vuelva a activar.
          </p>
        )}
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton onClick={() => void confirmar()} disabled={enviando}>
            {TEXTOS[tipo].confirmar}
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}
