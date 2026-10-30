import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { avisosDeBaja } from '../../../domain/identidad/usuarios'
import { useDatosParaAvisosDeBaja } from '../../../features/identidad/useAvisosDeBaja'
import { useDarDeBajaUsuario, useReactivarUsuario } from '../../../features/identidad/useUsuariosAdmin'
import type { UsuarioDetalle } from '../../../features/identidad/usuariosApi'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { describirErrorDeUsuarios, estaSinConexion, AVISO_SIN_CONEXION } from './errores'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

/**
 * Baja y reactivación de un usuario con confirmación (change 20b, D2, D5, D6; ADR-028, ADR-053).
 * La baja avisa de la jornada abierta y de los clientes asignados (leídos de las lecturas
 * existentes); no los impide. La reactivación avisa que el PIN hay que definirlo de nuevo y, si su
 * rol está de baja, que no va a poder entrar. Un reintento del mismo envío reenvía el mismo
 * `Operation-Id` (INV-06).
 */
export function FichaEstado({ usuario }: { usuario: UsuarioDetalle }) {
  const [dialogo, setDialogo] = useState<'baja' | 'reactivar' | null>(null)
  const activo = usuario.estado === 'ACTIVO'

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-base font-semibold text-primary">
        Estado <Ayuda clave="usuarios.baja" />
      </h2>
      <p className="text-sm text-primary">
        <Badge variante={activo ? 'positivo' : 'negativo'}>{activo ? 'Activo' : 'De baja'}</Badge>
      </p>
      <div>
        {activo ? (
          <Boton variante="peligro" onClick={() => setDialogo('baja')}>
            Dar de baja
          </Boton>
        ) : (
          <Boton onClick={() => setDialogo('reactivar')}>Reactivar</Boton>
        )}
      </div>
      {dialogo === 'baja' && <DialogoDeBaja usuario={usuario} onCerrar={() => setDialogo(null)} />}
      {dialogo === 'reactivar' && <DialogoDeReactivacion usuario={usuario} onCerrar={() => setDialogo(null)} />}
    </Card>
  )
}

function DialogoDeBaja({ usuario, onCerrar }: { usuario: UsuarioDetalle; onCerrar: () => void }) {
  const baja = useDarDeBajaUsuario()
  const datos = useDatosParaAvisosDeBaja(usuario.id)
  const [observacion, setObservacion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const texto = observacion.trim()
  const operationId = useOperationIdDeEnvio({ usuarioId: usuario.id, observacion: texto })
  const avisos = avisosDeBaja(datos)

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await baja.mutateAsync({
        usuarioId: usuario.id,
        observacion: texto === '' ? null : texto,
        operationId: operationId.obtener(),
      })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError(describirErrorDeUsuarios(falla))
    }
  }

  return (
    <Dialogo abierto titulo={`Confirmar baja de ${usuario.nombre}`} onCerrar={onCerrar}>
      <div className="flex flex-col gap-3 text-sm text-primary">
        <p>
          {usuario.nombre} deja de poder entrar y se cierran sus sesiones. Su PIN de autorización se borra. Después lo podés
          reactivar.
        </p>
        {avisos.map((aviso) => (
          <Alert key={aviso}>{aviso}</Alert>
        ))}
        <div className="flex flex-col gap-1">
          <label htmlFor="baja-observacion" className="font-medium">
            Observación (opcional)
          </label>
          <textarea
            id="baja-observacion"
            className={CLASE_CONTROL}
            rows={2}
            value={observacion}
            onChange={(evento) => setObservacion(evento.target.value)}
          />
        </div>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton variante="peligro" disabled={baja.isPending} onClick={() => void confirmar()}>
            Confirmar baja
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}

function DialogoDeReactivacion({ usuario, onCerrar }: { usuario: UsuarioDetalle; onCerrar: () => void }) {
  const reactivar = useReactivarUsuario()
  const [error, setError] = useState<string | null>(null)
  const operationId = useOperationIdDeEnvio({ usuarioId: usuario.id, accion: 'reactivar' })

  const confirmar = async () => {
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await reactivar.mutateAsync({ usuarioId: usuario.id, operationId: operationId.obtener() })
      operationId.completar()
      onCerrar()
    } catch (falla) {
      setError(describirErrorDeUsuarios(falla))
    }
  }

  return (
    <Dialogo abierto titulo={`Confirmar reactivación de ${usuario.nombre}`} onCerrar={onCerrar}>
      <div className="flex flex-col gap-3 text-sm text-primary">
        <p>{usuario.nombre} va a poder iniciar sesión de nuevo con su rol, su tope propio y sus clientes asignados.</p>
        <p>Si su rol autoriza excepciones, tiene que volver a definir su PIN de autorización.</p>
        {!usuario.rol_activo && (
          <Alert>Su rol está dado de baja: no va a poder entrar hasta que le asignes un rol activo.</Alert>
        )}
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Boton disabled={reactivar.isPending} onClick={() => void confirmar()}>
            Confirmar reactivación
          </Boton>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
        </div>
      </div>
    </Dialogo>
  )
}
