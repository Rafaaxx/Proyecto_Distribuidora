import { Link } from 'react-router-dom'

import { Card } from '../../../components/ui/Card'
import { textoDeSaldo, type CuentaTipo } from '../../../domain/cuentas-corrientes/presentacion'
import { useSaldoActual } from '../../../features/cuentas-corrientes/hooks'

/**
 * Saldo actual y enlace "Cuenta corriente" de la ficha de un cliente o de un
 * proveedor (change 08, tarea 7.2; spec `administracion-de-cuentas-corrientes`).
 *
 * Solo se monta dentro de la ficha en modo edición, que ya exige el permiso de
 * lectura de la cuenta (`GESTIONAR_CLIENTES` / `GESTIONAR_PROVEEDORES`, D2),
 * así que no consulta permisos por su cuenta. El saldo es el string de la API
 * formateado en el dominio (`textoDeSaldo`): ningún importe pasa por `number`.
 * Si no se pudo leer el saldo, se avisa pero el enlace sigue disponible: la
 * pantalla de cuenta corriente explica el error con más detalle.
 */
export function SaldoDeCuenta({ cuentaTipo, entidadId }: { cuentaTipo: CuentaTipo; entidadId: string }) {
  const saldo = useSaldoActual(cuentaTipo, entidadId)
  const coleccion = cuentaTipo === 'CLIENTE' ? 'clientes' : 'proveedores'

  return (
    <Card>
      <h2 className="text-sm font-medium text-primary">Cuenta corriente</h2>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
        {saldo.isPending && <p className="text-primary/70">Cargando saldo…</p>}
        {saldo.isError && <p className="text-primary/70">No se pudo obtener el saldo.</p>}
        {saldo.isSuccess && <p className="font-medium text-primary">{textoDeSaldo(cuentaTipo, saldo.data)}</p>}
        <Link
          to={`/admin/${coleccion}/${entidadId}/cuenta-corriente`}
          className="text-primary/70 hover:text-primary hover:underline"
        >
          Cuenta corriente
        </Link>
      </div>
    </Card>
  )
}

export default SaldoDeCuenta
