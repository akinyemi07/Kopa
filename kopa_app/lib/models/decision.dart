// SPDX-License-Identifier: Apache-2.0
//
// Models mirroring the KOPA backend's response schemas.
//
// Money arrives from the backend as decimal STRINGS, not numbers, and is kept
// that way for display. Parsing a currency amount into a double just to render
// it would reintroduce exactly the rounding error the backend's Decimal
// arithmetic was chosen to avoid.

import 'package:flutter/foundation.dart';

/// The three states KOPA can reach.
enum Verdict {
  safe,
  caution,
  unsafe;

  static Verdict parse(String raw) => switch (raw.toLowerCase()) {
        'safe' => Verdict.safe,
        'caution' => Verdict.caution,
        // An unrecognised verdict is treated as the most severe rather than
        // the least. Failing safe here means failing loud.
        _ => Verdict.unsafe,
      };

  String get label => switch (this) {
        Verdict.safe => 'Looks manageable',
        Verdict.caution => 'Think carefully',
        Verdict.unsafe => 'Not recommended',
      };

  /// Announced by screen readers ahead of the detail.
  String get semanticLabel => switch (this) {
        Verdict.safe => 'Safe. KOPA thinks this looks manageable.',
        Verdict.caution => 'Caution. KOPA suggests thinking carefully.',
        Verdict.unsafe => 'Unsafe. KOPA does not recommend this transfer.',
      };
}

@immutable
class ObligationFact {
  const ObligationFact({
    required this.description,
    required this.amount,
    required this.dueDate,
  });

  final String description;
  final String amount;
  final String dueDate;

  factory ObligationFact.fromJson(Map<String, dynamic> json) => ObligationFact(
        description: json['description'] as String,
        amount: json['amount'] as String,
        dueDate: json['due_date'] as String,
      );
}

@immutable
class CounterpartFacts {
  const CounterpartFacts({
    required this.counterpart,
    required this.isFirstTime,
    required this.previousPaymentCount,
    this.historicalAverageAmount,
    this.lastPaidOn,
    this.paymentFrequencyDays,
  });

  final String? counterpart;
  final bool isFirstTime;
  final int previousPaymentCount;
  final String? historicalAverageAmount;
  final String? lastPaidOn;
  final double? paymentFrequencyDays;

  factory CounterpartFacts.fromJson(Map<String, dynamic> json) =>
      CounterpartFacts(
        counterpart: json['counterpart'] as String?,
        isFirstTime: json['is_first_time_counterpart'] as bool? ?? true,
        previousPaymentCount: json['previous_payment_count'] as int? ?? 0,
        historicalAverageAmount: json['historical_average_amount'] as String?,
        lastPaidOn: json['last_paid_on'] as String?,
        paymentFrequencyDays:
            (json['payment_frequency_days'] as num?)?.toDouble(),
      );
}

/// Every figure behind the verdict, exactly as the safety engine computed it.
@immutable
class NumericJustification {
  const NumericJustification({
    required this.currency,
    required this.currentBalance,
    required this.proposedAmount,
    required this.resultingBalance,
    required this.pctOfBalanceUsed,
    required this.dailySpendSource,
    required this.obligationsTotal,
    required this.atRiskObligations,
    required this.upcomingObligations,
    required this.reasons,
    this.runwayDays,
    this.dailySpendEstimate,
    this.counterpartFacts,
  });

  final String currency;
  final String currentBalance;
  final String proposedAmount;
  final String resultingBalance;
  final double pctOfBalanceUsed;
  final int? runwayDays;
  final String? dailySpendEstimate;
  final String dailySpendSource;
  final String obligationsTotal;
  final List<ObligationFact> atRiskObligations;
  final List<ObligationFact> upcomingObligations;
  final CounterpartFacts? counterpartFacts;
  final List<String> reasons;

  /// True when there was not enough history to estimate a runway. The UI says
  /// so plainly rather than showing a blank or a zero.
  bool get hasRunway => runwayDays != null && dailySpendEstimate != null;

  /// How the daily-spend figure was arrived at, in words for the user.
  String get spendBasis => switch (dailySpendSource) {
        'history' => 'based on your recent spending',
        'history_limited' => 'based on limited recent history, so treat it as rough',
        'manual' => 'based on the estimate you gave KOPA',
        _ => 'not enough history to estimate',
      };

