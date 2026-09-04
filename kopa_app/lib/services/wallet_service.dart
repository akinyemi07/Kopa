// SPDX-License-Identifier: Apache-2.0
//
// The ONLY place in KOPA where the device talks to BMONI directly.
//
// Everything else goes through kopa_backend. This file exists because one
// operation genuinely cannot be delegated: the wallet's private key lives in
// the Android Keystore / iOS Secure Enclave and never leaves the device, so
// signatures must be produced here.
//
// Two signatures, two different methods, and mixing them up is the single most
// common way to stall a BMONI integration:
//
//   owner proof  -> signMessage()          EIP-191 prefixed, signs TEXT
//   proposal     -> signTransactionHash()  no prefix, signs a 32-byte DIGEST
//
// A signMessage signature submitted for a proposal recovers to a different
// address, and BMONI rejects it with an error that does not say why.

import 'package:bmoni_embedded_sdk/bmoni_embedded_sdk.dart';
import 'package:flutter/foundation.dart' show kIsWeb;

/// A wallet or signing failure, already translated for a human.
class WalletException implements Exception {
  WalletException(this.message, {this.code, this.isPinError = false});

  final String message;

  /// The native SDK's numeric code. `BmoniSignerErrorCode` exposes these as
  /// `static const int` values rather than as a Dart enum, so this is an int.
  final int? code;

  /// True when the user can fix this by re-entering their PIN.
  final bool isPinError;

  @override
  String toString() => message;
}

class WalletService {
  /// PIN length. Six digits matches Nigerian banking-app convention, so the
  /// interaction is already familiar to the target user.
  static const int pinLength = 6;

  /// A recognisably fake address, used only for the web demo path below.
  /// Never submitted to BMONI — demo-mode transactions never reach BMONI at
  /// all — and never mistaken for a real wallet: it doesn't checksum as one.
  static const String _webDemoAddress =
      '0x0000000000000000000000000000000000DEB0';

  // bmoni_embedded_sdk is documented for Android and iOS only — there is no
  // web platform implementation. On web, even PIN storage (pure Dart, no
  // platform channel) fails: the SDK hashes the PIN via `compute()`, which
  // spawns a Dart isolate, and browsers have no isolate support
  // ("Unsupported operation: new RawReceivePort"). These two fields let the
  // web build walk through the same screens as a real device without ever
  // calling into the native SDK — kept in memory only, and never touched
  // when `kIsWeb` is false, so the real Android path below is unaffected.
  bool _webWalletCreated = false;
  bool _webPinSet = false;

  /// Configure the SDK. Call once, before runApp. A no-op on web, since there
  /// is nothing to configure on a platform the SDK does not support.
  static void initialize() {
    if (kIsWeb) return;
    BmoniEmbeddedSdk.initialize(pinLength: pinLength, requirePin: true);
  }

  Future<bool> hasWallet() =>
      kIsWeb ? Future.value(_webWalletCreated) : BmoniEmbeddedSdk.hasWallet();

  Future<String?> walletAddress() => kIsWeb
      ? Future.value(_webWalletCreated ? _webDemoAddress : null)
      : BmoniEmbeddedSdk.walletAddress();

  Future<bool> hasPin() =>
      kIsWeb ? Future.value(_webPinSet) : BmoniEmbeddedSdk.hasPin();

  /// Generate the device keypair inside secure hardware.
  ///
  /// Returns the EIP-55 address, which is the only part that ever leaves the
  /// device. The private key is generated, encrypted with a platform-managed
  /// wrapping key, and zeroized in RAM — KOPA never sees it.
  Future<String> createWallet() async {
    if (kIsWeb) {
      _webWalletCreated = true;
      return _webDemoAddress;
    }
    try {
      return await BmoniEmbeddedSdk.initWallet();
    } on BmoniSignerException catch (e) {
      if (e.errorCode == BmoniSignerErrorCode.walletAlreadyExists) {
        final existing = await BmoniEmbeddedSdk.walletAddress();
        if (existing != null) return existing;
      }
      throw _translate(e);
    }
  }

  /// Set the signing PIN. Stored only as a PBKDF2-HMAC-SHA256 digest.
  Future<void> setPin(String pin) async {
    if (kIsWeb) {
      if (pin.length != pinLength) {
        throw WalletException(
          'Your PIN must be exactly $pinLength digits.',
          isPinError: true,
        );
      }
      _webPinSet = true;
      return;
    }
    try {
      await BmoniEmbeddedSdk.setPin(pin);
    } on BmoniSignerException catch (e) {
      throw _translate(e);
    }
  }

  /// Sign the owner-proof challenge — EIP-191 prefixed, over the message TEXT.
  ///
  /// Never reachable on web in demo mode; guarded anyway so a future caller
  /// gets a clear message instead of an isolate crash.
  Future<String> signOwnerProof(String message, String pin) async {
    if (kIsWeb) {
      throw WalletException(
        'Signing needs the Android app — a browser has no secure element '
        'to hold the key.',
      );
    }
    try {
      return await BmoniEmbeddedSdk.signMessage(message, pin: pin);
    } on BmoniSignerException catch (e) {
      throw _translate(e);
    }
  }

  /// Sign a transfer proposal — RAW 32-byte digest, no prefix.
  ///
  /// Never reachable on web in demo mode; guarded anyway for the same reason.
  Future<String> signProposal(String hashToSign, String pin) async {
    if (kIsWeb) {
      throw WalletException(
        'Signing needs the Android app — a browser has no secure element '
        'to hold the key.',
      );
    }
    try {
      return await BmoniEmbeddedSdk.signTransactionHash(hashToSign, pin: pin);
    } on BmoniSignerException catch (e) {
      throw _translate(e);
    }
  }

  /// Map SDK error codes to something a person can act on.
  ///
  /// Branching on the numeric constants rather than the message text, so a
  /// wording change in the native SDK cannot silently break this mapping.
  WalletException _translate(BmoniSignerException e) {
    const pinCodes = {
      BmoniSignerErrorCode.pinMismatch,
      BmoniSignerErrorCode.pinInvalid,
      BmoniSignerErrorCode.pinNotSet,
    };

    final message = switch (e.errorCode) {
      BmoniSignerErrorCode.pinMismatch =>
        'That PIN is not correct. Please try again.',
      BmoniSignerErrorCode.pinInvalid =>
        'Your PIN must be exactly $pinLength digits.',
      BmoniSignerErrorCode.pinNotSet =>
        'You have not set a PIN yet. Set one to continue.',
      BmoniSignerErrorCode.pinAlreadySet =>
        'A PIN is already set on this device.',
      BmoniSignerErrorCode.walletAlreadyExists =>
        'A wallet already exists on this device.',
      BmoniSignerErrorCode.signInvalidPrivateKey =>
        'KOPA could not access your wallet key on this device.',
      BmoniSignerErrorCode.signInvalidHash =>
        'KOPA received an invalid transaction to sign. Please start again.',
      _ => 'Your device could not complete that securely. Please try again.',
    };

    return WalletException(
      message,
      code: e.errorCode,
      isPinError: pinCodes.contains(e.errorCode),
    );
  }
}
