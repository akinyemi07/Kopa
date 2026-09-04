// SPDX-License-Identifier: Apache-2.0
//
// Widget tests for the screen the whole product turns on.
//
// The properties under test are the ones that would be embarrassing to get
// wrong in front of a judge: the numbers rendered must be exactly the numbers
// the engine produced, a demo balance must be labelled as one, and an unsafe
// verdict must never be communicated by colour alone.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:kopa_app/models/decision.dart';
import 'package:kopa_app/screens/safety_result_screen.dart';
import 'package:kopa_app/theme/verdict_style.dart';

/// Mirrors a real /decisions/evaluate response body.
Map<String, dynamic> decisionJson({
  String verdict = 'unsafe',
  bool aiFallback = false,
  bool isDemo = false,
  List<Map<String, dynamic>> atRisk = const [
    {'description': 'Rent', 'amount': '25000.00', 'due_date': '2026-09-10'},
  ],
  Map<String, dynamic>? counterpart,
}) {
  return {
    'decision_id': null,
    'verdict': verdict,
    'ai_explanation': 'Sending this would leave you short before rent is due.',
    'ai_is_fallback': aiFallback,
    'ai_model': aiFallback ? null : 'claude-sonnet-5',
    'is_demo': isDemo,
    'numeric_justification': {
      'currency': 'NGN',
      'verdict': verdict,
      'current_balance': '47500.00',
      'proposed_amount': '30000.00',
      'resulting_balance': '17500.00',
      'pct_of_balance_used': 63.16,
      'runway_days': 12,
      'daily_spend_estimate': '1397.22',
      'daily_spend_source': 'history',
      'obligations_total': '30000.00',
      'at_risk_obligations': atRisk,
      'upcoming_obligations': atRisk,
      'counterpart_context': counterpart,
      'reasons': ['obligation_at_risk: not enough would remain to cover Rent'],
    },
  };
}

Widget wrap(Widget child) => MaterialApp(home: child);

/// The safety screen is a tall ListView, and Flutter only builds what is on
/// screen. A phone-sized test surface leaves the actions and the disclaimer
/// unbuilt, so finders miss content that a scrolling user would see. Give the
/// test a surface tall enough to render the whole screen at once.
void useTallSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 3600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

Widget screenFor(Map<String, dynamic> json, {String counterpart = 'QuickLoan NG'}) {
  return wrap(
    SafetyResultScreen(
      decision: Decision.fromJson(json),
      counterpart: counterpart,
      onProceed: () {},
      onCancel: () {},
    ),
  );
}

void main() {
  group('money formatting', () {
    test('adds thousands separators without touching the value', () {
      expect(formatMoney('17500.00'), '₦17,500.00');
      expect(formatMoney('1397.22'), '₦1,397.22');
      expect(formatMoney('500.00'), '₦500.00');
      expect(formatMoney('1234567.89'), '₦1,234,567.89');
    });

    test('handles a negative resulting balance', () {
      expect(formatMoney('-5000.00'), '-₦5,000.00');
    });

    test('does not round or reformat the decimal it was given', () {
      // The engine already rounded. The UI must not touch the figure.
      expect(formatMoney('0.03'), '₦0.03');
      expect(formatMoney('99999.99'), '₦99,999.99');
    });
  });

  group('verdict parsing', () {
    test('parses the three known verdicts', () {
      expect(Verdict.parse('safe'), Verdict.safe);
      expect(Verdict.parse('caution'), Verdict.caution);
      expect(Verdict.parse('unsafe'), Verdict.unsafe);
    });

    test('treats an unrecognised verdict as unsafe, not safe', () {
      // Failing towards caution is the only acceptable default here.
      expect(Verdict.parse('banana'), Verdict.unsafe);
      expect(Verdict.parse(''), Verdict.unsafe);
    });
  });

  group('SafetyResultScreen', () {
    testWidgets('renders the engine figures verbatim', (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson()));

      expect(find.text('₦47,500.00'), findsOneWidget); // balance now
      expect(find.text('− ₦30,000.00'), findsOneWidget); // sending
      expect(find.text('₦17,500.00'), findsOneWidget); // after
      expect(find.text('63.2%'), findsOneWidget);
      expect(find.text('about 12 days'), findsOneWidget);
    });

    testWidgets('shows an unsafe verdict with icon AND text, not colour alone',
        (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson()));

      expect(find.text('Not recommended'), findsOneWidget);
      expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
    });

    testWidgets('names the obligations put at risk', (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson()));

      expect(find.text('What this puts at risk'), findsOneWidget);
      expect(find.text('Rent'), findsOneWidget);
      expect(find.text('₦25,000.00'), findsOneWidget);
    });

    testWidgets('offers "Send anyway" — KOPA advises, it does not block',
        (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson()));

      expect(find.text('Send anyway'), findsOneWidget);
      expect(find.text("Don't send"), findsOneWidget);
    });

    testWidgets('a safe verdict leads with sending, not cancelling',
        (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(
        screenFor(decisionJson(verdict: 'safe', atRisk: const [])),
      );

      expect(find.text('Looks manageable'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle_outline), findsOneWidget);
      expect(find.textContaining('Send ₦30,000.00'), findsOneWidget);
    });

    testWidgets('tells the user when the explanation is a fallback',
        (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson(aiFallback: true)));

      expect(
        find.textContaining('explanation service is temporarily unavailable'),
        findsOneWidget,
      );
    });

    testWidgets('does not claim a fallback when the model responded',
        (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson(aiFallback: false)));

      expect(
        find.textContaining('explanation service is temporarily unavailable'),
        findsNothing,
      );
    });

    testWidgets('labels demo data instead of passing it off as live',
        (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson(isDemo: true)));

      expect(find.textContaining('Demo data'), findsOneWidget);
    });

    testWidgets('never implies a guarantee of safety', (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson(verdict: 'safe')));

      expect(find.textContaining('Based on the information available to KOPA'),
          findsOneWidget);
      expect(find.textContaining('guarantee'), findsNothing);
    });

    testWidgets('flags a first-time recipient', (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson(counterpart: {
        'counterpart': 'QuickLoan NG',
        'is_first_time_counterpart': true,
        'previous_payment_count': 0,
        'historical_average_amount': null,
        'last_paid_on': null,
        'payment_frequency_days': null,
      })));

      expect(find.textContaining('first time KOPA has seen you pay'),
          findsOneWidget);
    });

    testWidgets('summarises a recurring recipient', (tester) async {
      useTallSurface(tester);
      await tester.pumpWidget(screenFor(decisionJson(counterpart: {
        'counterpart': 'Mama Nkechi Stores',
        'is_first_time_counterpart': false,
        'previous_payment_count': 3,
        'historical_average_amount': '1800.00',
        'last_paid_on': '2026-09-03',
        'payment_frequency_days': 7.0,
      })));

      expect(find.textContaining('3 times before'), findsOneWidget);
      expect(find.textContaining('₦1,800.00'), findsOneWidget);
    });

    testWidgets('says so plainly when there is no runway estimate',
        (tester) async {
      useTallSurface(tester);
      final json = decisionJson();
      json['numeric_justification']['runway_days'] = null;
      json['numeric_justification']['daily_spend_estimate'] = null;
      json['numeric_justification']['daily_spend_source'] = 'unavailable';

      await tester.pumpWidget(screenFor(json));

      expect(find.text('not enough history'), findsOneWidget);
      expect(
        find.textContaining('needs more spending history'),
        findsOneWidget,
      );
    });
  });
}
