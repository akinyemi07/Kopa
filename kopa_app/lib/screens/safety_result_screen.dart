// SPDX-License-Identifier: Apache-2.0
//
// The heart of KOPA: what happens to your money if you send this, shown
// BEFORE anything is signed.
//
// The information order is deliberate and reflects what the user actually
// needs to decide:
//
//   1. the verdict            — the answer
//   2. the AI explanation     — why, in a sentence
//   3. the numbers            — the evidence, auditable
//   4. what is at risk        — the consequence, concretely
//   5. the choice             — cancel is the easy path, not the hard one
//
// Note that "Send anyway" is always available. KOPA advises; it does not
// block. Blocking a user from their own money would be a worse product and a
// worse ethic — the goal is an informed decision, not an enforced one.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';

import '../models/decision.dart';
import '../theme/verdict_style.dart';

class SafetyResultScreen extends StatelessWidget {
  const SafetyResultScreen({
    super.key,
    required this.decision,
    required this.counterpart,
    required this.onProceed,
    required this.onCancel,
    this.onAskFollowup,
  });

  final Decision decision;
  final String counterpart;
  final VoidCallback onProceed;
  final VoidCallback onCancel;
  final void Function(String question)? onAskFollowup;

  @override
  Widget build(BuildContext context) {
    final j = decision.justification;
    final style = VerdictStyle.of(decision.verdict);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Safety check'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Cancel this transfer',
          onPressed: onCancel,
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
          children: [
            if (decision.isDemo) const _DemoBanner(),
            _VerdictCard(verdict: decision.verdict, style: style),
            const SizedBox(height: 20),
            _ExplanationCard(decision: decision),
            const SizedBox(height: 20),
            _FiguresCard(justification: j),
            if (j.atRiskObligations.isNotEmpty) ...[
              const SizedBox(height: 20),
              _AtRiskCard(obligations: j.atRiskObligations, currency: j.currency),
            ],
            if (j.counterpartFacts != null) ...[
              const SizedBox(height: 20),
              _CounterpartCard(
                facts: j.counterpartFacts!,
                currency: j.currency,
              ),
            ],
            const SizedBox(height: 28),
            _Actions(
              verdict: decision.verdict,
              amount: formatMoney(j.proposedAmount, currency: j.currency),
              counterpart: counterpart,
              onProceed: onProceed,
              onCancel: onCancel,
            ),
            const SizedBox(height: 16),
            const _Disclaimer(),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------

class _DemoBanner extends StatelessWidget {
  const _DemoBanner();

  @override
  Widget build(BuildContext context) {
    // Honesty requirement: demo figures are never presented as live BMONI data.
    return Semantics(
      label: 'Demo mode. These balances are seeded sample data, not a live '
          'BMONI balance.',
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: BMoniColors.grey800,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: BMoniColors.grey600),
        ),
        child: Row(
          children: [
            const Icon(Icons.science_outlined,
                size: 18, color: BMoniColors.grey300),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Demo data — seeded figures, not a live BMONI balance.',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: BMoniColors.grey300),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _VerdictCard extends StatelessWidget {
  const _VerdictCard({required this.verdict, required this.style});

  final Verdict verdict;
  final VerdictStyle style;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      label: verdict.semanticLabel,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: style.background,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: style.border, width: 1.5),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                // Icon + text, so the state survives without colour.
                Icon(style.icon, color: style.foreground, size: 30),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    style.title,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          color: style.foreground,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              style.recommendation,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: BMoniColors.grey100),
            ),
          ],
        ),
      ),
    );
  }
}

class _ExplanationCard extends StatelessWidget {
  const _ExplanationCard({required this.decision});

  final Decision decision;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.auto_awesome_outlined,
                size: 16, color: BMoniColors.grey400),
            const SizedBox(width: 6),
            Text(
              'What this means',
              style: Theme.of(context)
                  .textTheme
                  .labelLarge
                  ?.copyWith(color: BMoniColors.grey400),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          decision.aiExplanation,
          style: Theme.of(context)
              .textTheme
              .bodyLarge
              ?.copyWith(height: 1.5, color: BMoniColors.grey50),
        ),
        // When the model is unavailable the user is told, rather than being
        // shown a template dressed up as AI output.
        if (decision.aiIsFallback) ...[
          const SizedBox(height: 10),
          Text(
            "KOPA's safety analysis is complete, but the explanation service "
            'is temporarily unavailable — this summary was generated directly '
            'from the figures above.',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: BMoniColors.grey400, fontStyle: FontStyle.italic),
          ),
        ],
      ],
    );
  }
}

class _FiguresCard extends StatelessWidget {
  const _FiguresCard({required this.justification});

  final NumericJustification justification;

  @override
  Widget build(BuildContext context) {
    final j = justification;
    return _Panel(
      title: 'The numbers',
      child: Column(
        children: [
          _FactRow(
            label: 'Balance now',
            value: formatMoney(j.currentBalance, currency: j.currency),
          ),
          _FactRow(
            label: 'Sending',
            value: '− ${formatMoney(j.proposedAmount, currency: j.currency)}',
          ),
          const Divider(height: 20, color: BMoniColors.grey700),
          _FactRow(
            label: 'Balance afterwards',
            value: formatMoney(j.resultingBalance, currency: j.currency),
            emphasise: true,
          ),
          _FactRow(
            label: 'Share of your balance',
            value: '${j.pctOfBalanceUsed.toStringAsFixed(1)}%',
          ),
          // Absence of a runway is stated plainly rather than shown as zero.
          _FactRow(
            label: 'How long that lasts',
            value: j.hasRunway ? 'about ${j.runwayDays} days' : 'not enough history',
            hint: j.hasRunway
                ? '${formatMoney(j.dailySpendEstimate!, currency: j.currency)} a day, ${j.spendBasis}'
                : 'KOPA needs more spending history to estimate this',
          ),
        ],
      ),
    );
  }
}

