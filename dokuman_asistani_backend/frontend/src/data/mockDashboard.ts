export type QuickAction = {
  id: 'confused' | 'evidence' | 'terms' | 'hard-parts';
  title: string;
  shortLabel: string;
  prompt: string;
  description: string;
  detail: string;
  bullets: string[];
  toneClass: string;
  iconClass: string;
};

export type OverviewCard = {
  title: string;
  description: string;
  meta: string;
  toneClass: string;
};

export type NoteStream = {
  title: string;
  subtitle: string;
  toneClass: string;
  items: {
    title: string;
    meta: string;
    body: string;
  }[];
};

export type ChallengeCard = {
  title: string;
  subtitle: string;
  description: string;
  meta: string[];
  status: string;
  toneClass: string;
};

export type ProgressStep = {
  title: string;
  description: string;
  status: 'done' | 'active' | 'next';
};

export const overviewStats = [
  { label: 'Aktif belge', value: 'Yapay Sinir Ağları / 42 parça' },
  { label: 'Hazır aksiyon', value: '4 canlı kısayol' },
  { label: 'Öğrenme ritmi', value: 'Bugün 82 XP' },
];

export const overviewCards: OverviewCard[] = [
  {
    title: 'Bunu Anlamadım Akışı',
    description: 'Kafa karıştıran blokları kısa, katmanlı ve sakin bir dil ile açar.',
    meta: '12 vurgu satırı hazır',
    toneClass: 'border-teal-200 bg-teal-50/80',
  },
  {
    title: 'Kanıt Penceresi',
    description: 'Yanıtın hangi cümlelerden üretildiğini sade referans kartlarıyla gösterir.',
    meta: '7 kaynak izi',
    toneClass: 'border-sky-200 bg-sky-50/80',
  },
  {
    title: 'Terimler Alanı',
    description: 'Yoğun kavram kümelerini seviyelendirilmiş açıklamalarla listeler.',
    meta: '18 terim eşleşti',
    toneClass: 'border-violet-200 bg-violet-50/80',
  },
  {
    title: 'Zor Kısım Haritası',
    description: 'Anlama zorluğu yüksek pasajları ayrı bloklarda toplar.',
    meta: '3 kritik pasaj',
    toneClass: 'border-amber-200 bg-amber-50/80',
  },
];

export const quickActions: QuickAction[] = [
  {
    id: 'confused',
    title: 'Bunu Anlamadım',
    shortLabel: 'Anlamadım',
    prompt: 'Bu bölümü daha basit ve katmanlı anlat',
    description: 'Seçili pasajı iki seviyeli açıklama ile yeniden anlatır.',
    detail:
      'Sistem önce bir cümlede özeti verir, sonra teknik arka planı açar. Mobilde alt sabit aksiyon alanından tek dokunuşla tetiklenir.',
    bullets: [
      'Bir cümlede öz fikir',
      'Adım adım açılım',
      'Ön bilgi gerekiyorsa uyarı',
    ],
    toneClass: 'border-teal-200 bg-teal-50/80 text-teal-900',
    iconClass: 'bg-teal-600 text-white',
  },
  {
    id: 'evidence',
    title: 'Kanıt',
    shortLabel: 'Kanıt',
    prompt: 'Yanıtın dayandığı cümleleri göster',
    description: 'Yanıtı destekleyen alıntı bloklarını ve pasaj numaralarını listeler.',
    detail:
      'Öğrenme güvenini artırmak için her içgörü, belge içindeki kaynak satırlarıyla birlikte sunulur. Bu panel gelecekte API entegrasyonuyla gerçek chunk id’lerine bağlanabilir.',
    bullets: [
      'Kaynak satır kartları',
      'Parça numarası / bölüm etiketi',
      'Güven skoru göstergesi',
    ],
    toneClass: 'border-sky-200 bg-sky-50/80 text-sky-900',
    iconClass: 'bg-sky-600 text-white',
  },
  {
    id: 'terms',
    title: 'Terimler',
    shortLabel: 'Terimler',
    prompt: 'Metindeki yoğun terimleri açıkla',
    description: 'Terim yoğun alanları başlangıç, orta ve ileri seviye olarak ayırır.',
    detail:
      'Kullanıcı bir kavrama takıldığında, tanımın yanında bağlam ve örnek de görür. Dar görünümde kartlar tek kolona düşer veya yatay kaydırmalı çalışır.',
    bullets: [
      'Kısa tanım',
      'Bağlam cümlesi',
      'Benzer kavram eşleştirmesi',
    ],
    toneClass: 'border-violet-200 bg-violet-50/80 text-violet-900',
    iconClass: 'bg-violet-600 text-white',
  },
  {
    id: 'hard-parts',
    title: 'Zor Kısım',
    shortLabel: 'Zor Kısım',
    prompt: 'Anlaşılması en zor pasajları çıkar',
    description: 'Düşük anlama skorlu bölümleri ayrı özet bloklarında toplar.',
    detail:
      'Kritik pasajlar ayrı kartlarda tutulur; kullanıcı hem drawer içinden hem içerik sonunda bu kümelere ulaşabilir.',
    bullets: [
      'Riskli pasaj listesi',
      'Anlam eşiği notu',
      'Yeniden çalışma önerisi',
    ],
    toneClass: 'border-amber-200 bg-amber-50/80 text-amber-900',
    iconClass: 'bg-amber-500 text-white',
  },
];

export const surveyOptions = [
  'Araştırma özeti',
  'Sınav odaklı',
  'Kavram haritası',
  'Kanıt takipli',
  'Daha sade dil',
  'Daha teknik ton',
  'Örneklerle anlatım',
  'Hızlı tekrar modu',
];

