import { SectionShell } from '../layout/SectionShell';

const decisions = ['Netleşti', 'Bir Tur Daha', 'Kanıtla Destekle'];

export function DirectorsCutSection() {
  return (
    <SectionShell
      id="directors-cut"
      eyebrow="Director’s Cut"
      title="Okuma sonrası değerlendirme alanı"
      description="Geniş ekranda butonlar ve metin aynı satır bloklarında durur; dar ekranda butonlar üstte, yorum alanı altta kalır."
    >
      <div className="rounded-[26px] border border-slate-200 bg-slate-50 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-3">
            {decisions.map((decision) => (
              <button
                key={decision}
                type="button"
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300"
              >
                {decision}
              </button>
            ))}
          </div>

          <div className="max-w-2xl rounded-[22px] border border-white/70 bg-white p-4">
            <p className="text-sm leading-7 text-slate-600">
              Bu alan, kullanıcı cevabı veya açıklamayı okuduktan sonra “yeterince net mi?”, “kanıta dönmek ister mi?”,
              “bir üst seviyeye geçmeye hazır mı?” gibi kararları toplamak için hazırlandı.
            </p>
          </div>
        </div>
      </div>
    </SectionShell>
  );
}
