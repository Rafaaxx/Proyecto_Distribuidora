import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { etiquetaDeVendedor, mensajeDeErrorDeClientes, puedeAsignarse } from '../../../domain/clientes/cartera'
import type { Cliente } from '../../../features/clientes/api'
import { ErrorDeClientes } from '../../../features/clientes/errores'
import { useAsignarVendedor } from '../../../features/clientes/useMutaciones'
import { useVendedoresElegibles } from '../../../features/clientes/useVendedores'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { esErrorDeRed } from '../../../lib/api/reintentoDeRed'
import { AVISO_SIN_CONEXION, estaSinConexion } from '../precios/errores'
import { SelectorDeVendedor } from './SelectorDeVendedor'

const OPCION_NINGUNO = 'ninguno'

/**
 * Vendedor del cliente en la ficha (change 20b, D15; CLI-03): un selector con su propio comando
 * (`CLIENTE_VENDEDOR_ASIGNAR`; `CLIENTE_MODIFICAR` no cambia). Marca al vendedor dado de baja o sin
 * permiso para reasignarlo (D6). El consumidor final no se asigna: lo ven todos.
 */
export function VendedorDelCliente({ cliente }: { cliente: Cliente }) {
  const vendedores = useVendedoresElegibles()
  const asignar = useAsignarVendedor()
  const [elegido, setElegido] = useState(cliente.vendedor_id ?? OPCION_NINGUNO)
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)
  const operationId = useOperationIdDeEnvio({ clienteId: cliente.id, elegido })
  const actual = etiquetaDeVendedor(cliente)

  if (!puedeAsignarse(cliente)) {
    return (
      <Card>
        <h2 className="text-sm font-medium text-primary">Vendedor</h2>
        <p className="mt-2 text-sm text-primary/70">El consumidor final no se asigna a ningún vendedor: lo ven todos.</p>
      </Card>
    )
  }

  const hayActualFueraDeLaLista =
    cliente.vendedor_id !== null && !vendedores.vendedores.some((vendedor) => vendedor.id === cliente.vendedor_id)

  const guardar = async () => {
    setError(null)
    setGuardado(false)
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await asignar.mutateAsync({
        clienteIds: [cliente.id],
        vendedorId: elegido === OPCION_NINGUNO ? null : elegido,
        operationId: operationId.obtener(),
      })
      operationId.completar()
      setGuardado(true)
    } catch (falla) {
      if (esErrorDeRed(falla)) setError(AVISO_SIN_CONEXION)
      else setError(mensajeDeErrorDeClientes(falla instanceof ErrorDeClientes ? falla.codigo : null, falla instanceof Error ? falla.message : ''))
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-sm font-medium text-primary">
        Vendedor <Ayuda clave="clientes.vendedor" />
      </h2>
      {actual.paraReasignar && <Alert>Su vendedor está dado de baja o sin permiso: reasignalo.</Alert>}
      <SelectorDeVendedor
        id="cliente-vendedor"
        etiqueta="Vendedor"
        valor={elegido}
        vendedores={vendedores.vendedores}
        onCambio={setElegido}
        fijas={[
          { valor: OPCION_NINGUNO, etiqueta: 'Sin vendedor' },
          ...(hayActualFueraDeLaLista && cliente.vendedor_id !== null ? [{ valor: cliente.vendedor_id, etiqueta: actual.texto }] : []),
        ]}
      />
      {vendedores.estado === 'sin-acceso' && (
        <p className="text-sm text-primary/70">No podés ver la lista de vendedores con tu rol: solo podés quitar el vendedor.</p>
      )}
      {error && <Alert>{error}</Alert>}
      {guardado && !error && (
        <p role="status" className="text-sm text-primary">
          Listo: el vendedor quedó guardado.
        </p>
      )}
      <div>
        <Boton disabled={asignar.isPending} onClick={() => void guardar()}>
          Guardar vendedor
        </Boton>
      </div>
    </Card>
  )
}
