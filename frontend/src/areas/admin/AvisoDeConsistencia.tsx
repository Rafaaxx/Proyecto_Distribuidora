import { Ayuda } from '../../components/ui/Ayuda'
import { Card } from '../../components/ui/Card'
import { descripcionDeDiferencia, hayDiferencias } from '../../domain/sistema/consistencia'
import { usePermisos } from '../../features/identidad/usePermisos'
import { useConsistencia } from '../../features/sistema/hooks'
import { formatearFechaHora } from '../../lib/fecha'

/**
 * El aviso de consistencia del inicio de `/admin` (change 28, tarea 3.2; D5, D17; ADR-015, `02` §7.6, SEG-06).
 *
 * Aparece solo para quien tiene `VER_CONSISTENCIA` y mientras la última verificación de su organización haya
 * encontrado diferencias entre un saldo y su libro. Es de solo lectura: no ofrece ninguna acción que modifique
 * saldos (la verificación nunca corrige, para no tapar el problema) y trae su «(?)». Si la consulta falla o
 * todavía no hay ninguna corrida, no afirma nada.
 */
export function AvisoDeConsistencia() {
  const permisos = usePermisos()
  const consistencia = useConsistencia(permisos.tiene('VER_CONSISTENCIA'))
  const datos = consistencia.data

  if (datos === undefined || !hayDiferencias(datos)) {
    return null
  }

  return (
    <section role="alert" aria-labelledby="aviso-de-consistencia" className="max-w-xl">
      <Card className="flex flex-col gap-3 border-danger">
        <div className="flex items-center gap-2">
          <h2 id="aviso-de-consistencia" className="text-lg font-semibold text-danger">
            Diferencias de consistencia
          </h2>
          <Ayuda clave="consistenciaDiferencias" />
        </div>
        {datos.ejecutada_en !== null && (
          <p className="text-sm text-primary/70">Última verificación: {formatearFechaHora(datos.ejecutada_en)}</p>
        )}
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-primary">
          {datos.diferencias.map((diferencia, indice) => (
            <li key={`${diferencia.tipo}-${String(indice)}`}>{descripcionDeDiferencia(diferencia)}</li>
          ))}
        </ul>
      </Card>
    </section>
  )
}

export default AvisoDeConsistencia
