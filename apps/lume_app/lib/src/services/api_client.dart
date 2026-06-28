import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'token_store.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient(this.baseUrl, this._tokenStore, {http.Client? client})
      : _client = client ?? http.Client();

  final String baseUrl;
  final TokenStore _tokenStore;
  final http.Client _client;

  Future<Map<String, dynamic>> getJson(String path) async {
    final response = await _send('GET', path);
    return _decodeObject(response);
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) async {
    final response = await _send(
      'POST',
      path,
      body: body,
      authenticated: authenticated,
    );
    if (response.statusCode == 204) {
      return <String, dynamic>{};
    }
    return _decodeObject(response);
  }

  Future<http.Response> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };
    if (authenticated) {
      final token = await _tokenStore.readToken();
      if (token != null && token.isNotEmpty) {
        headers['Authorization'] = 'Token $token';
      }
    }

    final request = http.Request(method, AppConfig.apiUri(path))
      ..headers.addAll(headers);
    if (body != null) {
      request.body = jsonEncode(body);
    }

    final streamed = await _client.send(request).timeout(
          const Duration(seconds: 20),
          onTimeout: () => throw const ApiException('Tempo de conexao esgotado.'),
        );
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode >= 400) {
      final message = _errorMessage(response);
      throw ApiException(message, statusCode: response.statusCode);
    }
    return response;
  }

  Map<String, dynamic> _decodeObject(http.Response response) {
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    throw const ApiException('Resposta inesperada do servidor.');
  }

  String _errorMessage(http.Response response) {
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String && detail.isNotEmpty) {
          return detail;
        }
      }
    } on FormatException {
      return 'Falha na comunicacao com o servidor.';
    }
    return 'Falha na comunicacao com o servidor.';
  }

  void close() {
    _client.close();
  }
}
