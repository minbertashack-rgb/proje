export type NavItem = {
  label: string;
  href: string;
  hint: string;
};

export const navItems: NavItem[] = [
  { label: 'Ana Sayfa', href: '#overview', hint: 'Başlangıç' },
  { label: 'Konular', href: '#workspace', hint: 'Doküman' },
  { label: 'Quiz', href: '#challenge-hub', hint: 'Test' },
  { label: 'Boss Fight', href: '#challenge-hub', hint: 'Meydan okuma' },
  { label: 'Reels / Mini Klip', href: '#remix-console', hint: 'Kısa anlatım' },
  { label: 'Concept Fusion Lab', href: '#concept-graph', hint: 'Kavram' },
  { label: 'Kendi Cümlemle Anlat', href: '#own-words', hint: 'Anlatım' },
  { label: 'Sunum / Rapor', href: '#notes', hint: 'Çıktı' },
];
