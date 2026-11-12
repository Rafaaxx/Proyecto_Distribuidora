import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  CONDICIONES_IVA,
  costosParaRevisar,
  etiquetaDeCondicionIva,
} from '../../../domain/configuracion/condicionIva'
import type { CondicionIva } from '../../../features/configuracion/api'
import { ErrorDeConfiguracion } from '../../../features/configuracion/errores'
import {
  useCambiarCondicionIva,
  useConfiguracionFiscal,
  useResumenReglaIva,
} from '../../../features/configuracion/useConfiguracionFiscal'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'

/**
 * Condición frente al IVA de la organización (change 11b, tarea 7.4; spec
 * `parametros-de-organizacion`, CST-06, `design.md` D7, D10). Cualquier usuario autenticado
 * ve la condición vigente; solo con `ADMIN_CONFIGURACION` (mecanismo compartido
 * `<SiTienePermiso>`, ADR-027) se ofrece cambiarla, tras una confirmación que avisa que el
 * cambio no es retroactivo y cuántos costos vigentes conviene volver a informar. El comando
 * solo se envía al confirmar. El servidor valida igual (SEG-06).
 */
export function ConfiguracionFiscalScreen() {
  const fiscal = useConfiguracionFiscal()

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Configuración fiscal" />
      {fiscal.isPending && <p className="text-sm text-primary/70">Cargando…</p>}
      {fiscal.isError && <Alert>No se pudo obtener la condición frente al IVA.</Alert>}
      {fiscal.isSuccess && (
        <>
          <Card className="flex flex-col gap-1 text-sm text-primary">
            <p>
              Condición frente al IVA: <strong>{etiquetaDeCondicionIva(fiscal.data.condicion_iva)}</strong>
            </p>
            <p>
              {fiscal.data.computa_credito_fiscal
                ? 'Computa crédito fiscal de IVA en las compras: el IVA de una compra no es costo.'
                : 'No computa crédito fiscal de IVA en las compras: el valor pagado es el costo, IVA incluido.'}
            </p>
          </Card>
          <SiTienePermiso permiso="ADMIN_CONFIGURACION">
            <CambioDeCondicion actual={fiscal.data.condicion_iva} />
          </SiTienePermiso>
        </>
      )}
    </main>
  )
}

function CambioDeCondicion({ actual }: { actual: CondicionIva }) {
  const [elegida, setElegida] = useState<CondicionIva>(actual)
  const [confirmando, setConfirmando] = useState(false)
  const cambiar = useCambiarCondicionIva()
  const resumen = useResumenReglaIva(confirmando)

  const cerrar = () => {
    setConfirmando(false)
    cambiar.reset()
  }

  const confirmar = async () => {
    try {
      await cambiar.mutateAsync({ condicion_iva: elegida })
      setConfirmando(false)
    } catch {
      // El error queda en `cambiar.error` y se muestra en la confirmación.
    }
  }

  const mensajeDeError =
    cambiar.error instanceof ErrorDeConfiguracion
      ? cambiar.error.message
      : cambiar.error
        ? 'No se pudo cambiar la condición. Podés reintentar: se reenvía la misma operación.'
        : null

  return (
    <Card className="flex flex-wrap items-end gap-3">
      <Campo id="condicion-nueva" etiqueta="Nueva condición">
        <select
          id="condicion-nueva"
          className="rounded-md border border-border px-2 py-1 text-sm"
          value={elegida}
          onChange={(evento) => setElegida(evento.target.value as CondicionIva)}
        >
          {CONDICIONES_IVA.map((condicion) => (
            <option key={condicion} value={condicion}>
              {etiquetaDeCondicionIva(condicion)}
            </option>
          ))}
        </select>
      </Campo>
      <Boton disabled={elegida === actual} onClick={() => setConfirmando(true)}>
        Cambiar condición
      </Boton>

      <Dialogo abierto={confirmando} titulo="Confirmar cambio de condición" onCerrar={cerrar}>
        <div className="flex flex-col gap-3 text-sm text-primary">
          <p>
            Pasar de {etiquetaDeCondicionIva(actual)} a <strong>{etiquetaDeCondicionIva(elegida)}</strong>.
          </p>
          <p>
            El cambio no es retroactivo: no recalcula ningún costo informado, compra ni costo promedio ya
            registrado. Rige para lo que se registre desde ahora.
          </p>
          {resumen.isPending && <p className="text-primary/70">Calculando costos vigentes…</p>}
          {resumen.isSuccess &&
            (costosParaRevisar(elegida, resumen.data) > 0 ? (
              <p>
                Hay {costosParaRevisar(elegida, resumen.data)} costos vigentes calculados con la otra regla de
                IVA: conviene revisarlos y volver a informarlos.
              </p>
            ) : (
              <p>No hay costos vigentes para revisar.</p>
            ))}
          {mensajeDeError && <Alert>{mensajeDeError}</Alert>}
          <div className="flex gap-2">
            <Boton disabled={cambiar.isPending} onClick={() => void confirmar()}>
              Confirmar cambio
            </Boton>
            <Boton variante="secundario" onClick={cerrar}>
              Cancelar
            </Boton>
          </div>
        </div>
      </Dialogo>
    </Card>
  )
}

export default ConfiguracionFiscalScreen
