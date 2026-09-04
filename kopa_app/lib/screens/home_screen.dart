// SPDX-License-Identifier: Apache-2.0
//
// Wallet balance, upcoming commitments, and the two ways to send money.
//
// Obligations sit on the home screen on purpose: KOPA's whole argument is that
// a balance means nothing on its own. ₦47,500 looks like plenty until you
// remember rent is due on Thursday, so the two facts are shown together.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';

import '../models/decision.dart';
import '../theme/verdict_style.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({
    super.key,
    required this.balance,
    required this.walletAddress,
    required this.onSend,
    required this.onPayMerchant,
    required this.onRefresh,
    this.isLoading = false,
    this.error,
  });

  final Balance? balance;
  final String? walletAddress;
  final VoidCallback onSend;
  final VoidCallback onPayMerchant;
  final Future<void> Function() onRefresh;
  final bool isLoading;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('KOPA'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh balance',
            onPressed: isLoading ? null : () => onRefresh(),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: onRefresh,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
            children: [
              _BalanceCard(
                balance: balance,
                walletAddress: walletAddress,
                isLoading: isLoading,
                error: error,
                onRetry: onRefresh,
              ),
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(
                    child: BMoniButton(
                      onPressed: onSend,
                      text: 'Send money',
                      icon: Icons.arrow_upward,
                      width: double.infinity,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: BMoniButton(
                      onPressed: onPayMerchant,
                      text: 'Pay a merchant',
                      variant: BMoniButtonVariant.outline,
                      icon: Icons.storefront_outlined,
                      width: double.infinity,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 28),
              const _ValueProp(),
            ],
          ),
        ),
      ),
    );
  }
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({
    required this.balance,
    required this.walletAddress,
    required this.isLoading,
    required this.error,
    required this.onRetry,
  });

  final Balance? balance;
  final String? walletAddress;
  final bool isLoading;
  final String? error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: BMoniColors.grey900,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: BMoniColors.grey800),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                'Wallet balance',
                style: Theme.of(context)
                    .textTheme
                    .labelLarge
                    ?.copyWith(color: BMoniColors.grey400),
              ),
              const Spacer(),
              if (balance?.isDemo ?? false) const _DemoChip(),
            ],
          ),
          const SizedBox(height: 12),
          if (isLoading && balance == null)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: SizedBox(
                height: 32,
                width: 32,
                child: CircularProgressIndicator(strokeWidth: 2.5),
              ),
            )
          else if (error != null && balance == null)
            _InlineError(message: error!, onRetry: onRetry)
          else
            Semantics(
              label: 'Wallet balance '
                  '${formatMoney(balance?.amount.toStringAsFixed(2) ?? '0.00')}',
              excludeSemantics: true,
              child: Text(
                formatMoney(balance?.amount.toStringAsFixed(2) ?? '0.00'),
                style: Theme.of(context)
                    .textTheme
                    .displaySmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
            ),
          if (walletAddress != null) ...[
            const SizedBox(height: 14),
            Text(
              'Smart wallet  ${_shorten(walletAddress!)}',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: BMoniColors.grey500),
            ),
          ],
        ],
      ),
    );
  }

  static String _shorten(String address) => address.length <= 14
      ? address
      : '${address.substring(0, 8)}…${address.substring(address.length - 6)}';
}

class _DemoChip extends StatelessWidget {
  const _DemoChip();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: BMoniColors.grey800,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: BMoniColors.grey600),
      ),
      child: Text(
        'DEMO DATA',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: BMoniColors.grey300,
              letterSpacing: 0.5,
            ),
      ),
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError({required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            message,
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: BMoniColors.error300),
          ),
          const SizedBox(height: 8),
          BMoniButton(
            onPressed: () => onRetry(),
            text: 'Try again',
            variant: BMoniButtonVariant.outline,
            size: BMoniButtonSize.small,
          ),
        ],
      ),
    );
  }
}

class _ValueProp extends StatelessWidget {
  const _ValueProp();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: BMoniColors.grey900,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: BMoniColors.grey800),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.shield_outlined,
              size: 20, color: BMoniColors.grey400),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'KOPA checks what a transfer does to your balance, your runway '
              'and your upcoming bills — before you sign it.',
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: BMoniColors.grey300, height: 1.45),
            ),
          ),
        ],
      ),
    );
  }
}
