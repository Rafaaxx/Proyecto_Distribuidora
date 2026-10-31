/**
 * Archivo único de textos de ayuda contextual (change 16b, ADR-051, `design.md` D3 y D9).
 *
 * - Cada pantalla pide su ayuda por clave (`<Ayuda clave="descuentos.medida" />` o
 *   `<Campo ayuda="descuentos.medida">`); ninguna escribe un texto por su cuenta.
 *   `ClaveDeAyuda` y `TemaDeAyuda` son tipos derivados de este archivo: una clave mal escrita
 *   no compila.
 * - `reglas` lista los IDs de `docs/01-dominio.md` o los ADR en que se apoya el texto. Sirven
 *   para mantenerlo (si cambia la regla, se busca su ID acá) y NO se muestran en pantalla
 *   (D4 = A). `tests/unit/ayuda/trazabilidad.test.ts` exige que existan.
 * - Texto plano. Un asterisco (`*x*`) marca énfasis en cursiva y dos (`**x**`) negrita; el
 *   resto se muestra tal cual. Un `ejemplo` va en un recuadro aparte.
 * - Los textos son los aprobados por el usuario el 2026-10-15 (`design.md` D9, "Revisión del
 *   usuario"); un cambio de texto se aprueba antes de editar este archivo.
 */

export interface SeccionDeTema {
  titulo: string
  parrafos: readonly string[]
  ejemplo?: string
}

export interface TemaDeAyudaDef {
  titulo: string
  reglas: readonly string[]
  secciones: readonly SeccionDeTema[]
}

