import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class TokenStoreException implements Exception {
  const TokenStoreException(this.message);

  final String message;

  @override
  String toString() => message;
}

class TokenStore {
  const TokenStore({
    FlutterSecureStorage storage = const FlutterSecureStorage(
      aOptions: AndroidOptions(
        encryptedSharedPreferences: true,
        resetOnError: true,
      ),
    ),
  }) : _storage = storage;

  static const _tokenKey = 'lume_api_token';
  static const _fallbackTokenKey = 'lume_api_token_fallback';
  static String? _memoryToken;

  final FlutterSecureStorage _storage;

  Future<String?> readToken() async {
    final memoryToken = _memoryToken;
    if (memoryToken != null && memoryToken.isNotEmpty) {
      return memoryToken;
    }

    try {
      final token = await _storage.read(key: _tokenKey).timeout(const Duration(seconds: 10));
      if (token != null && token.isNotEmpty) {
        _memoryToken = token;
        return token;
      }
    } catch (_) {
      // Some Android devices can restore an unusable Keystore entry after reinstall.
    }

    try {
      final preferences = await SharedPreferences.getInstance();
      final token = preferences.getString(_fallbackTokenKey);
      if (token != null && token.isNotEmpty) {
        _memoryToken = token;
      }
      return token;
    } catch (_) {
      return _memoryToken;
    }
  }

  Future<void> saveToken(String token) async {
    if (token.isEmpty) {
      throw const TokenStoreException('O servidor nao retornou uma sessao valida.');
    }

    _memoryToken = token;
    var savedSecurely = false;

    try {
      await _storage.write(key: _tokenKey, value: token).timeout(const Duration(seconds: 10));
      savedSecurely = true;
    } catch (_) {
      // Keep the in-memory token and try the fallback storage below.
    }

    try {
      final preferences = await SharedPreferences.getInstance();
      if (savedSecurely) {
        await preferences.remove(_fallbackTokenKey);
      } else {
        await preferences.setString(_fallbackTokenKey, token);
      }
    } catch (_) {
      // Last resort: keep the session for the current app run.
    }
  }

  Future<void> clearToken() async {
    _memoryToken = null;

    try {
      await _storage.delete(key: _tokenKey).timeout(const Duration(seconds: 10));
    } catch (_) {
      // Continue clearing the fallback store even if secure storage is unavailable.
    }

    try {
      final preferences = await SharedPreferences.getInstance();
      await preferences.remove(_fallbackTokenKey);
    } catch (_) {
      // Nothing else to clear locally.
    }
  }
}
