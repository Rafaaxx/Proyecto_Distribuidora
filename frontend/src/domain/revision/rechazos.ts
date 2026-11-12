/**
 * Lectura de los rechazos sin conexión y de la cuarentena en `/admin/revision` (change 25, tarea 14.1; D7, D11;
 * SYN-06, SYN-08, SYN-09). Lógica pura, sin React. El motivo se traduce con los mismos textos que el teléfono
 * (`domain/ruta/textosDeSincronizacion.ts`, fixture de códigos de sincronización).
 */

import {
  NOMBRE_DE_LA_ENTREGA,
  TIPO_DE_ANULACION,
  TIPO_DE_COBRANZA,
  TIPO_DE_ENTREGA,
  textoDeRechazo,
  textoDeRechazoDeAnulacion,
  textoDeRechazoDeCobranza,
  textoDeRechazoDeEntrega,
  type TextoDeRechazo,
} from '../ruta/textosDeSincronizacion'

const TIPO_DE_VENTA = 'VENTA_CONFIRMAR'

/** Los tipos de comando que pueden quedar rechazados, en el orden en que se ofrecen como filtro. */
export const OPCIONES_DE_TIPO_DE_COMANDO: readonly { valor: string; etiqueta: string }[] = [
  { valor: TIPO_DE_VENTA, etiqueta: 'Venta' },
  { valor: TIPO_DE_ANULACION, etiqueta: 'Anulación de venta' },
  { valor: TIPO_DE_COBRANZA, etiqueta: 'Cobranza' },
  { valor: TIPO_DE_ENTREGA, etiqueta: NOMBRE_DE_LA_ENTREGA },
]

export function etiquetaDeTipoDeComando(tipo: string): string {
  return OPCIONES_DE_TIPO_DE_COMANDO.find((opcion) => opcion.valor === tipo)?.etiqueta ?? tipo
}

const TEXTO_GENERAL_DE_OPERACION = 'El sistema no aceptó esta operación.'

function textoPorTipo(tipo: string, codigo: string): TextoDeRechazo {
  switch (tipo) {
    case TIPO_DE_VENTA:
      return textoDeRechazo(codigo)
    case TIPO_DE_ANULACION:
      return textoDeRechazoDeAnulacion(codigo)
    case TIPO_DE_COBRANZA:
      return textoDeRechazoDeCobranza(codigo)
    case TIPO_DE_ENTREGA:
      return textoDeRechazoDeEntrega(codigo)
    default:
      return { texto: TEXTO_GENERAL_DE_OPERACION, codigo, conocido: false }
  }
}

/** El motivo del rechazo en palabras; un código que no se conoce muestra el texto general y el código. */
export function motivoDeRechazo(tipo: string, codigo: string): string {
  const { texto, conocido } = textoPorTipo(tipo, codigo)
  return conocido ? texto : `${texto} (${codigo})`
}

/**
 * Con qué se puede vincular la resolución según el tipo del comando (D7): una venta para la venta, una
 * cobranza para la cobranza; ninguna para lo demás (la anulación se resuelve solo con comentario).
 */
export function tipoDeVinculoPermitido(tipo: string): 'VENTA' | 'COBRANZA' | null {
  if (tipo === TIPO_DE_VENTA) return 'VENTA'
  if (tipo === TIPO_DE_COBRANZA) return 'COBRANZA'
  return null
}
