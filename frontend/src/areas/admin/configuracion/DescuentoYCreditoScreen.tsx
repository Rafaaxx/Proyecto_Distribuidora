import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  ETIQUETAS_DE_POLITICA,
  ETIQUETAS_DE_TIPO_DE_TOLERANCIA,
  POLITICAS_DE_CREDITO,
  leerTolerancia,
  toleranciaParaElFormulario,
  type PoliticaDeCredito,
  type TipoDeToleranciaElegido,
} from '../../../domain/configuracion/descuentoYCredito'
import type { CreditoOrganizacion, DescuentoManualConfig } from '../../../features/configuracion/api'
import { ErrorDeConfiguracion } from '../../../features/configuracion/errores'
import {
  useConfigurarCreditoOrganizacion,
  useConfigurarDescuentoManual,
  useCreditoOrganizacion,
  useDescuentoManual,
} from '../../../features/configuracion/useDescuentoYCredito'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'

const TITULO = 'Descuento manual y crédito'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MENSAJE_DE_RED = 'No se pudo guardar. Podés reintentar: se reenvía la misma operación.'

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para cambiar la configuración de la empresa.</p>
    </main>
  )
}

function mensajeDe(error: unknown): string | null {
  if (error === null || error === undefined) return null
  return error instanceof ErrorDeConfiguracion ? error.message : MENSAJE_DE_RED
}

/**
 * Descuento manual y crédito por defecto de la empresa (change 18b, tarea 14.1; spec
 * `parametros-de-organizacion`; D13, D14; DSC-06, CRE-03, CRE-06). Solo con `ADMIN_CONFIGURACION`
 * (ADR-027: sin el permiso no se monta ni pide nada). Cada bloque se guarda por separado. Sin lógica
 * de negocio: la tolerancia se arma en `domain/configuracion/descuentoYCredito.ts` y el servidor
 * valida igual (TR-10).
 */
export function DescuentoYCreditoScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      <Contenido />
    </SiTienePermiso>
  )
}

function Contenido() {
  const descuento = useDescuentoManual()
  const credito = useCreditoOrganizacion()
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      {(descuento.isPending || credito.isPending) && <p className="text-sm text-primary/70">Cargando…</p>}
      {(descuento.isError || credito.isError) && <Alert>No se pudo obtener la configuración.</Alert>}
      {descuento.isSuccess && <BloqueDeDescuentoManual actual={descuento.data} />}
      {credito.isSuccess && <BloqueDeCredito actual={credito.data} />}
    </main>
  )
}

function BloqueDeDescuentoManual({ actual }: { actual: DescuentoManualConfig }) {
  const [habilitado, setHabilitado] = useState(actual.habilitado)
  const [motivoObligatorio, setMotivoObligatorio] = useState(actual.motivo_obligatorio)
  const [guardado, setGuardado] = useState(false)
  const configurar = useConfigurarDescuentoManual()

  const sinCambios = habilitado === actual.habilitado && motivoObligatorio === actual.motivo_obligatorio
  const guardar = async (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    setGuardado(false)
    try {
      await configurar.mutateAsync({ habilitado, motivo_obligatorio: motivoObligatorio })
      setGuardado(true)
    } catch {
      // El error queda en `configurar.error` y se muestra abajo.
    }
  }
  const error = mensajeDe(configurar.error)

  return (
    <Card className="flex flex-col gap-3">
      <form onSubmit={(evento) => void guardar(evento)} className="flex flex-col gap-3" data-testid="bloque-descuento-manual">
        <div className="flex items-center gap-1">
          <h2 className="text-base font-semibold text-primary">Descuento manual</h2>
          <Ayuda clave="configuracion.descuentoManual" />
        </div>
        <label className="flex items-center gap-2 text-sm text-primary">
          <input type="checkbox" checked={habilitado} onChange={(evento) => setHabilitado(evento.target.checked)} />
          Permitir descuentos manuales en la venta
        </label>
        <label className="flex items-center gap-2 text-sm text-primary">
          <input
            type="checkbox"
            checked={motivoObligatorio}
            onChange={(evento) => setMotivoObligatorio(evento.target.checked)}
          />
          Exigir un motivo en toda venta con descuento manual
        </label>
        {error && <Alert>{error}</Alert>}
        {guardado && !error && (
          <p role="status" className="text-sm text-primary">
            Se guardó la configuración del descuento manual.
          </p>
        )}
        <div>
          <Boton type="submit" disabled={sinCambios || configurar.isPending}>
            Guardar descuento manual
          </Boton>
        </div>
      </form>
    </Card>
  )
}

