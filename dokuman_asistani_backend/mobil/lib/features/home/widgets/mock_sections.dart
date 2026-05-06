import 'package:flutter/material.dart';

import '../../../shared/widgets/section_card.dart';

class MockSections extends StatelessWidget {
  const MockSections({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SectionCard(
          title: 'Remix stil konsolu',
          subtitle: 'Mock: anlatimi farkli tonlara donusturme paneli.',
          icon: Icons.graphic_eq_rounded,
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: const [
              Chip(label: Text('Hocam gibi')),
              Chip(label: Text('5 yas')),
              Chip(label: Text('Sinav notu')),
              Chip(label: Text('Mizahsiz net')),
            ],
          ),
        ),
        const SizedBox(height: 14),
        const SectionCard(
          title: "Director's cut",
          subtitle: 'Mock: bu belge icin odak, risk ve tekrar karti.',
          icon: Icons.movie_filter_outlined,
          child: _ScoreRows(),
        ),
        const SizedBox(height: 14),
        SectionCard(
          title: 'Kavram grafigi',
          subtitle: 'Mock: ilk tur statik mobil uyumlu kavram agi.',
          icon: Icons.account_tree_outlined,
          child: Column(
            children: const [
              _ConceptNode(text: 'Ana kavram', level: 1),
              _ConceptNode(text: 'Alt baslik', level: 2),
              _ConceptNode(text: 'Kanita baglanan terim', level: 3),
            ],
          ),
        ),
        const SizedBox(height: 14),
        SizedBox(
          height: 192,
          child: ListView(
            scrollDirection: Axis.horizontal,
            children: const [
              _NoteCard(
                title: 'Akilli Notlar',
                text: 'Parcalardan ozet kartlar.',
              ),
              _NoteCard(
                title: 'Portal Notlar',
                text: 'Kaynak baglamli not alani.',
              ),
              _NoteCard(
                title: 'Kendi Cumlemle',
                text: 'Kullanici anlatimini yazacak.',
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        SectionCard(
          title: 'Test zamani',
          subtitle: 'Mock oyun modlari: Boss Fight, Kacis Odasi, Speedrun.',
          icon: Icons.sports_esports_outlined,
          child: Column(
            children: const [
              _ModeTile(icon: Icons.shield_outlined, title: 'Boss Fight'),
              _ModeTile(icon: Icons.lock_open_rounded, title: 'Kacis Odasi'),
              _ModeTile(icon: Icons.timer_outlined, title: 'Speedrun'),
            ],
          ),
        ),
      ],
    );
  }
}

class _ScoreRows extends StatelessWidget {
  const _ScoreRows();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: const [
        _ModeTile(
          icon: Icons.center_focus_strong_rounded,
          title: 'Odak: yuksek',
        ),
        _ModeTile(icon: Icons.warning_amber_rounded, title: 'Zor kisim: orta'),
        _ModeTile(icon: Icons.replay_rounded, title: 'Tekrar: 12 dk'),
      ],
    );
  }
}

class _ConceptNode extends StatelessWidget {
  const _ConceptNode({required this.text, required this.level});

  final String text;
  final int level;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: level == 1
          ? Alignment.centerLeft
          : level == 2
          ? Alignment.center
          : Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: level == 1 ? const Color(0xFFEFF6FF) : const Color(0xFFF8FAFC),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFE0E7EF)),
        ),
        child: Text(text),
      ),
    );
  }
}

class _NoteCard extends StatelessWidget {
  const _NoteCard({required this.title, required this.text});

  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 210,
      margin: const EdgeInsets.only(right: 12),
      child: SectionCard(
        title: title,
        subtitle: text,
        icon: Icons.sticky_note_2_outlined,
      ),
    );
  }
}

class _ModeTile extends StatelessWidget {
  const _ModeTile({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon),
      title: Text(title),
    );
  }
}
