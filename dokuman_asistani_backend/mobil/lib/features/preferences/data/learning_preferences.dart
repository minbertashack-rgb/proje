import '../../../core/utils/parse_utils.dart';

class LearningPreferences {
  const LearningPreferences({
    this.enabled = true,
    this.theme = 'default',
    this.explanationStyle = 'adim_adim',
    this.level = 'baslangic',
    this.exampleDensity = 'normal',
  });

  final bool enabled;
  final String theme;
  final String explanationStyle;
  final String level;
  final String exampleDensity;

  factory LearningPreferences.fromDynamic(dynamic value) {
    final map = ParseUtils.asMap(value);
    return LearningPreferences(
      enabled: map['enabled'] is bool ? map['enabled'] as bool : true,
      theme: ParseUtils.string(map['theme']) ?? 'default',
      explanationStyle:
          ParseUtils.string(map['explanation_style']) ?? 'adim_adim',
      level: ParseUtils.string(map['level']) ?? 'baslangic',
      exampleDensity: ParseUtils.string(map['example_density']) ?? 'normal',
    );
  }

  Map<String, dynamic> toJson() => {
    'theme': theme,
    'explanation_style': explanationStyle,
    'level': level,
    'example_density': exampleDensity,
  };

  LearningPreferences copyWith({
    String? theme,
    String? explanationStyle,
    String? level,
    String? exampleDensity,
  }) => LearningPreferences(
    enabled: enabled,
    theme: theme ?? this.theme,
    explanationStyle: explanationStyle ?? this.explanationStyle,
    level: level ?? this.level,
    exampleDensity: exampleDensity ?? this.exampleDensity,
  );
}
