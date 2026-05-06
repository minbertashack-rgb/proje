import '../../../core/utils/parse_utils.dart';
import '../../concepts/data/concept_models.dart';

class ExplainResponse {
  const ExplainResponse({
    this.oneSentence,
    this.simpleExplanation,
    this.rawExplanation,
    this.terms = const [],
    this.steps = const [],
    this.examples = const [],
    this.quiz = const [],
    this.evidence = const [],
    this.themedExamples = const [],
    this.concepts = const [],
    this.conceptRelations = const [],
  });

  final String? oneSentence;
  final String? simpleExplanation;
  final String? rawExplanation;
  final List<String> terms;
  final List<String> steps;
  final List<String> examples;
  final List<String> quiz;
  final List<String> evidence;
  final List<String> themedExamples;
  final List<ConceptItem> concepts;
  final List<ConceptRelation> conceptRelations;

  factory ExplainResponse.fromDynamic(dynamic value) {
    final raw = ParseUtils.string(value);
    if (value is! Map && raw != null) {
      return ExplainResponse(rawExplanation: raw);
    }
    return ExplainResponse.fromMap(ParseUtils.asMap(value));
  }

  factory ExplainResponse.fromJson(Map<String, dynamic> json) {
    return ExplainResponse.fromMap(json);
  }

  factory ExplainResponse.fromMap(Map<String, dynamic> json) {
    final payload = ParseUtils.nestedMap(json);
    return ExplainResponse(
      oneSentence: ParseUtils.firstString(payload, [
        'one_liner',
        'oneLiner',
        'tek_cumle',
        'one_sentence',
        'ozet',
        'summary',
        'kisa_ozet',
      ]),
      simpleExplanation: ParseUtils.firstString(payload, [
        'very_simple',
        'verySimple',
        'cok_basit_anlatim',
        'basit_anlatim',
        'basit',
        'simple_explanation',
        'explanation',
        'aciklama',
      ]),
      rawExplanation: ParseUtils.firstString(payload, [
        'raw',
        'text',
        'metin',
        'answer',
        'cevap',
      ]),
      terms: ParseUtils.stringList(
        payload['glossary'] ??
            payload['terimler'] ??
            payload['terms'] ??
            payload['sozluk'],
      ),
      steps: ParseUtils.stringList(
        payload['steps'] ??
            payload['adimlar'] ??
            payload['maddeler'] ??
            payload['adim_adim'],
      ),
      examples: ParseUtils.stringList(
        payload['ornekler'] ?? payload['examples'],
      ),
      quiz: ParseUtils.stringList(
        payload['mini_quiz'] ??
            payload['miniQuiz'] ??
            payload['quiz'] ??
            payload['sorular'],
      ),
      evidence: ParseUtils.stringList(
        payload['kanit_snippet'] ??
            payload['kanitlar'] ??
            payload['evidence'] ??
            payload['snippets'],
      ),
      themedExamples: ParseUtils.stringList(
        payload['themed_examples'] ??
            payload['tema_ornekleri'] ??
            payload['personal_examples'],
      ),
      concepts: ParseUtils.asList(payload['concepts'] ?? payload['kavramlar'])
          .map(ConceptItem.fromDynamic)
          .where((item) => !item.isEmpty)
          .toList(growable: false),
      conceptRelations:
          ParseUtils.asList(
                payload['concept_relations'] ?? payload['relations'],
              )
              .map(ConceptRelation.fromDynamic)
              .where((item) => !item.isEmpty)
              .toList(growable: false),
    );
  }

  bool get isEmpty =>
      [
        oneSentence,
        simpleExplanation,
        rawExplanation,
      ].every((value) => value == null) &&
      terms.isEmpty &&
      concepts.isEmpty &&
      steps.isEmpty &&
      examples.isEmpty &&
      quiz.isEmpty &&
      evidence.isEmpty &&
      themedExamples.isEmpty;

  Map<String, dynamic> toRemixSource() => {
    if (oneSentence?.trim().isNotEmpty == true) 'one_liner': oneSentence,
    if (simpleExplanation?.trim().isNotEmpty == true)
      'very_simple': simpleExplanation,
    if (terms.isNotEmpty) 'glossary': terms,
    if (steps.isNotEmpty) 'steps': steps,
    if (examples.isNotEmpty) 'examples': examples,
    if (quiz.isNotEmpty) 'mini_quiz': quiz,
    if (concepts.isNotEmpty)
      'concepts': concepts.map((item) => item.term).toList(growable: false),
  };
}
