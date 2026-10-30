import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { mensajeDeErrorDeClientes } from '../../../domain/clientes/cartera'
import { ErrorDeClientes } from '../../../features/clientes/errores'
import { useAsignarVendedor } from '../../../features/clientes/useMutaciones'
import type { VendedoresElegibles } from '../../../features/clientes/useVendedores'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { esErrorDeRed } from '../../../lib/api/reintentoDeRed'
import { AVISO_SIN_CONEXION, estaSinConexion } from '../precios/errores'
import { SelectorDeVendedor } from './SelectorDeVendedor'

const OPCION_QUITAR = 'ninguno'

interface AsignarVendedorDialogoProps {
  clienteIds: readonly string[]
  vendedores: VendedoresElegibles
  onCerrar: () => void
  onAsignado: () => void
}

/**
 * "Asignar vendedor" a uno o varios clientes (change 20b, D15, CLI-03): elige un vendedor elegible
 * o "Quitar vendedor" (`null`). Todo o nada (INV-01); el servidor valida igual (`VENDEDOR_INVALIDO`).
 * Sin conexión no se envía; el reintento reenvía el mismo `Operation-Id` mientras no cambie lo
 * elegido (INV-06).
 */
export function AsignarVendedorDialogo({ clienteIds, vendedores, onCerrar, onAsignado }: AsignarVendedorDialogoProps) {
  const asignar = useAsignarVendedor()
  const [elegido, setElegido] = useState('')
  const [error, setError] = useState<string | null>(null)
  const operationId = useOperationIdDeEnvio({ clienteIds: [...clienteIds].sort(), elegido })
  const cantidad = clienteIds.length

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await asignar.mutateAsync({
        clienteIds,
        vendedorId: elegido === OPCION_QUITAR ? null : elegido,
        operationId: operationId.obtener(),
      })
      operationId.completar()
      onAsignado()
    } catch (falla) {
      if (esErrorDeRed(falla)) setError(AVISO_SIN_CONEXION)
      else setError(mensajeDeErrorDeClientes(falla instanceof ErrorDeClientes ? falla.codigo : null, falla instanceof Error ? falla.message : ''))
    }
  }

  return (
    <Dialogo abierto titulo="Asignar vendedor" onCerrar={onCerrar}>
      <div className="flex flex-col gap-3 text-sm text-primary">
        <p>{cantidad === 1 ? 'Vas a asignar 1 cliente.' : `Vas a asignar ${cantidad} clientes.`}</p>
        <SelectorDeVendedor
          id="asignar-vendedor"
          etiqueta="Vendedor"
          valor={elegido}
          vendedores={vendedores.vendedores}
          onCambio={setElegido}
          fijas={[{ valor: OPCION_QUITAR, etiqueta: 'Quitar vendedor' }]}
        />
        {vendedores.estado === 'sin-acceso' && (
          <p className="text-primary/70">No podés ver la lista de vendedores con tu rol: solo podés quitar el vendedor.</p>
        )}
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton disabled={elegido === '' || asignar.isPending} onClick={() => void confirmar()}>
            Confirmar asignación
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}
