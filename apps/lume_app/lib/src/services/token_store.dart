import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenStore {
  const TokenStore({
    FlutterSecureStorage storage = const FlutterSecureStorage(),
  }) : _storage = storage;

  static const _tokenKey = 'lume_api_token';

  final FlutterSecureStorage _storage;

  Future<String?> readToken() {
    return _storage.read(key: _tokenKey).timeout(const Duration(seconds: 3));
  }

  Future<void> saveToken(String token) {
    return _storage.write(key: _tokenKey, value: token).timeout(const Duration(seconds: 3));
  }

  Future<void> clearToken() {
    return _storage.delete(key: _tokenKey).timeout(const Duration(seconds: 3));
  }
}
