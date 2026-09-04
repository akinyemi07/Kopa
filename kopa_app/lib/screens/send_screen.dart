// SPDX-License-Identifier: Apache-2.0
//
// Enter an amount and a recipient. Nothing is sent from here — the next screen
// is always the safety check. That ordering is the product.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class SendScreen extends StatefulWidget {
  const SendScreen({
    super.key,
    required this.onCheck,
    required this.isMerchant,
    this.balanceLabel,
    this.availableBalance,
  });

  /// Called with (amount, counterpart). The caller runs the safety check.
  final Future<void> Function(double amount, String counterpart) onCheck;
  final bool isMerchant;
  final String? balanceLabel;

  /// The real spendable balance, used to reject an amount you don't have
  /// before the safety check even runs. This is a hard constraint, not a
  /// risk judgement — KOPA advises on risk (obligations, spending pattern, an
  /// unfamiliar recipient) and never blocks those, but sending money that
  /// isn't there isn't a judgement call, the same way a bank refuses an
  /// overdraft it never agreed to. `null` while the balance is still loading
  /// skips this check rather than blocking on an unknown limit.
  final double? availableBalance;

  @override
  State<SendScreen> createState() => _SendScreenState();
}

class _SendScreenState extends State<SendScreen> {
  final _formKey = GlobalKey<FormState>();
  final _amountController = TextEditingController();
  final _counterpartController = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _amountController.dispose();
    _counterpartController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _error = null);
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() => _busy = true);
    try {
      await widget.onCheck(
        double.parse(_amountController.text.replaceAll(',', '')),
        _counterpartController.text.trim(),
      );
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final label = widget.isMerchant ? 'Merchant or business' : 'Who are you paying?';

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.isMerchant ? 'Pay a merchant' : 'Send money'),
      ),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
            children: [
              if (widget.balanceLabel != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 20),
                  child: Text(
                    'Available: ${widget.balanceLabel}',
                    style: Theme.of(context)
                        .textTheme
                        .bodyMedium
                        ?.copyWith(color: BMoniColors.grey300),
                  ),
                ),
              Text('Amount',
                  style: Theme.of(context)
                      .textTheme
                      .labelLarge
                      ?.copyWith(color: BMoniColors.grey300)),
              const SizedBox(height: 8),
              TextFormField(
                controller: _amountController,
                autofocus: true,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
                ],
                style: Theme.of(context).textTheme.headlineMedium,
                decoration: const InputDecoration(
                  prefixText: '₦ ',
                  hintText: '0.00',
                ),
                validator: (raw) {
                  final text = (raw ?? '').replaceAll(',', '').trim();
                  if (text.isEmpty) return 'Enter an amount';
                  final value = double.tryParse(text);
                  if (value == null) return 'Enter a valid amount';
                  if (value <= 0) return 'Amount must be more than zero';
                  final limit = widget.availableBalance;
                  if (limit != null && value > limit) {
                    return "You don't have that much in your wallet";
                  }
                  return null;
                },
              ),
              const SizedBox(height: 24),
              Text(label,
                  style: Theme.of(context)
                      .textTheme
                      .labelLarge
                      ?.copyWith(color: BMoniColors.grey300)),
              const SizedBox(height: 8),
              TextFormField(
                controller: _counterpartController,
                textCapitalization: TextCapitalization.words,
                decoration: InputDecoration(
                  hintText: widget.isMerchant ? 'e.g. Shoprite' : 'e.g. Chidi',
                ),
                validator: (raw) => (raw ?? '').trim().isEmpty
                    ? 'Enter who you are paying'
                    : null,
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                _ErrorNotice(message: _error!, onRetry: _submit),
              ],
              const SizedBox(height: 32),
              BMoniButton(
                onPressed: _busy ? null : _submit,
                text: 'Check before sending',
                isLoading: _busy,
                width: double.infinity,
              ),
              const SizedBox(height: 12),
              Text(
                "KOPA will show you what this does to your balance before "
                'anything is signed.',
                textAlign: TextAlign.center,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: BMoniColors.grey500),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ErrorNotice extends StatelessWidget {
  const _ErrorNotice({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: BMoniColors.error950,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: BMoniColors.error700),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.error_outline,
                size: 18, color: BMoniColors.error300),
            const SizedBox(width: 10),
            Expanded(
              child: Text(message,
                  style: Theme.of(context).textTheme.bodySmall),
            ),
            TextButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
