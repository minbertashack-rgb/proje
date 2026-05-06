import { useState } from 'react';
import { SectionShell } from '../layout/SectionShell';

const starterText =
  'Sinir ağı, örnekler gördükçe hata sinyaline göre iç bağlantılarını ayarlayan katmanlı bir öğrenme sistemi gibi çalışır.';

export function OwnSentenceSection() {
  const [text, setText] = useState(starterText);
  const [checked, setChecked] = useState(true);
  const base = Math.min(95, 52 + Math.floor(text.trim().length / 3));
  const metrics = {
    understanding: base,
    clarity: Math.min(97, base + 4),
    coverage: Math.max(48, base - 7),
  };

  return (
    <SectionShell
      id="own-words"
      eyebrow="Kendi Cümlemle Anlat"
      title="Serbest metin alanı ve responsive geri bildirim blokları"
      description="Temizle ve Cevabı Kontrol Et butonları genişte yan yana, darda üst-alt biçimde yerleşir. Sonuç kartları da viewport ile birlikte yeniden akar."
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.08fr),320px]">
        <div className="surface-muted p-5">
          <label htmlFor="own-words-input" className="text-sm font-semibold text-slate-900">
            Konuyu kendi cümlenle özetle
          </label>
          <textarea
            id="own-words-input"
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="mt-4 min-h-[220px] w-full rounded-[24px] border border-slate-200 bg-white p-4 text-sm leading-7 text-slate-700 outline-none transition focus:border-slate-400"
            placeholder="Buraya kendi anlatımını yaz..."
          />

          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={() => {
                setText('');
                setChecked(false);
              }}
              className="rounded-[20px] border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700"
            >
              Temizle
            </button>
            <button
              type="button"
              onClick={() => setChecked(true)}
              className="rounded-[20px] bg-slate-900 px-4 py-3 text-sm font-semibold text-white"
            >
              Cevabı Kontrol Et
            </button>
          </div>
        </div>

        <div className="grid gap-3">
          <div className="rounded-[24px] border border-teal-200 bg-teal-50/80 p-4">
            <p className="text-sm text-slate-500">Genel anlama yüzdesi</p>
            <p className="mt-2 text-3xl font-semibold text-slate-950">%{checked ? metrics.understanding : 0}</p>
          </div>
          <div className="rounded-[24px] border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-500">Netlik</p>
            <p className="mt-2 text-lg font-semibold text-slate-950">%{checked ? metrics.clarity : 0}</p>
          </div>
          <div className="rounded-[24px] border border-slate-200 bg-white p-4">
            <p className="text-sm text-slate-500">Kapsama</p>
            <p className="mt-2 text-lg font-semibold text-slate-950">%{checked ? metrics.coverage : 0}</p>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <div className="rounded-[22px] border border-slate-200 bg-white p-4">
          <p className="text-sm font-semibold text-slate-900">Güçlü nokta</p>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Öğrenme sisteminin hata üzerinden iyileştiğini doğru vurguladın.
          </p>
        </div>
        <div className="rounded-[22px] border border-slate-200 bg-white p-4">
          <p className="text-sm font-semibold text-slate-900">Eksik alan</p>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Aktivasyon ve kayıp fonksiyonunun neden gerekli olduğu ayrıca eklenebilir.
          </p>
        </div>
        <div className="rounded-[22px] border border-slate-200 bg-white p-4">
          <p className="text-sm font-semibold text-slate-900">Öneri</p>
          <p className="mt-2 text-sm leading-7 text-slate-600">
            Bir analogi ekleyerek açıklamayı daha akıcı hale getirebilirsin.
          </p>
        </div>
      </div>
    </SectionShell>
  );
}