  factory NumericJustification.fromJson(Map<String, dynamic> json) {
    List<ObligationFact> parseObligations(String key) =>
        ((json[key] as List<dynamic>?) ?? const [])
            .map((e) => ObligationFact.fromJson(e as Map<String, dynamic>))
            .toList();

    return NumericJustification(
      currency: json['currency'] as String? ?? 'NGN',
      currentBalance: json['current_balance'] as String,
      proposedAmount: json['proposed_amount'] as String,
      resultingBalance: json['resulting_balance'] as String,
      pctOfBalanceUsed: (json['pct_of_balance_used'] as num).toDouble(),
      runwayDays: json['runway_days'] as int?,
      dailySpendEstimate: json['daily_spend_estimate'] as String?,
      dailySpendSource: json['daily_spend_source'] as String? ?? 'unavailable',
      obligationsTotal: json['obligations_total'] as String? ?? '0.00',
      atRiskObligations: parseObligations('at_risk_obligations'),
      upcomingObligations: parseObligations('upcoming_obligations'),
      counterpartFacts: json['counterpart_context'] == null
          ? null
          : CounterpartFacts.fromJson(
              json['counterpart_context'] as Map<String, dynamic>),
      reasons: ((json['reasons'] as List<dynamic>?) ?? const [])
          .map((e) => e as String)
          .toList(),
    );
  }
}

@immutable
class Decision {
  const Decision({
    required this.verdict,
    required this.justification,
    required this.aiExplanation,
    required this.aiIsFallback,
    required this.isDemo,
    this.decisionId,
    this.aiModel,
    this.interpretedAs,
  });

  final Verdict verdict;
  final NumericJustification justification;
  final String aiExplanation;

  /// True when the explanation came from KOPA's deterministic template because
  /// the language model was unavailable. Surfaced to the user rather than
  /// hidden — an honest "explanation service is down" beats a silent downgrade.
  final bool aiIsFallback;
  final bool isDemo;
  final String? decisionId;
  final String? aiModel;

  /// For follow-up questions: how KOPA read the question.
  final String? interpretedAs;

  factory Decision.fromJson(Map<String, dynamic> json) => Decision(
        verdict: Verdict.parse(json['verdict'] as String),
        justification: NumericJustification.fromJson(
            json['numeric_justification'] as Map<String, dynamic>),
        aiExplanation: json['ai_explanation'] as String? ?? '',
        aiIsFallback: json['ai_is_fallback'] as bool? ?? true,
        isDemo: json['is_demo'] as bool? ?? false,
        decisionId: json['decision_id'] as String?,
        aiModel: json['ai_model'] as String?,
        interpretedAs: json['interpreted_as'] as String?,
      );
}

@immutable
class Balance {
  const Balance({
    required this.currency,
    required this.amount,
    required this.isDemo,
  });

  final String currency;
  final double amount;
  final bool isDemo;

  factory Balance.fromJson(Map<String, dynamic> json) => Balance(
        currency: json['currency'] as String? ?? 'NGN',
        amount: double.parse(json['balance'].toString()),
        isDemo: json['is_demo'] as bool? ?? false,
      );
}

@immutable
class OwnerProofChallenge {
  const OwnerProofChallenge({
    required this.challengeId,
    required this.message,
    this.expiresAt,
  });

  final String challengeId;

  /// The text the device signs with EIP-191 (`signMessage`).
  final String message;
  final String? expiresAt;

  factory OwnerProofChallenge.fromJson(Map<String, dynamic> json) =>
      OwnerProofChallenge(
        challengeId: json['challenge_id'] as String,
        message: json['message'] as String,
        expiresAt: json['expires_at'] as String?,
      );
}

@immutable
class Proposal {
  const Proposal({
    required this.proposalId,
    required this.status,
    required this.isDemo,
    this.hashToSign,
  });

  final String proposalId;
  final String status;

  /// The raw 32-byte digest signed with `signTransactionHash` — NOT
  /// `signMessage`. Using the wrong one produces a signature that recovers to
  /// a different address and BMONI rejects it.
  final String? hashToSign;
  final bool isDemo;

  factory Proposal.fromJson(Map<String, dynamic> json) => Proposal(
        proposalId: json['proposal_id'] as String,
        status: json['status'] as String,
        hashToSign: json['hash_to_sign'] as String?,
        isDemo: json['is_demo'] as bool? ?? false,
      );
}
