// SPDX-License-Identifier: Apache-2.0
//
// Transaction history — proof that a send actually moved money, not just a
// promise on a success screen. Every entry here is what KOPA itself recorded,
// which is also what the balance and the safety check read from — the same
// figure, wherever it's shown.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/decision.dart';
import '../theme/verdict_style.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key, required this.fetch});

  final Future<List<TransactionRecord>> Function() fetch;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late Future<List<TransactionRecord>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.fetch();
  }

  Future<void> _reload() async {
    final next = widget.fetch();
    setState(() => _future = next);
    await next;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Transaction history')),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _reload,
          child: FutureBuilder<List<TransactionRecord>>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snapshot.hasError) {
                return _ErrorState(
                  message: snapshot.error.toString(),
                  onRetry: _reload,
                );
              }
              final records = snapshot.data ?? const [];
              if (records.isEmpty) {
                return const _EmptyState();
              }
              return ListView.separated(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
                itemCount: records.length,
                separatorBuilder: (_, _) => const SizedBox(height: 10),
                itemBuilder: (context, i) => _TransactionTile(record: records[i]),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _TransactionTile extends StatelessWidget {
  const _TransactionTile({required this.record});

  final TransactionRecord record;

  static final _dateFormat = DateFormat('d MMM, h:mm a');

  @override
  Widget build(BuildContext context) {
    final money = formatMoney(record.amount, currency: record.currency);
    final when = _dateFormat.format(record.occurredAt.toLocal());
    final who = record.counterpart ?? 'Unknown recipient';

    return Semantics(
      label: '$money sent to $who, $when'
          '${record.isDemo ? ', demo transaction' : ''}',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: BMoniColors.grey900,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: BMoniColors.grey800),
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: BMoniColors.grey800,
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(
                Icons.arrow_upward,
                size: 18,
                color: BMoniColors.grey300,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    who,
                    style: Theme.of(context)
                        .textTheme
                        .bodyMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    when,
                    style: Theme.of(context)
                        .textTheme
                        .bodySmall
                        ?.copyWith(color: BMoniColors.grey500),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  '- $money',
                  style: Theme.of(context)
                      .textTheme
                      .bodyMedium
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
                if (record.isDemo) ...[
                  const SizedBox(height: 4),
                  const _DemoTag(),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _DemoTag extends StatelessWidget {
  const _DemoTag();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: BMoniColors.grey800,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: BMoniColors.grey700),
      ),
      child: Text(
        'DEMO',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: BMoniColors.grey400,
              fontSize: 10,
              letterSpacing: 0.4,
            ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.receipt_long_outlined,
                size: 40, color: BMoniColors.grey600),
            const SizedBox(height: 16),
            Text(
              'No transactions yet',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Every transfer you send through KOPA will show up here.',
              textAlign: TextAlign.center,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: BMoniColors.grey400),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 32, color: BMoniColors.error300),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            BMoniButton(
              onPressed: () => onRetry(),
              text: 'Try again',
              variant: BMoniButtonVariant.outline,
              size: BMoniButtonSize.small,
            ),
          ],
        ),
      ),
    );
  }
}