function BloqueDeCredito({ actual }: { actual: CreditoOrganizacion }) {
  const inicial = toleranciaParaElFormulario(actual.tolerancia_tipo, actual.tolerancia_valor)
  const [politica, setPolitica] = useState<PoliticaDeCredito>(actual.politica)
  const [tipo, setTipo] = useState<TipoDeToleranciaElegido>(inicial.tipo)
  const [valor, setValor] = useState(inicial.valor)
  const [guardado, setGuardado] = useState(false)
  const configurar = useConfigurarCreditoOrganizacion()

  const tolerancia = leerTolerancia({ tipo, valor })
  const sinCambios =
    tolerancia.valida && politica === actual.politica && tolerancia.tipo === actual.tolerancia_tipo && tolerancia.valor === actual.tolerancia_valor

  const guardar = async (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    if (!tolerancia.valida) return
    setGuardado(false)
    try {
      await configurar.mutateAsync({
        politica,
        tolerancia_tipo: tolerancia.tipo,
        tolerancia_valor: tolerancia.valor,
      })
      setGuardado(true)
    } catch {
      // El error queda en `configurar.error` y se muestra abajo.
    }
  }
  const error = mensajeDe(configurar.error)

  return (
    <Card className="flex flex-col gap-3">
      <form onSubmit={(evento) => void guardar(evento)} className="flex flex-col gap-3" data-testid="bloque-credito">
        <div className="flex items-center gap-1">
          <h2 className="text-base font-semibold text-primary">Crédito por defecto</h2>
          <Ayuda clave="configuracion.credito" />
        </div>
        <Campo id="credito-politica" etiqueta="Si un cliente se pasa de su límite">
          <select
            id="credito-politica"
            className={CLASE_CONTROL}
            value={politica}
            onChange={(evento) => setPolitica(evento.target.value as PoliticaDeCredito)}
          >
            {POLITICAS_DE_CREDITO.map((p) => (
              <option key={p} value={p}>
                {ETIQUETAS_DE_POLITICA[p]}
              </option>
            ))}
          </select>
        </Campo>
        <div className="flex flex-wrap items-start gap-3">
          <Campo id="credito-tolerancia-tipo" etiqueta="Tolerancia sin señal">
            <select
              id="credito-tolerancia-tipo"
              className={CLASE_CONTROL}
              value={tipo}
              onChange={(evento) => setTipo(evento.target.value as TipoDeToleranciaElegido)}
            >
              {(Object.keys(ETIQUETAS_DE_TIPO_DE_TOLERANCIA) as TipoDeToleranciaElegido[]).map((t) => (
                <option key={t} value={t}>
                  {ETIQUETAS_DE_TIPO_DE_TOLERANCIA[t]}
                </option>
              ))}
            </select>
          </Campo>
          {tipo !== '' && (
            <Campo
              id="credito-tolerancia-valor"
              etiqueta={tipo === 'IMPORTE' ? 'Importe de la tolerancia ($)' : 'Porcentaje del límite (%)'}
              error={tolerancia.valida ? undefined : tolerancia.mensaje}
            >
              <input
                id="credito-tolerancia-valor"
                className={`${CLASE_CONTROL} w-36`}
                inputMode="decimal"
                value={valor}
                onChange={(evento) => setValor(evento.target.value)}
              />
            </Campo>
          )}
        </div>
        {error && <Alert>{error}</Alert>}
        {guardado && !error && (
          <p role="status" className="text-sm text-primary">
            Se guardó el crédito por defecto.
          </p>
        )}
        <div>
          <Boton type="submit" disabled={sinCambios || !tolerancia.valida || configurar.isPending}>
            Guardar crédito por defecto
          </Boton>
        </div>
      </form>
    </Card>
  )
}

export default DescuentoYCreditoScreen
