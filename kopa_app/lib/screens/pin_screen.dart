// SPDX-License-Identifier: Apache-2.0
//
// The PIN gate in front of on-device signing.
//
// The PIN never leaves the device and is never sent to KOPA's backend. The SDK
// stores only a PBKDF2-HMAC-SHA256 digest; this screen hands the raw value
// straight to the SDK and holds it no longer than the call takes.

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/wallet_service.dart';

class PinScreen extends StatefulWidget {
  const PinScreen({
    super.key,
    required this.title,
    required this.subtitle,
    required this.onSubmit,
    this.confirmLabel = 'Confirm',
  });

  final String title;
  final String subtitle;
  final String confirmLabel;

  /// Receives the entered PIN. Throw to show an inline error and let the user
  /// try again without leaving the screen.
  final Future<void> Function(String pin) onSubmit;

  @override
  State<PinScreen> createState() => _PinScreenState();
}

class _PinScreenState extends State<PinScreen> {
  final _controller = TextEditingController();
  final _focus = FocusNode();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _focus.requestFocus());
  }

  @override
  void dispose() {
    _controller.clear(); // do not leave the PIN sitting in memory
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final pin = _controller.text;
    if (pin.length != WalletService.pinLength) {
      setState(() => _error =
          'Enter all ${WalletService.pinLength} digits of your PIN.');
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      await widget.onSubmit(pin);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _busy = false;
      });
      _controller.clear();
      _focus.requestFocus();
      return;
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Confirm with your PIN')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(widget.title,
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 10),
              Text(
                widget.subtitle,
                style: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.copyWith(color: BMoniColors.grey300, height: 1.45),
              ),
              const SizedBox(height: 32),
              Semantics(
                label: '${WalletService.pinLength} digit PIN',
                textField: true,
                child: TextField(
                  controller: _controller,
                  focusNode: _focus,
                  obscureText: true,
                  autofocus: true,
                  maxLength: WalletService.pinLength,
                  keyboardType: TextInputType.number,
                  textAlign: TextAlign.center,
                  enabled: !_busy,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  style: Theme.of(context)
                      .textTheme
                      .headlineMedium
                      ?.copyWith(letterSpacing: 14),
                  decoration: const InputDecoration(
                    counterText: '',
                    hintText: '••••••',
                  ),
                  onSubmitted: (_) => _submit(),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Semantics(
                  liveRegion: true,
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline,
                          size: 16, color: BMoniColors.error300),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _error!,
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(color: BMoniColors.error300),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const Spacer(),
              BMoniButton(
                onPressed: _busy ? null : _submit,
                text: widget.confirmLabel,
                isLoading: _busy,
                width: double.infinity,
              ),
              const SizedBox(height: 12),
              Text(
                'Your PIN unlocks the signing key held on this device. '
                'It is never sent to KOPA.',
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
