// SPDX-License-Identifier: Apache-2.0
//
// How a verdict looks, and — just as importantly — how it reads.
//
// ACCESSIBILITY: a verdict is NEVER communicated by colour alone. Every state
// carries four independent signals:
//
//   1. colour   (for the majority of users, at a glance)
//   2. icon     (shape, distinguishable without colour vision)
//   3. text     ("Not recommended")
//   4. sentence (the explanation underneath)
//
// Around 1 in 12 men has some form of colour-vision deficiency, and red/green
// is the most commonly affected pair — which is exactly the pair a naive
// safe/unsafe design would reach for. Removing colour from this file entirely
// should still leave the verdict unambiguous.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';

import '../models/decision.dart';

@immutable
class VerdictStyle {
  const VerdictStyle({
    required this.foreground,
    required this.background,
    required this.border,
    required this.icon,
    required this.title,
    required this.recommendation,
  });

  final Color foreground;
  final Color background;
  final Color border;
  final IconData icon;
  final String title;
  final String recommendation;

  static VerdictStyle of(Verdict verdict) => switch (verdict) {
        Verdict.safe => const VerdictStyle(
            foreground: BMoniColors.success300,
            background: BMoniColors.success950,
            border: BMoniColors.success700,
            icon: Icons.check_circle_outline,
            title: 'Looks manageable',
            recommendation: 'You can go ahead if you are happy with it.',
          ),
        Verdict.caution => const VerdictStyle(
            foreground: BMoniColors.warning300,
            background: BMoniColors.warning950,
            border: BMoniColors.warning700,
            icon: Icons.info_outline,
            title: 'Think carefully',
            recommendation: 'Consider whether this can wait or be reduced.',
          ),
        Verdict.unsafe => const VerdictStyle(
            foreground: BMoniColors.error300,
            background: BMoniColors.error950,
            border: BMoniColors.error700,
            icon: Icons.warning_amber_rounded,
            title: 'Not recommended',
            recommendation: 'We strongly suggest reconsidering this transfer.',
          ),
      };
}

/// Formats an amount for display.
///
/// The value arrives from the backend as an exact decimal string and is only
/// ever split for thousands separators — never parsed to a double and
/// re-formatted, which would risk changing the number the engine computed.
String formatMoney(String amount, {String currency = 'NGN'}) {
  final negative = amount.startsWith('-');
  final unsigned = negative ? amount.substring(1) : amount;

  final parts = unsigned.split('.');
  final whole = parts.first;
  final fraction = parts.length > 1 ? parts[1] : '00';

  final buffer = StringBuffer();
  for (var i = 0; i < whole.length; i++) {
    if (i > 0 && (whole.length - i) % 3 == 0) buffer.write(',');
    buffer.write(whole[i]);
  }

  final symbol = currency == 'NGN' ? '₦' : '$currency ';
  return '${negative ? '-' : ''}$symbol${buffer.toString()}.$fraction';
}
