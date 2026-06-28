import 'package:flutter/foundation.dart';

import '../../models/mobile_models.dart';
import '../../services/api_client.dart';
import '../../services/token_store.dart';

enum AuthStatus {
  checking,
  signedOut,
  signedIn,
}

class AuthController extends ChangeNotifier {
  AuthController(this._apiClient, this._tokenStore);

  final ApiClient _apiClient;
  final TokenStore _tokenStore;

  AuthStatus status = AuthStatus.checking;
  UserProfile? profile;
  List<String> features = const [];
  String? errorMessage;

  Future<void> restore() async {
    try {
      final token = await _tokenStore.readToken();
      if (token == null || token.isEmpty) {
        status = AuthStatus.signedOut;
        notifyListeners();
        return;
      }

      final payload = await _apiClient.getJson('/api/v1/mobile/profile/');
      profile = UserProfile.fromJson(payload['profile'] as Map<String, dynamic>? ?? {});
      features = (payload['features'] as List<dynamic>? ?? const [])
          .whereType<String>()
          .toList(growable: false);
      status = AuthStatus.signedIn;
      errorMessage = null;
    } on ApiException catch (error) {
      await _clearLocalToken();
      profile = null;
      features = const [];
      errorMessage = error.message;
      status = AuthStatus.signedOut;
    } catch (_) {
      await _clearLocalToken();
      profile = null;
      features = const [];
      errorMessage = null;
      status = AuthStatus.signedOut;
    }
    notifyListeners();
  }

  Future<void> signIn(String username, String password) async {
    status = AuthStatus.checking;
    errorMessage = null;
    notifyListeners();

    try {
      final payload = await _apiClient.postJson(
        '/api/v1/mobile/auth/login/',
        body: {'username': username, 'password': password},
        authenticated: false,
      );
      final session = MobileSession.fromJson(payload);
      await _tokenStore.saveToken(session.token);
      profile = session.profile;
      features = session.features;
      status = AuthStatus.signedIn;
    } on ApiException catch (error) {
      errorMessage = error.message;
      status = AuthStatus.signedOut;
    } catch (_) {
      errorMessage = 'Nao foi possivel salvar a sessao neste dispositivo.';
      status = AuthStatus.signedOut;
    }
    notifyListeners();
  }

  Future<void> signOut() async {
    try {
      await _apiClient.postJson('/api/v1/mobile/auth/logout/');
    } on ApiException {
      // The local token must be removed even if the network request fails.
    }
    await _clearLocalToken();
    profile = null;
    features = const [];
    status = AuthStatus.signedOut;
    notifyListeners();
  }

  Future<void> _clearLocalToken() async {
    try {
      await _tokenStore.clearToken();
    } catch (_) {
      // A failed local cleanup must not leave the app stuck in the loading state.
    }
  }
}
