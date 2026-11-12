import { describe, expect, it } from 'vitest'

import {
  esquemaSaldoInicial,
  resolverOperationId,
} from '../../../../src/domain/cuentas-corrientes/saldoInicialSchema'

describe('esquemaSaldoInicial (tarea 7.4)', () => {
  it.each(['150000.00', '150000', '0.5', ' 20.10 '])('acepta el importe %j', (importe) => {
    const resultado = esquemaSaldoInicial.safeParse({ importe, sentido: 'AUMENTA' })
    expect(resultado.success).toBe(true)
    if (resultado.success) expect(resultado.data.importe).toBe(importe.trim())
  })

  it.each(['', '0', '0.00', '-5.00', '12.345', '1,50', 'abc', '1e3', '1234567890123.00'])(
    'rechaza el importe %j con un mensaje para el usuario',
    (importe) => {
      const resultado = esquemaSaldoInicial.safeParse({ importe, sentido: 'REDUCE' })
      expect(resultado.success).toBe(false)
      if (!resultado.success) {
        expect(resultado.error.issues[0]?.message).toMatch(/importe/i)
      }
    },
  )

  it('rechaza un sentido fuera de AUMENTA/REDUCE', () => {
    expect(esquemaSaldoInicial.safeParse({ importe: '10.00', sentido: 'OTRO' }).success).toBe(false)
  })

  it('acepta el sentido REDUCE', () => {
    expect(esquemaSaldoInicial.safeParse({ importe: '10.00', sentido: 'REDUCE' }).success).toBe(true)
  })
})

describe('resolverOperationId (INV-06, TR-07)', () => {
  const datos = { importe: '150000.00', sentido: 'AUMENTA' as const }
  let contador = 0
  const generar = () => `nuevo-${String((contador += 1))}`

  it('sin envío pendiente genera un operation_id nuevo', () => {
    expect(resolverOperationId(null, datos, generar)).toBe('nuevo-1')
  })

  it('con un envío pendiente de los mismos datos reutiliza su operation_id', () => {
    const pendiente = { datos, operationId: 'guardado' }
    expect(resolverOperationId(pendiente, { ...datos }, generar)).toBe('guardado')
  })

  it('si el usuario cambió el importe o el sentido genera uno nuevo', () => {
    const pendiente = { datos, operationId: 'guardado' }
    expect(resolverOperationId(pendiente, { ...datos, importe: '1.00' }, generar)).not.toBe('guardado')
    expect(resolverOperationId(pendiente, { ...datos, sentido: 'REDUCE' }, generar)).not.toBe('guardado')
  })
})