export const TEMAS = {
  descuentos: {
    titulo: 'Cómo se aplican los descuentos',
    reglas: ['DSC-03', 'DSC-04', 'DSC-05', 'ADR-050'],
    secciones: [
      {
        titulo: 'En qué orden se resuelven',
        parrafos: [
          'En una venta pueden cumplirse varias reglas a la vez; el sistema las resuelve siempre en este orden.',
        ],
      },
      {
        titulo: '1. Qué reglas se cumplen',
        parrafos: [
          'Se revisa cada regla activa y vigente; para saber si se cumple se mira siempre la venta antes de cualquier descuento (cantidades y precios de lista).',
        ],
        ejemplo:
          'Ej.: con "≥ 20 cajas → 5 %", 19 cajas + 5 botellas de un vino x6 = 19,83 cajas, no se cumple; 20 cajas sí.',
      },
      {
        titulo: '2. Entre las no acumulables gana una sola',
        parrafos: [
          'Gana la que más descuento da en pesos en toda la venta; la prioridad solo desempata si dan exactamente lo mismo (gana el número más bajo).',
        ],
        ejemplo:
          'Ej.: 12 cajas de Vino A ($150.000) y 10 de Vino B ($86.000); "≥ 20 cajas → 5 %" sobre toda la venta daría $11.800 y "≥ 10 cajas de Vino A → 8 %" daría $12.000: gana la segunda y Vino B queda sin descuento aunque la otra lo incluía.',
      },
      {
        titulo: '3. Las acumulables, una después de otra',
        parrafos: [
          'Las acumulables se suman una después de otra, en orden de prioridad, cada una sobre el precio que dejó la anterior.',
        ],
        ejemplo: 'Ej.: 8 % y después 2 % = 9,84 %, no 10 %.',
      },
      {
        titulo: '4. El descuento manual, al final',
        parrafos: [
          'Al final, el descuento manual del vendedor sobre lo que quedó: uno general para toda la venta o uno distinto en una línea, que reemplaza al general en esa línea.',
        ],
      },
    ],
  },
  topes: {
    titulo: 'Cómo funcionan los topes',
    reglas: ['DSC-06', 'ADR-050'],
    secciones: [
      {
        titulo: 'Qué es el tope',
        parrafos: [
          'El tope es cuánto descuento manual puede dar alguien sin pedir permiso; se configura por rol en "Topes por rol". Solo cuenta el descuento manual (lo de las reglas automáticas no suma).',
        ],
      },
      {
        titulo: 'Cuándo se revisa',
        parrafos: [
          'Se revisa una vez por venta, contra el porcentaje manual más alto que haya quedado en algún producto.',
        ],
      },
      {
        titulo: 'Qué pasa si se supera',
        parrafos: [
          'Si lo supera, hace falta una autorización, y una sola alcanza para toda la venta: puede darla el mismo vendedor si tiene el permiso de autorizar, o un supervisor con su PIN. Quien autoriza puede aprobar cualquier porcentaje, aunque su propio tope sea menor; queda registrado quién autorizó.',
        ],
      },
      {
        titulo: 'Los topes iniciales',
        parrafos: [
          'Los roles empiezan con 0 %, salvo el Administrador (sin tope): hasta configurarlos, cualquier descuento manual pide autorización.',
        ],
        ejemplo:
          'Ej. con tope 5 %: 5 % a toda la venta pasa directo; 5 % a toda la venta y 10 % a un producto pide una autorización; 10 % a toda la venta pero 3 % puesto en cada producto → el máximo que quedó es 3 % y pasa directo.',
      },
    ],
  },
  precio: {
    titulo: 'Cómo se calcula el precio de una lista',
    reglas: ['PRC-11', 'PRC-12', 'PRC-13', 'PRC-14', 'PRC-15', 'PRC-17', 'CST-04'],
    secciones: [
      {
        titulo: 'Los tres pasos',
        parrafos: ['Cada precio sale de tres pasos y después se publica.'],
      },
      {
        titulo: '1. El costo',
        parrafos: [
          'El costo informado vigente del producto (no el promedio), llevado a su presentación de referencia, por ejemplo la caja.',
        ],
      },
      {
        titulo: '2. El margen',
        parrafos: [
          'La regla de margen más específica que le corresponda, en este orden: producto, marca, categoría, proveedor o la de toda la lista.',
        ],
      },
      {
        titulo: '3. El redondeo',
        parrafos: ['Al múltiplo de la lista, o al de su categoría si tiene uno propio.'],
        ejemplo:
          'Ej.: vino con costo $6.000 y margen bruto 30 % → $8.571,43; redondeo a múltiplo 100 hacia arriba → $8.600.',
      },
      {
        titulo: 'Nada cambia hasta que publicás',
        parrafos: [
          'Cargar un costo o cambiar una regla no toca los precios; primero generás un borrador, que recalcula todo y avisa lo que conviene revisar, y después lo publicás, ahora o con fecha. Los precios puestos a mano se mantienen de un borrador al siguiente.',
        ],
      },
    ],
  },
  'cobranzas-observaciones': {
    titulo: 'Avisos de los pagos cargados sin señal',
    reglas: ['SYN-05', 'SYN-07', 'SYN-10', 'RUT-09'],
    secciones: [
      {
        titulo: 'Por qué el pago se toma igual',
        parrafos: [
          'Cuando el vendedor cobra sin señal, la plata ya se cobró. Por eso el sistema toma el pago igual y, si algo no coincide con lo que hay hoy en la oficina, deja un aviso para revisar. Cada aviso dice qué pasó y en qué medio.',
        ],
      },
      {
        titulo: 'Medio inactivo',
        parrafos: ['Entró plata por un medio que en la oficina dieron de baja.'],
        ejemplo: 'Ej.: $10.000 por «Billetera» después de cerrar esa cuenta.',
      },
      {
        titulo: 'Falta la referencia',
        parrafos: ['Una transferencia llegó sin número de operación, que ese medio pide.'],
        ejemplo: 'Ej.: una transferencia de $20.000 sin número.',
      },
      {
        titulo: 'Permiso revocado',
        parrafos: ['Al vendedor le habían quitado el permiso de cobrar antes de que el pago llegara.'],
        ejemplo: 'Ej.: Juan cobró $50.000 a las 9:00 y a las 12:00 le sacaron el permiso; el pago llegó a las 18:00.',
      },
      {
        titulo: 'Jornada liberada',
        parrafos: ['Su jornada ya se había destrabado desde la oficina cuando el pago llegó.'],
        ejemplo: 'Ej.: la jornada de la camioneta 2 se destrabó a las 14:00 y el pago llegó a las 18:00.',
      },
      {
        titulo: 'Cliente no habilitado',
        parrafos: ['Se le cobró a «Consumidor final», que no tiene cuenta corriente.'],
        ejemplo: 'Ej.: $5.000 cobrados a «Consumidor final».',
      },
      {
        titulo: 'Qué hacer con los avisos',
        parrafos: [
          'Por ahora los avisos se ven en el detalle de cada cobranza, junto a la línea afectada. La bandeja para darlos por revisados llega más adelante.',
        ],
      },
    ],
  },
  credito: {
    titulo: 'Cómo funciona el crédito de los clientes',
    reglas: ['CRE-01', 'CRE-02', 'CRE-03', 'CRE-04', 'CRE-05', 'CRE-06', 'CRE-07', 'CRE-08', 'CRE-09', 'CRE-10'],
    secciones: [
      {
        titulo: 'Cuánto crédito le queda',
        parrafos: [
          'El disponible es el límite menos lo que el cliente ya debe. Sin límite cargado no hay control; con límite cero, solo se le vende de contado.',
        ],
      },
      {
        titulo: 'Qué consume una venta',
        parrafos: [
          'La venta usa crédito solo por lo que queda sin cobrar. Si se cobra todo en el acto no usa nada, aunque el cliente ya esté pasado de su límite.',
        ],
      },
      {
        titulo: 'Advertir',
        parrafos: ['Te muestra cuánto se pasa y podés confirmar aceptándolo. La venta queda marcada para revisar.'],
      },
      {
        titulo: 'Autorizar',
        parrafos: [
          'Hace falta el permiso de superar el crédito o el PIN de un supervisor que lo tenga. Queda registrado quién autorizó.',
        ],
      },
      {
        titulo: 'Bloquear',
        parrafos: ['La venta no se confirma, ni con permiso. Podés cobrar más en el acto o sacar productos del pedido.'],
      },
      {
        titulo: 'Sin señal',
        parrafos: [
          'El teléfono calcula con lo último que sabe del cliente y la venta nunca se rechaza por crédito, porque la mercadería ya se entregó. Con la política Autorizar, un exceso que entra en la tolerancia de la empresa se confirma solo; si no entra, hace falta permiso propio o el PIN de un supervisor.',
          'Cuando la venta llega al sistema, se vuelve a calcular con lo que el cliente debe de verdad. Si se pasaba y el teléfono no lo había visto, la venta queda marcada para revisar.',
        ],
        ejemplo:
          'Ej.: Exceso de $10.000: con tolerancia $20.000 se confirma y queda marcada; con $5.000 pide permiso o PIN.',
      },
      {
        titulo: 'Qué queda guardado en la venta',
        parrafos: [
          'La venta guarda lo que vio quien vendió: límite, deuda considerada, disponible, exceso, política, cómo se resolvió y quién autorizó. Si después cambia el límite del cliente, la venta no cambia.',
        ],
      },
    ],
  },
  'ventas-observaciones': {
    titulo: 'Avisos de las ventas cargadas sin señal',
    reglas: ['SYN-05', 'SYN-07', 'STK-06', 'CRE-09', 'DSC-09', 'ADR-054', 'ADR-055'],
    secciones: [
      {
        titulo: 'Por qué la venta se toma igual',
        parrafos: ['La venta se tomó igual porque la mercadería ya se entregó.'],
      },
      {
        titulo: 'Stock negativo',
        parrafos: ['Se vendió más de lo que figuraba en la ubicación. El stock quedó por debajo de cero hasta que se corrija con un ajuste o una transferencia.'],
      },
      {
        titulo: 'Lista no vigente',
        parrafos: ['El teléfono usó precios de una versión de lista que ya no regía al momento de la venta. La venta quedó con esos precios.'],
      },
      {
        titulo: 'Cliente no habilitado',
        parrafos: ['El cliente estaba suspendido o inactivo cuando se hizo la venta.'],
      },
      {
        titulo: 'Consumidor final con deuda',
        parrafos: ['Al consumidor final se le cobró un importe distinto del total. Su cuenta quedó con un saldo que no se puede cobrar después.'],
      },
      {
        titulo: 'Permiso revocado',
        parrafos: ['Al vendedor le habían quitado el permiso de vender antes de que la venta llegara.'],
      },
      {
        titulo: 'Jornada liberada',
        parrafos: ['Un supervisor liberó la jornada del vendedor antes de que la venta llegara.'],
      },
      {
        titulo: 'Ubicación tomada al sincronizar',
        parrafos: ['Cuando la venta llegó, la ubicación estaba tomada por otra jornada o en rendición. El stock se descontó igual.'],
      },
      {
        titulo: 'Vendido sin costo',
        parrafos: ['El producto no tenía costo cargado. La venta quedó sin costo y hay que revisarlo.'],
      },
      {
        titulo: 'Medio inactivo',
        parrafos: ['Se cobró con un medio de pago que estaba desactivado.'],
      },
      {
        titulo: 'Falta la referencia',
        parrafos: ['Se cobró con un medio que exige referencia, por ejemplo el número de transferencia, y no se cargó.'],
      },
      {
        titulo: 'Descuentos distintos',
        parrafos: ['Los descuentos que registró el teléfono no coinciden con los que da el sistema hoy, o el descuento manual ya no habría pasado la revisión (tope, permiso, motivo o autorizador). La venta se tomó con los descuentos del teléfono.'],
      },
      {
        titulo: 'Autorización sin señal',
        parrafos: ['Un descuento o un exceso de crédito se autorizó sin señal, con el PIN de un supervisor o con el permiso del propio vendedor. Conviene revisar que quien autorizó tenía el permiso.'],
      },
      {
        titulo: 'Exceso de crédito advertido',
        parrafos: ['El cliente se pasó de su límite y el vendedor aceptó el aviso para confirmar la venta.'],
      },
      {
        titulo: 'Exceso dentro de la tolerancia',
        parrafos: ['Sin señal, el cliente se pasó de su límite pero el exceso entraba en la tolerancia de la empresa, y la venta se confirmó sin pedir permiso.'],
      },
      {
        titulo: 'Exceso de crédito detectado al sincronizar',
        parrafos: ['Con lo que el cliente debía de verdad, la venta lo dejó pasado de su límite, aunque el teléfono no lo había visto.'],
      },
    ],
  },
} as const satisfies Record<string, TemaDeAyudaDef>