class _AtRiskCard extends StatelessWidget {
  const _AtRiskCard({required this.obligations, required this.currency});

  final List<ObligationFact> obligations;
  final String currency;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      title: 'What this puts at risk',
      icon: Icons.event_busy_outlined,
      borderColor: BMoniColors.error700,
      child: Column(
        children: [
          for (final o in obligations)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Semantics(
                label: '${o.description}, ${formatMoney(o.amount, currency: currency)}, '
                    'due ${o.dueDate}, would not be covered',
                child: Row(
                  children: [
                    const Icon(Icons.remove_circle_outline,
                        size: 18, color: BMoniColors.error300),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(o.description,
                              style: Theme.of(context).textTheme.bodyMedium),
                          Text(
                            'due ${o.dueDate}',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: BMoniColors.grey400),
                          ),
                        ],
                      ),
                    ),
                    Text(
                      formatMoney(o.amount, currency: currency),
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _CounterpartCard extends StatelessWidget {
  const _CounterpartCard({required this.facts, required this.currency});

  final CounterpartFacts facts;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final String body;
    final IconData icon;

    if (facts.isFirstTime) {
      icon = Icons.person_add_alt_outlined;
      body = 'This is the first time KOPA has seen you pay '
          '${facts.counterpart}. Double-check the details before you send.';
    } else {
      final avg = facts.historicalAverageAmount;
      final freq = facts.paymentFrequencyDays;
      body = 'You have paid ${facts.counterpart} '
          '${facts.previousPaymentCount} time'
          '${facts.previousPaymentCount == 1 ? '' : 's'} before'
          '${avg != null ? ', averaging ${formatMoney(avg, currency: currency)}' : ''}'
          '${freq != null ? ', about every ${freq.round()} days' : ''}.';
      icon = Icons.history;
    }

    return _Panel(
      title: 'About this recipient',
      icon: icon,
      child: Text(
        body,
        style: Theme.of(context)
            .textTheme
            .bodyMedium
            ?.copyWith(color: BMoniColors.grey100, height: 1.45),
      ),
    );
  }
}

class _Actions extends StatelessWidget {
  const _Actions({
    required this.verdict,
    required this.amount,
    required this.counterpart,
    required this.onProceed,
    required this.onCancel,
  });

  final Verdict verdict;
  final String amount;
  final String counterpart;
  final VoidCallback onProceed;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final isRisky = verdict != Verdict.safe;

    // On a risky verdict the safe choice is the visually dominant one, and
    // proceeding is the secondary action — but it is never hidden or disabled.
    final cancel = BMoniButton(
      onPressed: onCancel,
      text: isRisky ? "Don't send" : 'Cancel',
      variant: isRisky ? BMoniButtonVariant.primary : BMoniButtonVariant.outline,
      width: double.infinity,
    );

    final proceed = BMoniButton(
      onPressed: onProceed,
      text: isRisky ? 'Send anyway' : 'Send $amount',
      variant: isRisky ? BMoniButtonVariant.outline : BMoniButtonVariant.primary,
      width: double.infinity,
    );

    return Column(
      children: isRisky
          ? [cancel, const SizedBox(height: 12), proceed]
          : [proceed, const SizedBox(height: 12), cancel],
    );
  }
}

class _Disclaimer extends StatelessWidget {
  const _Disclaimer();

  @override
  Widget build(BuildContext context) {
    // KOPA must never imply a guarantee. This wording is deliberate.
    return Text(
      'Based on the information available to KOPA. This is decision support, '
      'not financial advice, and it cannot see money or commitments KOPA does '
      'not know about.',
      textAlign: TextAlign.center,
      style: Theme.of(context)
          .textTheme
          .bodySmall
          ?.copyWith(color: BMoniColors.grey500, height: 1.4),
    );
  }
}

// ---------------------------------------------------------------------------

class _Panel extends StatelessWidget {
  const _Panel({
    required this.title,
    required this.child,
    this.icon,
    this.borderColor,
  });

  final String title;
  final Widget child;
  final IconData? icon;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: BMoniColors.grey900,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: borderColor ?? BMoniColors.grey800),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[
                Icon(icon, size: 16, color: BMoniColors.grey400),
                const SizedBox(width: 6),
              ],
              Text(
                title,
                style: Theme.of(context)
                    .textTheme
                    .labelLarge
                    ?.copyWith(color: BMoniColors.grey400),
              ),
            ],
          ),
          const SizedBox(height: 14),
          child,
        ],
      ),
    );
  }
}

class _FactRow extends StatelessWidget {
  const _FactRow({
    required this.label,
    required this.value,
    this.hint,
    this.emphasise = false,
  });

  final String label;
  final String value;
  final String? hint;
  final bool emphasise;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Semantics(
        label: '$label: $value${hint != null ? '. $hint' : ''}',
        excludeSemantics: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(color: BMoniColors.grey300),
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  value,
                  style: (emphasise
                          ? theme.textTheme.titleMedium
                          : theme.textTheme.bodyMedium)
                      ?.copyWith(
                    fontWeight: emphasise ? FontWeight.w700 : FontWeight.w600,
                    color: BMoniColors.white,
                  ),
                ),
              ],
            ),
            if (hint != null)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  hint!,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: BMoniColors.grey500),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
