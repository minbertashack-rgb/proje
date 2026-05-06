import 'package:flutter/material.dart';

class BottomActionBox extends StatelessWidget {
  const BottomActionBox({super.key, required this.onAction});

  final ValueChanged<String> onAction;

  @override
  Widget build(BuildContext context) {
    final actions = [
      _Action('explain', Icons.lightbulb_outline_rounded, 'Anlamadim'),
      _Action('evidence', Icons.verified_outlined, 'Kanit'),
      _Action('terms', Icons.travel_explore_rounded, 'Terimler'),
      _Action('hard', Icons.priority_high_rounded, 'Zor Kisim'),
    ];

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        child: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: const Color(0xFFE5EAF1)),
            boxShadow: const [
              BoxShadow(
                color: Color(0x1A101828),
                blurRadius: 24,
                offset: Offset(0, 10),
              ),
            ],
          ),
          child: Row(
            children: actions
                .map(
                  (action) => Expanded(
                    child: Tooltip(
                      message: action.label,
                      child: InkWell(
                        onTap: () => onAction(action.id),
                        borderRadius: BorderRadius.circular(16),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 9),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(action.icon, size: 21),
                              const SizedBox(height: 4),
                              Text(
                                action.label,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context).textTheme.labelSmall,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ),
      ),
    );
  }
}

class _Action {
  const _Action(this.id, this.icon, this.label);

  final String id;
  final IconData icon;
  final String label;
}
