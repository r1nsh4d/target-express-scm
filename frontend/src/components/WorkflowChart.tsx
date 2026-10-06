/* The whole cycle, as a chart.
 *
 * The question this answers is the one people actually ask on day one: "when
 * does a consignment get created, and what has to exist before it can?" A list
 * of numbered steps does not answer that, because the real shape is not a list —
 * it is a one-time setup that feeds a loop you run every day.
 *
 * Drawn as inline SVG rather than a picture so it reads in both themes, scales
 * to any width, and can be read by a screen reader. Everything is laid out on a
 * fixed viewBox and scaled by the container, which is what keeps the arrows
 * meeting the boxes at every size.
 */

const SETUP = [
  { label: 'Goods category', detail: 'Spare parts / furniture' },
  { label: 'Vendor', detail: 'Then its divisions' },
  { label: 'Warehouse', detail: 'Where runs start and end' },
  { label: 'Rate card', detail: 'What the vendor is charged' },
  { label: 'Vehicle + driver', detail: 'Owned or hired in' },
  { label: 'Customers', detail: 'The delivery points' },
]

const DAILY = [
  { label: 'Freight', detail: 'Pick division, warehouse, date, points' },
  { label: 'Consignment', detail: 'One vendor bill, attached to one point' },
  { label: 'Boxes', detail: 'Created under the bill' },
  { label: 'Labels', detail: 'One QR sticker per box' },
  { label: 'Dispatch', detail: 'LR issued, opening odometer' },
  { label: 'Deliver', detail: 'Scan each box at the point' },
  { label: 'Return', detail: 'Closing odometer, freight completes' },
  { label: 'Invoice + settle', detail: 'Vendor billed, driver paid' },
]

