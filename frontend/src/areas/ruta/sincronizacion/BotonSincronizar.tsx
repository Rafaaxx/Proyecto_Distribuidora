import { Boton } from '../../../components/ui/Button'
import { sincronizarAPedido } from '../../../sync/disparadores'
import { useEstadoDeEnvio } from '../datos/sincronizacion'
import { TEXTO_DE_OTRA_PESTANA, TEXTO_DE_SIN_SENAL, TEXTO_ENVIANDO } from './presentacion'

/**
 * «Sincronizar» (change 22b, `design.md` D8; `02` §13.3): envía a pedido. Mientras envía queda
 * deshabilitado con «Enviando…»; si otra pestaña está sincronizando lo dice; sin señal informa y
 * no cambia nada. Sin lógica de negocio: la decisión es de `sync/disparadores.ts`.
 */
export function BotonSincronizar() {
  const { fase } = useEstadoDeEnvio()
  const enviando = fase === 'enviando'
  return (
    <div className="flex flex-col gap-1">
      <Boton variante="secundario" disabled={enviando} onClick={() => void sincronizarAPedido()}>
        {enviando ? TEXTO_ENVIANDO : 'Sincronizar'}
      </Boton>
      {fase === 'otra_pestana' && <p className="text-sm text-primary/70">{TEXTO_DE_OTRA_PESTANA}</p>}
      {fase === 'sin_senal' && <p className="text-sm text-primary/70">{TEXTO_DE_SIN_SENAL}</p>}
    </div>
  )
}
