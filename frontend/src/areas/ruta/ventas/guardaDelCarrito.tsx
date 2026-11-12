import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { ContextoGuarda } from './contextoGuarda'

/**
 * Proveedor de la guarda del carrito (change 22a, `design.md` D12; `02` §13.5, VTA-07). Estado en
 * memoria: el carrito no se persiste. Va por encima de la sesión y del aviso de versión nueva.
 */
export function ProveedorGuardaDelCarrito({ children }: { children: ReactNode }) {
  const [ocupado, setOcupado] = useState(false)
  const marcar = useCallback((valor: boolean) => setOcupado(valor), [])
  const valor = useMemo(() => ({ ocupado, marcar }), [ocupado, marcar])
  return <ContextoGuarda.Provider value={valor}>{children}</ContextoGuarda.Provider>
}
