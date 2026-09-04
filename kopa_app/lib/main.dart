// SPDX-License-Identifier: Apache-2.0
//
// KOPA — financial safety analysis before you sign.
//
// The journey this app exists to deliver:
//
//   home -> amount + recipient -> SAFETY CHECK -> decide -> PIN -> sign -> done
//
// The safety check is not optional and not skippable. Every path to signing
// goes through it.

import 'dart:async';

import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'models/decision.dart';
import 'screens/home_screen.dart';
import 'screens/pin_screen.dart';
import 'screens/safety_result_screen.dart';
import 'screens/send_screen.dart';
import 'screens/success_screen.dart';
import 'services/wallet_service.dart';
import 'theme/verdict_style.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Configure the BMONI SDK once, before the first signer call.
  WalletService.initialize();
  runApp(const KopaApp());
}

class KopaApp extends StatelessWidget {
  const KopaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'KOPA',
      debugShowCheckedModeBanner: false,
      theme: BMoniTheme.darkTheme(),
      home: const KopaShell(),
    );
  }
}

class KopaShell extends StatefulWidget {
  const KopaShell({super.key});

  @override
  State<KopaShell> createState() => _KopaShellState();
}

class _KopaShellState extends State<KopaShell> {
  final _api = KopaApi();
  final _wallet = WalletService();

  /// In demo mode the backend serves seeded data for any user id. A real
  /// deployment would persist the id returned by POST /users.
  static const String _demoUserId = '11111111-1111-1111-1111-111111111111';

  Balance? _balance;
  String? _walletAddress;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _api.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // The device address is read from the SDK, never from the backend.
      final address = await _wallet.walletAddress();
      final balance = await _api.getBalance(_demoUserId);
      if (!mounted) return;
      setState(() {
        _walletAddress = address;
        _balance = balance;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  // -------------------------------------------------------------- the journey

  Future<void> _startSend({required bool isMerchant}) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => SendScreen(
          isMerchant: isMerchant,
          balanceLabel: _balance == null
              ? null
              : formatMoney(_balance!.amount.toStringAsFixed(2)),
          availableBalance: _balance?.amount,
          onCheck: (amount, counterpart) =>
              _runSafetyCheck(amount, counterpart, isMerchant),
        ),
      ),
    );
    // The balance may have moved while we were away.
    unawaited(_bootstrap());
  }

  /// Step 1 of every send: ask KOPA before doing anything.
  Future<void> _runSafetyCheck(
    double amount,
    String counterpart,
    bool isMerchant,
  ) async {
    final decision = await _api.evaluate(
      userId: _demoUserId,
      amount: amount,
      counterpart: counterpart,
      type: isMerchant ? 'merchant' : 'personal',
    );

    if (!mounted) return;

    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (routeContext) => SafetyResultScreen(
          decision: decision,
          counterpart: counterpart,
          onCancel: () => Navigator.of(routeContext).pop(),
          onProceed: () => _confirmAndSign(
            routeContext,
            amount: amount,
            counterpart: counterpart,
            decision: decision,
          ),
        ),
      ),
    );
  }

  /// Step 2: the user has seen the consequence and chosen to continue.
  Future<void> _confirmAndSign(
    BuildContext routeContext, {
    required double amount,
    required String counterpart,
    required Decision decision,
  }) async {
    var hasPin = await _wallet.hasPin();
    // Guard the context we are actually about to use, not the State's.
    if (!routeContext.mounted) return;

    // First-time users set their signing PIN here rather than being sent away
    // to a settings screen and losing the transfer they were part-way through.
    if (!hasPin) {
      final created = await Navigator.of(routeContext).push<bool>(
        MaterialPageRoute(
          builder: (setupContext) => PinScreen(
            title: 'Create your signing PIN',
            subtitle:
                'This ${WalletService.pinLength}-digit PIN protects the key '
                'held on this device. KOPA never sees it, and it cannot be '
                'recovered — choose something you will remember.',
            confirmLabel: 'Set PIN',
            onSubmit: (pin) async {
              await _wallet.setPin(pin);
              if (setupContext.mounted) Navigator.of(setupContext).pop(true);
            },
          ),
        ),
      );
      hasPin = created ?? false;
      if (!hasPin || !routeContext.mounted) return;
    }

    await Navigator.of(routeContext).push<void>(
      MaterialPageRoute(
        builder: (pinContext) => PinScreen(
          title: 'Send ${formatMoney(decision.justification.proposedAmount)}',
          subtitle:
              'to $counterpart. Enter your PIN to sign this transfer on your '
              'device.',
          confirmLabel: 'Sign and send',
          onSubmit: (pin) => _signAndSubmit(
            pinContext,
            amount: amount,
            counterpart: counterpart,
            pin: pin,
          ),
        ),
      ),
    );
  }

  /// Step 3: propose via the backend, sign on-device, submit the signature.
  ///
  /// The private key never leaves this device, and the backend never sees the
  /// PIN — it only ever receives the resulting signature hex.
  Future<void> _signAndSubmit(
    BuildContext pinContext, {
    required double amount,
    required String counterpart,
    required String pin,
  }) async {
    final proposal = await _api.createTransaction(
      userId: _demoUserId,
      amount: amount,
      counterpart: counterpart,
      description: 'Sent with KOPA',
    );

    String? reference = proposal.proposalId;

    if (!proposal.isDemo) {
      final hash = proposal.hashToSign;
      if (hash == null) {
        throw Exception(
          'BMONI has not released the signing payload yet. Please try again '
          'in a moment.',
        );
      }
      // signProposal -> signTransactionHash: RAW digest, no EIP-191 prefix.
      final signature = await _wallet.signProposal(hash, pin);
      await _api.submitSignature(
        userId: _demoUserId,
        proposalId: proposal.proposalId,
        signature: signature,
      );
    } else {
      // In demo mode we still require the PIN, so the gesture the judge sees
      // is the real one — but no BMONI transaction is created or implied.
      final ok = await _wallet.hasPin();
      if (!ok) throw Exception('No PIN is set on this device.');
    }

    if (!pinContext.mounted) return;

    Navigator.of(pinContext).pushReplacement(
      MaterialPageRoute(
        builder: (_) => SuccessScreen(
          amount: formatMoney(amount.toStringAsFixed(2)),
          counterpart: counterpart,
          reference: reference,
          isDemo: proposal.isDemo,
          onDone: () => Navigator.of(context).popUntil((r) => r.isFirst),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return HomeScreen(
      balance: _balance,
      walletAddress: _walletAddress,
      isLoading: _loading,
      error: _error,
      onRefresh: _bootstrap,
      onSend: () => _startSend(isMerchant: false),
      onPayMerchant: () => _startSend(isMerchant: true),
    );
  }
}
