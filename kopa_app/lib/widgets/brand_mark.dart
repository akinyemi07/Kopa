// SPDX-License-Identifier: Apache-2.0
//
// The co-brand lockup: KOPA is the product, built on BMONI's infrastructure.
// A single reusable widget so every place the wordmark appears stays in sync
// — change the relationship once here, not per-screen.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';

class KopaBrandMark extends StatelessWidget {
  const KopaBrandMark({super.key, this.style});

  /// Base style for "KOPA". "BMONI" derives from it at reduced weight/opacity
  /// so the lockup reads as one brand mark, not two competing logos.
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final base = style ?? Theme.of(context).textTheme.titleLarge;
    return Semantics(
      label: 'KOPA, built on BMONI',
      child: RichText(
        text: TextSpan(
          style: base?.copyWith(fontWeight: FontWeight.w700),
          children: [
            const TextSpan(text: 'KOPA'),
            TextSpan(
              text: '  |  BMONI',
              style: base?.copyWith(
                fontWeight: FontWeight.w400,
                color: BMoniColors.grey400,
                fontSize: (base.fontSize ?? 20) * 0.62,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