export type TemaDeAyuda = keyof typeof TEMAS

export interface EntradaDeAyuda {
  titulo: string
  texto: string
  ejemplo?: string
  reglas: readonly string[]
  verMas?: TemaDeAyuda
}

export const AYUDAS = {
  // --- Descuentos: formulario de regla, detalle y topes por rol ---
  'descuentos.alcance': {
    titulo: 'Alcance de la regla',
    texto:
      '¿A qué productos se aplica la regla? *Toda la venta*: cuenta y descuenta todo lo vendido. *Productos, categorías o marcas*: solo lo que coincida con alguno de los que elijas.',
    ejemplo:
      'Ej.: si elegís la marca Bodega Norte y la categoría Cervezas, entran todos los vinos de Bodega Norte y todas las cervezas.',
    reglas: ['DSC-02', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.medida': {
    titulo: 'Medida',
    texto:
      'Qué se cuenta para saber si la regla se cumple. *Cajas equivalentes*: lo vendido pasado a cajas, aunque se venda suelto (15 botellas de un vino que viene x6 = 2,5 cajas). *Unidades*: botellas o latas sueltas. *Importe*: pesos, a precio de lista, antes de descuentos.',
    reglas: ['DSC-03', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.umbral': {
    titulo: 'Umbral',
    texto:
      'El número que hay que alcanzar. En cajas admite decimales (2,5); en unidades, solo enteros (60); en importe, pesos con centavos ($31.250,00).',
    reglas: ['DSC-03'],
  },
  'descuentos.accion': {
    titulo: 'Acción',
    texto:
      'Qué descuento se hace. *Porcentaje*: se descuenta ese % de cada producto que entra en la regla. *Importe fijo*: un monto total que se reparte entre esos productos según lo que vale cada uno.',
    ejemplo: 'Ej.: $1.000 entre un producto de $31.250 y otro de $4.300 → $879,04 y $120,96.',
    reglas: ['DSC-04', 'DSC-07'],
    verMas: 'descuentos',
  },
  'descuentos.prioridad': {
    titulo: 'Prioridad',
    texto:
      '1 es la más importante. Si se cumplen varias reglas no acumulables, gana la que **más descuento da**, no la de prioridad 1: la prioridad solo decide si dan exactamente lo mismo. En las acumulables, indica en qué orden se aplican.',
    reglas: ['DSC-05', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.acumulable': {
    titulo: 'Acumulable',
    texto:
      '*No acumulable*: si se cumplen varias, se aplica solo una, la que más descuento da. *Acumulable*: se suma a las demás, y cada una se calcula sobre el precio que dejó la anterior.',
    ejemplo: 'Ej.: 8 % y después 2 % dan 9,84 %, no 10 %.',
    reglas: ['DSC-03', 'DSC-05', 'ADR-050'],
    verMas: 'descuentos',
  },
  'descuentos.vigencia': {
    titulo: 'Vigencia',
    texto:
      "Desde cuándo y hasta cuándo aplica. Si dejás 'desde' vacío, aplica desde que la activás. Si dejás 'hasta' vacío, no vence.",
    ejemplo: 'Ej.: desde el 1/11 hasta el 1/12 = todo noviembre.',
    reglas: ['ADR-050'],
  },
  'descuentos.activar': {
    titulo: 'Activar',
    texto:
      'Una regla solo se puede editar mientras es borrador. Activada, solo se puede pausar, reactivar o ponerle fecha de fin. Para cambiarle otra cosa, pausala y creá una nueva.',
    reglas: ['ADR-050'],
  },
  'descuentos.tope': {
    titulo: 'Tope de descuento',
    texto:
      'Cuánto descuento manual puede dar este rol sin pedir autorización. No limita los descuentos automáticos de las reglas. Si el vendedor pasa el tope en algún producto, la venta necesita **una** autorización, que vale para toda la venta. Los roles empiezan con 0 %, salvo el Administrador.',
    ejemplo:
      'Ej.: con tope 5 %, un 3 % a toda la venta pasa directo; un 10 % a un producto pide autorización.',
    reglas: ['DSC-06', 'ADR-050'],
    verMas: 'topes',
  },

  // --- Listas de precios ---
  'precios.redondeo': {
    titulo: 'Redondeo',
    texto:
      'Para que los precios queden redondos. El precio calculado se lleva al múltiplo que elijas: hacia arriba, hacia abajo o al más cercano (si queda justo en la mitad, sube). Se redondea el precio sin IVA.',
    ejemplo: 'Ej.: $8.571,43 con múltiplo 100 → $8.600 hacia arriba o al más cercano; $8.500 hacia abajo.',
    reglas: ['PRC-01', 'PRC-14', 'PRC-15'],
    verMas: 'precio',
  },
  'precios.redondeoCategoria': {
    titulo: 'Redondeo por categoría',
    texto:
      'Permite que una categoría redondee distinto que el resto de la lista. Si está activo, manda sobre el redondeo de la lista para los productos de esa categoría. Si al redondear el precio queda en $0, el producto queda sin precio.',
    reglas: ['PRC-14'],
    verMas: 'precio',
  },
  'precios.tipoMargen': {
    titulo: 'Tipo de margen',
    texto:
      'Cómo se calcula el precio a partir del costo. *Markup*: al costo se le suma un % del costo. *Margen bruto*: el % es la ganancia sobre el precio de venta (tiene que ser menor que 100 %).',
    ejemplo: 'Ej.: costo $6.000 y 30 % → markup $7.800; margen bruto $8.571,43.',
    reglas: ['PRC-12'],
    verMas: 'precio',
  },
  'precios.alcanceMargen': {
    titulo: 'Se aplica a',
    texto:
      'A qué productos aplica este margen. Si a un producto le corresponden varias reglas, manda la más específica, en este orden: producto, marca, categoría, proveedor y, por último, la de toda la lista.',
    ejemplo:
      'Ej.: si Cervezas tiene 25 % y la cerveza X tiene su propia regla de 20 %, la cerveza X va con 20 %. Los cambios se ven recién en el próximo borrador.',
    reglas: ['PRC-13'],
    verMas: 'precio',
  },
  'precios.borrador': {
    titulo: 'Borrador de precios',
    texto:
      'Los precios nuevos se preparan en un borrador antes de publicarlos. Cargar un costo nuevo no cambia ningún precio: hay que generar el borrador, que recalcula todos los productos. Los precios puestos a mano se mantienen. Hay un solo borrador por lista; regenerarlo reemplaza el anterior.',
    reglas: ['PRC-17', 'PRC-18'],
    verMas: 'precio',
  },
  'precios.senales': {
    titulo: 'Señales del precio',
    texto:
      'Avisos para revisar antes de publicar. *Costos distintos por presentación*: la botella sale distinto si se compró suelta o en caja. *Otra regla de IVA*: el costo se cargó con otra condición frente al IVA. *Margen menor*: el precio puesto a mano quedó por debajo del calculado.',
    reglas: ['PRC-11', 'PRC-17'],
  },
  'precios.sinPrecio': {
    titulo: 'Productos sin precio',
    texto:
      'Productos activos a los que el borrador no les pudo calcular precio. Pasa si les falta el costo, una regla de margen o la presentación de referencia, o si el precio da $0 o menos. Si ya corregiste lo que faltaba, regenerá el borrador. Para ponerle precio a mano, el producto tiene que tener presentación de referencia.',
    reglas: ['PRC-19'],
  },
  'precios.precioManual': {
    titulo: 'Precio manual',
    texto:
      'Para fijar un precio a mano en lugar del calculado. Se mantiene en los próximos borradores, que te avisan si quedó por debajo del calculado. Se puede poner aunque el producto no tenga costo.',
    reglas: ['PRC-16', 'PRC-17'],
  },
  'precios.publicacion': {
    titulo: 'Vigencia de la publicación',
    texto:
      "Desde cuándo rigen los precios nuevos. Si dejás 'desde' vacío, rigen apenas publicás (nunca puede ser una fecha pasada). Cuando empieza la nueva versión, la anterior deja de regir sola; si la nueva tiene 'hasta' y vence, vuelve a regir la anterior. Solo se puede anular una publicación que todavía no empezó.",
    reglas: ['PRC-02', 'PRC-03', 'PRC-05'],
    verMas: 'precio',
  },

  // --- Compras y costos ---
  'costos.valorConIva': {
    titulo: 'Valor',
    texto:
      'El precio de la presentación como figura en la factura. Si marcás que incluye IVA, el sistema se lo saca al costo, porque como responsable inscripto ese IVA lo recuperás.',
    ejemplo: 'Ej.: caja x12 a $18.000 con IVA → $18.000 / 1,21 / 12 = unos $1.239,67 por botella.',
    reglas: ['CST-02', 'CST-06'],
  },
  'costos.valorPagado': {
    titulo: 'Valor pagado',
    texto:
      'Lo que pagaste por la presentación, con el IVA incluido. Como el IVA no lo recuperás, es parte del costo y no se descuenta.',
    ejemplo: 'Ej.: caja x12 a $21.780 → $21.780 / 12 = $1.815 por botella.',
    reglas: ['CST-02', 'CST-06'],
  },
  'costos.bonificacion': {
    titulo: 'Bonificación',
    texto:
      'El descuento que te hizo el proveedor en ese producto. Se resta del valor antes de calcular el costo.',
    ejemplo: 'Ej.: caja x12 a $18.000 con 10 % → $16.200, o sea $1.350 por botella.',
    reglas: ['CST-02'],
  },
  'costos.costoBase': {
    titulo: 'Costo base',
    texto:
      'Lo que te cuesta una sola botella o lata. Es el costo que el sistema usa para todo (precios y ganancia de las ventas) y se calcula a partir de la presentación que compraste.',
    ejemplo: 'Ej.: caja x12 a $18.000 sin IVA → $1.500 por botella.',
    reglas: ['CST-02', 'CMP-02'],
  },
  'compras.totalFactura': {
    titulo: 'Total de factura',
    texto:
      'El total que figura en la factura del proveedor. El sistema te sugiere uno sumando los productos (con su IVA, si corresponde); corregilo si no coincide. Este total es lo que le debés al proveedor; el costo de la mercadería se calcula con los valores de cada producto, no con este total.',
    reglas: ['CMP-02', 'CMP-03'],
  },
  'compras.costoPromedioEInformado': {
    titulo: 'Costo promedio y costo informado',
    texto:
      'Al registrar la compra, el sistema ya actualizó el **costo promedio**, que se usa para calcular la ganancia de cada venta. El **costo informado** es otro: es el que usa la lista de precios, y solo cambia si marcás esta opción.',
    ejemplo: 'Ej.: tenías 60 botellas a $1.000 y compraste 60 a $1.100 → el promedio queda en $1.050.',
    reglas: ['CST-04', 'CST-11', 'CMP-04'],
  },

  // --- Stock y jornadas ---
  'stock.requiereToma': {
    titulo: 'Requiere toma',
    texto:
      'Para ubicaciones que un vendedor usa durante su jornada, como un vehículo. Mientras un vendedor la tiene tomada, solo su jornada puede mover el stock de ahí. Los vehículos siempre la requieren.',
    reglas: ['STK-02', 'STK-09', 'RUT-01'],
  },
  'stock.tomaActual': {
    titulo: 'Toma actual',
    texto:
      "Muestra qué jornada tiene tomada esta ubicación. Mientras la jornada está abierta, solo ese vendedor (desde su dispositivo) puede mover el stock. Cuando pasa a rendición, ya nadie puede, salvo quien tiene el permiso 'Liberar ubicación'.",
    reglas: ['STK-09', 'RUT-01'],
  },
  'stock.liberacion': {
    titulo: 'Liberar ubicación',
    texto:
      'Destraba la ubicación cuando una jornada quedó trabada (por ejemplo, se le rompió el teléfono al vendedor). No toca el stock del vehículo. Pide un motivo y queda registrado quién lo hizo. Si después llegan ventas de esa jornada desde el dispositivo, se aceptan, pero quedan marcadas para revisar.',
    reglas: ['RUT-09', 'STK-09', 'AUD-01'],
  },

  // --- Cobranzas ---
  'cobranzas.medios': {
    titulo: 'Medios de pago',
    texto:
      'Cómo te pagó el cliente. Podés repartir el total entre varios medios, y la suma tiene que dar justo lo que cobraste. Algunos medios, como la transferencia, piden el número de la operación.',
    ejemplo: 'Ej.: Kiosco La Esquina paga $50.000: $30.000 en efectivo y $20.000 por transferencia (n.º 0042).',
    reglas: ['COB-01', 'COB-02', 'INV-08'],
  },
  'cobranzas.saldoAFavor': {
    titulo: 'Saldo después de la cobranza',
    texto:
      'Lo que el cliente va a deber después de este pago. El pago baja lo que debe en total, no una factura en particular. Si paga de más, le queda plata a favor y se descuenta sola de su próxima compra.',
    ejemplo: 'Ej.: Kiosco La Esquina debe $150.000 y paga $160.000 → le quedan $10.000 a favor.',
    reglas: ['COB-03', 'CC-04'],
  },
  'cobranzas.jornada': {
    titulo: 'Jornada',
    texto:
      'Muestra en qué recorrido del vendedor entró este pago. Si lo cobra un vendedor con su jornada abierta, queda en esa jornada y aparece cuando rinde la plata. Lo que se carga desde la oficina no lleva jornada.',
    ejemplo: 'Ej.: Juan cobra $50.000 en Kiosco La Esquina desde la camioneta 2 → figura en su jornada de hoy.',
    reglas: ['RUT-07'],
  },
  'cobranzas.anulacion': {
    titulo: 'Anular una cobranza',
    texto:
      'Deja el pago sin efecto: el cliente vuelve a deber lo mismo que antes. No se borra: queda como anulado, con el motivo y quién lo anuló. Se anula entero; si te equivocaste en un medio, anulalo y cargalo de nuevo. El cobro de una venta se anula anulando la venta.',
    ejemplo: 'Ej.: un cheque de $20.000 de Almacén Don Pedro vuelve rechazado → lo anulás y su deuda sube $20.000.',
    reglas: ['COB-05', 'CC-02'],
  },
  'cobranzas.observaciones': {
    titulo: 'Avisos de una cobranza sin señal',
    texto:
      'Avisos para revisar en un pago que el vendedor cargó sin señal. El pago se tomó igual, porque la plata ya se cobró. Cada aviso dice qué pasó y en qué medio; tocá «Ver más» para ver qué significa cada uno.',
    reglas: ['SYN-05', 'SYN-07', 'SYN-10', 'RUT-09'],
    verMas: 'cobranzas-observaciones',
  },
  // --- Medios de pago y roles (change 17b, textos aprobados el 2026-10-17) ---
  'mediosPago.requiereReferencia': {
    titulo: 'Pide referencia',
    texto:
      'Marcalo si cada vez que se use este medio hay que anotar un dato para encontrar la plata después, como el número de la transferencia o del cheque. Con conexión, sin ese dato no se guarda el cobro ni el pago; si el vendedor está sin señal, entra igual y queda marcado para revisar.',
    ejemplo: 'Ej.: «Transferencia» pide referencia: al cobrar $20.000 por transferencia hay que escribir el n.º 0042.',
    reglas: ['COB-02', 'PAG-01', 'SYN-07'],
  },
  'mediosPago.baja': {
    titulo: 'Dar de baja un medio',
    texto:
      'Deja de ofrecerse en cobros y pagos nuevos. No se borra: los de antes lo siguen mostrando, y lo podés volver a activar cuando quieras. Siempre tiene que quedar al menos un medio activo.',
    ejemplo:
      'Ej.: cerraste la cuenta de la billetera → das de baja «Billetera»; el pago de $10.000 de ayer sigue diciendo «Billetera».',
    reglas: ['CAT-05', 'TR-06', 'ADR-053'],
  },
  'roles.permisos': {
    titulo: 'Permisos del rol',
    texto:
      'Lo que puede hacer cada persona que tiene este rol. Cuando guardás, el cambio vale para todos los usuarios del rol desde su próxima acción, sin cerrar la sesión.',
    ejemplo: 'Ej.: le quitás «Anular cobranzas» al Supervisor comercial → ya no ven el botón «Anular» en las cobranzas.',
    reglas: ['ADR-017'],
  },
  'roles.ultimoAdministrador': {
    titulo: 'Último administrador',
    texto:
      'Siempre tiene que quedar al menos una persona activa que pueda administrar usuarios y roles; si no, nadie podría arreglar los permisos después. Por eso no te deja quitar este permiso, dar de baja a ese usuario o a su rol, ni cambiarle el rol, si es el último que lo tiene.',
    reglas: ['ADR-053'],
  },
  'roles.autorizacion': {
    titulo: 'Permisos de autorización',
    texto:
      'Con estos permisos, la persona puede autorizar excepciones con su PIN, como un descuento mayor o vender pasado el límite de crédito. Si el rol se queda sin ninguno, se borra el PIN de sus usuarios y, si después se los devolvés, cada uno tiene que crear uno nuevo.',
    ejemplo:
      'Ej.: le sacás «Autorizar descuentos» y «Vender con exceso de crédito» al Supervisor → el PIN de Ana deja de servir.',
    reglas: ['ADR-011'],
  },
  // --- Usuarios, roles y cartera (change 20b, textos aprobados el 2026-10-28, D18; sin ejemplos) ---
  'usuarios.baja': {
    titulo: 'Dar de baja a un usuario',
    texto:
      'Al dar de baja a un usuario deja de poder entrar y se cierran sus sesiones. Si tiene una jornada abierta, su teléfono puede subir lo que vendió o cobró sin conexión, pero no puede operar. No se puede dar de baja al último usuario que administra usuarios y roles, ni a uno mismo.',
    reglas: ['ADR-028', 'ADR-053'],
  },
  'usuarios.cambioDeRol': {
    titulo: 'Cambiar el rol de un usuario',
    texto:
      'El cambio rige desde la próxima acción del usuario. Si el rol nuevo no puede autorizar excepciones, se borra su PIN de autorización.',
    reglas: ['ADR-017', 'ADR-011'],
  },
  'usuarios.topePropio': {
    titulo: 'Tope de descuento propio',
    texto:
      'Si el usuario tiene tope propio, reemplaza al de su rol, sea mayor o menor. Vacío: rige el del rol. Solo tiene efecto si su rol tiene descuento manual.',
    reglas: ['DSC-06'],
  },
  'usuarios.contrasena': {
    titulo: 'Restablecer la contraseña',
    texto: 'La contraseña nueva cierra sus sesiones abiertas y desbloquea el inicio de sesión si estaba bloqueado.',
    reglas: ['ADR-018', 'ADR-057'],
  },
  'roles.baja': {
    titulo: 'Dar de baja un rol',
    texto:
      'Un rol con usuarios activos no se puede dar de baja: primero cambiales el rol. Un rol de baja no se puede asignar.',
    reglas: ['ADR-028'],
  },
  'clientes.vendedor': {
    titulo: 'Vendedor del cliente',
    texto:
      'Los vendedores ven primero sus clientes asignados y pueden buscar en todos. Un vendedor sin clientes asignados ve todos.',
    reglas: ['ADR-052', 'CLI-03'],
  },
  // --- Ventas (change 18a, textos aprobados por el usuario el 2026-10-17 y el 2026-10-19; D22) ---
  'ventas.cajasYUnidades': {
    titulo: 'Cajas y unidades',
    texto:
      'Cargá cuántas cajas y cuántas unidades sueltas lleva el cliente. Se cobra en proporción al precio de la caja, aunque lleve botellas sueltas. Si el producto no tiene presentación de una unidad, solo se vende por caja.',
    ejemplo: 'Ej.: 2 cajas + 3 botellas de Vino A (caja x6 a $12.500) = 15 botellas → $31.250.',
    reglas: ['CAT-07', 'CAT-08', 'VTA-02', 'PRC-22'],
  },
  'ventas.precio': {
    titulo: 'Precio',
    texto:
      'El precio sale de la lista del cliente (o la general, si no tiene una) vigente en el momento de la venta. Queda guardado en la venta: si mañana cambia la lista, esta venta no cambia.',
    ejemplo: 'Ej.: Kiosco La Esquina usa la lista General: Vino A a $12.500 la caja.',
    reglas: ['PRC-20', 'PRC-22', 'PRC-23'],
  },
  'ventas.listaAnterior': {
    titulo: 'Lista o versión anterior',
    texto:
      'Sirve para respetar un precio de otra lista o de una versión anterior. Solo lo puede hacer quien tiene permiso, pide un motivo y queda registrado quién lo hizo.',
    ejemplo:
      'Ej.: Almacén Don Pedro tenía Vino A a $8.600 la semana pasada → elegís esa versión con el motivo «Precio acordado con el cliente».',
    reglas: ['PRC-21', 'AUD-01'],
  },
  'ventas.cobranza': {
    titulo: 'Cobranza en el acto',
    texto:
      'Lo que el cliente te paga ahora. Puede ser nada, una parte, todo o más: la venta suma el total a su cuenta y el pago lo baja. Si paga de más, le queda saldo a favor.',
    ejemplo: 'Ej.: Venta de $80.000 con $20.000 en efectivo y un saldo de $150.000 → queda debiendo $210.000.',
    reglas: ['VTA-11', 'CC-05', 'COB-02'],
  },
  'ventas.consumidorFinal': {
    titulo: 'Consumidor final',
    texto: 'Al cliente sin nombre se le vende solo de contado: el pago tiene que ser igual al total.',
    ejemplo: 'Ej.: Venta de $4.300 → cobrás $4.300.',
    reglas: ['CLI-03', 'ADR-054'],
  },
  'ventas.stock': {
    titulo: 'Stock',
    texto:
      'Muestra cuánto queda en la ubicación de la venta. Si no alcanza, la venta no se confirma, salvo que tengas permiso para dejar el stock en negativo; en ese caso queda marcada para revisar.',
    ejemplo: 'Ej.: Quedan 48 botellas y vendés 50 → queda en −2 y se marca.',
    reglas: ['STK-05', 'STK-01', 'ADR-054'],
  },
  'ventas.numero': {
    titulo: 'Número de venta',
    texto:
      'Es el número de la nota de venta: las letras son de este dispositivo y el número sube de a uno. No se repite nunca en la organización.',
    ejemplo: 'Ej.: V03-000142 es la venta 142 del teléfono V03.',
    reglas: ['VTA-06', 'ADR-008'],
  },
  'ventas.costo': {
    titulo: 'Costo',
    texto:
      'Lo que costó la mercadería vendida, al costo promedio del momento de la venta. Queda fijo: si después el producto sube, esta venta no cambia.',
    ejemplo: 'Ej.: 72 botellas a $1.050 de promedio → costo $75.600.',
    reglas: ['VTA-05', 'INV-10'],
  },
  'ventas.observaciones': {
    titulo: 'Avisos de una venta',
    texto:
      'Avisos para revisar en una venta. La venta se tomó igual porque la mercadería ya se entregó. Tocá «Ver más» para ver qué significa cada aviso.',
    reglas: ['SYN-05', 'SYN-07', 'STK-06', 'ADR-054'],
    verMas: 'ventas-observaciones',
  },
  // --- Venta con descuentos, crédito y autorización (change 18b, D22; textos corregidos por el
  // usuario el 2026-10-21 y cargados tal cual) ---
  'ventas.descuentoGeneral': {
    titulo: 'Descuento a toda la venta',
    texto:
      'Un porcentaje para todos los productos, que se aplica después de los descuentos automáticos. Si a una línea le ponés su propio porcentaje, ese reemplaza al general en esa línea: no se suman.',
    ejemplo: 'Ej.: 5 % general sobre un vino que ya quedó en $29.687,50 por volumen → $1.484,38 menos.',
    reglas: ['DSC-05', 'DSC-06'],
    verMas: 'topes',
  },
  'ventas.descuentoPropio': {
    titulo: 'Descuento de esta línea',
    texto:
      'Reemplaza al general solo en esta línea, sea mayor o menor. No se puede poner 0 % para dejar una línea sin el general.',
    ejemplo: 'Ej.: General 5 % y 10 % en el vino → el vino lleva 10 % y el resto 5 %.',
    reglas: ['DSC-05', 'DSC-08', 'ADR-050'],
  },
  'ventas.topeDescuento': {
    titulo: 'Tu tope',
    texto:
      'Cuánto descuento manual podés dar sin pedir autorización. Se compara con el porcentaje manual más alto que quedó en algún producto; los descuentos automáticos no cuentan.',
    ejemplo:
      'Ej.: Con tope 5 %: 5 % general pasa directo; 5 % general y 8 % en un producto pide autorización.',
    reglas: ['DSC-06'],
    verMas: 'topes',
  },
  'ventas.autorizacion': {
    titulo: 'Autorización',
    texto:
      'Si el descuento pasa tu tope, o el cliente se pasa del crédito y su política pide autorización, alguien tiene que aprobar la venta. Si tenés el permiso, la aprobás vos. Si no, un supervisor elige su nombre y escribe su PIN acá; el PIN no se guarda y queda registrado quién autorizó.',
    ejemplo: 'Ej.: Marta escribe su PIN y la venta queda con Marta como autorizadora.',
    reglas: ['DSC-06', 'CRE-05', 'SEG-05'],
  },
  'ventas.motivoDescuento': {
    titulo: 'Motivo del descuento',
    texto:
      'Si la empresa lo exige, toda venta con descuento manual lleva un motivo, uno solo por venta, que queda guardado en cada producto con descuento manual.',
    reglas: ['DSC-06', 'DSC-08'],
  },
  'ventas.descuentosAutomaticos': {
    titulo: 'Descuentos automáticos',
    texto:
      'Salen de las reglas activas (por cajas, unidades o importe) y se calculan solos; desde la venta no se quitan ni se cambian. Si cambian entre que armaste el pedido y confirmás, la venta no se confirma y se muestran los nuevos.',
    reglas: ['DSC-05', 'DSC-09'],
  },
  'ventas.credito': {
    titulo: 'Crédito del cliente',
    texto:
      'Disponible = límite − lo que ya debe. La venta usa crédito solo por lo que queda sin cobrar. Sin límite cargado no hay control; límite cero es solo de contado.',
    ejemplo:
      'Ej.: Límite $200.000, debe $150.000, venta $80.000 con cobranza $20.000 → queda debiendo $210.000: se pasa $10.000.',
    reglas: ['CRE-01', 'CRE-02'],
    verMas: 'credito',
  },
  'ventas.politicaCredito': {
    titulo: 'Si se pasa del crédito',
    texto:
      'Depende de la política del cliente o, si no tiene, la de la empresa. Advertir: te avisa y podés confirmar; la venta queda marcada para revisar. Autorizar: hace falta tu permiso o el PIN de un supervisor. Bloquear: no se confirma; podés cobrar más o sacar productos.',
    reglas: ['CRE-03', 'CRE-04', 'CRE-05', 'CRE-07'],
    verMas: 'credito',
  },

  // --- Anulación de una venta (change 19, D18; textos aprobados el 2026-10-24, sin ejemplos) ---
  'ventas.anulacion': {
    titulo: 'Anular una venta',
    texto:
      'Deja la venta sin efecto: la mercadería vuelve a la ubicación de donde salió y al cliente se le descuenta de su cuenta el total de la venta. No se borra: queda como anulada, con el motivo y quién la anuló. Se anula entera y una sola vez.',
    reglas: ['VTA-20', 'VTA-21', 'INV-19', 'TR-06'],
  },
  'ventas.devolverDinero': {
    titulo: '¿Devolvés lo que cobraste?',
    texto:
      'Si le devolvés al cliente lo que pagó con esta venta, el cobro también se anula y su cuenta queda como antes de la venta. Si no se lo devolvés, ese pago le queda a favor para lo próximo que compre.',
    reglas: ['VTA-22', 'COB-05', 'ADR-058'],
  },
  'ventas.motivoAnulacion': {
    titulo: 'Motivo',
    texto: 'Elegí por qué anulás. Queda guardado en la venta y en la auditoría.',
    reglas: ['VTA-20', 'AUD-01', 'AUD-02'],
  },
  'ventas.consumidorFinalAnulacion': {
    titulo: 'Consumidor final',
    texto: 'Al cliente sin nombre siempre se le devuelve lo que pagó: no tiene cuenta donde dejarle saldo a favor.',
    reglas: ['CLI-03', 'VTA-22', 'ADR-058'],
  },
  'ventas.reingresoUbicacion': {
    titulo: 'Adónde vuelve la mercadería',
    texto:
      'Vuelve a la ubicación de donde salió. Si esa camioneta está ahora en la jornada de otro vendedor, solo puede anular quien tiene permiso para mover una ubicación tomada.',
    reglas: ['VTA-21', 'STK-09', 'ADR-058'],
  },
  'ventas.costoAnulacion': {
    titulo: 'Costo de lo que vuelve',
    texto:
      'La mercadería vuelve al mismo costo con que salió en la venta, y el costo promedio del producto se recalcula como en una compra.',
    reglas: ['VTA-21', 'CST-11', 'CST-13'],
  },

  // --- Configuración del descuento manual y del crédito (change 18b, D22) ---
  'configuracion.descuentoManual': {
    titulo: 'Descuento manual',
    texto:
      'Deshabilitado: nadie da descuentos manuales en la venta (los automáticos siguen). Exigir motivo: cada venta con descuento manual pide elegir un motivo.',
    reglas: ['DSC-06'],
  },
  'configuracion.credito': {
    titulo: 'Crédito por defecto',
    texto:
      'La política vale para los clientes que no tienen una propia. La tolerancia sin señal es cuánto puede pasarse un vendedor sin conexión cuando la política es Autorizar, en pesos o en porcentaje del límite; sin tolerancia, todo exceso sin señal pide permiso o PIN.',
    ejemplo: 'Ej.: Exceso de $10.000: con tolerancia $20.000 se confirma y queda marcada; con $5.000 pide permiso o PIN.',
    reglas: ['CRE-03', 'CRE-06', 'ADR-032'],
  },

  // --- PIN de autorización (change 18b, D21, D22) ---
  'roles.pinAutorizacion': {
    titulo: 'PIN de autorización',
    texto: 'Con este PIN un supervisor aprueba, en la pantalla de otro, un descuento o un exceso de crédito.',
    reglas: ['SEG-05', 'ADR-011', 'ADR-019'],
  },
  'cuenta.miPin': {
    titulo: 'Mi PIN',
    texto:
      'Es el PIN con el que aprobás, en la pantalla de otra persona, un descuento o una venta que se pasa del crédito. Para cambiarlo te pedimos tu contraseña. Tiene que tener al menos 6 números y no puede ser fácil de adivinar, como 123456 o 111111. Es distinto del PIN con el que desbloqueás el teléfono. Cuando lo cambiás, el anterior deja de servir.',
    reglas: ['SEG-05', 'ADR-011', 'ADR-019'],
  },

  // --- Nota de venta (change 20, D11; textos aprobados el 2026-10-27, sin ejemplos) ---
  'ventas.notaDeVenta': {
    titulo: 'Nota de venta',
    texto:
      'Es un comprobante interno de la venta, para entregarle al cliente. No es una factura. Al volver a imprimirla sale igual que la original, aunque después cambien los precios o los datos del cliente.',
    reglas: ['VTA-13', 'ADR-008'],
  },
  'ventas.notaAnulada': {
    titulo: 'Nota de una venta anulada',
    texto:
      'La nota sale con la marca ANULADA, la fecha y el motivo de la anulación, y si se devolvió lo cobrado. No muestra el saldo de la cuenta.',
    reglas: ['VTA-13', 'ADR-058', 'ADR-059'],
  },
  'configuracion.notaMuestraSaldo': {
    titulo: 'Saldo en la nota',
    texto:
      'Si lo activás, la nota muestra cuánto debe el cliente después de esa venta, sumando lo que ya debía, el total y restando lo cobrado en el acto. Ese saldo es el del momento de la venta y no cambia al volver a imprimirla. No se muestra al consumidor final ni en una venta anulada.',
    reglas: ['VTA-13', 'CRE-02'],
  },
  'configuracion.notaDatosOrganizacion': {
    titulo: 'Domicilio y teléfono',
    texto:
      'Salen en el encabezado de todas las notas, junto al nombre y el CUIT de la empresa. Son opcionales: si los dejás vacíos, la nota no los muestra.',
    reglas: ['VTA-13'],
  },

  // --- Motivos, alícuotas y redondeo por defecto (change 20c, D14; textos aprobados el 2026-10-30, sin ejemplos) ---
  'motivos.ambito': {
    titulo: 'Ámbito del motivo',
    texto:
      'Cada motivo sirve para un solo tipo de operación: los de un ámbito solo se ofrecen en esa operación. El ámbito no se cambia después de crear el motivo.',
    reglas: ['TR-09', 'ADR-061'],
  },
  'motivos.nombre': {
    titulo: 'Nombre del motivo',
    texto:
      'Si le cambiás el nombre, las operaciones anteriores que lo usaron muestran el nombre nuevo. No puede haber dos motivos con el mismo nombre en un ámbito.',
    reglas: ['ADR-061'],
  },
  'motivos.baja': {
    titulo: 'Dar de baja un motivo',
    texto:
      'Deja de ofrecerse en operaciones nuevas. No se borra: las anteriores lo siguen mostrando y lo podés volver a activar. Cada ámbito tiene que conservar al menos un motivo activo.',
    reglas: ['CAT-05', 'TR-06', 'ADR-061'],
  },
  'alicuotas.valor': {
    titulo: 'Porcentaje de la alícuota',
    texto:
      'El porcentaje no se cambia una vez creada la alícuota. Si cambia la tasa, creá una nueva, pasá los productos a ella y dá de baja la anterior. Las compras y ventas ya hechas conservan el porcentaje con que se hicieron.',
    reglas: ['TR-02', 'CAT-01', 'ADR-061'],
  },
  'alicuotas.baja': {
    titulo: 'Dar de baja una alícuota',
    texto:
      'Deja de ofrecerse al crear o editar productos. No se puede dar de baja mientras la use un producto activo, ni si es la última activa.',
    reglas: ['CAT-05', 'ADR-061'],
  },
  'configuracion.redondeoPorDefecto': {
    titulo: 'Redondeo por defecto',
    texto:
      'Es el redondeo que aparece cargado al crear una lista de precios nueva; en cada lista lo podés cambiar. Cambiarlo no modifica las listas que ya existen ni sus precios. Sin definir, la lista nueva empieza con el redondeo vacío.',
    reglas: ['PRC-01', 'PRC-14', 'ADR-061'],
  },
  // --- Área de ruta (change 21, ADR-062; textos aprobados el 2026-10-30, sin ejemplos) ---
  'ruta.pin': {
    titulo: 'PIN de este teléfono',
    texto:
      'El PIN abre la aplicación en este teléfono, con o sin señal. No es tu contraseña. Si lo errás varias veces seguidas, tenés que iniciar sesión con conexión y definir uno nuevo; lo que tengas pendiente no se pierde.',
    reglas: ['SEG-03', 'SEG-04', 'ADR-011', 'ADR-062'],
  },
  'ruta.datosDelDia': {
    titulo: 'Datos del día',
    texto:
      'Los clientes, precios, saldos y stock se descargan al abrir la jornada. Hasta que los actualices, ves los de ese momento, aunque no tengas señal. Actualizar requiere conexión y no toca lo que tengas pendiente.',
    reglas: ['SYN-11', 'ADR-006'],
  },
  'ruta.almacenamiento': {
    titulo: 'Almacenamiento del teléfono',
    texto:
      'Este navegador no garantiza conservar los datos de la aplicación y puede borrarlos si le falta espacio. Instalá la aplicación en la pantalla de inicio y actualizá los datos con conexión cuando puedas.',
    reglas: ['ADR-062'],
  },
  'ruta.cartera': {
    titulo: 'Tu cartera de clientes',
    texto: 'Primero ves tus clientes asignados. Podés buscar y venderle a cualquier cliente de la organización.',
    reglas: ['ADR-060'],
  },
} as const satisfies Record<string, EntradaDeAyuda>

export type ClaveDeAyuda = keyof typeof AYUDAS