export function WorkflowChart() {
  const W = 1000
  const boxW = 142
  const boxH = 54
  const gap = 28

  const setupY = 54
  const dailyY1 = 206
  const dailyY2 = 316

  const setupX = (i: number) => 18 + i * (boxW + gap)
  const dailyX = (i: number) => 18 + i * (boxW + gap)

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${W} 400`}
        className="w-full"
        role="img"
        aria-label={
          'The Target Express cycle. Set up once per vendor: goods category, vendor and its ' +
          'divisions, warehouse, rate card, vehicle and driver, customers. Then every day: ' +
          'create a freight, attach consignments to its points, boxes are created under each ' +
          'bill, print one QR label per box, dispatch which issues the LR number, deliver by ' +
          'scanning each box at its point, return to the warehouse to complete the freight, ' +
          'then invoice the vendor and settle the driver.'
        }
      >
        <defs>
          <marker
            id="wf-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-faint)" />
          </marker>
        </defs>

        {/* ---------------- set up once ---------------- */}
        <text x="18" y="26" className="fill-[var(--text-faint)]" fontSize="12" letterSpacing="1.6">
          SET UP ONCE PER VENDOR
        </text>

        {SETUP.map((node, i) => (
          <g key={node.label}>
            <rect
              x={setupX(i)}
              y={setupY}
              width={boxW}
              height={boxH}
              rx="9"
              fill="var(--surface)"
              stroke="var(--border-strong)"
            />
            <text
              x={setupX(i) + boxW / 2}
              y={setupY + 22}
              textAnchor="middle"
              fontSize="13"
              fontWeight="600"
              className="fill-[var(--text)]"
            >
              {node.label}
            </text>
            <text
              x={setupX(i) + boxW / 2}
              y={setupY + 39}
              textAnchor="middle"
              fontSize="10.5"
              className="fill-[var(--text-faint)]"
            >
              {node.detail}
            </text>
            {i < SETUP.length - 1 ? (
              <line
                x1={setupX(i) + boxW}
                y1={setupY + boxH / 2}
                x2={setupX(i + 1) - 6}
                y2={setupY + boxH / 2}
                stroke="var(--text-faint)"
                strokeWidth="1.5"
                markerEnd="url(#wf-arrow)"
              />
            ) : null}
          </g>
        ))}

        {/* Setup feeds the daily loop. */}
        <path
          d={`M ${setupX(0) + boxW / 2} ${setupY + boxH} L ${setupX(0) + boxW / 2} ${dailyY1 - 8}`}
          stroke="var(--text-faint)"
          strokeWidth="1.5"
          strokeDasharray="4 4"
          fill="none"
          markerEnd="url(#wf-arrow)"
        />

        {/* ---------------- every run ---------------- */}
        <text
          x="18"
          y={dailyY1 - 26}
          className="fill-[var(--accent)]"
          fontSize="12"
          letterSpacing="1.6"
        >
          EVERY RUN
        </text>

        {DAILY.map((node, i) => {
          const row = i < 4 ? 0 : 1
          const col = i < 4 ? i : i - 4
          const x = dailyX(col)
          const y = row === 0 ? dailyY1 : dailyY2
          // The consignment step is what the whole chart is here to locate.
          const highlight = node.label === 'Consignment'

          return (
            <g key={node.label}>
              <rect
                x={x}
                y={y}
                width={boxW}
                height={boxH}
                rx="9"
                fill={highlight ? 'var(--accent-dim)' : 'var(--surface)'}
                stroke={highlight ? 'var(--accent)' : 'var(--border-strong)'}
                strokeWidth={highlight ? 1.5 : 1}
              />
              <text
                x={x + boxW / 2}
                y={y + 22}
                textAnchor="middle"
                fontSize="13"
                fontWeight="600"
                fill={highlight ? 'var(--accent)' : 'var(--text)'}
              >
                {node.label}
              </text>
              <text
                x={x + boxW / 2}
                y={y + 39}
                textAnchor="middle"
                fontSize="10.5"
                className="fill-[var(--text-faint)]"
              >
                {node.detail}
              </text>

              {/* within a row */}
              {col < 3 && i !== DAILY.length - 1 ? (
                <line
                  x1={x + boxW}
                  y1={y + boxH / 2}
                  x2={dailyX(col + 1) - 6}
                  y2={y + boxH / 2}
                  stroke="var(--text-faint)"
                  strokeWidth="1.5"
                  markerEnd="url(#wf-arrow)"
                />
              ) : null}
            </g>
          )
        })}

        {/* wrap from the end of row one down to the start of row two */}
        <path
          d={`M ${dailyX(3) + boxW / 2} ${dailyY1 + boxH}
              L ${dailyX(3) + boxW / 2} ${dailyY1 + boxH + 26}
              L ${dailyX(0) + boxW / 2} ${dailyY1 + boxH + 26}
              L ${dailyX(0) + boxW / 2} ${dailyY2 - 8}`}
          stroke="var(--text-faint)"
          strokeWidth="1.5"
          fill="none"
          markerEnd="url(#wf-arrow)"
        />

        {/* and back round for the next run */}
        <path
          d={`M ${dailyX(3) + boxW / 2} ${dailyY2 + boxH}
              L ${dailyX(3) + boxW / 2} ${dailyY2 + boxH + 24}
              L ${dailyX(0) + boxW / 2 - 40} ${dailyY2 + boxH + 24}
              L ${dailyX(0) + boxW / 2 - 40} ${dailyY1 + boxH / 2}
              L ${dailyX(0) - 6} ${dailyY1 + boxH / 2}`}
          stroke="var(--accent)"
          strokeWidth="1.5"
          strokeDasharray="5 5"
          fill="none"
          opacity="0.6"
          markerEnd="url(#wf-arrow)"
        />
        <text
          x={dailyX(1)}
          y={dailyY2 + boxH + 40}
          fontSize="10.5"
          className="fill-[var(--text-faint)]"
        >
          the next run starts again here — the setup above is not repeated
        </text>
      </svg>
    </figure>
  )
}
