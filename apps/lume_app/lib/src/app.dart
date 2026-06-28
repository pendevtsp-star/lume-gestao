import 'package:flutter/material.dart';

import 'config/app_config.dart';
import 'features/auth/auth_controller.dart';
import 'features/auth/auth_gate.dart';
import 'services/api_client.dart';
import 'services/token_store.dart';

class LumeApp extends StatefulWidget {
  const LumeApp({super.key});

  @override
  State<LumeApp> createState() => _LumeAppState();
}

class _LumeAppState extends State<LumeApp> {
  late final TokenStore _tokenStore;
  late final ApiClient _apiClient;
  late final AuthController _authController;

  @override
  void initState() {
    super.initState();
    _tokenStore = const TokenStore();
    _apiClient = ApiClient(AppConfig.apiBaseUrl, _tokenStore);
    _authController = AuthController(_apiClient, _tokenStore)..restore();
  }

  @override
  void dispose() {
    _authController.dispose();
    _apiClient.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Lume Gestao',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F766E),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF7F9F8),
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
        ),
        cardTheme: const CardThemeData(
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(8)),
            side: BorderSide(color: Color(0xFFE1E7E5)),
          ),
        ),
      ),
      home: AuthGate(
        controller: _authController,
        apiClient: _apiClient,
      ),
    );
  }
}
