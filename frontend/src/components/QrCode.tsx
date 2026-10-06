/* A QR code, drawn as SVG.
 *
 * SVG rather than canvas because these are printed. A canvas renders at screen
 * resolution and a 20mm sticker printed from a 96dpi bitmap has soft module
 * edges, which is exactly what makes a scan fail on a dusty box in a godown.
 * SVG prints at whatever the printer can do.
 *
 * The encoded value is the bare barcode — `TE-A7K2M-003` — not a URL. A URL
 * would be three times the characters, which means a denser code, which means
 * smaller modules at the same sticker size and a harder scan. Nothing needs to
 * resolve it: the driver's app is already open at the point, and the code only
 * has to be unique.
 *
 * Error correction is set to M (~15% recoverable). Stickers get scuffed in a
 * lorry and taped over at the edges; L would be smaller but a single scrape
 * across a corner kills it.
 */

import { useEffect, useState } from 'react'

export function QrCode({
  value,
  size = 64,
  className,
}: {
  value: string
  size?: number
  className?: string
}) {
  const [svg, setSvg] = useState<string | null>(null)

  useEffect(() => {
    let live = true

    /* The generator is imported here rather than at the top of the file so it
       lands in its own chunk. Only the labels screen draws QR codes, and that
       is admin-only — without this every driver downloads 56KB of label
       printer onto a phone that will never print one. */
    import('qrcode')
      .then(({ default: QRCode }) =>
        QRCode.toString(value, {
          type: 'svg',
          errorCorrectionLevel: 'M',
          // No quiet zone from the library: the sticker layout provides its
          // own white space, and the default 4-module margin would waste a
          // third of the width at this size.
          margin: 0,
          color: { dark: '#000000', light: '#ffffff' },
        }),
      )
      .then((markup) => {
        if (live) setSvg(markup)
      })
      .catch(() => {
        // A label that cannot draw its QR still prints — the code is also on
        // the sticker as text, and a sticker without a QR beats no sticker.
        if (live) setSvg(null)
      })
    return () => {
      live = false
    }
  }, [value])

  if (!svg) {
    // Hold the space so the label does not reflow when the code arrives.
    return <div className={className} style={{ width: size, height: size }} aria-hidden />
  }

  return (
    <div
      className={className}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`QR code for ${value}`}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
