// SPDX-License-Identifier: Apache-2.0
//
// The single place KOPA's Flutter app talks to the network.
//
// SECURITY: this client holds no credentials. It talks only to the KOPA
// backend, which owns the BMONI partner key. There is deliberately no BMONI
// base URL, no x-api-key, and no Anthropic key anywhere in this project —
// grep for them and you will find nothing.
//
// The only privileged operation that happens on the device is signing, and
// that never leaves bmoni_embedded_sdk.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;

import '../models/decision.dart';

/// A failure the user can be shown.
///
/// Raw response bodies and stack traces stay out of this on purpose — the
/// backend already translates BMONI failures into human sentences.
class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  /// True when retrying might plausibly succeed.
  bool get isRetryable =>
      statusCode == null || statusCode! >= 500 || statusCode == 408;

  @override
  String toString() => message;
}

class KopaApi {
  KopaApi({String? baseUrl, http.Client? client})
      : baseUrl = baseUrl ?? defaultBaseUrl,
        _client = client ?? http.Client();

  /// Where the KOPA backend lives.
  ///
  /// Resolution order:
  ///   1. `--dart-define=KOPA_API_BASE_URL=...`, if provided
  ///   2. On web: the origin serving this page. The deployed build is served
  ///      as static files by the same FastAPI process that exposes the API, so
  ///      same-origin means no CORS configuration to get wrong.
  ///   3. On Android: 10.0.2.2, the emulator's route to the host's localhost.
  ///
  /// This is a URL, not a secret. The app holds no credentials.
  static String get defaultBaseUrl {
    const configured = String.fromEnvironment('KOPA_API_BASE_URL');
    if (configured.isNotEmpty) return configured;
    if (kIsWeb) return Uri.base.origin;
    return 'http://10.0.2.2:8000';
  }

  final String baseUrl;
  final http.Client _client;

  static const Duration _timeout = Duration(seconds: 30);

  void dispose() => _client.close();

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    late http.Response response;
    try {
      response = await _client
          .post(
            Uri.parse('$baseUrl$path'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(_timeout);
    } on TimeoutException {
      throw ApiException(
        'KOPA took too long to respond. Check your connection and try again.',
      );
    } catch (_) {
      throw ApiException(
        'KOPA could not be reached. Check your connection and try again.',
      );
    }
    return _decode(response);
  }

  Future<Map<String, dynamic>> _get(String path) async {
    late http.Response response;
    try {
      response = await _client.get(Uri.parse('$baseUrl$path')).timeout(_timeout);
    } on TimeoutException {
      throw ApiException('KOPA took too long to respond.');
    } catch (_) {
      throw ApiException('KOPA could not be reached.');
    }
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    Map<String, dynamic> parsed;
    try {
      parsed = jsonDecode(response.body) as Map<String, dynamic>;
    } catch (_) {
      throw ApiException(
        'KOPA returned an unexpected response.',
        statusCode: response.statusCode,
      );
    }

    if (response.statusCode >= 400) {
      final detail = parsed['detail'];
      throw ApiException(
        detail is String ? detail : 'Something went wrong. Please try again.',
        statusCode: response.statusCode,
      );
    }
    return parsed;
  }

  // ---------------------------------------------------------------- decisions

  /// Ask KOPA whether a transaction is safe — BEFORE anything is signed.
  ///
  /// This is the call the whole product exists for.
  Future<Decision> evaluate({
    required String userId,
    required double amount,
    String? counterpart,
    String type = 'personal',
  }) async {
    final json = await _post('/decisions/evaluate', {
      'user_id': userId,
      'proposed_amount': amount,
      'counterpart': counterpart,
      'type': type,
    });
    return Decision.fromJson(json);
  }

  /// Re-run the safety engine against a "what if" adjustment.
  Future<Decision> followup({
    required String userId,
    required double originalAmount,
    required String question,
    String? counterpart,
    String type = 'personal',
  }) async {
    final json = await _post('/decisions/followup', {
      'user_id': userId,
      'original_amount': originalAmount,
      'question': question,
      'counterpart': counterpart,
      'type': type,
    });
    return Decision.fromJson(json);
  }

  // ------------------------------------------------------------------ wallet

  Future<Balance> getBalance(String userId) async {
    final json = await _get('/wallets/$userId/balance');
    return Balance.fromJson(json);
  }

  /// Step 1 of wallet creation: get the challenge the device must sign.
  Future<OwnerProofChallenge> requestWalletChallenge({
    required String userId,
    required String ownerAddress,
  }) async {
    final json = await _post('/users/$userId/wallet/challenge', {
      'owner_address': ownerAddress,
    });
    return OwnerProofChallenge.fromJson(json);
  }

  /// Step 2: hand back the EIP-191 signature so BMONI can deploy the wallet.
  Future<Map<String, dynamic>> createWallet({
    required String userId,
    required String ownerAddress,
    required String challengeId,
    required String signature,
  }) {
    return _post('/users/$userId/wallet', {
      'owner_address': ownerAddress,
      'challenge_id': challengeId,
      'owner_proof_signature': signature,
    });
  }

  // ------------------------------------------------------------ transactions

  /// Create + approve a proposal. Returns the digest the device must sign.
  Future<Proposal> createTransaction({
    required String userId,
    required double amount,
    String? toAddress,
    String? counterpart,
    String? description,
  }) async {
    final json = await _post('/transactions?user_id=$userId', {
      'amount': amount,
      'to_address': toAddress,
      'counterpart': counterpart,
      'description': description,
    });
    return Proposal.fromJson(json);
  }

  /// Submit the on-device signature over `hashToSign`.
  Future<Map<String, dynamic>> submitSignature({
    required String userId,
    required String proposalId,
    required String signature,
  }) {
    return _post('/transactions/sign?user_id=$userId', {
      'proposal_id': proposalId,
      'signature': signature,
    });
  }

  Future<Map<String, dynamic>> health() => _get('/health');
}
