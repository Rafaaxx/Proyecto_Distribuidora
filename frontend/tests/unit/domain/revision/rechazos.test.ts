import { describe, expect, it } from 'vitest'

import {
  OPCIONES_DE_TIPO_DE_COMANDO,
  etiquetaDeTipoDeComando,
  motivoDeRechazo,
  tipoDeVinculoPermitido,
} from '../../../../src/domain/revision/rechazos'

/** Change 25, tarea 14.1 (D7, D11; SYN-06, SYN-08, SYN-09): cómo se leen los rechazos y qué se puede vincular. */
describe('rechazos de la revisión (SYN-06)', () => {
  it('el motivo se traduce con los textos del teléfono según el tipo de operación', () => {
    expect(motivoDeRechazo('VENTA_CONFIRMAR', 'DISPOSITIVO_REVOCADO')).toBe(
      'Este teléfono fue dado de baja; la venta quedó para revisión.',
    )
    expect(motivoDeRechazo('VENTA_ANULAR', 'VENTA_YA_ANULADA')).toBe('La venta ya estaba anulada en el sistema.')
    expect(motivoDeRechazo('COBRANZA_REGISTRAR', 'COBRANZA_DUPLICADA')).toBe(
      'El sistema ya tenía otra cobranza con el mismo identificador.',
    )
    expect(motivoDeRechazo('JORNADA_ENTREGAR', 'JORNADA_YA_ENTREGADA')).toBe('La jornada ya estaba entregada.')
  })

  it('un código desconocido muestra el texto general y el código', () => {
    expect(motivoDeRechazo('VENTA_CONFIRMAR', 'CODIGO_NUEVO')).toBe('El sistema no aceptó esta venta. (CODIGO_NUEVO)')
    expect(motivoDeRechazo('TIPO_RARO', 'CODIGO_NUEVO')).toBe('El sistema no aceptó esta operación. (CODIGO_NUEVO)')
  })

  it('solo la venta y la cobranza admiten vínculo; la anulación no (D7)', () => {
    expect(tipoDeVinculoPermitido('VENTA_CONFIRMAR')).toBe('VENTA')
    expect(tipoDeVinculoPermitido('VENTA_ANULAR')).toBeNull()
    expect(tipoDeVinculoPermitido('COBRANZA_REGISTRAR')).toBe('COBRANZA')
    expect(tipoDeVinculoPermitido('JORNADA_ENTREGAR')).toBeNull()
    expect(tipoDeVinculoPermitido('OTRO')).toBeNull()
  })

  it('nombra los tipos de comando', () => {
    expect(OPCIONES_DE_TIPO_DE_COMANDO.map((o) => o.valor)).toEqual([
      'VENTA_CONFIRMAR',
      'VENTA_ANULAR',
      'COBRANZA_REGISTRAR',
      'JORNADA_ENTREGAR',
    ])
    expect(etiquetaDeTipoDeComando('VENTA_ANULAR')).toBe('Anulación de venta')
    expect(etiquetaDeTipoDeComando('JORNADA_ENTREGAR')).toBe('Entrega del día')
    expect(etiquetaDeTipoDeComando('OTRO')).toBe('OTRO')
  })
})