export const surveyHighlights = [
  { label: 'Önerilen tema', value: 'Daha sade dil + Kanıt takipli' },
  { label: 'Odak yoğunluğu', value: 'Orta seviye açıklama' },
  { label: 'Çıktı formatı', value: 'Kart + kısa not kombinasyonu' },
];

export const remixModes = {
  tones: ['Hafif', 'Dengeli', 'Akademik', 'Analoji odaklı'],
  depths: ['30 sn özet', '2 dk anlatım', 'Derin dalış'],
  preview: {
    Hafif:
      'Bu konu, ağ içindeki bağlantıların veri gördükçe daha anlamlı hale gelmesi fikrine dayanır.',
    Dengeli:
      'Model, örneklerden gelen sinyalleri ağırlıklar üzerinden işler ve hata geri yayılımı ile bu ağırlıkları ayarlar.',
    Akademik:
      'Öğrenme dinamiği, kayıp fonksiyonunun gradyanına göre parametre uzayında yapılan iteratif optimizasyona yaslanır.',
    'Analoji odaklı':
      'Bunu, her denemede biraz daha doğru ezber yapan ama sonunda sadece ezberlemeyip desen yakalayan bir ekip gibi düşünebiliriz.',
  },
};

export const noteStreams: NoteStream[] = [
  {
    title: 'Akıllı Notlar',
    subtitle: 'Sistemin otomatik çıkardığı yoğun içgörüler',
    toneClass: 'border-slate-200 bg-white',
    items: [
      {
        title: 'Geri yayılım omurgası',
        meta: '2 dk okuma',
        body: 'Hata sinyali, katmanlar arasında geriye doğru taşınarak hangi ağırlığın ne kadar etkili olduğunu belirler.',
      },
      {
        title: 'Aktivasyon rolü',
        meta: '1 dk özet',
        body: 'Doğrusal olmayan aktivasyonlar eklenmezse ağ karmaşık ilişkileri ayırt edemez.',
      },
      {
        title: 'Ezber riski',
        meta: 'Uyarı',
        body: 'Aşırı öğrenme durumunda eğitim başarısı yükselirken yeni veri performansı düşer.',
      },
    ],
  },
  {
    title: 'Portal Notlar',
    subtitle: 'Kullanıcıya dönük paylaşım ve dışa aktarım notları',
    toneClass: 'border-slate-200 bg-white',
    items: [
      {
        title: 'Sunum kartı',
        meta: 'Paylaşılabilir',
        body: 'Sinir ağları, veriden desen öğrenen katmanlı matematiksel yapılardır.',
      },
      {
        title: 'Sınav öncesi kısa tur',
        meta: '90 sn tekrar',
        body: 'Ağırlık, aktivasyon, kayıp, geri yayılım ve optimizasyon beşlisi konunun çekirdeğini oluşturur.',
      },
      {
        title: 'Hocaya sor',
        meta: 'Açık soru',
        body: 'Regularization hangi veri büyüklüğünden sonra en kritik hale gelir?',
      },
    ],
  },
];

export const challenges: ChallengeCard[] = [
  {
    title: 'Test Zamanı',
    subtitle: 'Quiz kartları',
    description: 'Soru, XP ve kısa meta alanlarını düzenli kartlarda sunar. Alan daraldığında bilgi blokları alt alta geçer.',
    meta: ['8 soru', '120 XP', 'Orta zorluk'],
    status: 'Hazır',
    toneClass: 'border-slate-200 bg-white',
  },
  {
    title: 'Vay Boss Fight',
    subtitle: 'Tek büyük meydan okuma',
    description: 'Animasyonsuz, net ve odaklı. Öğrenciyi tek kuvvetli soruya karşı konumlandırır.',
    meta: ['1 boss soru', '240 XP', 'Kanıt zorunlu'],
    status: 'Isınma tamam',
    toneClass: 'border-rose-200 bg-rose-50/80',
  },
  {
    title: 'Kaçış Odası',
    subtitle: 'Görev zinciri',
    description: 'Soru, toplam XP ve doğru cevap puanı tek kart akışında ilerler. Mobilde tek kolona düşer.',
    meta: ['4 oda', '300 XP', '+45 puan / doğru'],
    status: '2. kilit açık',
    toneClass: 'border-amber-200 bg-amber-50/80',
  },
  {
    title: 'Speedrun',
    subtitle: 'Hız odaklı tekrar',
    description: 'Süre, puan, toplam XP ve soru alanlarını sıkışmadan taşır. Gerekirse dikey akışa döner.',
    meta: ['6 soru', '75 sn', 'En iyi skor 860'],
    status: 'Kişisel rekor',
    toneClass: 'border-sky-200 bg-sky-50/80',
  },
];

export const progressSteps: ProgressStep[] = [
  {
    title: 'Belge Yüklendi',
    description: 'Ham doküman sisteme alındı ve indeks kuyruğuna girdi.',
    status: 'done',
  },
  {
    title: 'Parçalama',
    description: 'Metin mantıklı pasaj bloklarına ayrıldı.',
    status: 'done',
  },
  {
    title: 'Anlama Katmanı',
    description: 'Terimler, zor alanlar ve kanıt zinciri üretildi.',
    status: 'active',
  },
  {
    title: 'Quiz ve Oyunlar',
    description: 'Test Zamanı, Boss Fight ve Kaçış Odası sahneleri beslendi.',
    status: 'next',
  },
  {
    title: 'Kişisel Özet',
    description: 'Kendi cümlemle anlat ve portal notlar final hale geliyor.',
    status: 'next',
  },
];
