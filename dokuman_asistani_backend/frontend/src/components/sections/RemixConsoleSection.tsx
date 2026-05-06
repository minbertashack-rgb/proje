import { useState } from 'react';
import { SectionShell } from '../layout/SectionShell';
import { remixModes } from '../../data/mockDashboard';

type ToneKey = keyof typeof remixModes.preview;

export function RemixConsoleSection() {
  const [tone, setTone] = useState<ToneKey>('Dengeli');
  const [depth, setDepth] = useState('2 dk anlatım');
  const preview = remixModes.preview[tone];

  return (
    <SectionShell
      id="remix-console"
      eyebrow="Remix Stil Konsolu"
      title="Ton ve derinlik kontrolleri dar ekranda alt alta akan bir konsolda"
      description="Yan yana alanlar tablet ve mobilde bozulmadan alt alta geçer. Yazı boyutu ve kart yoğunluğu viewport ile birlikte yumuşak biçimde ayarlanır."
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.95fr),minmax(0,1.05fr)]">
        <div className="space-y-4">
          <div className="surface-muted p-5">
            <p className="text-sm font-semibold text-slate-900">Ton</p>
            <div className="mt-4 flex flex-wrap gap-3">
              {remixModes.tones.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setTone(item as ToneKey)}
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                    tone === item
                      ? 'border-slate-900 bg-slate-900 text-white'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="surface-muted p-5">
            <p className="text-sm font-semibold text-slate-900">Derinlik</p>
            <div className="mt-4 flex flex-wrap gap-3">
              {remixModes.depths.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setDepth(item)}
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                    depth === item
                      ? 'border-teal-600 bg-teal-600 text-white'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-[26px] border border-slate-200 bg-slate-950 p-5 text-slate-100">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold tracking-[0.2em] text-slate-200">
              {tone}
            </span>
            <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold tracking-[0.2em] text-slate-200">
              {depth}
            </span>
          </div>

          <div className="mt-5 space-y-4 rounded-[22px] border border-white/10 bg-white/5 p-5">
            <p className="text-sm font-semibold text-white">Ön izleme</p>
            <p className="text-sm leading-7 text-slate-300 sm:text-[15px]">{preview}</p>
            <div className="rounded-[20px] bg-white/5 px-4 py-4 text-sm leading-7 text-slate-300">
              Seçili remix ayarı gelecekte API katmanına bağlandığında aynı yapıdan prompt parametreleri üretilebilir.
            </div>
          </div>
        </div>
      </div>
    </SectionShell>
  );
}
