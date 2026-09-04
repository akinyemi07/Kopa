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

  /// Configure the SDK. Call once, before runApp.
  static void initialize() {
    BmoniEmbeddedSdk.initialize(pinLength: pinLength, requirePin: true);
  }

  Future<bool> hasWallet() => BmoniEmbeddedSdk.hasWallet();

  Future<String?> walletAddress() => BmoniEmbeddedSdk.walletAddress();

  Future<bool> hasPin() => BmoniEmbeddedSdk.hasPin();

  /// Generate the device keypair inside secure hardware.
  ///
  /// Returns the EIP-55 address, which is the only part that ever leaves the
  /// device. The private key is generated, encrypted with a platform-managed
  /// wrapping key, and zeroized in RAM — KOPA never sees it.
  Future<String> createWallet() async {
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
    try {
      await BmoniEmbeddedSdk.setPin(pin);
    } on BmoniSignerException catch (e) {
      throw _translate(e);
    }
  }

  /// Sign the owner-proof challenge — EIP-191 prefixed, over the message TEXT.
  Future<String> signOwnerProof(String message, String pin) async {
    try {
      return await BmoniEmbeddedSdk.signMessage(message, pin: pin);
    } on BmoniSignerException catch (e) {
      throw _translate(e);
    }
  }

  /// Sign a transfer proposal — RAW 32-byte digest, no prefix.
  Future<String> signProposal(String hashToSign, String pin) async {
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
