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

      await _loadBootstrapSession();
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
        '/api/v1/mobile/auth/token/',
        body: {'username': username, 'password': password},
        authenticated: false,
      );
      final token = payload['token'] as String? ?? '';
      await _tokenStore.saveToken(token);
      await _loadBootstrapSession();
      status = AuthStatus.signedIn;
    } on ApiException catch (error) {
      await _clearLocalToken();
      errorMessage = error.message;
      status = AuthStatus.signedOut;
    } on TokenStoreException catch (error) {
      await _clearLocalToken();
      errorMessage = error.message;
      status = AuthStatus.signedOut;
    } catch (_) {
      await _clearLocalToken();
      errorMessage = 'Nao foi possivel iniciar a sessao neste dispositivo.';
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

  Future<void> _loadBootstrapSession() async {
    final payload = await _apiClient.getJson('/api/v1/mobile/bootstrap/');
    final summary = DashboardSummary.fromJson(payload);
    if (summary.profile.username.isEmpty || summary.profile.role.isEmpty) {
      throw const TokenStoreException(
        'Seu usuario entrou, mas ainda nao possui perfil liberado para o aplicativo.',
      );
    }
    profile = summary.profile;
    features = summary.features;
  }
}
