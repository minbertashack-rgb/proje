import { useState } from 'react';
import { SectionShell } from '../layout/SectionShell';
import { surveyHighlights, surveyOptions } from '../../data/mockDashboard';

const defaultSelection = surveyOptions.slice(0, 3);

export function ThemeSurveySection() {
  const [selected, setSelected] = useState<string[]>(defaultSelection);

  const toggleOption = (option: string) => {
    setSelected((previous) =>
      previous.includes(option) ? previous.filter((item) => item !== option) : [...previous, option].slice(-4),
    );
  };

  return (
    <SectionShell
      id="survey"
      eyebrow="Tema / İlgi Alanı Anketi"
      title="Kullanıcı tercihlerini bozulmadan toplayan sade seçim alanı"
      description="Chip yapısı küçük ekranlarda satır kırarak ilerler; kart, yazı ve boşluk oranları mobilde de dengeli kalır."
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr),minmax(260px,0.85fr)]">
        <div className="surface-muted p-5">
          <p className="text-sm font-semibold text-slate-900">Hangi sunum biçimi sana daha uygun?</p>
          <div className="mt-4 flex flex-wrap gap-3">
            {surveyOptions.map((option) => {
              const isActive = selected.includes(option);
              return (
                <button
                  key={option}
                  type="button"
                  onClick={() => toggleOption(option)}
                  className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                    isActive
                      ? 'border-slate-900 bg-slate-900 text-white'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                  }`}
                >
                  {option}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid gap-3">
          {surveyHighlights.map((item) => (
            <div key={item.label} className="rounded-[22px] border border-slate-200 bg-white p-4">
              <p className="text-sm text-slate-500">{item.label}</p>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-900">{item.value}</p>
            </div>
          ))}
          <div className="rounded-[22px] border border-teal-200 bg-teal-50/80 p-4">
            <p className="text-sm text-slate-500">Seçili etiketler</p>
            <p className="mt-2 text-sm font-semibold leading-6 text-slate-900">
              {selected.length ? selected.join(' • ') : 'Henüz seçim yapılmadı'}
            </p>
          </div>
        </div>
      </div>
    </SectionShell>
  );
}
