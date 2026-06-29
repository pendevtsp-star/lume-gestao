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

  final FlutterSecureStorage _storage;

  Future<String?> readToken() async {
    try {
      final token = await _storage.read(key: _tokenKey).timeout(const Duration(seconds: 10));
      if (token != null && token.isNotEmpty) {
        return token;
      }
    } catch (_) {
      // Some Android devices can restore an unusable Keystore entry after reinstall.
    }
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(_fallbackTokenKey);
  }

  Future<void> saveToken(String token) async {
    try {
      await _storage.write(key: _tokenKey, value: token).timeout(const Duration(seconds: 10));
      final preferences = await SharedPreferences.getInstance();
      await preferences.remove(_fallbackTokenKey);
      return;
    } catch (_) {
      final preferences = await SharedPreferences.getInstance();
      final saved = await preferences.setString(_fallbackTokenKey, token);
      if (!saved) {
        throw const TokenStoreException('Nao foi possivel salvar a sessao neste dispositivo.');
      }
    }
  }

  Future<void> clearToken() async {
    try {
      await _storage.delete(key: _tokenKey).timeout(const Duration(seconds: 10));
    } catch (_) {
      // Continue clearing the fallback store even if secure storage is unavailable.
    }
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(_fallbackTokenKey);
  }
}
