// SPDX-License-Identifier: Apache-2.0
//
// Confirmation after a transfer.
//
// A demo transfer is labelled as one, unmistakably. Showing a fake reference
// styled as a real BMONI transaction would be the single most dishonest thing
// this app could do, so the two states are visually and textually distinct.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class SuccessScreen extends StatelessWidget {
  const SuccessScreen({
    super.key,
    required this.amount,
    required this.counterpart,
    required this.onDone,
    required this.isDemo,
    this.reference,
  });

  final String amount;
  final String counterpart;
  final String? reference;
  final bool isDemo;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(),
              Semantics(
                liveRegion: true,
                label: isDemo
                    ? 'Transfer successful. Demo mode — no real money moved.'
                    : 'Transfer signed and sent.',
                child: Column(
                  children: [
                    Icon(
                      isDemo ? Icons.science_outlined : Icons.check_circle,
                      size: 64,
                      color: isDemo
                          ? BMoniColors.grey300
                          : BMoniColors.success300,
                    ),
                    const SizedBox(height: 20),
                    Text(
                      'Transfer successful',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      '$amount sent to $counterpart',
                      textAlign: TextAlign.center,
                      style: Theme.of(context)
                          .textTheme
                          .bodyLarge
                          ?.copyWith(color: BMoniColors.grey200),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),
              if (isDemo)
                const _Notice(
                  icon: Icons.info_outline,
                  text: 'This ran in demo mode. No BMONI transaction was '
                      'created and no money moved.',
                )
              else if (reference != null)
                _ReferenceBlock(reference: reference!),
              const Spacer(),
              BMoniButton(
                onPressed: onDone,
                text: 'Done',
                width: double.infinity,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ReferenceBlock extends StatelessWidget {
  const _ReferenceBlock({required this.reference});

  final String reference;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: BMoniColors.grey900,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: BMoniColors.grey800),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'BMONI proposal reference',
            style: Theme.of(context)
                .textTheme
                .labelMedium
                ?.copyWith(color: BMoniColors.grey400),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: SelectableText(
                  reference,
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(fontFamily: 'monospace'),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.copy, size: 18),
                tooltip: 'Copy reference',
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: reference));
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Reference copied')),
                  );
                },
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: BMoniColors.grey900,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: BMoniColors.grey700),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: BMoniColors.grey400),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: BMoniColors.grey300, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
