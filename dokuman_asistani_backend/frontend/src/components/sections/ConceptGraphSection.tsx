import { SectionShell } from '../layout/SectionShell';

const graphNodes = [
  { label: 'Veri', x: 80, y: 130 },
  { label: 'Ağırlık', x: 240, y: 65 },
  { label: 'Aktivasyon', x: 240, y: 190 },
  { label: 'Kayıp', x: 410, y: 130 },
  { label: 'Geri Yayılım', x: 575, y: 130 },
];

const graphEdges = [
  ['Veri', 'Ağırlık'],
  ['Veri', 'Aktivasyon'],
  ['Ağırlık', 'Kayıp'],
  ['Aktivasyon', 'Kayıp'],
  ['Kayıp', 'Geri Yayılım'],
];

const positions = Object.fromEntries(graphNodes.map((node) => [node.label, node]));

export function ConceptGraphSection() {
  return (
    <SectionShell
      id="concept-graph"
      eyebrow="Kavram Grafiği"
      title="Basit, taşmayan ve şık örnek kavram bağlantıları"
      description="Statik örnek grafik kullanılıyor; node ve bağlantılar `viewBox` ile ölçeklenerek mobilde de taşmadan kalır."
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr),300px]">
        <div className="surface-muted overflow-hidden p-4">
          <svg viewBox="0 0 660 260" className="h-auto w-full">
            {graphEdges.map(([from, to]) => {
              const start = positions[from];
              const end = positions[to];
              return (
                <line
                  key={`${from}-${to}`}
                  x1={start.x}
                  y1={start.y}
                  x2={end.x}
                  y2={end.y}
                  stroke="#cbd5e1"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
              );
            })}
            {graphNodes.map((node) => (
              <g key={node.label}>
                <circle cx={node.x} cy={node.y} r="42" fill="white" stroke="#cbd5e1" strokeWidth="3" />
                <text
                  x={node.x}
                  y={node.y + 5}
                  textAnchor="middle"
                  fill="#0f172a"
                  fontSize="14"
                  fontFamily="Manrope, sans-serif"
                  fontWeight="700"
                >
                  {node.label}
                </text>
              </g>
            ))}
          </svg>
        </div>

        <div className="grid gap-3">
          {graphNodes.map((node) => (
            <div key={node.label} className="rounded-[22px] border border-slate-200 bg-white p-4">
              <p className="text-sm font-semibold text-slate-900">{node.label}</p>
              <p className="mt-2 text-sm leading-7 text-slate-600">
                {node.label === 'Kayıp'
                  ? 'Modelin hatayı nasıl ölçtüğünü temsil eder.'
                  : 'Grafikteki birincil kavram düğümlerinden biridir.'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </SectionShell>
  );
}
