import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { Ayuda } from '../../../components/ui/Ayuda'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import { listarOpcionesDeClientes, listarCobranzas } from '../../../features/cobranzas/api'
import { listarVentas } from '../../../features/ventas/api'
import { formatearFechaHora } from '../../../lib/fecha'
import { CLASE_CONTROL } from './DialogoDeResolucion'

export interface Vinculo {
  tipo: 'VENTA' | 'COBRANZA'
  id: string
}

interface VinculoDeRechazoProps {
  tipo: 'VENTA' | 'COBRANZA'
  valor: Vinculo | null
  onChange: (valor: Vinculo | null) => void
}

const NOMBRE_DEL_GRUPO = 'vinculo-de-rechazo'

/**
 * «Vincular con» (change 25, tarea 14.1; D7, D11; SYN-08): la venta —buscada por número— o la cobranza del
 * cliente que se cargó con conexión en lugar de lo rechazado. Es opcional («Sin vincular»). El servidor valida
 * el vínculo (`VINCULO_INVALIDO`); acá solo se ofrece lo que corresponde al tipo.
 */
export function VinculoDeRechazo({ tipo, valor, onChange }: VinculoDeRechazoProps) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="flex items-center gap-1 text-sm font-medium text-primary">
        <span>Vincular con (opcional)</span>
        <Ayuda clave="revision.vinculo" />
      </legend>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="radio"
          name={NOMBRE_DEL_GRUPO}
          checked={valor === null}
          onChange={() => onChange(null)}
        />
        Sin vincular
      </label>
      {tipo === 'VENTA' ? (
        <BuscadorDeVentas valor={valor} onChange={onChange} />
      ) : (
        <BuscadorDeCobranzas valor={valor} onChange={onChange} />
      )}
    </fieldset>
  )
}

function Opcion({ etiqueta, marcada, onElegir }: { etiqueta: string; marcada: boolean; onElegir: () => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="radio" name={NOMBRE_DEL_GRUPO} checked={marcada} onChange={onElegir} />
      {etiqueta}
    </label>
  )
}

const LIMITE_DE_COINCIDENCIAS = 20

function BuscadorDeVentas({ valor, onChange }: Pick<VinculoDeRechazoProps, 'valor' | 'onChange'>) {
  const [texto, setTexto] = useState('')
  const numero = texto.trim()
  // El servidor busca por número (parcial, sin distinguir mayúsculas), de cualquier estado.
  const ventas = useQuery({
    queryKey: ['revision', 'buscar-venta', numero],
    queryFn: () => listarVentas({ numero }, undefined, LIMITE_DE_COINCIDENCIAS),
    enabled: numero !== '',
  })
  const coincidencias = numero === '' ? [] : (ventas.data?.items ?? [])

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="vinculo-buscar-venta" className="text-sm text-primary">
        Buscar venta por número
      </label>
      <input
        id="vinculo-buscar-venta"
        type="search"
        className={CLASE_CONTROL}
        value={texto}
        onChange={(evento) => setTexto(evento.target.value)}
      />
      {coincidencias.map((venta) => (
        <Opcion
          key={venta.venta_id}
          etiqueta={`Venta ${venta.numero} · ${venta.cliente_nombre ?? ''} · ${formatearMonto(venta.total)}`}
          marcada={valor?.id === venta.venta_id}
          onElegir={() => onChange({ tipo: 'VENTA', id: venta.venta_id })}
        />
      ))}
    </div>
  )
}

function BuscadorDeCobranzas({ valor, onChange }: Pick<VinculoDeRechazoProps, 'valor' | 'onChange'>) {
  const [clienteId, setClienteId] = useState('')
  const clientes = useQuery({
    queryKey: ['revision', 'clientes-para-vincular'],
    queryFn: () => listarOpcionesDeClientes('', undefined, 200),
  })
  const cobranzas = useQuery({
    queryKey: ['revision', 'buscar-cobranza', clienteId],
    queryFn: () => listarCobranzas({ clienteId, estado: 'CONFIRMADA' }, undefined, 100),
    enabled: clienteId !== '',
  })

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="vinculo-buscar-cobranza" className="text-sm text-primary">
        Buscar cobranza del cliente
      </label>
      <select
        id="vinculo-buscar-cobranza"
        className={CLASE_CONTROL}
        value={clienteId}
        onChange={(evento) => {
          setClienteId(evento.target.value)
          onChange(null)
        }}
      >
        <option value="">Elegí un cliente</option>
        {(clientes.data?.items ?? []).map((cliente) => (
          <option key={cliente.id} value={cliente.id}>
            {cliente.nombre}
          </option>
        ))}
      </select>
      {(cobranzas.data?.items ?? []).map((cobranza) => (
        <Opcion
          key={cobranza.cobranza_id}
          etiqueta={`Cobranza ${formatearFechaHora(cobranza.occurred_at)} · ${formatearMonto(cobranza.importe)}`}
          marcada={valor?.id === cobranza.cobranza_id}
          onElegir={() => onChange({ tipo: 'COBRANZA', id: cobranza.cobranza_id })}
        />
      ))}
    </div>
  )
}
